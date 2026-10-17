"""Small UI translation layer for the English and Polish interface."""
from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QTextEdit, QWidget


EN = {
    "Gotowy": "Ready", "Agent pracuje": "Agent is working", "Anuluj wszystko": "Cancel all",
    "Zatrzymaj mikrofon, generowanie, żądania i zdalny serwer LLM": "Stop the microphone, generation, requests, and remote LLM server",
    "⚙  Ustawienia": "⚙  Settings", "Ustawienia zapisane": "Settings saved",
    "Brak aktywnego zadania": "No active task", "LOCAL IMAGE STUDIO": "LOCAL IMAGE STUDIO",
    "TWOJE STUDIO OBRAZU": "YOUR IMAGE STUDIO", "Od pomysłu\ndo obrazu.": "From idea\nto image.",
    "Wybierz sposób pracy. Możesz tworzyć bezpośrednio albo prowadzić z agentem rozmowę, która rozwija obraz krok po kroku.": "Choose how to work. Generate directly or build an image step by step through conversation with the agent.",
    "Auto generate": "Auto generate", "Pełny panel generowania i ustawień workflow.": "Full generation workspace and workflow settings.",
    "Otwórz generator  →": "Open generator  →", "Tryb rozmowy": "Conversation mode",
    "Rozmawiaj, poprawiaj obraz i zachowuj kontekst sesji.": "Chat, refine the image, and keep the session context.",
    "Rozpocznij rozmowę  →": "Start a conversation  →", "Workflow ComfyUI  ·  lokalny podgląd  ·  konfigurowalne połączenia": "ComfyUI workflows  ·  local previews  ·  configurable connections",
    "Twój asystent kreatywny": "Your creative assistant", "Opisz, co chcesz zobaczyć. Agent przygotuje prompt, wygeneruje obraz i pomoże wprowadzić kolejne zmiany.": "Describe what you want to see. The agent will prepare a prompt, generate the image, and help you refine it.",
    "Język": "Language", "English": "English", "Polski": "Polish",
    "← Wróć": "← Back", "← Tryby": "← Modes", "Ustawienia": "Settings",
    "Konfiguracja połączeń i zachowania agenta": "Configure connections and agent behavior", "Zapisz ustawienia": "Save settings",
    "Model językowy": "Language model", "Adres API, model i parametry generowania.": "API address, model, and generation parameters.",
    "Adres API": "API address", "Klucz API": "API key", "Model": "Model", "Limit czasu (s)": "Timeout (s)",
    "Temperatura": "Temperature", "Maks. tokenów": "Max tokens", "Serwer i ścieżki wynikowe.": "Server and output paths.",
    "Adres serwera": "Server address", "Odstęp odpytywania (s)": "Polling interval (s)", "Limit generowania (s)": "Generation timeout (s)",
    "Folder wynikowy": "Output folder", "SSH · zdalny serwer LLM": "SSH · remote LLM server",
    "Możesz użyć klucza OpenSSH albo hasła. Weryfikacja hosta korzysta z systemowego pliku known_hosts.": "Use an OpenSSH key or password. Host verification uses the system known_hosts file.",
    "Zarządzaj serwerem przez SSH": "Manage server over SSH", "Użytkownik": "User", "Ścieżka klucza SSH": "SSH key path",
    "Hasło SSH / hasło klucza": "SSH password / key passphrase", "Komenda start": "Start command", "Komenda stop": "Stop command",
    "Komenda status": "Status command", "Limit uruchamiania (s)": "Startup timeout (s)", "Limit zatrzymywania (s)": "Shutdown timeout (s)",
    "Port SSH": "SSH port", "Opcjonalne powiadomienia o generacjach.": "Optional generation notifications.", "Włącz Telegram": "Enable Telegram",
    "Token bota": "Bot token", "Wysyłaj wyniki": "Send results", "Chat ID": "Chat ID", "Ustawienia pracy oraz lokalizacje danych.": "Agent behavior and data locations.",
    "Tryb ciągły": "Continuous mode", "Przerwa (s)": "Cooldown (s)", "Maks. prób LLM": "Max LLM attempts", "Zapisuj prompty": "Save prompts",
    "Lokalne pliki i foldery projektu.": "Local project files and folders.", "Plik stanu": "State file", "Folder promptów": "Prompts folder",
    "Folder presetów": "Presets folder", "Folder workflow": "Workflows folder", "Ścieżki": "Paths", "Agent i pliki": "Agent and files",
    "Pozostaw puste, jeśli nie używasz": "Leave blank if unused",
    "Pokaż": "Show", "Ustawienia zapisane": "Settings saved", "Konfiguracja została zapisana.": "Configuration saved.", "Nie udało się zapisać": "Could not save",
    "Opisz obraz albo poproś o zmianę bieżącej sceny": "Describe an image or ask to change the current scene", "Wynik obrazu": "Image result",
    "Wygenerowany obraz pojawi się tutaj": "Your generated image will appear here", "Co chcesz stworzyć lub zmienić?…": "What would you like to create or change?…",
    "Wyślij": "Send", "🎙 Mów": "🎙 Speak", "Zacznij od początku": "Start over", "Narzędzia": "Tools",
    "Model LLM": "LLM model", "Odśwież listę": "Refresh list", "Workflow API ComfyUI": "ComfyUI API workflow", "Wybierz…": "Browse…",
    "Opcje workflow i img2img": "Workflow and img2img options", "ID promptu": "Prompt node ID", "ID LoadImage": "LoadImage node ID",
    "ID switcha": "Switch node ID", "Używaj poprzedniego obrazu przy edycji (img2img)": "Use the previous image when editing (img2img)",
    "Rozdzielczość (MP)": "Resolution (MP)", "PRACA AGENTA": "AGENT STATUS", "Czeka na Twoją wiadomość.": "Waiting for your message.",
    "MOWA NA ŻYWO": "LIVE TRANSCRIPTION", "Rozpoznawany tekst pojawi się tutaj…": "Recognized speech will appear here…", "Historia rozmowy": "Conversation history",
    "Tutaj pojawią się wypowiedzi i odpowiedzi.": "Messages and replies will appear here.", "Prompt Krea2": "Krea2 prompt", "Gotowy prompt pojawi się tutaj.": "The completed prompt will appear here.",
    "Wynik generowania": "Generation result", "Co chcesz wygenerować?": "What would you like to generate?", "Opisz obraz lub nowy pomysł…": "Describe an image or a new idea…",
    "Generuj / Start": "Generate / Start", "+ Nowy preset": "+ New preset", "Zapisz preset": "Save preset", "Preset": "Preset",
    "Odśwież listę modeli": "Refresh model list", "Workflow ComfyUI": "ComfyUI workflow", "Wybierz workflow…": "Choose workflow…",
    "Wysyłaj do Telegrama": "Send to Telegram", "Zaawansowane wytyczne promptu": "Advanced prompt guidance", "Prompt bazowy": "Base prompt",
    "Styl": "Style", "Typ": "Type", "Prompt odniesienia": "Reference prompt", "Instrukcje": "Instructions", "Historia promptów": "Prompt history",
    "Archiwizuj prompty": "Archive prompts", "Rozpoczęto": "Started", "Generacje": "Generations", "Generowanie obrazów": "Image generation",
    "Anulowano": "Cancelled", "Rozpoznano: ": "Recognized: ", "Obraz gotowy": "Image ready", "Odpowiedź gotowa": "Reply ready",
    "Przygotowuję odpowiedź…": "Preparing a reply…", "Uruchamiam mikrofon…": "Starting microphone…", "Mikrofon gotowy — możesz mówić": "Microphone ready — you can speak",
    "Ustawienia zapisane — odśwież listę modeli, aby wczytać zmiany": "Settings saved — refresh the model list to load changes",
    "Poprawiono oczywisty błąd rozpoznawania mowy": "Corrected an obvious speech recognition error", "Serwer nie zwrócił listy modeli": "The server returned no model list",
    "Gotowy — nowa rozmowa": "Ready — new conversation", "Generowanie zakończone": "Generation complete",
    "Analizuję polecenie": "Analyzing request", "Sprawdzam, czy chcesz porozmawiać, utworzyć obraz czy zmienić bieżący.": "Checking whether you want to chat, create an image, or edit the current one.",
    "Analizuję rozmowę": "Reviewing conversation", "Ustalam, czy odpowiedzieć, wygenerować obraz, czy zacząć nowy.": "Deciding whether to reply, generate an image, or start a new one.",
    "Odpowiadam": "Replying", "Przygotowuję obraz": "Preparing image", "Układam prompt dla Krea2 na podstawie rozmowy.": "Building a Krea2 prompt from the conversation.",
    "Rozpoczynam nowy obraz bez kontekstu poprzedniej sceny.": "Starting a new image without the previous scene's context.", "Prompt gotowy": "Prompt ready",
    "Wysyłam wybrany workflow do ComfyUI i czekam na obraz.": "Sending the selected workflow to ComfyUI and waiting for the image.",
    "ComfyUI generuje": "ComfyUI is generating", "Przygotowuję rozpoznawanie mowy": "Preparing speech recognition",
    "Ładuję polski model Whisper small. Przy pierwszym uruchomieniu może pobrać model; później będzie działał lokalnie.": "Loading the Whisper small speech model. It may download on first launch; afterward it runs locally.",
    "Rozpoznawanie mowy gotowe": "Speech recognition ready", "Mikrofon używa lokalnego modelu Whisper small.": "The microphone uses the local Whisper small model.",
    "Model mowy niedostępny": "Speech model unavailable", "Obraz jest gotowy i można go dalej zmieniać.": "The image is ready for further edits.",
    "Poprawiono: ": "Corrected: ", "Wczytuję modele…": "Loading models…",
    "Zatrzymano aktywną pracę agenta.": "Stopped the active agent task.", "Zadanie anulowane": "Task cancelled",
    "Nowa rozmowa": "New conversation", "Kontekst LLM i poprzedni obraz zostały wyczyszczone. Czekam na nowe polecenie.": "The LLM context and previous image were cleared. Waiting for a new request.",
    "Asystent: Nie udało się wykonać polecenia: ": "Assistant: Could not complete the request: ",
}


