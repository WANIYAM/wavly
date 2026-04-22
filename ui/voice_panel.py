"""
VoicePanel — Settings tab for Voice + Gesture Hybrid (Phase 4 Feature 2)

Shows:
  - Enable / Disable toggle
  - Current status (listening / recording / idle)
  - Last heard transcript + matched action
  - Link to edit voice_bindings.py
  - Language indicator (English + Urdu)
  - Live activity log (last 10 commands)
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QCheckBox, QScrollArea,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QColor


class VoicePanel(QWidget):

    def __init__(self, voice_thread=None, parent=None):
        super().__init__(parent)
        self._voice_thread  = voice_thread
        self._log: list     = []   # (transcript, action, timestamp)
        self._status        = "idle"
        self._build_ui()

    def set_voice_thread(self, vt):
        self._voice_thread = vt

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("Voice Commands")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))

        self._enable_check = QCheckBox("Enabled")
        self._enable_check.setChecked(True)
        self._enable_check.toggled.connect(self._toggle_enabled)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._enable_check)
        layout.addLayout(header)

        # Status indicator
        self._status_frame = QFrame()
        self._status_frame.setStyleSheet(
            "QFrame { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; }"
        )
        sl = QHBoxLayout(self._status_frame)
        sl.setContentsMargins(12, 10, 12, 10)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color:#22c55e; font-size:14px;")
        self._status_lbl = QLabel("Say 'Hey Wavly' to start a command")
        self._status_lbl.setStyleSheet("color:#166534; font-size:11px;")

        sl.addWidget(self._status_dot)
        sl.addWidget(self._status_lbl)
        sl.addStretch()

        # Language badges
        for lang, color in [("EN", "#3b82f6"), ("اردو", "#8b5cf6")]:
            badge = QLabel(lang)
            badge.setStyleSheet(f"""
                QLabel {{
                    background:{color}; color:white;
                    border-radius:4px; padding:2px 6px;
                    font-size:10px; font-weight:600;
                }}
            """)
            sl.addWidget(badge)

        layout.addWidget(self._status_frame)

        # Wake word info
        info = QLabel(
            "🎤  Wake word: 'Hey Wavly'  →  speak your command  →  action fires\n"
            "Supports English and Urdu commands. Edit config/voice_bindings.py to customise."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#666; font-size:11px;")
        layout.addWidget(info)

        # Activity log
        log_lbl = QLabel("RECENT COMMANDS")
        log_lbl.setStyleSheet("color:#aaa; font-size:10px; letter-spacing:1px;")
        layout.addWidget(log_lbl)

        self._log_list = QListWidget()
        self._log_list.setStyleSheet("""
            QListWidget {
                background: #fafafa;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
                font-size: 11px;
            }
            QListWidget::item { padding: 6px 10px; border-bottom: 1px solid #f0f0f0; }
            QListWidget::item:selected { background: #eff6ff; color: #1d4ed8; }
        """)
        self._log_list.setMaximumHeight(180)
        layout.addWidget(self._log_list)

        # Placeholder
        self._placeholder = QLabel("No commands yet.\nSay 'Hey Wavly' followed by a command.")
        self._placeholder.setStyleSheet("color:#aaa; font-size:11px;")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._placeholder)

        layout.addStretch()

        # Bottom row
        bottom = QHBoxLayout()
        self._last_lbl = QLabel("")
        self._last_lbl.setStyleSheet("color:#aaa; font-size:10px;")

        clear_btn = QPushButton("Clear log")
        clear_btn.setStyleSheet("""
            QPushButton {
                background:transparent; color:#888;
                border:1px solid #e8e8e8; border-radius:6px;
                padding:5px 12px; font-size:11px;
            }
            QPushButton:hover { background:#f5f5f5; }
        """)
        clear_btn.clicked.connect(self._clear_log)

        bottom.addWidget(self._last_lbl)
        bottom.addStretch()
        bottom.addWidget(clear_btn)
        layout.addLayout(bottom)

    # ── Status updates (called from VoiceThread via QTimer) ───────────────

    @pyqtSlot()
    def on_listening(self):
        """Wake word detected — now recording."""
        self._status = "listening"
        self._status_frame.setStyleSheet(
            "QFrame { background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; }"
        )
        self._status_dot.setStyleSheet("color:#3b82f6; font-size:14px;")
        self._status_lbl.setText("🎤  Listening... speak your command now")
        self._status_lbl.setStyleSheet("color:#1d4ed8; font-size:11px;")

        # Auto-reset after 5 seconds
        QTimer.singleShot(5000, self._reset_status)

    @pyqtSlot()
    def on_heard(self):
        """Recording finished — processing."""
        self._status_dot.setStyleSheet("color:#f59e0b; font-size:14px;")
        self._status_lbl.setText("⚙  Processing...")
        self._status_lbl.setStyleSheet("color:#92400e; font-size:11px;")

    @pyqtSlot(str, object)
    def on_result(self, transcript: str, action):
        """Transcript + matched action received."""
        import time as _time
        ts = _time.strftime("%H:%M:%S")

        if action:
            text = f"✓  '{transcript}'  →  {action}"
            color = "#166534"
        else:
            text = f"?  '{transcript}'  →  no match"
            color = "#92400e"

        self._log.insert(0, (ts, text, color))
        if len(self._log) > 20:
            self._log.pop()

        self._refresh_log()
        self._reset_status()

    def _refresh_log(self):
        self._log_list.clear()
        if not self._log:
            self._placeholder.show()
            self._log_list.hide()
            return

        self._placeholder.hide()
        self._log_list.show()

        for ts, text, color in self._log:
            item = QListWidgetItem(f"[{ts}]  {text}")
            item.setForeground(QColor(color))
            self._log_list.addItem(item)

        self._last_lbl.setText(
            f"Last command: {self._log[0][1][:50]}" if self._log else ""
        )

    def _reset_status(self):
        self._status = "idle"
        self._status_frame.setStyleSheet(
            "QFrame { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; }"
        )
        self._status_dot.setStyleSheet("color:#22c55e; font-size:14px;")
        self._status_lbl.setText("Say 'Hey Wavly' to start a command")
        self._status_lbl.setStyleSheet("color:#166534; font-size:11px;")

    def _clear_log(self):
        self._log.clear()
        self._refresh_log()

    def _toggle_enabled(self, checked: bool):
        if self._voice_thread:
            self._voice_thread.set_enabled(checked)
        if checked:
            self._reset_status()
        else:
            self._status_dot.setStyleSheet("color:#aaa; font-size:14px;")
            self._status_lbl.setText("Voice commands disabled")
            self._status_lbl.setStyleSheet("color:#888; font-size:11px;")
            self._status_frame.setStyleSheet(
                "QFrame { background:#f5f5f5; border:1px solid #e8e8e8; border-radius:8px; }"
            )