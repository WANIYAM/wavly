"""
OnScreenKeyboard — Two-hand floating keyboard.

HOVER FIX — three root causes fixed:

1. QTimer.singleShot flood: main.py was creating a new QTimer every camera
   frame (30/sec). Most fired late or out of order. Replaced with a proper
   Qt slot decorated with @pyqtSlot so the camera thread can invoke it
   directly and safely via QMetaObject.invokeMethod with QueuedConnection.

2. Wrong coordinate space: tip.x * screen_w mapped the fingertip to where
   the CURSOR would go (top of screen = top of monitor). But the keyboard
   sits at the BOTTOM. The finger needs to point at the actual keyboard
   pixel position. Fixed by passing raw normalised coords (0-1) and letting
   the keyboard convert them to its own widget space.

3. mapToGlobal timing: buttons sometimes returned wrong global coords before
   the window had fully rendered. Fixed by caching button rects after the
   window shows, and refreshing the cache on move/resize.
"""

import pyautogui
import pyperclip
import time

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout,
    QHBoxLayout, QLabel, QSizePolicy, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QRect, QPoint, QTimer
from PyQt6.QtGui import QFont


ROWS_NORMAL = [
    ["`","1","2","3","4","5","6","7","8","9","0","-","=","⌫"],
    ["q","w","e","r","t","y","u","i","o","p","[","]","\\"],
    ["⇪","a","s","d","f","g","h","j","k","l",";","'","↵"],
    ["⇧","z","x","c","v","b","n","m",",",".","/","⇧"],
    ["SPACE"],
]

ROWS_SHIFT = [
    ["~","!","@","#","$","%","^","&","*","(",")","_","+","⌫"],
    ["Q","W","E","R","T","Y","U","I","O","P","{","}","|"],
    ["⇪","A","S","D","F","G","H","J","K","L",":","\"","↵"],
    ["⇧","Z","X","C","V","B","N","M","<",">","?","⇧"],
    ["SPACE"],
]

WIDE_KEYS    = {"⌫":1.5, "⇪":1.5, "↵":1.8, "⇧":2.0, "SPACE":10}
SPECIAL_KEYS = {"⌫", "⇪", "↵", "⇧", "SPACE"}

PINCH_THRESHOLD = 0.18
PINCH_DEBOUNCE  = 6


def _type_char(char: str):
    """Type via clipboard paste — works for all unicode/symbols."""
    try:
        prev = pyperclip.paste()
    except Exception:
        prev = ""
    try:
        pyperclip.copy(char)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.02)
    except Exception:
        try:
            pyautogui.typewrite(char, interval=0)
        except Exception:
            pass
    try:
        pyperclip.copy(prev)
    except Exception:
        pass


class KeyButton(QPushButton):

    def __init__(self, label: str, parent=None):
        super().__init__("" if label == "SPACE" else label, parent)
        self.key_label  = label
        self._hov_l     = False
        self._hov_r     = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(44)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._style()

    def set_hover(self, left: bool, right: bool):
        if left != self._hov_l or right != self._hov_r:
            self._hov_l = left
            self._hov_r = right
            self._style()

    def _style(self):
        special = self.key_label in SPECIAL_KEYS
        if self._hov_l and self._hov_r:
            bg, border, fw = "#7c3aed", "1px solid rgba(255,255,255,0.5)", "700"
        elif self._hov_l:
            bg, border, fw = "#2563eb", "1px solid rgba(255,255,255,0.4)", "600"
        elif self._hov_r:
            bg, border, fw = "#16a34a", "1px solid rgba(255,255,255,0.4)", "600"
        elif special:
            bg, border, fw = "rgba(255,255,255,0.06)", "none", "400"
        else:
            bg, border, fw = "rgba(255,255,255,0.11)", "none", "400"

        self.setStyleSheet(f"""
            QPushButton {{
                background:{bg}; color:rgba(255,255,255,0.92);
                border:{border}; border-radius:7px;
                font-size:13px; font-family:'Segoe UI'; font-weight:{fw};
            }}
            QPushButton:pressed {{ background:rgba(255,255,255,0.30); }}
        """)


