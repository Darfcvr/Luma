import json
import threading
import time
from pathlib import Path

from .comfy import ComfyClient
from .llm import LLMClient
from .llm_lifecycle import LLMServerLifecycle
from .state import State
from .telegram import TelegramBot
from .utils import load_json, now


class Agent:
    def __init__(self, root="."):
        self.root = Path(root).resolve()
        defaults = {
            "llm": {"base_url": "http://127.0.0.1:1234/v1", "api_key": "", "model": "local-model", "timeout": 180, "temperature": .9, "top_p": .95, "max_tokens": 1400},
            "comfyui": {"base_url": "http://127.0.0.1:8188", "poll_interval": 1, "timeout": 3600, "output_directory": ""},
            "telegram": {"enabled": False, "bot_token": "", "chat_id": "", "send_results": False},
            "llm_lifecycle": {"enabled": False, "host": "", "port": 22, "user": "", "key_path": "~/.ssh/id_ed25519", "password": "", "start_command": "start", "stop_command": "stop", "status_command": "status", "start_timeout": 190, "stop_timeout": 45},
            "agent": {"continuous": False, "cooldown_seconds": 10, "max_llm_attempts": 4, "save_prompts": True},
            "paths": {"state": "state.json", "prompts": "prompts", "presets": "presets", "workflows": "workflows"},
        }
        self.config = load_json(self.root / "config.json", {}) or {}
        for section, values in defaults.items():
            current = self.config.setdefault(section, {})
            for key, value in values.items():
                current.setdefault(key, value)
        self.state = State(self.root / self.config["paths"]["state"])
        self.llm = LLMClient(self.config["llm"])
        self.llm_server = LLMServerLifecycle(self.config.get("llm_lifecycle", {}))
        self.comfy = ComfyClient(self.config["comfyui"], self.root)
        self.stop_event = threading.Event()
        self.running = False
        self._run_lock = threading.Lock()
        self.listeners = []
        self.current_preset = "selfie"
        self.telegram = TelegramBot(self.config.get("telegram", {}), self.telegram_command, self.emit)

    def on_event(self, fn):
        self.listeners.append(fn)

    def emit(self, event, data=None):
        for fn in self.listeners:
            try:
                fn(event, data)
            except Exception:
                pass

    def preset(self, name):
        path = self.root / self.config["paths"]["presets"] / (name + ".json")
        data = load_json(path)
        if not data:
            raise FileNotFoundError(path)
        return data

    def _workflow_path(self, workflow):
        path = Path(workflow)
        if path.is_absolute():
            return path
        candidates = [self.root / path, self.root / self.config["paths"]["workflows"] / path]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[0]

    def generate_once(self, preset_name=None, user_prompt=None, conversational=False, init_image=None):
        name = preset_name or self.current_preset
        preset = self.preset(name)
        accepted, chosen = False, None
        prompt_request = user_prompt if user_prompt else preset.get("llm_prompt", preset.get("prompt", ""))
        prompt_request = prompt_request or "Create a completely new image concept."
        minimum_words = max(100, int(self.config["agent"].get("minimum_prompt_words", 180)))
        attempt = 0
        retry_delay = 1.0
        while not accepted and not self.stop_event.is_set():
            attempt += 1
            self.emit("status", f"LLM: generating variation {attempt}")
            instructions = preset.get("instructions", preset.get("Instructions", ""))
            if isinstance(instructions, list):
                instructions = "\n".join(map(str, instructions))
            llm_started = time.perf_counter()
            try:
                candidate = self.llm.generate(
                    preset.get("base_prompt", preset.get("Base", "")), preset.get("type", preset.get("Type", "")),
                    prompt_request, instructions,
                    preset.get("reference_prompt", ""), attempt, preset.get("style", preset.get("Style", "")),
                    minimum_words, conversational,
                )
                llm_seconds = time.perf_counter() - llm_started
            except Exception as exc:
                if self.stop_event.is_set():
                    break
                llm_seconds = time.perf_counter() - llm_started
                self.emit("error", f"LLM attempt {attempt} failed after {llm_seconds:.1f}s; retrying: {exc}")
                self.emit("status", f"LLM: attempt {attempt} failed after {llm_seconds:.1f}s; retrying in {retry_delay:g}s")
                if self.stop_event.wait(retry_delay):
                    break
                retry_delay = min(retry_delay * 2, 30.0)
                continue
            word_count = len(candidate.split())
            length_ok = word_count >= minimum_words
            ok = length_ok
            rejection_reason = ""
            if not length_ok:
                rejection_reason = f"too short ({word_count}/{minimum_words} words)"
            self.emit("variation", {"attempt": attempt, "accepted": ok,
                                     "length_ok": length_ok, "word_count": word_count,
                                     "minimum_words": minimum_words, "llm_seconds": llm_seconds,
                                     "rejection_reason": rejection_reason})
            chosen = candidate
            if ok:
                accepted = True
                continue
            self.emit("status", f"LLM: prompt too short; generating another variation (attempt {attempt + 1})")
            if self.stop_event.wait(1.0):
                break
        if self.stop_event.is_set():
            raise InterruptedError("Generation stopped by user")
        if not accepted:
            raise RuntimeError("Could not create a prompt that meets the minimum length. No image was submitted.")
        if self.stop_event.is_set():
            raise InterruptedError("Generation stopped by user")

        generation = self.state.data.get("generation_count", 0) + 1
        job = f"{name}-{generation:06d}"
        workflow = preset.get("workflow_api", preset.get("workflow"))
        if not workflow:
            raise ValueError(f"Preset {name} has no workflow_api configured")
        workflow_data = self.comfy.load_workflow(self._workflow_path(workflow))
        if conversational and init_image:
            image_node_id = preset.get("image_node_id")
            if image_node_id is None:
                image_nodes = [(key, node) for key, node in workflow_data.items()
                               if node.get("class_type") == "LoadImage"]
                if len(image_nodes) == 1:
                    image_node_id = image_nodes[0][0]
            image_node = workflow_data.get(str(image_node_id)) if image_node_id is not None else None
            if image_node is None:
                self.emit("status", "ComfyUI: selected workflow has no configured image input; keeping the conversation context")
            else:
                uploaded_image = self.comfy.upload_image(init_image)
                image_node.setdefault("inputs", {})["image"] = uploaded_image
        randomized_seeds = self.comfy.randomize_seeds(workflow_data)
        if randomized_seeds:
            self.emit("status", "ComfyUI: randomized sampler seed")
        node_id = preset.get("prompt_node_id", "74")
        input_name = preset.get("prompt_input_name", "text")
        if str(node_id) not in workflow_data and node_id not in workflow_data:
            # ComfyUI node IDs may include a subgraph path (for example 74:11).
            candidates = [(key, node) for key, node in workflow_data.items()
                          if node.get("class_type") == "CLIPTextEncode" and "text" in node.get("inputs", {})
                          and "positive" in str(node.get("_meta", {}).get("title", "")).lower()]
            if len(candidates) == 1:
                node_id = candidates[0][0]
            else:
                raise KeyError(f"Prompt node {node_id} not found in workflow {workflow}")
        self.comfy.set_prompt(workflow_data, node_id, input_name, chosen)
        self.emit("status", f"ComfyUI: generation {generation}")
        prompt_id = self.comfy.queue(workflow_data)
        self.emit("queued", {"generation": generation, "job_id": job, "prompt_id": prompt_id, "prompt": chosen})
        item = self.comfy.wait(prompt_id, self.stop_event)
        outputs = self.comfy.output_files(item)
        generation = self.state.next_generation()
        if self.config["agent"].get("save_prompts", True):
            prompt_dir = self.root / self.config["paths"]["prompts"]
            prompt_dir.mkdir(parents=True, exist_ok=True)
            (prompt_dir / f"prompt_{generation:06d}.txt").write_text(
                f"GENERATION: {generation}\nJOB: {job}\nPRESET: {name}\nDATE: {now()}\n\nBASE:\n{preset.get('base_prompt', '')}\n\nTYPE:\n{preset.get('type', '')}\n\nLLM REQUEST:\n{prompt_request}\n\nFINAL PROMPT:\n{chosen}\n", encoding="utf-8")
        self.state.add(chosen, job, name, outputs[0] if outputs else "")
        if self.config.get("telegram", {}).get("send_results") and outputs:
            for output in outputs:
                self.telegram.send_photo(output, f"Generation {generation} | {name}")
        self.emit("completed", {"generation": generation, "job_id": job, "prompt": chosen, "outputs": outputs})
        return {"generation": generation, "outputs": outputs, "prompt": chosen}

    def generate_conversation_image(self, workflow, prompt, prompt_node_id="", prompt_input_name="text",
                                    init_image=None, image_node_id="", megapixels=None,
                                    switch_node_id="", resolution_node_id="", stop_event=None):
        """Submit a freeform conversational prompt without loading any preset."""
        if not workflow:
            raise ValueError("Choose a ComfyUI workflow first.")
        generation = int(self.state.data.get("generation_count", 0)) + 1
        job = f"conversation-{generation:06d}"
        workflow_data = self.comfy.load_workflow(self._workflow_path(workflow))
        stop_event = stop_event or self.stop_event
        if stop_event.is_set():
            raise InterruptedError("Generation cancelled")

        # ResolutionSelector controls the latent dimensions upstream of the
        # sampler. Locate it from the workflow so the UI doesn't depend on a
        # hard-coded node number.
        if megapixels is not None:
            if isinstance(megapixels, bool) or not 0.01 <= float(megapixels) <= 10.0:
                raise ValueError("Megapixels must be between 0.01 and 10.")
            if resolution_node_id:
                resolution_node = workflow_data.get(str(resolution_node_id))
                if resolution_node is None:
                    raise ValueError(f"Resolution node {resolution_node_id} was not found.")
            else:
                resolution_nodes = [(key, node) for key, node in workflow_data.items()
                                    if node.get("class_type") == "ResolutionSelector"
                                    and "megapixels" in node.get("inputs", {})]
                resolution_node = resolution_nodes[0][1] if len(resolution_nodes) == 1 else None
            if resolution_node is None or "megapixels" not in resolution_node.get("inputs", {}):
                raise ValueError("Could not identify the workflow's ResolutionSelector megapixels input.")
            resolution_node["inputs"]["megapixels"] = float(megapixels)

        # The workflow switch always starts in the empty-latent branch. It is
        # only enabled when a previous image is actually available and sent.
        if switch_node_id:
            switch_node = workflow_data.get(str(switch_node_id))
            if switch_node is None or not {"switch", "on_true", "on_false"}.issubset(switch_node.get("inputs", {})):
                raise ValueError(f"Image switch node {switch_node_id} is missing or is not a Comfy switch.")
            switch_nodes = [(str(switch_node_id), switch_node)] if switch_node else []
        else:
            switch_nodes = [(key, node) for key, node in workflow_data.items()
                            if node.get("class_type") == "ComfySwitchNode"
                            and {"switch", "on_true", "on_false"}.issubset(node.get("inputs", {}))]
        if len(switch_nodes) == 1:
            switch_node = switch_nodes[0][1]
            switch_node["inputs"]["switch"] = bool(init_image)

        if prompt_node_id:
            node = workflow_data.get(str(prompt_node_id))
            if node is None:
                raise KeyError(f"Prompt node {prompt_node_id} was not found in the selected workflow.")
        else:
            candidates = [(key, node) for key, node in workflow_data.items()
                          if isinstance(node.get("inputs"), dict) and "text" in node["inputs"]]
            positive = [(key, node) for key, node in candidates
                        if "positive" in str(node.get("_meta", {}).get("title", "")).lower()]
            if not positive:
                positive = [(key, node) for key, node in candidates
                            if "negative" not in str(node.get("_meta", {}).get("title", "")).lower()]
            if len(positive) == 1:
                prompt_node_id, node = positive[0]
            elif len(candidates) == 1:
                prompt_node_id, node = candidates[0]
            else:
                raise ValueError("Could not identify the positive prompt node. Enter its node ID.")
        input_name = prompt_input_name or "text"
        if input_name not in node.get("inputs", {}):
            raise KeyError(f"Prompt input '{input_name}' was not found on workflow node {prompt_node_id}.")

        if init_image:
            if stop_event.is_set():
                raise InterruptedError("Generation cancelled")
            if image_node_id:
                image_node = workflow_data.get(str(image_node_id))
            else:
                image_nodes = [(key, node) for key, node in workflow_data.items()
                               if node.get("class_type") == "LoadImage"]
                image_node = image_nodes[0][1] if len(image_nodes) == 1 else None
            if image_node is None or "image" not in image_node.get("inputs", {}):
                raise ValueError("For img2img, set the workflow's LoadImage node ID or use a workflow with one LoadImage node.")
            image_node["inputs"]["image"] = self.comfy.upload_image(init_image)
        if stop_event.is_set():
            raise InterruptedError("Generation cancelled")
        self.comfy.set_prompt(workflow_data, prompt_node_id, input_name, prompt)
        if stop_event.is_set():
            raise InterruptedError("Generation cancelled")
        self.comfy.randomize_seeds(workflow_data)
        self.emit("status", f"ComfyUI: conversation image {generation}")
        prompt_id = self.comfy.queue(workflow_data)
        if stop_event.is_set():
            self.comfy.interrupt()
            raise InterruptedError("Generation cancelled")
        self.emit("queued", {"generation": generation, "job_id": job, "prompt_id": prompt_id, "prompt": prompt})
        item = self.comfy.wait(prompt_id, stop_event)
        outputs = self.comfy.output_files(item)
        generation = self.state.next_generation()
        if self.config["agent"].get("save_prompts", True):
            prompt_dir = self.root / self.config["paths"]["prompts"]
            prompt_dir.mkdir(parents=True, exist_ok=True)
            (prompt_dir / f"prompt_{generation:06d}.txt").write_text(
                f"GENERATION: {generation}\nJOB: {job}\nMODE: conversation\nDATE: {now()}\n\nFINAL PROMPT:\n{prompt}\n",
                encoding="utf-8")
        self.state.add(prompt, job, "conversation", outputs[0] if outputs else "")
        if self.config.get("telegram", {}).get("send_results") and outputs:
            for output in outputs:
                self.telegram.send_photo(output, f"Generation {generation} | conversation")
        self.emit("completed", {"generation": generation, "job_id": job, "prompt": prompt, "outputs": outputs})
        return {"generation": generation, "outputs": outputs, "prompt": prompt}

    def start(self, preset=None, once=False):
        with self._run_lock:
            if self.running:
                return False
            self.running = True
            self.current_preset = preset or self.current_preset
            self.stop_event.clear()
            self.telegram.start()
            self.telegram.send_message(f"AI Image Agent uruchomiony. Preset: {self.current_preset}.\nKomendy: /run /stop /status /preset <nazwa> /generate")
            threading.Thread(target=self._loop, args=(once,), daemon=True).start()
        self.emit("status", "Agent started")
        return True

    def _loop(self, once=False):
        try:
            if self.llm_server.enabled:
                self.emit("status", "LLM: starting remote server over SSH")
                result = self.llm_server.start()
                self.emit("status", f"LLM: remote server {result.lower()}")
            while not self.stop_event.is_set():
                inp = load_json(self.root / "input.json", {})
                name = inp.get("preset", self.current_preset)
                self.current_preset = name
                preset_data = self.preset(name)
                request = inp.get("llm_prompt") or preset_data.get("llm_prompt") or preset_data.get("prompt") or inp.get("prompt") or None
                self.generate_once(name, request)
                if once or not self.config["agent"].get("continuous", True) or not inp.get("continuous", True):
                    break
                self.stop_event.wait(max(0, float(self.config["agent"].get("cooldown_seconds", 10))))
        except InterruptedError:
            pass
        except Exception as exc:
            if not self.stop_event.is_set():
                self.emit("error", str(exc))
                self.telegram.send_message(f"Błąd agenta: {exc}")
        finally:
            if self.llm_server.enabled:
                try:
                    self.emit("status", "LLM: stopping remote server over SSH")
                    result = self.llm_server.stop()
                    self.emit("status", f"LLM: remote server {result.lower()}")
                except Exception as exc:
                    self.emit("error", f"LLM server shutdown failed: {exc}")
                    self.telegram.send_message(f"Nie udało się zatrzymać zdalnego LLM: {exc}")
            with self._run_lock:
                self.running = False
            self.emit("status", "Stopped")
            self.telegram.send_message(f"Agent zatrzymany. Wykonane generacje: {self.state.data.get('generation_count', 0)}")

    def stop(self):
        self.stop_event.set()
        self.llm.cancel_active()
        threading.Thread(target=self.comfy.interrupt, name="comfy-interrupt", daemon=True).start()
        self.emit("status", "Stopping...")

    def telegram_command(self, text):
        parts = text.split(maxsplit=1)
        command = parts[0].split("@", 1)[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""
        if command in ("/start", "/run"):
            if self.start(self.current_preset):
                self.telegram.send_message(f"Agent rozpoczął pracę. Preset: {self.current_preset}")
            else:
                self.telegram.send_message("Agent już pracuje.")
        elif command == "/stop":
            self.stop()
            self.telegram.send_message("Zatrzymuję agenta.")
        elif command == "/status":
            self.telegram.send_message(f"Agent: {'pracuje' if self.running else 'zatrzymany'}\nPreset: {self.current_preset}\nGeneracje: {self.state.data.get('generation_count', 0)}")
        elif command == "/preset":
            if not arg:
                self.telegram.send_message("Użycie: /preset nazwa")
            else:
                available = {p.stem for p in (self.root / self.config["paths"]["presets"]).glob("*.json")}
                if arg not in available:
                    self.telegram.send_message("Nieznany preset. Dostępne: " + ", ".join(sorted(available)))
                else:
                    self.current_preset = arg
                    input_path = self.root / "input.json"
                    input_data = load_json(input_path, {})
                    input_data["preset"] = arg
                    selected_preset = self.preset(arg)
                    input_data["llm_prompt"] = selected_preset.get("llm_prompt", selected_preset.get("prompt", ""))
                    input_path.write_text(json.dumps(input_data, ensure_ascii=False, indent=2), encoding="utf-8")
                    self.telegram.send_message(f"Ustawiono preset: {arg}")
        elif command == "/generate":
            if self.start(self.current_preset, once=True):
                self.telegram.send_message("Uruchamiam jedną generację.")
            else:
                self.telegram.send_message("Agent już pracuje; użyj /status.")
        else:
            self.telegram.send_message("Komendy: /run, /generate, /stop, /status, /preset nazwa")
