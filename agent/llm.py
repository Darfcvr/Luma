import json
import secrets
import threading
import requests
from .utils import clean_llm_text


def is_llm_refusal(text):
    """Don't turn a model refusal into a valid-looking base-only image prompt."""
    normalized = (text or "").strip().lower().replace("’", "'")
    prefixes = (
        "i can't help", "i cannot help", "i can't fulfill", "i cannot fulfill",
        "i can't assist", "i cannot assist", "i'm unable to help", "i am unable to help",
        "sorry, i can't", "sorry, i cannot", "i'm sorry, but i can't", "i'm sorry, but i cannot",
    )
    return normalized.startswith(prefixes)


class LLMClient:
    def __init__(self,cfg):
        self.cfg=cfg; self.base=cfg['base_url'].rstrip('/'); self.api_key=cfg.get('api_key',''); self.model=cfg['model']; self.timeout=cfg.get('timeout',180)
        self._anchor_bags = {}
        self._active_request_lock = threading.Lock()
        self._active_response = None
        self._cancel_epoch = 0
    def cancel_active(self):
        """Close an in-flight HTTP response so a Cancel action interrupts the LLM request."""
        with self._active_request_lock:
            self._cancel_epoch += 1
            response = self._active_response
            self._active_response = None
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
    def _request_json(self, method, url, **kwargs):
        with self._active_request_lock:
            request_epoch = self._cancel_epoch
        kwargs["stream"] = True
        response = requests.request(method, url, **kwargs)
        with self._active_request_lock:
            cancelled = request_epoch != self._cancel_epoch
            if not cancelled:
                self._active_response = response
        if cancelled:
            response.close()
            raise InterruptedError("LLM request cancelled")
        try:
            response.raise_for_status()
            return response.json()
        finally:
            with self._active_request_lock:
                if self._active_response is response:
                    self._active_response = None
            response.close()
    def headers(self):
        h={'Content-Type':'application/json'}
        if self.api_key:h['Authorization']=f"Bearer {self.api_key}"
        return h
    def check(self): self._request_json('GET', self.base+'/models',headers=self.headers(),timeout=15); return True
    def list_models(self):
        payload = self._request_json('GET', self.base + '/models', headers=self.headers(), timeout=20)
        models = payload.get('data', []) if isinstance(payload, dict) else []
        return sorted({str(item.get('id', '')).strip() for item in models
                       if isinstance(item, dict) and item.get('id')})

    def converse(self, turns, current_prompt=""):
        """Normalize the latest utterance, answer naturally, and classify image intent."""
        system = '''Jesteś polskojęzycznym asystentem obsługującym rozmowę i generowanie obrazów.
Najpierw odczytaj OSTATNIĄ wiadomość użytkownika w kontekście całej rozmowy. Może pochodzić z rozpoznawania mowy i zawierać błędnie rozpoznane słowa, odmianę lub składnię. W polu "corrected" zwróć poprawioną wersję tej wiadomości: naprawiaj oczywiste błędy transkrypcji i gramatyki, korzystając z kontekstu, ale zachowuj dokładnie intencję, szczegóły i styl użytkownika. Przykład: „w ryżącej na łóżku” w opisie osoby popraw na „leżącej na łóżku”. Nie dopowiadaj szczegółów. Jeśli nie da się rozstrzygnąć błędu z dużą pewnością, pozostaw oryginalne sformułowanie zamiast zgadywać. Dalsze działanie i odpowiedź oprzyj na poprawionej wiadomości.
Użytkownik może pisać potocznie, z błędami, skrótami albo niepełnym zdaniem. Nie wymagaj słów „wygeneruj obraz”.

Wybierz dokładnie jedno działanie:
- "chat" — zwykłe pytanie, rozmowa, podziękowanie, potwierdzenie albo odpowiedź, która nie zmienia obrazu. Samo „okej” oznacza chat.
- "image" — każda prośba o nowy obraz LUB zmianę/rozwinięcie aktualnego obrazu. Dotyczy też krótkich i kontekstowych próśb, np. „teraz w złotej sukni”, „pokaż ją w lesie”, „dodaj okulary”, „zmień kolor włosów”, „zrób bardziej realistycznie”, „a teraz z bliska”. Gdy bieżąca sesja ma obraz/prompt, odczytuj takie dopowiedzenia jako edycję tego obrazu, chyba że użytkownik wyraźnie zaczyna nowy temat.
- "new_image" — tylko gdy użytkownik wyraźnie chce porzucić bieżący obraz i stworzyć inny, niezwiązany obraz, np. „zacznij od początku”, „nowy obraz: samochód”, „zapomnij poprzednią scenę”.

Nie wybieraj "chat" dla prośby o zmianę wyglądu tylko dlatego, że jest sformułowana jako pytanie („czy możesz pokazać ją w…?”). Nie zmieniaj działania na podstawie samego promptu; liczy się intencja w ostatniej wiadomości.
Odpowiadaj krótko i po polsku. Zwróć WYŁĄCZNIE poprawny JSON: {"action":"chat|image|new_image","reply":"krótka odpowiedź po polsku","corrected":"poprawiona ostatnia wiadomość użytkownika"}.'''
        if current_prompt:
            system += "\nBieżący prompt obrazu (kontekst, nie wypisuj go w odpowiedzi):\n" + current_prompt[:5000]
        messages = [{"role": "system", "content": system}]
        messages.extend({"role": role, "content": content} for role, content in turns[-16:])
        payload = {"model": self.model, "messages": messages, "temperature": 0.4,
                   "max_tokens": 280, "stream": False, "cache_prompt": False}
        result = self._request_json('POST', self.base + '/chat/completions', json=payload,
                                    headers=self.headers(), timeout=self.timeout)
        content = result['choices'][0]['message']['content']
        try:
            result = json.loads(content)
        except (ValueError, TypeError):
            start, end = content.find('{'), content.rfind('}')
            result = json.loads(content[start:end + 1]) if start >= 0 and end > start else {}
        action = result.get('action', 'image')
        if action not in ('chat', 'image', 'new_image'):
            action = 'image'
        latest_user = next((content for role, content in reversed(turns) if role == "user"), "")
        corrected = result.get("corrected", latest_user)
        if not isinstance(corrected, str) or not corrected.strip():
            corrected = latest_user
        return {"action": action, "reply": str(result.get('reply') or "Jasne."),
                "corrected": corrected.strip()}

    def create_krea2_prompt(self, turns, current_prompt="", new_image=False):
        """Create a Krea2 image prompt using only the live conversation."""
        system = '''Tworzysz prompt obrazu dla modelu Krea2 działającego w ComfyUI. Rozum polecenia użytkownika po polsku, również potoczne, z literówkami i skrótami. Zanim napiszesz prompt, ustal dokładnie, co użytkownik chce zobaczyć lub zmienić.
Przekaż jego prośbę wiernie. Nie pomijaj kolorów, ubioru, liczby osób, relacji między obiektami, miejsca, kadru ani innych podanych szczegółów. Nie dopisuj zmian, których użytkownik nie chciał.
Nie ma presetów, stałego stylu, szablonu postaci ani obowiązkowego tematu. Używaj wyłącznie próśb użytkownika i istotnego kontekstu rozmowy.
Zwróć jeden klarowny, szczegółowy prompt po angielsku, odpowiedni dla Krea2. Tłumaczenie na angielski nie może zmieniać sensu polskiej prośby.
Przy edycji zachowaj tożsamość postaci, jej wygląd, kompozycję i wszystkie elementy sceny, których użytkownik nie kazał zmienić; zastosuj dokładnie najnowszą zmianę. Przy nowym, niezwiązanym obrazie nie przenoś tematu ani sceny z poprzedniego obrazu.
Zwróć wyłącznie gotowy prompt, bez wyjaśnień i nagłówków.'''
        if current_prompt and not new_image:
            system += "\nCurrent image prompt to preserve and revise as requested:\n" + current_prompt[:7000]
        selected_turns = turns[-16:]
        if new_image:
            selected_turns = turns[-1:]
        messages = [{"role": "system", "content": system}]
        messages.extend({"role": role, "content": content} for role, content in selected_turns)
        payload = {"model": self.model, "messages": messages,
                   "temperature": self.cfg.get('temperature', 0.7),
                   "top_p": self.cfg.get('top_p', 0.95),
                   "max_tokens": self.cfg.get('max_tokens', 1400),
                   "stream": False, "cache_prompt": False}
        result = self._request_json('POST', self.base + '/chat/completions', json=payload,
                                    headers=self.headers(), timeout=self.timeout)
        content = result['choices'][0]['message']['content']
        prompt = clean_llm_text(content)
        if not prompt or prompt.startswith(('```', 'I cannot help', 'I can\'t help')):
            raise RuntimeError('LLM did not return a usable Krea2 image prompt.')
        return prompt
    def _fresh_scene_anchors(self):
        """Draw anchors without replacement, without reading generated prompts."""
        choices = {
            'hair': [
                'a blunt dark bob with a side part', 'long wavy auburn hair',
                'a short curly black crop', 'straight shoulder-length ash-brown hair',
                'a loose dark braid', 'a tousled blonde pixie cut',
                'thick chestnut curls', 'long straight blue-black hair',
            ],
            'place': [
                'a softly lit hotel bathroom', 'a compact apartment kitchen',
                'a sunlit bedroom beside an open wardrobe', 'a quiet hallway with a full-length mirror',
                'a lived-in studio apartment near a window', 'a tiled dressing room',
                'a small laundry room', 'a guest bedroom with patterned curtains',
            ],
            'pose/action': [
                'sitting sideways on a chair while turning toward the phone',
                'standing by a doorway with one shoulder resting against the frame',
                'kneeling beside a bed while checking the phone screen',
                'leaning toward a mirror and lifting the phone above eye level',
                'sitting on the floor with one knee raised, glancing away from the camera',
                'standing near a window and looking back over one shoulder',
                'reclining diagonally across an armchair, one arm extended with the phone',
                'perched on a vanity stool while adjusting an earring',
            ],
            'framing': [
                'a slightly tilted waist-up mirror selfie', 'a close portrait from above eye level',
                'a candid three-quarter view with the phone partly visible',
                'a wider reflection showing more of the room',
                'a low, casual angle with foreground furniture partly in frame',
                'a shoulder-level crop with the subject off-center',
            ],
            'light': [
                'cool window light mixed with a warm bedside lamp',
                'uneven overhead bathroom light with soft window spill',
                'late-afternoon light filtered through thin curtains',
                'a dim amber lamp with gentle shadows',
                'neutral daylight and a slightly underexposed background',
                'mixed practical lighting with a subtle phone-camera flash reflection',
            ],
        }
        selected = []
        for name, options in choices.items():
            bag = self._anchor_bags.setdefault(name, [])
            if not bag:
                bag.extend(options)
                secrets.SystemRandom().shuffle(bag)
            selected.append(f'{name}: {bag.pop()}')
        return '; '.join(selected)

    def generate(self,base,typ,user_prompt,instructions,reference,attempt=1,style='',minimum_words=None,conversation=False):
        fixed_start=' '.join(x.strip() for x in (base,style) if x and x.strip())
        minimum_words = max(100, int(minimum_words if minimum_words is not None else self.cfg.get('minimum_prompt_words', 180)))
        continuity = ('Continue the current image session. Preserve the same adult subject, identity, face, hair, and scene unless the user explicitly changes them. Apply the newest requested changes to the existing concept; do not restart the scene. These continuity rules override conflicting preset instructions to invent a different person or situation.' if conversation else 'Create a fully conceived scene from only the fixed settings and the current request. Treat this request as an isolated task; do not assume or continue any earlier conversation.')
        system=f'''You are the creative director of a universal image-generation agent.\n\nBASE PROMPT (must remain exactly at the beginning):\n{base}\n\nSTYLE:\n{style or '(none)'}\n\nTYPE:\n{typ}\n\nINSTRUCTIONS:\n{instructions}\n\nREFERENCE PROMPT:\n{reference or '(none)'}\n\n{continuity} Make the character, place, action, pose, camera framing, lighting, and surrounding details concrete and visually specific.\n\nLENGTH AND DETAIL: The complete final prompt must contain at least {minimum_words} words, including the fixed BASE PROMPT. Aim for 200-250 words. Do not compress or summarize the scene. Develop the character's visible appearance, setting, action and pose, camera framing, lighting, and photographic texture in full sentences.\n\nOUTPUT RULES:\n- Output ONLY one finished image-generation prompt.\n- Start with the BASE PROMPT text exactly, followed by the STYLE text exactly when supplied.\n- Treat the user message as the requested creative direction.{' Use these visual anchors unless they conflict with the established subject or scene: ' + self._fresh_scene_anchors() if not conversation else ''}\n- Keep the fixed style and instructions while developing the image.\n- Do not explain anything or add labels or commentary.'''
        # Each image gets an isolated, newly constructed chat request. Disable
        # llama.cpp's prompt/KV-prefix reuse as well, so every request is
        # evaluated from its own system + user messages.
        request_text = user_prompt.strip() or 'Create a completely new image concept from scratch.'
        payload={'model':self.model,'messages':[{'role':'system','content':system},{'role':'user','content':request_text}],'temperature':self.cfg.get('temperature',.9),'top_p':self.cfg.get('top_p',.95),'max_tokens':self.cfg.get('max_tokens',1400),'stream':False,'cache_prompt':False}
        result=self._request_json('POST',self.base+'/chat/completions',json=payload,headers=self.headers(),timeout=self.timeout); text=clean_llm_text(result['choices'][0]['message']['content'])
        if is_llm_refusal(text):
            raise RuntimeError('LLM declined the prompt. No image was sent to ComfyUI.')
        if not text or (fixed_start and text.strip() == fixed_start.strip()):
            raise RuntimeError('LLM returned no scene description. No image was sent to ComfyUI.')
        if fixed_start and not text.startswith(fixed_start): text=fixed_start.rstrip()+' '+text.lstrip()
        return text