class OnScreenKeyboard(QWidget):

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shift = False
        self._caps  = False
        self._flat_buttons: list[KeyButton] = []

        # Cached button screen rects — rebuilt after show/resize
        self._btn_rects: list[tuple[QRect, KeyButton]] = []
        self._rects_dirty = True

        # Pinch state
        self._lframes = 0;  self._lfired = False
        self._rframes = 0;  self._rfired = False

        self._lhov: KeyButton | None = None
        self._rhov: KeyButton | None = None

        # Debug: show fingertip positions as dots
        self._debug_l: tuple | None = None
        self._debug_r: tuple | None = None

        self._setup_window()
        self._build_ui()
        self._position_bottom()

    def _setup_window(self):
        self.setWindowTitle("Wavly Keyboard")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint  |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._root = QWidget()
        self._root.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._root.setStyleSheet("""
            QWidget {
                background:rgba(18,18,20,240);
                border-radius:14px;
                border:1px solid rgba(255,255,255,0.08);
            }
        """)
        outer.addWidget(self._root)

        vbox = QVBoxLayout(self._root)
        vbox.setContentsMargins(12, 10, 12, 12)
        vbox.setSpacing(6)

        # Title bar
        tr = QHBoxLayout()
        for color, text in [("#3b82f6","● Left hand"), ("#22c55e","● Right hand")]:
            l = QLabel(text)
            l.setStyleSheet(f"color:{color};font-size:11px;background:transparent;border:none;")
            tr.addWidget(l)
        tr.addStretch()
        hint = QLabel("⌨️  Hover finger over key, then pinch  |  or click with mouse")
        hint.setStyleSheet("color:rgba(255,255,255,0.35);font-size:10px;background:transparent;border:none;")
        tr.addWidget(hint)
        tr.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.setStyleSheet("""
            QPushButton{background:rgba(255,255,255,0.08);color:rgba(255,255,255,0.5);
                        border:none;border-radius:12px;font-size:11px;}
            QPushButton:hover{background:#e5534b;color:white;}
        """)
        close_btn.clicked.connect(self.hide_keyboard)
        tr.addWidget(close_btn)
        vbox.addLayout(tr)

        self._key_vbox = QVBoxLayout()
        self._key_vbox.setSpacing(5)
        vbox.addLayout(self._key_vbox)

        self._render_keys()

    def _render_keys(self):
        while self._key_vbox.count():
            item = self._key_vbox.takeAt(0)
            if item.layout():
                while item.layout().count():
                    c = item.layout().takeAt(0)
                    if c.widget():
                        c.widget().deleteLater()

        self._flat_buttons.clear()
        self._lhov = None
        self._rhov = None
        self._rects_dirty = True

        rows = ROWS_SHIFT if (self._shift or self._caps) else ROWS_NORMAL
        for row_keys in rows:
            rl = QHBoxLayout()
            rl.setSpacing(5)
            for key in row_keys:
                btn = KeyButton(key)
                btn.clicked.connect(lambda chk=False, k=key: self._on_key(k))
                rl.addWidget(btn, int(WIDE_KEYS.get(key, 1) * 10))
                self._flat_buttons.append(btn)
            self._key_vbox.addLayout(rl)

        # Rebuild rect cache after layout settles
        QTimer.singleShot(150, self._rebuild_rects)

    def _rebuild_rects(self):
        """Cache global screen rects of every button for fast hit-testing."""
        self._btn_rects = []
        for btn in self._flat_buttons:
            if not btn.isVisible():
                continue
            tl = btn.mapToGlobal(QPoint(0, 0))
            self._btn_rects.append((QRect(tl, btn.size()), btn))
        self._rects_dirty = False

    def showEvent(self, event):
        super().showEvent(event)
        # Rebuild rects after window is actually visible and positioned
        QTimer.singleShot(200, self._rebuild_rects)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._rects_dirty = True
        QTimer.singleShot(50, self._rebuild_rects)

    # ── Thread-safe slot called from camera thread ────────────────────────
    # Using @pyqtSlot + direct call via invokeMethod — no QTimer flood

    @pyqtSlot(object, object, float, float)
    def update_hands(
        self,
        left_screen:  object,   # (screen_x, screen_y) | None
        right_screen: object,   # (screen_x, screen_y) | None
        left_pinch:   float,
        right_pinch:  float,
    ):
        """
        Called every camera frame.
        Coordinates are already in SCREEN pixels (from camera_thread).
        """
        if not self.isVisible():
            return

        if self._rects_dirty:
            self._rebuild_rects()

        new_l = self._btn_at(left_screen)
        new_r = self._btn_at(right_screen)

        # Clear stale hovers
        if self._lhov and self._lhov is not new_l:
            self._lhov.set_hover(False, self._lhov._hov_r)
        if self._rhov and self._rhov is not new_r:
            self._rhov.set_hover(self._rhov._hov_l, False)

        if new_l:
            new_l.set_hover(True, new_l._hov_r)
        if new_r:
            new_r.set_hover(new_r._hov_l, True)

        self._lhov = new_l
        self._rhov = new_r

        self._handle_pinch("l", left_pinch,  new_l)
        self._handle_pinch("r", right_pinch, new_r)

    def _btn_at(self, screen_pos) -> KeyButton | None:
        if screen_pos is None:
            return None
        pt = QPoint(int(screen_pos[0]), int(screen_pos[1]))
        for rect, btn in self._btn_rects:
            if rect.contains(pt):
                return btn
        return None

    def _handle_pinch(self, hand: str, dist: float, btn: KeyButton | None):
        pinching = dist < PINCH_THRESHOLD
        if hand == "l":
            if pinching:
                self._lframes += 1
                if self._lframes >= PINCH_DEBOUNCE and not self._lfired:
                    self._lfired = True
                    if btn:
                        self._on_key(btn.key_label)
            else:
                self._lframes = 0
                self._lfired  = False
        else:
            if pinching:
                self._rframes += 1
                if self._rframes >= PINCH_DEBOUNCE and not self._rfired:
                    self._rfired = True
                    if btn:
                        self._on_key(btn.key_label)
            else:
                self._rframes = 0
                self._rfired  = False

    def _on_key(self, key: str):
        if key == "⌫":
            pyautogui.press("backspace")
        elif key == "↵":
            pyautogui.press("enter")
        elif key == "⇧":
            self._shift = not self._shift
            self._render_keys()
        elif key == "⇪":
            self._caps  = not self._caps
            self._shift = False
            self._render_keys()
        elif key == "SPACE":
            pyautogui.press("space")
        else:
            _type_char(key)
            if self._shift and not self._caps:
                self._shift = False
                self._render_keys()

    def show_keyboard(self):
        self._position_bottom()
        self.show()
        self.raise_()

    def hide_keyboard(self):
        self.hide()
        self.closed.emit()

    def toggle(self):
        if self.isVisible():
            self.hide_keyboard()
        else:
            self.show_keyboard()

    def _position_bottom(self):
        screen = QApplication.primaryScreen().geometry()
        self.adjustSize()
        w = min(self.sizeHint().width(), screen.width() - 40)
        x = (screen.width() - w) // 2
        y = screen.height() - self.sizeHint().height() - 60
        self.setGeometry(x, y, w, self.sizeHint().height())
        self._rects_dirty = True