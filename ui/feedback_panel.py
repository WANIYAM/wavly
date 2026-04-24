"""
FeedbackPanel — Phase 4 Step 10: Gesture & Action Activity Log

Shows:
  - Live status (latest gesture + executed action)
  - Scrollable activity log (last 20 events)
  - Color-coded entries: green = success, red = unknown/failed
  - Timestamped history for debugging and user reassurance
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QColor


class FeedbackPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log: list = []   # (timestamp, gesture, action, success)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("Gesture Activity")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))

        self._live_dot = QLabel("●")
        self._live_dot.setStyleSheet("color:#22c55e; font-size:12px;")
        self._live_lbl = QLabel("Waiting for gesture…")
        self._live_lbl.setStyleSheet("color:#666; font-size:11px;")

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._live_dot)
        header.addWidget(self._live_lbl)
        layout.addLayout(header)

        # Live status frame
        self._status_frame = QFrame()
        self._status_frame.setStyleSheet(
            "QFrame { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; }"
        )
        sf = QHBoxLayout(self._status_frame)
        sf.setContentsMargins(12, 10, 12, 10)

        self._status_gesture = QLabel("—")
        self._status_gesture.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self._status_gesture.setStyleSheet("color:#166534;")

        self._status_arrow = QLabel("→")
        self._status_arrow.setStyleSheet("color:#888;")
        self._status_arrow.hide()

        self._status_action = QLabel("—")
        self._status_action.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self._status_action.setStyleSheet("color:#166534;")

        sf.addWidget(self._status_gesture)
        sf.addWidget(self._status_arrow)
        sf.addWidget(self._status_action)
        sf.addStretch()

        layout.addWidget(self._status_frame)

        # Activity log
        log_lbl = QLabel("RECENT ACTIVITY")
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
        self._log_list.setMaximumHeight(280)
        layout.addWidget(self._log_list)

        # Placeholder
        self._placeholder = QLabel("No gestures yet.\nPerform a gesture to see activity here.")
        self._placeholder.setStyleSheet("color:#aaa; font-size:11px;")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._placeholder)

        layout.addStretch()

        # Bottom row
        bottom = QHBoxLayout()
        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet("color:#aaa; font-size:10px;")

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

        bottom.addWidget(self._stats_lbl)
        bottom.addStretch()
        bottom.addWidget(clear_btn)
        layout.addLayout(bottom)

    # ── Public API (called from main thread via QTimer) ───────────────────

    @pyqtSlot(str, float)
    def on_gesture_detected(self, name: str, confidence: float):
        """Called when a gesture passes debounce and is fired."""
        self._live_dot.setStyleSheet("color:#f59e0b; font-size:12px;")
        self._live_lbl.setText("Gesture detected…")

        self._status_frame.setStyleSheet(
            "QFrame { background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; }"
        )
        self._status_gesture.setText(f"{name.upper().replace('_', ' ')}  ({confidence*100:.0f}%)")
        self._status_gesture.setStyleSheet("color:#1d4ed8;")
        self._status_arrow.hide()
        self._status_action.setText("executing…")
        self._status_action.setStyleSheet("color:#f59e0b;")

    @pyqtSlot(str, str, str, bool)
    def on_action_executed(self, source: str, gesture: str, action: str, success: bool):
        """Called when ActionThread finishes executing an action."""
        import time as _time
        ts = _time.strftime("%H:%M:%S")

        # Update live status
        self._live_dot.setStyleSheet("color:#22c55e; font-size:12px;")
        self._live_lbl.setText("Action complete")

        if success:
            self._status_frame.setStyleSheet(
                "QFrame { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; }"
            )
            self._status_gesture.setStyleSheet("color:#166534;")
            self._status_action.setText(action)
            self._status_action.setStyleSheet("color:#166534;")
        else:
            self._status_frame.setStyleSheet(
                "QFrame { background:#fef2f2; border:1px solid #fecaca; border-radius:8px; }"
            )
            self._status_gesture.setStyleSheet("color:#991b1b;")
            self._status_action.setText(action or "failed")
            self._status_action.setStyleSheet("color:#991b1b;")

        self._status_arrow.show()

        # Add to log
        if success:
            text = f"✓  {gesture}  →  {action}"
            color = "#166534"
        else:
            text = f"✗  {gesture}  →  {action or 'unknown / failed'}"
            color = "#991b1b"

        self._log.insert(0, (ts, text, color))
        if len(self._log) > 20:
            self._log.pop()

        self._refresh_log()

        # Auto-reset status after 2 seconds
        QTimer.singleShot(2000, self._reset_status)

    # ── Internals ─────────────────────────────────────────────────────────

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

        total = len(self._log)
        ok = sum(1 for _, _, c in self._log if c == "#166534")
        self._stats_lbl.setText(f"{ok}/{total} successful")

    def _reset_status(self):
        self._live_lbl.setText("Waiting for gesture…")
        self._status_frame.setStyleSheet(
            "QFrame { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; }"
        )
        self._status_gesture.setText("—")
        self._status_gesture.setStyleSheet("color:#166534;")
        self._status_arrow.hide()
        self._status_action.setText("—")
        self._status_action.setStyleSheet("color:#166534;")

    def _clear_log(self):
        self._log.clear()
        self._refresh_log()

