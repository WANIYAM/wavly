"""
SettingsWindow — PyQt6 GUI for managing gesture bindings and sensitivity.

Fixes:
  - Trainer launches using the same Python interpreter as Wavly
    (so it uses the same venv with sklearn installed)
  - Pause only stops gesture processing — physical mouse is never frozen
  - Camera is released so trainer can access it
"""

import os
import sys
import subprocess
import importlib
import pickle
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QScrollArea, QSlider,
    QMessageBox, QTabWidget, QApplication, QLineEdit,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


BUILTIN_ACTIONS = [
    ("Move cursor",      "cursor_move"),
    ("Left click",       "click"),
    ("Right click",      "right_click"),
    ("Double click",     "double_click"),
    ("Scroll up",        "scroll_up"),
    ("Scroll down",      "scroll_down"),
    ("Start drag",       "drag_start"),
    ("Stop / release",   "stop"),
    ("Zoom in",          "zoom_in"),
    ("Zoom out",         "zoom_out"),
    ("Show keyboard ⌨️", "show_keyboard"),
    ("Custom…",          "__custom__"),
]

GESTURE_ICONS = {
    "cursor_move":  "☝️",
    "click":        "🤌",
    "scroll_up":    "✌️",
    "scroll_down":  "✌️",
    "drag_start":   "✊",
    "stop":         "🖐️",
    "zoom_in":      "🤏",
    "zoom_out":     "🤏",
}

BINDINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "gesture_bindings.py")
MODEL_PATH    = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "models", "gesture_model.pkl")
)
TRAINER_PATH  = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "gestures", "trainer.py")
)

# Always use the same Python that's running Wavly — guarantees correct venv
PYTHON_EXE = sys.executable


def _load_bindings() -> dict:
    try:
        import config.gesture_bindings as gb
        importlib.reload(gb)
        return dict(gb.GESTURE_BINDINGS)
    except Exception:
        return {
            "cursor_move": "cursor_move",
            "click":       "click",
            "scroll_up":   "scroll_up",
            "scroll_down": "scroll_down",
            "drag_start":  "drag_start",
            "stop":        "stop",
        }


