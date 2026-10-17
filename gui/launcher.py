"""Polished single-window launcher and application navigation."""
from pathlib import Path
import json

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget, QComboBox, QLabel,
)

from .app import STYLE, Window
from .conversation import ConversationWindow
from .settings import SettingsPage
from .visuals import AgentAvatar
from .i18n import apply_language, tr


class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.root = Path(__file__).resolve().parents[1]
        self.language = self._load_language()
        self.setWindowTitle("Lumo")
        self.resize(1440, 920)
        self.setMinimumSize(980, 680)
        self.setStyleSheet(STYLE)
        self._fade = None
        self._active = False

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(22, 16, 22, 18)
        shell_layout.setSpacing(14)
        topbar = QFrame()
        topbar.setObjectName("header")
        top = QHBoxLayout(topbar)
        top.setContentsMargins(14, 8, 12, 8)
        self.header_avatar = AgentAvatar(38)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        name = QLabel("Lumo")
        name.setStyleSheet("font-weight:650;font-size:11pt")
        caption = QLabel("LOCAL IMAGE STUDIO")
        caption.setObjectName("muted")
        caption.setStyleSheet("font-size:8pt;letter-spacing:1px")
        brand.addWidget(name)
        brand.addWidget(caption)
        self.global_status = QLabel("Gotowy")
        self.global_status.setObjectName("badge")
        self.settings_button = QPushButton("⚙  Ustawienia")
        self.settings_button.clicked.connect(self.open_settings)
        self.cancel_button = QPushButton("Anuluj wszystko")
        self.cancel_button.setObjectName("danger")
        self.cancel_button.setToolTip("Zatrzymaj mikrofon, generowanie, żądania i zdalny serwer LLM")
        self.cancel_button.clicked.connect(self.cancel_all)
        top.addWidget(self.header_avatar)
        top.addLayout(brand)
        top.addStretch(1)
        top.addWidget(self.global_status)
        top.addWidget(self.settings_button)
        top.addWidget(self.cancel_button)
        shell_layout.addWidget(topbar)

        self.stack = QStackedWidget()
        self.stack.currentChanged.connect(self._animate_current)
        shell_layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.menu_page, self.menu_avatar = self._make_menu()
        self.stack.addWidget(self.menu_page)
        self.settings_page = SettingsPage(self.root)
        self.settings_page.back.connect(self.show_menu)
        self.settings_page.saved.connect(self._settings_saved)
        self.stack.addWidget(self.settings_page)

        self.auto_screen = None
        self.conversation_screen = None
        self.stack.setCurrentWidget(self.menu_page)
        self._apply_language()

    def _load_language(self):
        try:
            config = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
            return "pl" if config.get("ui", {}).get("language") == "pl" else "en"
        except (OSError, ValueError, TypeError):
            return "en"

    def _save_language(self):
        path = self.root / "config.json"
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            config = {}
        config.setdefault("ui", {})["language"] = self.language
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _apply_language(self):
        apply_language(self, self.language)
        if self.settings_page:
            apply_language(self.settings_page, self.language)
        if self.auto_screen:
            apply_language(self.auto_screen, self.language)
        if self.conversation_screen:
            apply_language(self.conversation_screen, self.language)
        self.global_status.setText(tr("Agent pracuje" if self._active else "Gotowy", self.language))

    def _language_changed(self, index):
        self.language = "pl" if index == 1 else "en"
        self._save_language()
        self._apply_language()

    def _make_menu(self):
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(38, 26, 38, 34)
        outer.setSpacing(26)

        left = QVBoxLayout()
        left.setSpacing(16)
        language_row = QHBoxLayout()
        language_label = QLabel("Język")
        language_label.setObjectName("muted")
        self.language_picker = QComboBox()
        self.language_picker.addItems(["English", "Polski"])
        self.language_picker.setCurrentIndex(1 if self.language == "pl" else 0)
        self.language_picker.setFixedWidth(140)
        self.language_picker.currentIndexChanged.connect(self._language_changed)
        language_row.addWidget(language_label)
        language_row.addWidget(self.language_picker)
        language_row.addStretch(1)
        left.addLayout(language_row)
        eyebrow = QLabel("TWOJE STUDIO OBRAZU")
        eyebrow.setObjectName("muted")
        eyebrow.setStyleSheet("font-size:9pt;font-weight:650;letter-spacing:1.5px")
        title = QLabel("Od pomysłu\ndo obrazu.")
        title.setObjectName("pageTitle")
        title.setStyleSheet("font-size:34pt;line-height:1.1")
        subtitle = QLabel("Wybierz sposób pracy. Możesz tworzyć bezpośrednio albo prowadzić z agentem rozmowę, która rozwija obraz krok po kroku.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        subtitle.setMaximumWidth(570)
        left.addWidget(eyebrow)
        left.addWidget(title)
        left.addWidget(subtitle)
        left.addSpacing(14)

        auto_card, auto_button = self._mode_card(
            "01", "Auto generate", "Pełny panel generowania i ustawień workflow.", "Otwórz generator  →", True)
        conversation_card, conversation_button = self._mode_card(
            "02", "Tryb rozmowy", "Rozmawiaj, poprawiaj obraz i zachowuj kontekst sesji.", "Rozpocznij rozmowę  →", False)
        auto_button.clicked.connect(self._open_auto)
        conversation_button.clicked.connect(self._open_conversation)
        left.addWidget(auto_card)
        left.addWidget(conversation_card)
        left.addStretch(1)
        footer = QLabel("Workflow ComfyUI  ·  lokalny podgląd  ·  konfigurowalne połączenia")
        footer.setObjectName("muted")
        left.addWidget(footer)

        hero = QFrame()
        hero.setObjectName("heroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 32, 28, 28)
        hero_layout.setSpacing(12)
        hero_layout.addStretch(1)
        avatar = AgentAvatar(220)
        orb_row = QHBoxLayout()
        orb_row.addStretch(1)
        orb_row.addWidget(avatar)
        orb_row.addStretch(1)
        hero_layout.addLayout(orb_row)
        assistant = QLabel("Twój asystent kreatywny")
        assistant.setObjectName("sectionTitle")
        assistant.setAlignment(Qt.AlignmentFlag.AlignCenter)
        line = QLabel("Opisz, co chcesz zobaczyć. Agent przygotuje prompt, wygeneruje obraz i pomoże wprowadzić kolejne zmiany.")
        line.setObjectName("muted")
        line.setWordWrap(True)
        line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(assistant)
        hero_layout.addWidget(line)
        hero_layout.addStretch(1)

        outer.addLayout(left, 6)
        outer.addWidget(hero, 4)
        return page, avatar

    def _mode_card(self, number, title, description, action, primary):
        card = QFrame()
        card.setObjectName("modeCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 17, 20, 17)
        layout.setSpacing(7)
        number_label = QLabel(number)
        number_label.setObjectName("muted")
        number_label.setStyleSheet("font-size:9pt;font-weight:650")
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        heading.setStyleSheet("font-size:14pt;font-weight:650")
        detail = QLabel(description)
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        button = QPushButton(action)
        if primary:
            button.setObjectName("primary")
        button.setMinimumHeight(38)
        layout.addWidget(number_label)
        layout.addWidget(heading)
        layout.addWidget(detail)
        layout.addSpacing(2)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        return card, button

    def _embed(self, screen):
        screen.setParent(self.stack)
        screen.setWindowFlags(Qt.WindowType.Widget)
        self.stack.addWidget(screen)

    def _animate_current(self, index):
        page = self.stack.widget(index)
        if page is None:
            return
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        self._fade = QPropertyAnimation(effect, b"opacity", self)
        self._fade.setDuration(190)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.start()

    def show_menu(self):
        self.stack.setCurrentWidget(self.menu_page)

    def open_settings(self):
        if self.stack.currentWidget() is not self.settings_page:
            self.settings_page.reload()
        self.stack.setCurrentWidget(self.settings_page)

    def _open_auto(self):
        if self.auto_screen is None:
            self.auto_screen = Window(self.show_menu, self._set_activity)
            self._embed(self.auto_screen)
            apply_language(self.auto_screen, self.language)
        self.stack.setCurrentWidget(self.auto_screen)

    def _open_conversation(self):
        if self.conversation_screen is None:
            self.conversation_screen = ConversationWindow(self.root, self.show_menu, self._set_activity)
            self._embed(self.conversation_screen)
            apply_language(self.conversation_screen, self.language)
        self.stack.setCurrentWidget(self.conversation_screen)

    def _set_activity(self, active):
        self._active = bool(active)
        self.header_avatar.set_working(self._active)
        self.menu_avatar.set_working(self._active)
        self.global_status.setText(tr("Agent pracuje" if self._active else "Gotowy", self.language))

    def cancel_all(self):
        active = self._active
        if self.conversation_screen is not None:
            self.conversation_screen.cancel_all()
        if self.auto_screen is not None:
            self.auto_screen.cancel_all()
        if not active:
            self.global_status.setText(tr("Brak aktywnego zadania", self.language))

    def _settings_saved(self, config):
        if self.auto_screen is not None:
            self.auto_screen.reload_settings()
        if self.conversation_screen is not None:
            self.conversation_screen.reload_settings()
        self.global_status.setText(tr("Ustawienia zapisane", self.language))
