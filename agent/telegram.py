import threading
import time
from pathlib import Path

import requests


class TelegramBot:
    def __init__(self, cfg, on_command=None, on_event=None):
        self.cfg = cfg
        self.token = cfg.get("bot_token", "")
        self.chat_id = str(cfg.get("chat_id", ""))
        self.enabled = bool(cfg.get("enabled")) and bool(self.token)
        self.on_command = on_command
        self.on_event = on_event or (lambda *_: None)
        self.stop_event = threading.Event()
        self.offset = 0

    def _url(self, method):
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def send_message(self, text):
        if not self.enabled or not self.chat_id:
            return False
        try:
            response = requests.post(self._url("sendMessage"), data={"chat_id": self.chat_id, "text": text}, timeout=15)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("description", "Telegram sendMessage failed"))
            return True
        except Exception as exc:
            self.on_event("error", f"Telegram: {exc}")
            return False

    def send_photo(self, path, caption=""):
        if not self.enabled or not self.chat_id or not Path(path).is_file():
            return False
        try:
            with open(path, "rb") as photo:
                response = requests.post(self._url("sendPhoto"), data={"chat_id": self.chat_id, "caption": caption[:1024]}, files={"photo": photo}, timeout=60)
            response.raise_for_status()
            return bool(response.json().get("ok"))
        except Exception as exc:
            self.on_event("error", f"Telegram photo: {exc}")
            return False

    def start(self):
        if not self.enabled:
            self.on_event("status", "Telegram disabled: check telegram.enabled and bot token in config.json")
            return
        if not self.chat_id:
            self.on_event("status", "Telegram commands enabled, but chat_id is missing in config.json")
            return
        if self.stop_event.is_set():
            self.stop_event.clear()
        if not any(t.name == "telegram-poll" and t.is_alive() for t in threading.enumerate()):
            threading.Thread(target=self._loop, name="telegram-poll", daemon=True).start()

    def stop(self):
        self.stop_event.set()

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                response = requests.get(self._url("getUpdates"), params={"timeout": 10, "offset": self.offset}, timeout=20)
                response.raise_for_status()
                payload = response.json()
                if not payload.get("ok"):
                    raise RuntimeError(payload.get("description", "Telegram getUpdates failed"))
                for update in payload.get("result", []):
                    self.offset = update["update_id"] + 1
                    message = update.get("message", {})
                    if str(message.get("chat", {}).get("id", "")) == self.chat_id and self.on_command:
                        command = message.get("text", "").strip()
                        if command:
                            self.on_command(command)
            except Exception as exc:
                if not self.stop_event.is_set():
                    self.on_event("error", f"Telegram polling: {exc}")
                    time.sleep(3)
