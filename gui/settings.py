"""Editable application settings without exposing credentials by default."""
import json
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from agent.agent import Agent
from .i18n import tr


class SettingsPage(QWidget):
    saved = Signal(object)
    back = Signal()

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root).resolve()
        self.config = Agent(self.root).config
        self.fields = {}
        self.setObjectName("settingsPage")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 24, 30, 22)
        outer.setSpacing(14)

        header = QHBoxLayout()
        back = QPushButton("← Wróć")
        back.clicked.connect(self.back.emit)
        heading = QVBoxLayout()
        title = QLabel("Ustawienia")
        title.setObjectName("pageTitle")
        note = QLabel("Konfiguracja połączeń i zachowania agenta")
        note.setObjectName("muted")
        heading.addWidget(title)
        heading.addWidget(note)
        header.addWidget(back)
        header.addLayout(heading)
        header.addStretch(1)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        contents = QWidget()
        content_layout = QVBoxLayout(contents)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(self._section("Model językowy", "Adres API, model i parametry generowania.", "llm", [
            ("base_url", "Adres API", "line"), ("api_key", "Klucz API", "secret"),
            ("model", "Model", "line"), ("timeout", "Limit czasu (s)", "int:1:3600"),
            ("temperature", "Temperatura", "float:0:2:0.01"),
            ("top_p", "Top P", "float:0:1:0.01"), ("max_tokens", "Maks. tokenów", "int:64:32000"),
        ]))
        content_layout.addWidget(self._section("ComfyUI", "Serwer i ścieżki wynikowe.", "comfyui", [
            ("base_url", "Adres serwera", "line"), ("poll_interval", "Odstęp odpytywania (s)", "float:0.1:60:0.1"),
            ("timeout", "Limit generowania (s)", "int:10:86400"),
            ("output_directory", "Folder wynikowy", "line"),
        ]))
        content_layout.addWidget(self._section("SSH · zdalny serwer LLM", "Możesz użyć klucza OpenSSH albo hasła. Weryfikacja hosta korzysta z systemowego pliku known_hosts.", "llm_lifecycle", [
            ("enabled", "Zarządzaj serwerem przez SSH", "bool"), ("host", "Adres hosta", "line"),
            ("port", "Port SSH", "int:1:65535"),
            ("user", "Użytkownik", "line"), ("key_path", "Ścieżka klucza SSH", "line"),
            ("password", "Hasło SSH / hasło klucza", "secret"),
            ("start_command", "Komenda start", "line"), ("stop_command", "Komenda stop", "line"),
            ("status_command", "Komenda status", "line"),
            ("start_timeout", "Limit uruchamiania (s)", "int:30:3600"),
            ("stop_timeout", "Limit zatrzymywania (s)", "int:10:900"),
        ]))
        content_layout.addWidget(self._section("Telegram", "Opcjonalne powiadomienia o generacjach.", "telegram", [
            ("enabled", "Włącz Telegram", "bool"), ("bot_token", "Token bota", "secret"),
            ("chat_id", "Chat ID", "line"), ("send_results", "Wysyłaj wyniki", "bool"),
        ]))
        content_layout.addWidget(self._section("Agent i pliki", "Ustawienia pracy oraz lokalizacje danych.", "agent", [
            ("continuous", "Tryb ciągły", "bool"), ("cooldown_seconds", "Przerwa (s)", "int:0:3600"),
            ("max_llm_attempts", "Maks. prób LLM", "int:1:30"), ("save_prompts", "Zapisuj prompty", "bool"),
        ]))
        paths_values = [(key, label, "line") for key, label in [
            ("state", "Plik stanu"), ("prompts", "Folder promptów"),
            ("presets", "Folder presetów"), ("workflows", "Folder workflow"),
        ]]
        content_layout.addWidget(self._section("Ścieżki", "Lokalne pliki i foldery projektu.", "paths", paths_values))
        content_layout.addStretch(1)
        scroll.setWidget(contents)
        outer.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.save_button = QPushButton("Zapisz ustawienia")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self._save)
        actions.addWidget(self.save_button)
        outer.addLayout(actions)

    def reload(self):
        self.config = Agent(self.root).config
        for (section, key), widget in self.fields.items():
            value = self.config.get(section, {}).get(key, "")
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            else:
                widget.setText(str(value))

    def _section(self, title, description, section, specs):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 16)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        description_label = QLabel(description)
        description_label.setObjectName("muted")
        description_label.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(description_label)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(22)
        form.setVerticalSpacing(9)
        values = self.config.setdefault(section, {})
        for key, label, kind in specs:
            value = values.get(key, "")
            if kind == "bool":
                widget = QCheckBox(label)
                widget.setChecked(bool(value))
                form.addRow(widget)
            elif kind == "secret":
                widget = QLineEdit(str(value))
                widget.setEchoMode(QLineEdit.EchoMode.Password)
                widget.setPlaceholderText("Pozostaw puste, jeśli nie używasz")
                reveal = QCheckBox("Pokaż")
                reveal.toggled.connect(lambda checked, field=widget:
                                       field.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
                row = QHBoxLayout()
                row.addWidget(widget, 1)
                row.addWidget(reveal)
                container = QWidget()
                container.setLayout(row)
            elif kind.startswith("int:"):
                _, low, high = kind.split(":")
                widget = QSpinBox()
                widget.setRange(int(low), int(high))
                widget.setValue(int(value))
            elif kind.startswith("float:"):
                _, low, high, step = kind.split(":")
                widget = QDoubleSpinBox()
                widget.setRange(float(low), float(high))
                widget.setSingleStep(float(step))
                widget.setDecimals(2)
                widget.setValue(float(value))
            else:
                widget = QLineEdit(str(value))
            if kind == "bool":
                self.fields[(section, key)] = widget
            elif kind == "secret":
                form.addRow(label, container)
                self.fields[(section, key)] = widget
            else:
                form.addRow(label, widget)
                self.fields[(section, key)] = widget
        layout.addLayout(form)
        return card

    def _save(self):
        try:
            for (section, key), widget in self.fields.items():
                if isinstance(widget, QCheckBox):
                    value = widget.isChecked()
                elif isinstance(widget, QSpinBox):
                    value = widget.value()
                elif isinstance(widget, QDoubleSpinBox):
                    value = widget.value()
                else:
                    value = widget.text().strip()
                self.config[section][key] = value
            config_path = self.root / "config.json"
            temporary = config_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(config_path)
            self.saved.emit(self.config)
            QMessageBox.information(self, tr("Ustawienia zapisane", getattr(self, "language", "en")), tr("Konfiguracja została zapisana.", getattr(self, "language", "en")))
        except Exception as exc:
            QMessageBox.critical(self, tr("Nie udało się zapisać", getattr(self, "language", "en")), str(exc))
