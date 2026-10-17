"""PySide6 desktop interface for the image agent."""
import json
import zipfile
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QComboBox,
    QTextEdit, QVBoxLayout, QWidget, QInputDialog, QProgressBar, QGridLayout,
    QSplitter, QToolButton, QScrollArea,
)

from agent.agent import Agent
from .i18n import tr

STYLE = """QMainWindow,QWidget{background:#f4f5f2;color:#252925;font-size:10pt}
QFrame#glass,QFrame#card,QFrame#header{background:#ffffff;border:1px solid #e3e6e1;border-radius:14px}
QFrame#heroCard{background:#ecefe9;border:1px solid #e0e4dd;border-radius:22px}
QFrame#modeCard{background:#ffffff;border:1px solid #e3e6e1;border-radius:13px}
QFrame#subcard{background:#f8f9f7;border:1px solid #e7e9e5;border-radius:10px}
QLabel{color:#252925;background:transparent}
QLabel#pageTitle{font-size:19pt;font-weight:650;color:#1f2420}
QLabel#sectionTitle{font-size:11pt;font-weight:600;color:#2d332e}
QLabel#muted,QLabel#fieldLabel{color:#747c75}
QLabel#fieldLabel{font-size:9pt;font-weight:550}
QLabel#badge{background:#f3f5f1;border:1px solid #e2e6e0;border-radius:8px;padding:6px 10px;color:#535c55;font-weight:600}
QLineEdit,QTextEdit,QComboBox,QListWidget,QSpinBox,QDoubleSpinBox{background:#ffffff;color:#252925;border:1px solid #dfe3dd;border-radius:8px;padding:8px;selection-background-color:#dbe4dc;selection-color:#202720}
QLineEdit:hover,QTextEdit:hover,QComboBox:hover,QListWidget:hover,QSpinBox:hover,QDoubleSpinBox:hover{border-color:#c4cdc5}
QLineEdit:focus,QTextEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus{border:1px solid #708477}
QComboBox::drop-down{border:0;width:24px}
QComboBox QAbstractItemView{background:#ffffff;color:#252925;border:1px solid #dfe3dd;selection-background-color:#e8eee8}
QPushButton,QToolButton{background:#ffffff;color:#343b35;border:1px solid #dfe3dd;border-radius:8px;padding:8px 13px;font-weight:550}
QPushButton:hover,QToolButton:hover{background:#f4f6f2;border-color:#cbd3cc}
QPushButton:pressed,QToolButton:pressed{background:#e9ede8}
QPushButton:disabled{background:#f2f3f1;color:#a1a8a1;border-color:#e6e8e4}
QPushButton#primary{background:#394b40;color:#ffffff;border-color:#394b40;font-weight:650}
QPushButton#primary:hover{background:#465b4b;border-color:#465b4b}
QPushButton#danger{color:#ffffff;background:#a84943;border-color:#a84943;font-weight:600}
QPushButton#danger:hover{background:#923d38;border-color:#923d38}
QCheckBox{color:#414942;spacing:8px}
QCheckBox::indicator{width:16px;height:16px;border-radius:4px;background:#ffffff;border:1px solid #cbd2cb}
QCheckBox::indicator:checked{background:#506656;border-color:#506656}
QProgressBar{background:#eef0ec;border:1px solid #dfe3dd;border-radius:5px;min-height:8px;max-height:8px;text-align:center}
QProgressBar::chunk{background:#627b68;border-radius:4px}
QScrollBar:vertical{background:#f4f5f2;width:10px;margin:2px}
QScrollBar::handle:vertical{background:#cbd1cb;border-radius:4px;min-height:24px}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
QSlider::groove:horizontal{height:4px;background:#e0e4de;border-radius:2px}
QSlider::handle:horizontal{width:14px;margin:-5px 0;background:#526957;border-radius:7px}
QSplitter::handle{background:#e6e9e4}
QSplitter::handle:hover{background:#bcc8be}"""


class AgentEventBridge(QObject):
    received = Signal(str, object)


