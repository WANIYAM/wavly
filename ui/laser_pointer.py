

"""
LaserPointer — Phase 5: Presentation Mode

A small always-on-top glowing dot that follows the index fingertip.
Looks exactly like a real laser pointer on screen.

Features:
  - Smooth movement via exponential moving average
  - Pulsing glow animation
  - Color: red (default) or green (configurable)
  - Fades out when hand not detected
  - Never steals focus from PowerPoint
"""

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSlot
from PyQt6.QtGui import QPainter, QColor, QRadialGradient


DOT_SIZE     = 40    # outer glow diameter px
CORE_SIZE    = 10    # bright core diameter px
SMOOTH_ALPHA = 0.25  # EMA smoothing (lower = smoother)
FADE_MS      = 800   # ms before dot fades when hand lost


class LaserPointer(QWidget):

    def __init__(self, color: str = "red", parent=None):
        super().__init__(parent)
        self._color   = color
        self._x       = 0.0
        self._y       = 0.0
        self._visible_hand = False
        self._opacity      = 0.0
        self._pulse        = 0.0
        self._pulse_dir    = 1

        self._setup_window()

        # Pulse animation — 30fps
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick)
        self._pulse_timer.start(33)

        # Fade timer — starts when hand lost
        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._start_fade)
        self._fading = False

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint  |
            Qt.WindowType.Tool                  |
            Qt.WindowType.WindowTransparentForInput  # clicks pass through!
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(DOT_SIZE, DOT_SIZE)

    # ── Position update ───────────────────────────────────────────────────

    @pyqtSlot(float, float)
    def move_to(self, screen_x: float, screen_y: float):
        """Called from camera thread via invokeMethod — smooth EMA movement."""
        if not self._visible_hand:
            # First detection — jump to position
            self._x = screen_x
            self._y = screen_y
            self._visible_hand = True
            self._fading = False
            self._opacity = 1.0
            self._fade_timer.stop()
        else:
            # Smooth movement
            self._x = SMOOTH_ALPHA * screen_x + (1 - SMOOTH_ALPHA) * self._x
            self._y = SMOOTH_ALPHA * screen_y + (1 - SMOOTH_ALPHA) * self._y

        # Position window centred on fingertip
        self.move(int(self._x) - DOT_SIZE // 2,
                  int(self._y) - DOT_SIZE // 2)
        self.update()

    @pyqtSlot()
    def hand_lost(self):
        """Called when hand goes out of frame — start fade timer."""
        self._visible_hand = False
        self._fade_timer.stop()
        self._fade_timer.start(FADE_MS)

    def _start_fade(self):
        self._fading = True

    # ── Animation tick ────────────────────────────────────────────────────

    def _tick(self):
        # Pulse
        self._pulse += 0.08 * self._pulse_dir
        if self._pulse >= 1.0:
            self._pulse_dir = -1
        elif self._pulse <= 0.0:
            self._pulse_dir = 1

        # Fade out when hand lost
        if self._fading and self._opacity > 0:
            self._opacity = max(0.0, self._opacity - 0.05)
            if self._opacity == 0:
                self._fading = False

        self.update()

    # ── Drawing ───────────────────────────────────────────────────────────

    def paintEvent(self, event):
        if self._opacity <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)

        cx = DOT_SIZE / 2
        cy = DOT_SIZE / 2

        # Outer glow — pulsing
        glow_r  = (DOT_SIZE / 2) * (0.7 + 0.3 * self._pulse)
        gradient = QRadialGradient(cx, cy, glow_r)

        if self._color == "red":
            core_color  = QColor(255, 50,  50,  220)
            glow_color  = QColor(255, 0,   0,   80)
            outer_color = QColor(255, 0,   0,   0)
        else:  # green
            core_color  = QColor(50,  255, 50,  220)
            glow_color  = QColor(0,   255, 0,   80)
            outer_color = QColor(0,   255, 0,   0)

        gradient.setColorAt(0.0, core_color)
        gradient.setColorAt(0.3, glow_color)
        gradient.setColorAt(1.0, outer_color)

        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(cx - glow_r), int(cy - glow_r),
                            int(glow_r * 2),  int(glow_r * 2))

        # Bright core
        core_r = CORE_SIZE / 2
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawEllipse(int(cx - core_r), int(cy - core_r),
                            CORE_SIZE, CORE_SIZE)

        painter.end()

    # ── Visibility ────────────────────────────────────────────────────────

    def show_pointer(self):
        self._opacity = 1.0
        self._fading  = False
        self.show()

    def hide_pointer(self):
        self._opacity = 0.0
        self.hide()