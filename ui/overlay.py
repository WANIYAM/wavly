 
"""
WavlyOverlay — Transparent PyQt6 HUD that floats over all windows.
Shows active gesture, confidence, mode, and FPS.
Updates by polling GestureQueue every 100ms via a QTimer.
"""

import time
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QIcon, QPixmap

from core.gesture_queue import GestureQueue
from config.settings import Settings


class WavlyOverlay(QWidget):

    def __init__(self, gesture_queue: GestureQueue, settings: Settings):
        super().__init__()
        self.gesture_queue = gesture_queue
        self.settings = settings

        self._last_gesture = "—"
        self._last_confidence = 0.0
        self._frame_count = 0
        self._fps = 0.0
        self._fps_timer = time.time()
        self._active = True

        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._setup_timer()

    def _setup_window(self):
        """Configure frameless, always-on-top transparent window."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool  # Doesn't appear in taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Position: bottom-right corner
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen.width() - 280, screen.height() - 200, 260, 160)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        # Header row
        header = QHBoxLayout()

        self.title_label = QLabel("◈ WAVLY")
        self.title_label.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #00FF88; letter-spacing: 2px;")

        self.toggle_btn = QPushButton("■")
        self.toggle_btn.setFixedSize(22, 22)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #FF4466;
                border: 1px solid #FF4466;
                font-size: 10px;
                border-radius: 3px;
            }
            QPushButton:hover { background: #FF4466; color: #000; }
        """)
        self.toggle_btn.clicked.connect(self._toggle_active)

        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.toggle_btn)

        # Gesture name
        self.gesture_label = QLabel("IDLE")
        self.gesture_label.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        self.gesture_label.setStyleSheet("color: #FFFFFF;")
        self.gesture_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Confidence bar + value
        conf_row = QHBoxLayout()
        self.conf_bar_label = QLabel()
        self.conf_bar_label.setFont(QFont("Courier New", 8))
        self.conf_bar_label.setStyleSheet("color: #888888;")
        self.conf_value_label = QLabel("0%")
        self.conf_value_label.setFont(QFont("Courier New", 9))
        self.conf_value_label.setStyleSheet("color: #00CCFF;")
        conf_row.addWidget(self.conf_bar_label)
        conf_row.addStretch()
        conf_row.addWidget(self.conf_value_label)

        # Status row
        status_row = QHBoxLayout()
        self.mode_label = QLabel("RULE-BASED")
        self.mode_label.setFont(QFont("Courier New", 8))
        self.mode_label.setStyleSheet("color: #FFAA00;")
        self.fps_label = QLabel("0 fps")
        self.fps_label.setFont(QFont("Courier New", 8))
        self.fps_label.setStyleSheet("color: #666666;")
        status_row.addWidget(self.mode_label)
        status_row.addStretch()
        status_row.addWidget(self.fps_label)

        layout.addLayout(header)
        layout.addWidget(self.gesture_label)
        layout.addLayout(conf_row)
        layout.addLayout(status_row)

    def _setup_tray(self):
        """System tray icon for show/hide/quit."""
        # Create a simple colored square as tray icon
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor("#00FF88"))
        icon = QIcon(pixmap)

        self.tray = QSystemTrayIcon(icon, self)
        tray_menu = QMenu()
        tray_menu.addAction("Show", self.show)
        tray_menu.addAction("Hide", self.hide)
        tray_menu.addSeparator()
        tray_menu.addAction("Quit Wavly", self._quit)
        self.tray.setContextMenu(tray_menu)
        self.tray.setToolTip("Wavly — Gesture Interface")
        self.tray.show()

    def _setup_timer(self):
        """Poll gesture queue every 80ms to update UI."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_ui)
        self.timer.start(80)

    def _update_ui(self):
        event = self.gesture_queue.peek_latest()
        if event is None:
            return

        self._frame_count += 1

        # FPS calculation every second
        now = time.time()
        elapsed = now - self._fps_timer
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_timer = now

        name = event.name if self._active else "PAUSED"
        conf = event.confidence

        # Gesture label with color coding
        color = self._gesture_color(name)
        self.gesture_label.setText(name.upper().replace("_", " "))
        self.gesture_label.setStyleSheet(f"color: {color};")

        # Confidence bar (20 chars)
        bar_filled = int(conf * 20)
        bar = "▓" * bar_filled + "░" * (20 - bar_filled)
        self.conf_bar_label.setText(bar)
        self.conf_value_label.setText(f"{conf * 100:.0f}%")

        self.fps_label.setText(f"{self._fps:.0f} fps")

        # Repaint background
        self.update()

    def _gesture_color(self, name: str) -> str:
        colors = {
            "cursor_move": "#FFFFFF",
            "click":       "#00FF88",
            "double_click":"#00FF88",
            "right_click": "#FFAA00",
            "scroll_up":   "#00CCFF",
            "scroll_down": "#00CCFF",
            "drag_start":  "#FF6600",
            "stop":        "#FF4466",
            "zoom_in":     "#CC88FF",
            "zoom_out":    "#CC88FF",
            "PAUSED":      "#444444",
        }
        return colors.get(name, "#888888")

    def paintEvent(self, event):
        """Draw semi-transparent dark panel background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background panel
        painter.setBrush(QBrush(QColor(10, 10, 15, 210)))
        painter.setPen(QPen(QColor(0, 255, 136, 80), 1))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)

    def mousePressEvent(self, event):
        """Allow dragging the overlay."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def _toggle_active(self):
        self._active = not self._active
        color = "#00FF88" if self._active else "#FF4466"
        symbol = "■" if self._active else "▶"
        self.toggle_btn.setText(symbol)
        self.gesture_queue.clear()

    def _quit(self):
        self.timer.stop()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()