def _save_bindings(bindings: dict):
    lines = [
        '"""\nGesture Bindings — managed by Wavly Settings.\n"""\n\n',
        'GESTURE_BINDINGS: dict = {\n',
    ]
    for gesture, action in bindings.items():
        lines.append(f'    {gesture!r}: {action!r},\n')
    lines.append('}\n')
    with open(BINDINGS_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _load_trained_gestures() -> list:
    if os.path.exists(MODEL_PATH):
        try:
            with open(MODEL_PATH, "rb") as f:
                saved = pickle.load(f)
            return list(saved["label_encoder"].classes_)
        except Exception:
            pass
    return list(_load_bindings().keys())


# ── Gesture row ───────────────────────────────────────────────────────────────

class GestureRow(QWidget):

    def __init__(self, gesture: str, action: str, parent=None):
        super().__init__(parent)
        self.gesture = gesture
        self._custom_action = action if action.startswith(("hotkey:", "type:", "run:")) else ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        icon_lbl = QLabel(GESTURE_ICONS.get(gesture, "👋"))
        icon_lbl.setFixedWidth(28)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        name_lbl = QLabel(gesture.replace("_", " ").title())
        name_lbl.setFixedWidth(130)
        name_lbl.setFont(QFont("Segoe UI", 10))

        arrow = QLabel("→")
        arrow.setStyleSheet("color: #888;")
        arrow.setFixedWidth(18)

        self.combo = QComboBox()
        self.combo.setMinimumWidth(160)
        for label, value in BUILTIN_ACTIONS:
            self.combo.addItem(label, value)

        matched = False
        for i, (_, value) in enumerate(BUILTIN_ACTIONS):
            if value == action:
                self.combo.setCurrentIndex(i)
                matched = True
                break
        if not matched:
            self._custom_action = action
            for i, (_, value) in enumerate(BUILTIN_ACTIONS):
                if value == "__custom__":
                    self.combo.setCurrentIndex(i)
                    break

        self.combo.currentIndexChanged.connect(self._on_combo_changed)

        self.custom_input = QLineEdit()
        self.custom_input.setPlaceholderText("e.g. hotkey:ctrl+z  or  run:notepad.exe")
        self.custom_input.setVisible(bool(self._custom_action))
        if self._custom_action:
            self.custom_input.setText(self._custom_action)

        layout.addWidget(icon_lbl)
        layout.addWidget(name_lbl)
        layout.addWidget(arrow)
        layout.addWidget(self.combo, 1)
        layout.addWidget(self.custom_input, 1)

        self.setStyleSheet("""
            GestureRow {
                background: white;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
        """)

    def _on_combo_changed(self):
        self.custom_input.setVisible(self.combo.currentData() == "__custom__")

    def get_action(self) -> str:
        data = self.combo.currentData()
        if data == "__custom__":
            return self.custom_input.text().strip() or "stop"
        return data


# ── Main settings window ──────────────────────────────────────────────────────

class SettingsWindow(QWidget):

    # Injected by WavlyTray so we can pause the camera for training
    camera_thread   = None
    quit_fn         = None
    adaptive_engine = None
    voice_thread    = None   # injected by main.py — Phase 4 Feature 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wavly — Settings")
        self.setMinimumWidth(520)
        self.setWindowFlags(Qt.WindowType.Window)
        self._rows: list = []
        self._poll_timer = None
        self._model_mtime_before = None
        self._build_ui()
        self._load()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background:#fafafa; border-bottom:1px solid #e8e8e8;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 14, 20, 14)
        title = QLabel("Wavly Settings")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Medium))
        hl.addWidget(title)
        hl.addStretch()
        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab { padding:10px 20px; font-size:12px; border:none; color:#888; }
            QTabBar::tab:selected { color:#111; border-bottom:2px solid #111; font-weight:600; }
        """)
        self.tabs.addTab(self._build_gestures_tab(), "Gestures")
        self.tabs.addTab(self._build_sensitivity_tab(), "Sensitivity")

        # Phase 4 — Adaptive tab
        try:
            from ui.adaptive_panel import AdaptivePanel
            self._adaptive_panel = AdaptivePanel(
                adaptive_engine=getattr(SettingsWindow, "adaptive_engine", None)
            )
            self.tabs.addTab(self._adaptive_panel, "Adaptive ✨")
        except Exception as e:
            print(f"[Settings] Adaptive tab unavailable: {e}")

        # Phase 4 Feature 2 — Voice tab
        try:
            from ui.voice_panel import VoicePanel
            self._voice_panel = VoicePanel(
                voice_thread=getattr(SettingsWindow, "voice_thread", None)
            )
            self.tabs.addTab(self._voice_panel, "Voice 🎤")
        except Exception as e:
            print(f"[Settings] Voice tab unavailable: {e}")

        root.addWidget(self.tabs)

        footer = QWidget()
        footer.setStyleSheet("background:#fafafa; border-top:1px solid #e8e8e8;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 12, 20, 12)
        self.status_msg = QLabel("")
        self.status_msg.setStyleSheet("color:#22c55e; font-size:11px;")
        save_btn = QPushButton("Save changes")
        save_btn.setStyleSheet("""
            QPushButton { background:#111; color:white; border:none; border-radius:7px;
                          padding:8px 22px; font-size:12px; font-weight:600; }
            QPushButton:hover { background:#333; }
        """)
        save_btn.clicked.connect(self._save)
        fl.addWidget(self.status_msg)
        fl.addStretch()
        fl.addWidget(save_btn)
        root.addWidget(footer)

    def _build_gestures_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        banner = QFrame()
        banner.setStyleSheet("""
            QFrame { background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; }
        """)
        bl = QHBoxLayout(banner)
        bl.setContentsMargins(12, 10, 12, 10)

        self._banner_txt = QLabel(
            "Want to teach Wavly a new gesture? Record it with your camera."
        )
        self._banner_txt.setStyleSheet(
            "color:#1d4ed8; font-size:11px; border:none; background:transparent;"
        )
        self._banner_txt.setWordWrap(True)

        self._record_btn = QPushButton("+ Record gesture")
        self._record_btn.setStyleSheet("""
            QPushButton { background:transparent; color:#1d4ed8; border:1px solid #93c5fd;
                          border-radius:6px; padding:5px 12px; font-size:11px; }
            QPushButton:hover { background:#dbeafe; }
            QPushButton:disabled { color:#aaa; border-color:#ccc; }
        """)
        self._record_btn.setFixedWidth(140)
        self._record_btn.clicked.connect(self._launch_trainer)

        bl.addWidget(self._banner_txt, 1)
        bl.addWidget(self._record_btn)
        layout.addWidget(banner)

        lbl = QLabel("YOUR GESTURES")
        lbl.setStyleSheet("color:#aaa; font-size:10px; letter-spacing:1px;")
        layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        self._rows_layout.addStretch()

        scroll.setWidget(self._rows_container)
        layout.addWidget(scroll, 1)
        return page

    def _build_sensitivity_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        def make_slider(label, min_v, max_v, value, note):
            box = QVBoxLayout()
            top = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
            val_lbl = QLabel(str(value))
            val_lbl.setStyleSheet("color:#555;")
            top.addWidget(lbl)
            top.addStretch()
            top.addWidget(val_lbl)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(min_v, max_v)
            slider.setValue(value)
            slider.valueChanged.connect(lambda v, l=val_lbl: l.setText(str(v)))
            note_lbl = QLabel(note)
            note_lbl.setStyleSheet("color:#aaa; font-size:10px;")
            box.addLayout(top)
            box.addWidget(slider)
            box.addWidget(note_lbl)
            return box, slider

        hold_box,   self.hold_slider   = make_slider(
            "Gesture hold time", 4, 20, 8,
            "Frames gesture must be held before firing. Higher = fewer accidents.")
        smooth_box, self.smooth_slider = make_slider(
            "Cursor smoothness", 1, 10, 4,
            "Higher = smoother but slightly delayed.")
        scroll_box, self.scroll_slider = make_slider(
            "Scroll speed", 1, 10, 3,
            "Lines scrolled per gesture event.")

        layout.addLayout(hold_box)
        layout.addLayout(smooth_box)
        layout.addLayout(scroll_box)
        layout.addStretch()
        return page

    # ── Data ─────────────────────────────────────────────────────────────

    def _load(self):
        bindings = _load_bindings()
        gestures = _load_trained_gestures()
        for g in gestures:
            if g not in bindings:
                bindings[g] = "stop"

        for row in self._rows:
            row.deleteLater()
        self._rows.clear()

        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for gesture, action in bindings.items():
            row = GestureRow(gesture, action)
            self._rows.append(row)
            self._rows_layout.addWidget(row)

        self._rows_layout.addStretch()

    def _save(self):
        bindings = {row.gesture: row.get_action() for row in self._rows}
        try:
            _save_bindings(bindings)
            self.status_msg.setText("✓ Saved — changes active immediately")
            QTimer.singleShot(3000, lambda: self.status_msg.setText(""))
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    # ── Trainer ───────────────────────────────────────────────────────────

    def _launch_trainer(self):
        reply = QMessageBox.information(
            self,
            "Record new gesture",
            "Wavly will pause gesture control and open the trainer.\n\n"
            "Your physical mouse will work normally during training.\n\n"
            "Steps:\n"
            "  1. The trainer window opens automatically\n"
            "  2. Follow the on-screen prompts\n"
            "  3. Wavly resumes when training completes\n\n"
            "Click OK to start.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return

        # Note the model file time BEFORE training so we can detect when it changes
        self._model_mtime_before = (
            os.path.getmtime(MODEL_PATH) if os.path.exists(MODEL_PATH) else 0
        )

        # Pause Wavly — releases camera, stops gesture actions
        # Physical mouse is unaffected (PyAutoGUI is not involved here)
        if SettingsWindow.camera_thread is not None:
            SettingsWindow.camera_thread.pause()

        self._record_btn.setEnabled(False)
        self._record_btn.setText("Training…")
        self._banner_txt.setText(
            "Trainer is open — follow the prompts in the terminal window."
        )
        self.status_msg.setText("Wavly paused — your mouse works normally")

        # Launch trainer using THE SAME Python/venv as Wavly
        # This guarantees sklearn, mediapipe etc. are all available
        if sys.platform == "win32":
            subprocess.Popen(
                f'start cmd /k "{PYTHON_EXE}" "{TRAINER_PATH}"',
                shell=True,
            )
        else:
            subprocess.Popen(
                ["x-terminal-emulator", "-e", PYTHON_EXE, TRAINER_PATH]
            )

        # Poll every 2s for model file update (signals training finished)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._check_training_done)
        self._poll_timer.start(2000)

    def _check_training_done(self):
        if not os.path.exists(MODEL_PATH):
            return
        new_mtime = os.path.getmtime(MODEL_PATH)
        if new_mtime > self._model_mtime_before:
            self._poll_timer.stop()
            self._on_training_done()

    def _on_training_done(self):
        # Resume Wavly
        if SettingsWindow.camera_thread is not None:
            SettingsWindow.camera_thread.resume()

        self._record_btn.setEnabled(True)
        self._record_btn.setText("+ Record gesture")
        self._banner_txt.setText(
            "Want to teach Wavly a new gesture? Record it with your camera."
        )

        # Reload — new gesture appears in the list
        self._load()

        self.status_msg.setText("✓ New gesture recorded! Assign an action and hit Save.")
        QTimer.singleShot(6000, lambda: self.status_msg.setText(""))


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SettingsWindow()
    win.show()
    sys.exit(app.exec())