"""Voice enabled, stateful image conversation window."""
import json
import math
import os
import queue
import threading
import time
from collections import deque
from array import array
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget,
    QSplitter, QToolButton, QScrollArea, QSlider, QDoubleSpinBox)

from agent.agent import Agent
from .app import STYLE
from .i18n import tr


class Events(QObject):
    finished = Signal(object)
    failed = Signal(str)
    heard = Signal(str)
    partial = Signal(str)
    agent_update = Signal(str, str)
    listening = Signal()
    cancelled = Signal()


class ConversationWindow(QMainWindow):
    def __init__(self, root, return_to_menu, activity_changed=None):
        super().__init__()
        self.root = Path(root).resolve()
        self.agent = Agent(self.root)
        self.return_to_menu = return_to_menu
        self.activity_changed = activity_changed
        self.events = Events(self)
        self.events.finished.connect(self._finished)
        self.events.failed.connect(self._failed)
        self.events.heard.connect(self._heard)
        self.events.partial.connect(self._partial_transcript)
        self.events.agent_update.connect(self._agent_update)
        self.events.listening.connect(self._listening_ready)
        self.events.cancelled.connect(self._cancelled)
        self.busy = False
        self.llm_started_here = False
        self.last_prompt = ""
        self.turns = []
        self.last_image = ""
        self._speech_finalized = False
        self._speech_model = None
        self._speech_model_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._tts_engine = None
        self._tts_lock = threading.Lock()
        self._tts_cancel_event = threading.Event()
        self.setWindowTitle("Lumo")
        self.resize(1280, 900)
        self.setStyleSheet(STYLE)
        self._build()

    def _build(self):
        root = QWidget(); self.setCentralWidget(root); layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 14, 18, 14); layout.setSpacing(10)
        header = QFrame(); header.setObjectName("header")
        header_layout = QHBoxLayout(header); header_layout.setContentsMargins(16, 9, 16, 9)
        heading = QVBoxLayout(); heading.setSpacing(1)
        title = QLabel("Tryb rozmowy"); title.setObjectName("pageTitle")
        subtitle = QLabel("Opisz obraz albo poproś o zmianę bieżącej sceny"); subtitle.setObjectName("muted")
        heading.addWidget(title); heading.addWidget(subtitle)
        self.status = QLabel("Gotowy"); self.status.setObjectName("badge")
        self.back_button = QPushButton("← Tryby")
        self.back_button.clicked.connect(self.return_to_menu)
        header_layout.addWidget(self.back_button); header_layout.addLayout(heading); header_layout.addStretch(1); header_layout.addWidget(self.status)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setChildrenCollapsible(False); splitter.setHandleWidth(7)
        main_panel = QFrame(); main_panel.setObjectName("card")
        main_layout = QVBoxLayout(main_panel); main_layout.setContentsMargins(14, 12, 14, 14); main_layout.setSpacing(10)
        image_title = QLabel("Wynik obrazu"); image_title.setObjectName("sectionTitle"); main_layout.addWidget(image_title)
        self.preview = QLabel("Wygenerowany obraz pojawi się tutaj"); self.preview.setObjectName("subcard"); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setMinimumSize(500, 360)
        main_layout.addWidget(self.preview, 1)
        composer = QFrame(); composer.setObjectName("subcard")
        composer_layout = QHBoxLayout(composer); composer_layout.setContentsMargins(10, 8, 10, 8); composer_layout.setSpacing(8)
        self.message = QLineEdit(); self.message.setPlaceholderText("Co chcesz stworzyć lub zmienić?…"); self.message.returnPressed.connect(self._send)
        self.send = QPushButton("Wyślij"); self.send.setObjectName("primary"); self.send.clicked.connect(self._send)
        self.talk = QPushButton("🎙 Mów"); self.talk.clicked.connect(self._listen)
        self.reset = QPushButton("Zacznij od początku"); self.reset.clicked.connect(self._reset)
        composer_layout.addWidget(self.message, 1); composer_layout.addWidget(self.send); composer_layout.addWidget(self.talk); composer_layout.addWidget(self.reset)
        main_layout.addWidget(composer); splitter.addWidget(main_panel)

        sidebar_scroll = QScrollArea(); sidebar_scroll.setWidgetResizable(True); sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_panel = QFrame(); side_panel.setObjectName("card")
        side_layout = QVBoxLayout(side_panel); side_layout.setContentsMargins(13, 12, 13, 12); side_layout.setSpacing(9)
        side_title = QLabel("Narzędzia"); side_title.setObjectName("sectionTitle"); side_layout.addWidget(side_title)
        model_row = QHBoxLayout(); model_row.addWidget(QLabel("Model LLM"))
        self.model = QComboBox(); self.model.setEditable(False); self.model.addItem(self.agent.llm.model)
        self.refresh = QPushButton("Odśwież listę"); self.refresh.clicked.connect(self._refresh_models)
        model_row.addWidget(self.model, 1); model_row.addWidget(self.refresh); side_layout.addLayout(model_row)
        self.workflow = QLineEdit(); self.workflow.setPlaceholderText("Workflow API ComfyUI")
        self.workflow_button = QPushButton("Wybierz…"); self.workflow_button.clicked.connect(self._choose_workflow)
        workflow_row = QHBoxLayout(); workflow_row.addWidget(self.workflow, 1); workflow_row.addWidget(self.workflow_button); side_layout.addLayout(workflow_row)

        self.node_options_button = QToolButton(); self.node_options_button.setText("Opcje workflow i img2img"); self.node_options_button.setCheckable(True); self.node_options_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon); self.node_options_button.setArrowType(Qt.ArrowType.RightArrow)
        node_options = QWidget(); node_layout = QVBoxLayout(node_options); node_layout.setContentsMargins(0, 0, 0, 0); node_layout.setSpacing(6)
        node_row = QHBoxLayout(); self.prompt_node = QLineEdit(); self.prompt_node.setPlaceholderText("Auto"); self.prompt_node.setMaximumWidth(90)
        self.image_node = QLineEdit(); self.image_node.setPlaceholderText("Auto"); self.image_node.setMaximumWidth(90)
        self.switch_node = QLineEdit(); self.switch_node.setPlaceholderText("Auto"); self.switch_node.setMaximumWidth(75)
        node_row.addWidget(QLabel("ID promptu")); node_row.addWidget(self.prompt_node); node_row.addWidget(QLabel("ID LoadImage")); node_row.addWidget(self.image_node); node_row.addWidget(QLabel("ID switcha")); node_row.addWidget(self.switch_node); node_layout.addLayout(node_row)
        self.use_img2img = QCheckBox("Używaj poprzedniego obrazu przy edycji (img2img)"); self.use_img2img.setChecked(True); node_layout.addWidget(self.use_img2img)
        resolution_row = QHBoxLayout()
        resolution_row.addWidget(QLabel("Rozdzielczość (MP)"))
        self.megapixels_slider = QSlider(Qt.Orientation.Horizontal); self.megapixels_slider.setRange(1, 1000); self.megapixels_slider.setValue(50)
        self.megapixels_value = QDoubleSpinBox(); self.megapixels_value.setRange(0.01, 10.0); self.megapixels_value.setDecimals(2); self.megapixels_value.setSingleStep(0.01); self.megapixels_value.setValue(0.50); self.megapixels_value.setSuffix(" MP"); self.megapixels_value.setFixedWidth(105)
        self.megapixels_slider.valueChanged.connect(lambda value: self.megapixels_value.setValue(value / 100))
        self.megapixels_value.valueChanged.connect(lambda value: self.megapixels_slider.setValue(round(value * 100)))
        resolution_row.addWidget(self.megapixels_slider, 1); resolution_row.addWidget(self.megapixels_value); node_layout.addLayout(resolution_row)
        node_options.hide(); side_layout.addWidget(self.node_options_button); side_layout.addWidget(node_options)
        self.node_options_button.toggled.connect(lambda expanded: (node_options.setVisible(expanded), self.node_options_button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)))

        state_title = QLabel("PRACA AGENTA"); state_title.setObjectName("fieldLabel"); side_layout.addWidget(state_title)
        self.agent_status = QLabel("Czeka na Twoją wiadomość."); self.agent_status.setWordWrap(True); side_layout.addWidget(self.agent_status)
        speech_title = QLabel("MOWA NA ŻYWO"); speech_title.setObjectName("fieldLabel"); side_layout.addWidget(speech_title)
        self.live_transcript = QTextEdit(); self.live_transcript.setReadOnly(True); self.live_transcript.setPlaceholderText("Rozpoznawany tekst pojawi się tutaj…"); self.live_transcript.setMaximumHeight(82); side_layout.addWidget(self.live_transcript)
        history_title = QLabel("Historia rozmowy"); history_title.setObjectName("fieldLabel"); side_layout.addWidget(history_title)
        self.chat = QTextEdit(); self.chat.setReadOnly(True); self.chat.setPlaceholderText("Tutaj pojawią się wypowiedzi i odpowiedzi."); self.chat.setMaximumHeight(145); side_layout.addWidget(self.chat)
        self.prompt_toggle = QToolButton(); self.prompt_toggle.setText("Prompt Krea2"); self.prompt_toggle.setCheckable(True); self.prompt_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon); self.prompt_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.prompt_preview = QTextEdit(); self.prompt_preview.setReadOnly(True); self.prompt_preview.setPlaceholderText("Gotowy prompt pojawi się tutaj."); self.prompt_preview.setMaximumHeight(170); self.prompt_preview.hide()
        self.prompt_toggle.toggled.connect(lambda expanded: (self.prompt_preview.setVisible(expanded), self.prompt_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)))
        side_layout.addWidget(self.prompt_toggle); side_layout.addWidget(self.prompt_preview); side_layout.addStretch(1)
        sidebar_scroll.setWidget(side_panel); splitter.addWidget(sidebar_scroll)
        splitter.setStretchFactor(0, 5); splitter.setStretchFactor(1, 2); splitter.setSizes([1010, 390])
        layout.addWidget(splitter, 1)
        self._refresh_models()
        threading.Thread(target=self._warm_speech_model, daemon=True).start()

    def _get_speech_model(self):
        if self._speech_model is None:
            from faster_whisper import WhisperModel
            cpu_threads = max(2, min(8, os.cpu_count() or 4))
            self._speech_model = WhisperModel(
                "small", device="cpu", compute_type="int8", cpu_threads=cpu_threads,
                num_workers=1)
        return self._speech_model

    def _warm_speech_model(self):
        try:
            self.events.agent_update.emit(
                "Przygotowuję rozpoznawanie mowy",
                "Ładuję polski model Whisper small. Przy pierwszym uruchomieniu może pobrać model; później będzie działał lokalnie.")
            with self._speech_model_lock:
                self._get_speech_model()
            self.events.agent_update.emit("Rozpoznawanie mowy gotowe", "Mikrofon używa lokalnego modelu Whisper small.")
        except Exception as exc:
            self.events.agent_update.emit("Model mowy niedostępny", str(exc))

    def _transcribe_polish(self, pcm_bytes, partial=False):
        import numpy as np
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return ""
        with self._speech_model_lock:
            model = self._get_speech_model()
            segments, _ = model.transcribe(
                audio, language="pl", task="transcribe", beam_size=1 if partial else 3,
                condition_on_previous_text=False, vad_filter=not partial,
                initial_prompt=("Po polsku. Polecenia do tworzenia i edycji obrazów: "
                                "wygeneruj, zmień, pokaż, modelka, sukienka, złota suknia, "
                                "kolor włosów, tło, zbliżenie."))
            return " ".join(segment.text.strip() for segment in segments).strip()

    def _choose_workflow(self):
        path, _ = QFileDialog.getOpenFileName(self, "Wybierz workflow API ComfyUI", str(self.root / "workflows"), "Pliki JSON (*.json)")
        if path:
            selected = Path(path).resolve()
            try: self.workflow.setText(str(selected.relative_to(self.root)))
            except ValueError: self.workflow.setText(str(selected))
            try:
                workflow_data = json.loads(selected.read_text(encoding="utf-8"))
                selectors = [node for node in workflow_data.values()
                             if node.get("class_type") == "ResolutionSelector"
                             and "megapixels" in node.get("inputs", {})]
                if len(selectors) == 1:
                    value = float(selectors[0]["inputs"]["megapixels"])
                    self.megapixels_value.setValue(min(10.0, max(0.01, value)))
            except (OSError, ValueError, TypeError, KeyError):
                pass

    def _refresh_models(self):
        self.refresh.setEnabled(False)
        self.status.setText(tr("Wczytuję modele…", getattr(self, "language", "en")))
        def work():
            started_here = False
            try:
                if self.agent.llm_server.enabled and self.agent.llm_server.status() == "STOPPED":
                    self.agent.llm_server.start(); started_here = True
                models = self.agent.llm.list_models()
                self.events.heard.emit("\0MODELS\0" + "\n".join(models))
            except Exception as exc: self.events.failed.emit(str(exc))
            finally:
                if started_here:
                    try: self.agent.llm_server.stop()
                    except Exception as exc: self.events.failed.emit(f"Could not stop temporary LLM server: {exc}")
        threading.Thread(target=work, daemon=True).start()

    def _send(self):
        text = self.message.text().strip()
        if not text or self.busy: return
        self.message.clear()
        self._handle_text(text)

    def _handle_text(self, text):
        original_text = text
        self._cancel_event = threading.Event()
        cancel_event = self._cancel_event
        self.agent.stop_event.clear()
        self.turns.append(("user", text))
        self._agent_update("Analizuję polecenie", "Sprawdzam, czy chcesz porozmawiać, utworzyć obraz czy zmienić bieżący.")
        self.busy = True; self.send.setEnabled(False); self.talk.setEnabled(False); self.reset.setEnabled(False); self.status.setText(tr("Przygotowuję odpowiedź…", getattr(self, "language", "en")))
        if self.activity_changed:
            self.activity_changed(True)
        self.agent.config["llm"]["model"] = self.model.currentText().strip()
        self.agent.llm.model = self.model.currentText().strip()
        (self.root / "config.json").write_text(json.dumps(self.agent.config, ensure_ascii=False, indent=2), encoding="utf-8")
        workflow = self.workflow.text().strip()
        prompt_node_id = self.prompt_node.text().strip()
        image_node_id = self.image_node.text().strip()
        switch_node_id = self.switch_node.text().strip()
        megapixels = self.megapixels_value.value()
        use_img2img = self.use_img2img.isChecked()
        def work():
            try:
                if self.agent.llm_server.enabled:
                    state = self.agent.llm_server.status()
                    if state == "STOPPED":
                        self.agent.llm_server.start(); self.llm_started_here = True
                if cancel_event.is_set():
                    raise InterruptedError("Generation cancelled")
                self.events.agent_update.emit("Analizuję rozmowę", "Ustalam, czy odpowiedzieć, wygenerować obraz, czy zacząć nowy.")
                decision = self.agent.llm.converse(self.turns, self.last_prompt)
                if cancel_event.is_set():
                    raise InterruptedError("Generation cancelled")
                corrected = str(decision.get("corrected") or original_text).strip()
                if not corrected:
                    corrected = original_text
                if corrected != original_text:
                    self.turns[-1] = ("user", corrected)
                    correction = json.dumps({"raw": original_text, "corrected": corrected}, ensure_ascii=False)
                    self.events.heard.emit("\0CORRECTION\0" + correction)
                if decision["action"] == "chat":
                    if cancel_event.is_set():
                        raise InterruptedError("Generation cancelled")
                    self.events.agent_update.emit("Odpowiadam", decision["reply"])
                    self.events.finished.emit({"chat": True, "reply": decision["reply"]}); return
                starting_new_image = decision["action"] == "new_image"
                self.events.agent_update.emit("Przygotowuję obraz", "Układam prompt dla Krea2 na podstawie rozmowy." if not starting_new_image else "Rozpoczynam nowy obraz bez kontekstu poprzedniej sceny.")
                if starting_new_image:
                    self.last_prompt = ""; self.last_image = ""
                    self.turns[:] = self.turns[-1:]
                self.events.heard.emit("\0IMAGE\0" + decision["reply"])
                prompt = self.agent.llm.create_krea2_prompt(self.turns, self.last_prompt, starting_new_image)
                if cancel_event.is_set():
                    raise InterruptedError("Generation cancelled")
                self.events.agent_update.emit("Prompt gotowy", prompt)
                init_image = self.last_image if use_img2img else None
                self.events.agent_update.emit("ComfyUI generuje", "Wysyłam wybrany workflow do ComfyUI i czekam na obraz.")
                result = self.agent.generate_conversation_image(
                    workflow, prompt, prompt_node_id, "text", init_image, image_node_id,
                    megapixels=megapixels, switch_node_id=switch_node_id,
                    stop_event=cancel_event)
                self.events.finished.emit(result)
            except InterruptedError:
                self.events.cancelled.emit()
            except Exception as exc:
                if cancel_event.is_set():
                    self.events.cancelled.emit()
                else:
                    self.events.failed.emit(str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _listen(self):
        if self.busy: return
        self._cancel_event = threading.Event()
        cancel_event = self._cancel_event
        self.busy = True; self.send.setEnabled(False); self.talk.setEnabled(False); self.reset.setEnabled(False)
        if self.activity_changed:
            self.activity_changed(True)
        self.status.setText(tr("Uruchamiam mikrofon…", getattr(self, "language", "en")))
        self.live_transcript.setPlainText("Słucham… transkrypcja pojawi się tutaj.")
        def work():
            try:
                import sounddevice as sd
                blocks = queue.Queue()
                def on_audio(indata, frames, timing, status):
                    blocks.put(bytes(indata))
                captured = []
                started = False
                last_voice = time.monotonic()
                last_partial = time.monotonic()
                ambient = []
                calibration_audio = []
                threshold = 450
                # Keep ~1.5 s before the voice trigger so soft initial
                # syllables are not lost while the energy detector catches up.
                preroll = deque(maxlen=24)
                partial_pending = threading.Event()
                self._speech_finalized = False
                def transcribe_partial(snapshot):
                    try:
                        recognized = self._transcribe_polish(snapshot, partial=True)
                        if recognized.strip(): self.events.partial.emit(recognized.strip())
                    except Exception:
                        pass
                    finally:
                        partial_pending.clear()
                with sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=1024, callback=on_audio):
                    if cancel_event.is_set():
                        raise InterruptedError("Listening cancelled")
                    self.events.listening.emit()
                    deadline = time.monotonic() + 25
                    while time.monotonic() < deadline:
                        if cancel_event.is_set():
                            raise InterruptedError("Listening cancelled")
                        try: chunk = blocks.get(timeout=0.3)
                        except queue.Empty: continue
                        samples = array("h"); samples.frombytes(chunk)
                        if not samples: continue
                        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
                        if not started and len(ambient) < 8:
                            ambient.append(rms)
                            calibration_audio.append((chunk, rms))
                            if len(ambient) == 8:
                                quiet_samples = sorted(ambient)[:5]
                                threshold = max(320, (sum(quiet_samples) / len(quiet_samples)) * 2.8)
                                voiced = [index for index, (_, level) in enumerate(calibration_audio)
                                          if level >= threshold]
                                if voiced:
                                    start_index = max(0, voiced[0] - preroll.maxlen)
                                    captured.extend(block for block, _ in calibration_audio[start_index:])
                                    started = True
                                    last_voice = time.monotonic()
                                else:
                                    preroll.extend(block for block, _ in calibration_audio[-preroll.maxlen:])
                            continue
                        if not started:
                            if rms < threshold:
                                preroll.append(chunk)
                                continue
                            started = True
                            captured.extend(preroll)
                            last_voice = time.monotonic()
                        if started:
                            captured.append(chunk)
                            if rms >= threshold:
                                last_voice = time.monotonic()
                            if time.monotonic() - last_partial >= 2.5 and not partial_pending.is_set():
                                partial_pending.set()
                                threading.Thread(target=transcribe_partial, args=(b"".join(captured),), daemon=True).start()
                                last_partial = time.monotonic()
                            if rms < threshold and time.monotonic() - last_voice > 1.2: break
                    if not started:
                        raise RuntimeError("Nie wykryto mowy. Sprawdź mikrofon i spróbuj ponownie.")
                if cancel_event.is_set():
                    raise InterruptedError("Listening cancelled")
                recognized = self._transcribe_polish(b"".join(captured), partial=False)
                if cancel_event.is_set():
                    raise InterruptedError("Listening cancelled")
                if not recognized:
                    raise RuntimeError("Whisper nie rozpoznał wypowiedzi. Spróbuj powiedzieć ją jeszcze raz.")
                self.events.heard.emit(recognized)
            except InterruptedError:
                self.events.cancelled.emit()
            except Exception as exc:
                if cancel_event.is_set():
                    self.events.cancelled.emit()
                else:
                    self.events.failed.emit(f"Speech recognition: {exc}")
        threading.Thread(target=work, daemon=True).start()

    def _listening_ready(self):
        self.status.setText(tr("Mikrofon gotowy — możesz mówić", getattr(self, "language", "en")))

    def cancel_all(self):
        self._cancel_event.set()
        self._tts_cancel_event.set()
        with self._tts_lock:
            if self._tts_engine is not None:
                try:
                    self._tts_engine.stop()
                except Exception:
                    pass
        self.agent.stop()
        if self.activity_changed:
            self.activity_changed(False)
        if self.agent.llm_server.enabled:
            threading.Thread(target=self.agent.llm_server.stop, daemon=True).start()
        self.events.cancelled.emit()

    def _cancelled(self):
        self._speech_finalized = True
        self.busy = False
        self.send.setEnabled(True)
        self.talk.setEnabled(True)
        self.reset.setEnabled(True)
        self.status.setText(tr("Anulowano", getattr(self, "language", "en")))
        self._agent_update("Zadanie anulowane", "Zatrzymano aktywną pracę agenta.")
        if self.activity_changed:
            self.activity_changed(False)

    def reload_settings(self):
        self.cancel_all()
        old_agent = self.agent
        try:
            old_agent.telegram.stop()
        except Exception:
            pass
        self.agent = Agent(self.root)
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItem(self.agent.llm.model)
        self.model.blockSignals(False)
        self.status.setText(tr("Ustawienia zapisane — odśwież listę modeli, aby wczytać zmiany", getattr(self, "language", "en")))

    def _heard(self, text):
        if text.startswith("\0CORRECTION\0"):
            try:
                correction = json.loads(text[len("\0CORRECTION\0"):])
                raw = correction.get("raw", "")
                corrected = correction.get("corrected", "")
                self.live_transcript.setPlainText(f"Rozpoznano: {raw}\n\nPoprawiono: {corrected}")
                self.status.setText(tr("Poprawiono oczywisty błąd rozpoznawania mowy", getattr(self, "language", "en")))
            except (ValueError, TypeError):
                pass
            return
        if text.startswith("\0IMAGE\0"):
            self.chat.append("You: " + self.turns[-1][1]); self.chat.append("Assistant: " + text[len("\0IMAGE\0"):]); return
        if text.startswith("\0MODELS\0"):
            models = text[len("\0MODELS\0"):].splitlines()
            current = self.model.currentText(); self.model.clear(); self.model.addItems(models)
            if current and current not in models: self.model.addItem(current)
            self.model.setCurrentText(current if current else (models[0] if models else ""))
            self.refresh.setEnabled(True)
            if models:
                self.status.setText(tr(f"Wczytano modeli: {len(models)}", getattr(self, "language", "en")))
            else:
                self.status.setText(tr("Serwer nie zwrócił listy modeli", getattr(self, "language", "en")))
            return
        self._speech_finalized = True
        self.live_transcript.setPlainText(text)
        self.busy = False; self.send.setEnabled(True); self.talk.setEnabled(True); self.reset.setEnabled(True)
        self.status.setText(tr("Rozpoznano: ", getattr(self, "language", "en")) + text); self._handle_text(text)

    def _partial_transcript(self, text):
        if not self._speech_finalized:
            self.live_transcript.setPlainText(text + " …")

    def _agent_update(self, title, detail):
        title = tr(title, getattr(self, "language", "en"))
        detail = tr(detail, getattr(self, "language", "en"))
        self.agent_status.setText(f"{title}\n\n{detail}")
        if title == "Prompt gotowy":
            self.prompt_preview.setPlainText(detail)

    def _finished(self, result):
        self.busy = False; self.send.setEnabled(True); self.talk.setEnabled(True); self.reset.setEnabled(True)
        if self.activity_changed:
            self.activity_changed(False)
        if result.get("chat"):
            self.turns.append(("assistant", result["reply"]))
            self.chat.append("You: " + self.turns[-2][1]); self.chat.append("Assistant: " + result["reply"])
            self.status.setText(tr("Gotowy", getattr(self, "language", "en"))); self._agent_update("Odpowiedź gotowa", result["reply"]); self._speak(result["reply"]); return
        self.last_prompt = result["prompt"]
        self.turns.append(("assistant", "Obraz jest gotowy i można go dalej zmieniać."))
        outputs = result.get("outputs", [])
        if outputs:
            self.last_image = outputs[0]
            pixmap = QPixmap(self.last_image)
            if not pixmap.isNull(): self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        answer = "Gotowe, obraz jest przygotowany. Co chcesz zmienić?"
        self.chat.append("Assistant: " + answer); self.status.setText(tr("Generowanie zakończone", getattr(self, "language", "en"))); self._agent_update("Obraz gotowy", answer); self._speak(answer)

    def _failed(self, error):
        self.refresh.setEnabled(True)
        self.busy = False; self.send.setEnabled(True); self.talk.setEnabled(True); self.reset.setEnabled(True)
        if self.activity_changed:
            self.activity_changed(False)
        self.status.setText(tr("Błąd: ", getattr(self, "language", "en")) + error); self._agent_update("Wystąpił błąd", error); self.chat.append(tr("Asystent: Nie udało się wykonać polecenia: ", getattr(self, "language", "en")) + error)

    def _speak(self, text):
        self._tts_cancel_event = threading.Event()
        cancel_event = self._tts_cancel_event
        def work():
            engine = None
            try:
                import pyttsx3
                engine = pyttsx3.init()
                with self._tts_lock:
                    self._tts_engine = engine
                if cancel_event.is_set():
                    engine.stop()
                    return
                polish_voice = next((voice.id for voice in engine.getProperty("voices")
                                     if "pl" in (voice.id + " " + voice.name).lower()
                                     or "polish" in (voice.id + " " + voice.name).lower()), None)
                if polish_voice: engine.setProperty("voice", polish_voice)
                engine.say(text); engine.runAndWait(); engine.stop()
            except Exception: pass
            finally:
                with self._tts_lock:
                    if self._tts_engine is engine:
                        self._tts_engine = None
        threading.Thread(target=work, daemon=True).start()

    def _reset(self):
        self.last_prompt = ""
        self.last_image = ""
        self.turns.clear()
        self.preview.clear()
        self.preview.setText("Wygenerowany obraz pojawi się tutaj")
        self.prompt_preview.clear()
        self.prompt_toggle.setChecked(False)
        self.live_transcript.clear()
        self.chat.clear()
        self.agent.llm._anchor_bags.clear()
        self._speech_finalized = False
        self._agent_update("Nowa rozmowa", "Kontekst LLM i poprzedni obraz zostały wyczyszczone. Czekam na nowe polecenie.")
        self.status.setText(tr("Gotowy — nowa rozmowa", getattr(self, "language", "en")))

    def closeEvent(self, event):
        if self.llm_started_here:
            threading.Thread(target=self.agent.llm_server.stop, daemon=True).start()
        self.return_to_menu(); event.accept()