def tr(text, language="en"):
    if language != "en":
        return text
    if text in EN:
        return EN[text]
    for prefix, translated in (("Wczytano modeli: ", "Models loaded: "), ("Błąd: ", "Error: "),
                               ("Rozpoznano: ", "Recognized: "), ("Agent pracuje", "Agent is working"),
                               ("Generacje  ", "Generations  ")):
        if text.startswith(prefix):
            return translated + text[len(prefix):]
    return text


def apply_language(root, language="en"):
    """Translate static widget copy while keeping user-entered content untouched."""
    root.language = language
    widgets = [root, *root.findChildren(QWidget)]
    for widget in widgets:
        if not hasattr(widget, "property"):
            continue
        if isinstance(widget, QAbstractButton):
            source = widget.property("i18n_source_text")
            if source is None:
                source = widget.text()
                widget.setProperty("i18n_source_text", source)
            widget.setText(tr(source, language))
        if isinstance(widget, QLabel):
            source = widget.property("i18n_source_text")
            if source is None:
                source = widget.text()
                widget.setProperty("i18n_source_text", source)
            widget.setText(tr(source, language))
        if isinstance(widget, (QLineEdit, QTextEdit)):
            source = widget.property("i18n_source_placeholder")
            if source is None:
                source = widget.placeholderText()
                widget.setProperty("i18n_source_placeholder", source)
            widget.setPlaceholderText(tr(source, language))
        source_title = widget.property("i18n_source_title")
        if source_title is None and widget.windowTitle():
            source_title = widget.windowTitle()
            widget.setProperty("i18n_source_title", source_title)
        if source_title is not None:
            widget.setWindowTitle(tr(source_title, language))