class Window(QMainWindow):
    def __init__(self, return_to_menu=None, activity_changed=None):
        super().__init__()
        self.return_to_menu = return_to_menu
        self.activity_changed = activity_changed
        self.root = Path(__file__).resolve().parents[1]
        self.setWindowTitle("Lumo")
        self.resize(1440, 920)
        self.setStyleSheet(STYLE)
        try:
            self.agent = Agent(self.root)
            preset_dir = self.root / self.agent.config["paths"]["presets"]
            self.presets = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in preset_dir.glob("*.json")}
        except Exception as exc:
            QMessageBox.critical(self, "Startup error", f"Could not load the agent configuration or presets:\n{exc}")
            raise
        if not self.presets:
            raise RuntimeError("No presets found in the presets folder.")
        self.event_bridge = AgentEventBridge(self)
        self.event_bridge.received.connect(self._update_from_agent)
        self.model_load_in_progress = False
        self.agent_running = False
        self.agent.on_event(self.handle_agent_event)
        self.build()

    def build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(18, 14, 18, 14); root_layout.setSpacing(10)
        top = QFrame(); top.setObjectName("header")
        top_layout = QHBoxLayout(top); top_layout.setContentsMargins(16, 10, 16, 10); top_layout.setSpacing(10)
        brand = QVBoxLayout(); brand.setSpacing(1)
        title = QLabel("Lumo"); title.setObjectName("pageTitle")
        subtitle = QLabel("Generowanie obrazów"); subtitle.setObjectName("muted")
        brand.addWidget(title); brand.addWidget(subtitle)
        self.status = QLabel("● Gotowy"); self.status.setObjectName("badge")
        self.gen = QLabel(f"Generacje  {self.agent.state.data.get('generation_count', 0)}"); self.gen.setObjectName("badge")
        if self.return_to_menu:
            back = QPushButton("← Tryby")
            back.clicked.connect(self.return_to_menu)
            top_layout.addWidget(back)
        top_layout.addLayout(brand); top_layout.addStretch(1); top_layout.addWidget(self.status); top_layout.addWidget(self.gen)
        root_layout.addWidget(top)
        self.progress_label = QLabel("")
        self.progress_bar = QProgressBar(); self.progress_bar.setTextVisible(False); self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0)
        self.progress_label.hide(); self.progress_bar.hide()
        root_layout.addWidget(self.progress_label); root_layout.addWidget(self.progress_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setChildrenCollapsible(False); splitter.setHandleWidth(7)
        main_panel = QFrame(); main_panel.setObjectName("card")
        main_layout = QVBoxLayout(main_panel); main_layout.setContentsMargins(14, 12, 14, 14); main_layout.setSpacing(10)
        image_title = QLabel("Wynik generowania"); image_title.setObjectName("sectionTitle")
        self.preview = QLabel("Wygenerowany obraz pojawi się tutaj")
        self.preview.setObjectName("subcard"); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setMinimumSize(500, 300)
        self.preview.setStyleSheet("QLabel#subcard{background:#f6f7f4;border:1px solid #e3e6e1;border-radius:10px;color:#8b928b;}")
        main_layout.addWidget(image_title); main_layout.addWidget(self.preview, 1)
        composer = QFrame(); composer.setObjectName("subcard")
        composer_layout = QVBoxLayout(composer); composer_layout.setContentsMargins(10, 8, 10, 8); composer_layout.setSpacing(6)
        composer_layout.addWidget(QLabel("Co chcesz wygenerować?"))
        self.llm_prompt = QTextEdit(); self.llm_prompt.setPlaceholderText("Opisz obraz lub nowy pomysł…"); self.llm_prompt.setMaximumHeight(84)
        composer_layout.addWidget(self.llm_prompt)
        action_row = QHBoxLayout(); action_row.addStretch(1)
        start = QPushButton("Generuj / Start"); start.setObjectName("primary"); start.clicked.connect(self.start_agent)
        stop = QPushButton("Anuluj wszystko"); stop.setObjectName("danger"); stop.clicked.connect(self.cancel_all)
        action_row.addWidget(start); action_row.addWidget(stop); composer_layout.addLayout(action_row)
        main_layout.addWidget(composer)
        splitter.addWidget(main_panel)

        sidebar_scroll = QScrollArea(); sidebar_scroll.setWidgetResizable(True); sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sidebar = QFrame(); sidebar.setObjectName("card")
        form_layout = QVBoxLayout(sidebar); form_layout.setContentsMargins(13, 12, 13, 12); form_layout.setSpacing(10)
        sidebar_title = QLabel("Narzędzia"); sidebar_title.setObjectName("sectionTitle"); form_layout.addWidget(sidebar_title)
        preset_row = QHBoxLayout()
        self.preset = QComboBox()
        self.preset.addItems(sorted(self.presets))
        self.preset.currentTextChanged.connect(self.select_preset)
        add_preset = QPushButton("+ Nowy preset")
        add_preset.clicked.connect(self.create_preset)
        save_preset = QPushButton("Zapisz preset")
        save_preset.clicked.connect(self.save_current_preset)
        preset_row.addWidget(QLabel("Preset")); preset_row.addWidget(self.preset, 1)
        preset_row.addWidget(add_preset); preset_row.addWidget(save_preset); form_layout.addLayout(preset_row)
        model_label = QLabel("Model LLM"); model_label.setObjectName("fieldLabel"); form_layout.addWidget(model_label)
        self.model_combo = QComboBox(); self.model_combo.setEditable(False)
        configured_model = str(self.agent.config["llm"].get("model", "local-model")); self.model_combo.addItem(configured_model)
        self.model_combo.currentTextChanged.connect(self.select_model); form_layout.addWidget(self.model_combo)
        self.refresh_models_button = QPushButton("Odśwież listę modeli"); self.refresh_models_button.clicked.connect(self.refresh_models); form_layout.addWidget(self.refresh_models_button)
        workflow_label = QLabel("Workflow ComfyUI"); workflow_label.setObjectName("fieldLabel"); form_layout.addWidget(workflow_label)
        self.workflow = QLineEdit(); self.workflow.setReadOnly(True)
        choose_workflow = QPushButton("Wybierz workflow…"); choose_workflow.clicked.connect(self.choose_workflow)
        workflow_row = QHBoxLayout(); workflow_row.addWidget(self.workflow, 1); workflow_row.addWidget(choose_workflow); form_layout.addLayout(workflow_row)
        self.continuous = QCheckBox("Tryb ciągły")
        self.continuous.setChecked(bool(self.agent.config["agent"].get("continuous", True)))
        self.send_telegram = QCheckBox("Wysyłaj do Telegrama")
        self.send_telegram.setChecked(bool(self.agent.config.get("telegram", {}).get("send_results", False)))
        form_layout.addWidget(self.continuous); form_layout.addWidget(self.send_telegram)

        self.base = QTextEdit()
        self.style = QTextEdit()
        self.kind = QLineEdit()
        self.reference_prompt = QTextEdit()
        self.instructions = QTextEdit()
        self.base.setMaximumHeight(85)
        self.style.setMaximumHeight(70)
        self.llm_prompt.setMaximumHeight(70)
        self.reference_prompt.setMaximumHeight(70)
        self.instructions.setMaximumHeight(105)
        def field(label, widget):
            container = QWidget(); box = QVBoxLayout(container); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(5)
            caption = QLabel(label); caption.setObjectName("fieldLabel")
            box.addWidget(caption); box.addWidget(widget)
            return container
        self.prompt_details_button = QToolButton(); self.prompt_details_button.setText("Zaawansowane wytyczne promptu"); self.prompt_details_button.setCheckable(True); self.prompt_details_button.setChecked(False); self.prompt_details_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon); self.prompt_details_button.setArrowType(Qt.ArrowType.RightArrow)
        self.prompt_details = QWidget(); prompt_grid = QGridLayout(self.prompt_details); prompt_grid.setContentsMargins(0, 0, 0, 0); prompt_grid.setHorizontalSpacing(8); prompt_grid.setVerticalSpacing(7)
        prompt_grid.addWidget(field("Prompt bazowy", self.base), 0, 0)
        prompt_grid.addWidget(field("Styl", self.style), 1, 0)
        prompt_grid.addWidget(field("Typ", self.kind), 2, 0)
        prompt_grid.addWidget(field("Prompt odniesienia", self.reference_prompt), 3, 0)
        prompt_grid.addWidget(field("Instrukcje", self.instructions), 4, 0)
        self.prompt_details.hide(); self.prompt_details_button.toggled.connect(self._toggle_prompt_details)
        form_layout.addWidget(self.prompt_details_button); form_layout.addWidget(self.prompt_details)
        self.history = QListWidget()
        history_title = QLabel("Historia promptów"); history_title.setObjectName("sectionTitle")
        self.archive_button = QPushButton("Archiwizuj prompty")
        self.archive_button.clicked.connect(self.archive_prompts)
        form_layout.addWidget(history_title); form_layout.addWidget(self.history, 1); form_layout.addWidget(self.archive_button)
        sidebar_scroll.setWidget(sidebar); splitter.addWidget(sidebar_scroll)
        splitter.setStretchFactor(0, 5); splitter.setStretchFactor(1, 2); splitter.setSizes([1000, 390])
        root_layout.addWidget(splitter, 1)
        self.select_preset(self.preset.currentText())

    def _toggle_prompt_details(self, expanded):
        self.prompt_details.setVisible(expanded)
        self.prompt_details_button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def select_preset(self, name):
        preset = self.presets.get(name, {})
        self.base.setPlainText(preset.get("Base", preset.get("base_prompt", "")))
        self.style.setPlainText(preset.get("Style", ""))
        self.kind.setText(preset.get("Type", preset.get("type", "")))
        instructions = preset.get("Instructions", preset.get("instructions", ""))
        self.instructions.setPlainText("\n".join(map(str, instructions)) if isinstance(instructions, list) else str(instructions or ""))
        self.llm_prompt.setPlainText(preset.get("llm_prompt", preset.get("prompt", "Create a completely new image concept.")))
        self.reference_prompt.setPlainText(preset.get("reference_prompt", ""))
        workflow = preset.get("workflow_api", preset.get("workflow", ""))
        self.workflow.setText(str(workflow))

    def choose_workflow(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select ComfyUI API workflow", str(self.root / "workflows"), "JSON files (*.json)")
        if path:
            selected = Path(path).resolve()
            try:
                workflow_ref = str(selected.relative_to(self.root.resolve()))
            except ValueError:
                workflow_ref = str(selected)
            self.workflow.setText(workflow_ref)

    def select_model(self, model):
        model = str(model).strip()
        if not model:
            return
        self.agent.config["llm"]["model"] = model
        self.agent.llm.model = model
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(self.agent.config, ensure_ascii=False, indent=2), encoding="utf-8")

    def refresh_models(self):
        if self.model_load_in_progress or self.agent_running:
            return
        self.model_load_in_progress = True
        self.refresh_models_button.setEnabled(False)
        self.model_combo.setEnabled(False)
        self.status.setText("● Loading available text models…")
        threading.Thread(target=self._refresh_models_worker, name="llm-model-list", daemon=True).start()

    def _refresh_models_worker(self):
        started_here = False
        try:
            if self.agent.llm_server.enabled:
                state = self.agent.llm_server.status()
                if state == "STOPPED":
                    result = self.agent.llm_server.start()
                    started_here = result == "STARTED"
            models = self.agent.llm.list_models()
            if not models:
                raise RuntimeError("The LLM API returned an empty model list.")
            self.handle_agent_event("models_loaded", models)
        except Exception as exc:
            self.handle_agent_event("models_error", str(exc))
        finally:
            if started_here:
                try:
                    self.agent.llm_server.stop()
                except Exception as exc:
                    self.handle_agent_event("models_error", f"Could not stop temporary model server: {exc}")

    def start_agent(self):
        if self.model_load_in_progress:
            QMessageBox.information(self, "Models are loading", "Wait for the model list refresh to finish.")
            return
        selected_model = self.model_combo.currentText().strip()
        if selected_model:
            self.select_model(selected_model)
        name = self.preset.currentText()
        preset = self.presets.get(name, {})
        workflow_ref = self.workflow.text().strip()
        if not workflow_ref:
            QMessageBox.warning(self, "Workflow required", "Choose a ComfyUI API workflow JSON first.")
            return
        preset.update({"name": preset.get("name", name),
                       "base_prompt": self.base.toPlainText().strip(), "style": self.style.toPlainText().strip(),
                       "type": self.kind.text().strip(), "llm_prompt": self.llm_prompt.toPlainText().strip(),
                       "prompt": self.llm_prompt.toPlainText().strip(), "reference_prompt": self.reference_prompt.toPlainText().strip(),
                       "instructions": self.instructions.toPlainText().strip(), "workflow_api": workflow_ref,
                       "Base": self.base.toPlainText().strip(), "Style": self.style.toPlainText().strip(),
                       "Type": self.kind.text().strip(), "Prompt": self.llm_prompt.toPlainText().strip(),
                       "Instructions": self.instructions.toPlainText().strip()})
        if not preset.get("prompt_node_id"):
            QMessageBox.warning(self, "Prompt node required", "Set prompt_node_id in the selected preset JSON to the workflow node that accepts the positive prompt.")
            return
        preset_path = self.root / self.agent.config["paths"]["presets"] / f"{name}.json"
        preset_path.write_text(json.dumps(preset, ensure_ascii=False, indent=2), encoding="utf-8")
        self.presets[name] = preset
        self.agent.config["agent"]["continuous"] = self.continuous.isChecked()
        self.agent.config.setdefault("telegram", {})["send_results"] = self.send_telegram.isChecked()
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(self.agent.config, ensure_ascii=False, indent=2), encoding="utf-8")
        input_path = self.root / "input.json"
        input_data = json.loads(input_path.read_text(encoding="utf-8")) if input_path.exists() else {}
        input_data["preset"] = name
        input_data["prompt"] = self.llm_prompt.toPlainText().strip()
        input_data["llm_prompt"] = self.llm_prompt.toPlainText().strip()
        input_data["continuous"] = self.continuous.isChecked()
        input_path.write_text(json.dumps(input_data, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.activity_changed:
            self.activity_changed(True)
        self.agent.start(name)

    def cancel_all(self):
        self.agent.stop()
        if self.activity_changed:
            self.activity_changed(False)
        if self.agent.llm_server.enabled:
            threading.Thread(target=self.agent.llm_server.stop, daemon=True).start()

    def reload_settings(self):
        self.cancel_all()
        old_agent = self.agent
        try:
            old_agent.telegram.stop()
        except Exception:
            pass
        self.agent = Agent(self.root)
        self.agent.on_event(self.handle_agent_event)
        self.agent_running = False
        self.presets = {p.stem: json.loads(p.read_text(encoding="utf-8"))
                        for p in (self.root / self.agent.config["paths"]["presets"]).glob("*.json")}
        selected = self.preset.currentText()
        self.preset.blockSignals(True)
        self.preset.clear()
        self.preset.addItems(sorted(self.presets))
        self.preset.blockSignals(False)
        if selected in self.presets:
            self.preset.setCurrentText(selected)
        elif self.presets:
            self.preset.setCurrentIndex(0)
        model = str(self.agent.config["llm"].get("model", "local-model"))
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItem(model)
        self.model_combo.blockSignals(False)
        self.continuous.setChecked(bool(self.agent.config["agent"].get("continuous", True)))
        self.send_telegram.setChecked(bool(self.agent.config.get("telegram", {}).get("send_results", False)))
        if self.preset.currentText():
            self.select_preset(self.preset.currentText())

    def _form_preset(self):
        name = self.preset.currentText()
        preset = self.presets.get(name, {})
        preset.update({"name": preset.get("name", name),
                       "base_prompt": self.base.toPlainText().strip(), "style": self.style.toPlainText().strip(),
                       "type": self.kind.text().strip(), "llm_prompt": self.llm_prompt.toPlainText().strip(),
                       "prompt": self.llm_prompt.toPlainText().strip(), "reference_prompt": self.reference_prompt.toPlainText().strip(),
                       "instructions": self.instructions.toPlainText().strip(), "workflow_api": self.workflow.text().strip(),
                       "Base": self.base.toPlainText().strip(), "Style": self.style.toPlainText().strip(),
                       "Type": self.kind.text().strip(), "Prompt": self.llm_prompt.toPlainText().strip(),
                       "Instructions": self.instructions.toPlainText().strip()})
        self.presets[name] = preset
        return preset

    def save_current_preset(self):
        name = self.preset.currentText()
        preset = self._form_preset()
        path = self.root / self.agent.config["paths"]["presets"] / f"{name}.json"
        path.write_text(json.dumps(preset, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status.setText(f"● Saved preset: {name}")

    def create_preset(self):
        name, accepted = QInputDialog.getText(self, "New preset", "Preset name:")
        if not accepted:
            return
        name = name.strip()
        if not name or any(ch in name for ch in '\\/:*?"<>|'):
            QMessageBox.warning(self, "Invalid name", "Use a non-empty name without Windows filename characters.")
            return
        if name in self.presets:
            QMessageBox.warning(self, "Preset exists", "A preset with this name already exists.")
            return
        preset = {"name": name, "base_prompt": "", "style": "", "type": "", "llm_prompt": "Create a completely new image concept.",
                  "instructions": "", "workflow_api": "", "prompt_node_id": "74", "prompt_input_name": "text"}
        self.presets[name] = preset
        preset_path = self.root / self.agent.config["paths"]["presets"] / f"{name}.json"
        preset_path.write_text(json.dumps(preset, ensure_ascii=False, indent=2), encoding="utf-8")
        self.preset.addItem(name)
        self.preset.setCurrentText(name)
        self.base.clear(); self.style.clear(); self.kind.clear(); self.reference_prompt.clear(); self.instructions.clear()
        self.llm_prompt.setPlainText(preset["llm_prompt"])

    def archive_prompts(self):
        prompt_dir = self.root / self.agent.config["paths"]["prompts"]
        prompt_dir.mkdir(parents=True, exist_ok=True)
        files = list(prompt_dir.glob("*.txt"))
        if not files:
            QMessageBox.information(self, "Prompt archive", "There are no saved prompts to archive yet.")
            return
        archive_dir = self.root / "archive"
        archive_dir.mkdir(exist_ok=True)
        archive_path = archive_dir / f"prompts_{datetime.now():%Y%m%d_%H%M%S}.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                archive.write(file, file.name)
        QMessageBox.information(self, "Prompt archive", f"Saved {len(files)} prompts to:\n{archive_path}")

    def handle_agent_event(self, event_name, data):
        """Schedule worker-thread events on Qt's UI thread (QMainWindow.event stays untouched)."""
        self.event_bridge.received.emit(event_name, data)

    def _update_from_agent(self, event_name, data):
        if event_name == "models_loaded":
            selected = self.model_combo.currentText()
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            self.model_combo.addItems(data)
            if selected not in data:
                self.model_combo.addItem(selected)
            self.model_combo.setCurrentText(selected)
            self.model_combo.blockSignals(False)
            self.model_load_in_progress = False
            self.model_combo.setEnabled(not self.agent_running)
            self.refresh_models_button.setEnabled(not self.agent_running)
            self.status.setText(f"● Loaded {len(data)} models")
        elif event_name == "models_error":
            self.model_load_in_progress = False
            self.model_combo.setEnabled(not self.agent_running)
            self.refresh_models_button.setEnabled(not self.agent_running)
            self.status.setText("● Model list error: " + str(data))
        elif event_name == "status":
            message = str(data)
            self.status.setText("● " + message)
            if message == "Agent started":
                self.agent_running = True
                if self.activity_changed:
                    self.activity_changed(True)
                self.model_combo.setEnabled(False)
                self.refresh_models_button.setEnabled(False)
            elif message == "Stopped":
                self.agent_running = False
                if self.activity_changed:
                    self.activity_changed(False)
                self.model_combo.setEnabled(not self.model_load_in_progress)
                self.refresh_models_button.setEnabled(not self.model_load_in_progress)
            if message.startswith("LLM:"):
                self._show_progress(message)
            elif message.startswith("ComfyUI:"):
                self._show_progress(message)
            elif message == "Stopped":
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(0)
                self.progress_label.hide()
                self.progress_bar.hide()
        elif event_name == "variation":
            elapsed = data.get("llm_seconds")
            timing = f" | {elapsed:.1f}s" if elapsed is not None else ""
            reason = data.get("rejection_reason") or "accepted"
            self.status.setText(f"● LLM {reason} | try {data['attempt']}{timing}")
        elif event_name == "queued":
            self.gen.setText(tr(f"Generacje  {data['generation']}", getattr(self, "language", "en")))
        elif event_name == "error":
            self.status.setText("● ERROR: " + str(data))
        elif event_name == "completed":
            self.gen.setText(tr(f"Generacje  {data['generation']}", getattr(self, "language", "en")))
            self.history.insertItem(0, data.get("prompt", ""))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_label.setText(tr("Generowanie zakończone", getattr(self, "language", "en")))
            self.progress_label.show()
            self.progress_bar.show()
            for image_path in data.get("outputs", []):
                self.show_image(image_path)

    def _show_progress(self, message):
        if message.startswith("LLM:"):
            phase = "LLM — tworzenie i sprawdzanie promptu"
            if "variation" in message:
                phase += " (" + message.split("variation", 1)[1].strip() + ")"
            elif "retrying" in message:
                phase = "LLM — ponawianie po błędzie"
            elif "starting" in message:
                phase = "LLM — uruchamianie zdalnego serwera"
            elif "stopping" in message:
                phase = "LLM — zatrzymywanie zdalnego serwera"
        else:
            phase = "ComfyUI — generowanie obrazu"
        self.progress_label.setText(phase)
        self.progress_label.show()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()

    def show_image(self, filename):
        path = Path(filename)
        if path.exists():
            pixmap = QPixmap(str(path))
            self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))
