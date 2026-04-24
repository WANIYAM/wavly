"""
OnScreenKeyboard — Two-hand floating keyboard.

All issues fixed:
  1. FULL WIDTH — keyboard spans entire screen width
  2. CACHED RECTS — button positions computed once, not every frame
  3. NO FOCUS STEAL — NoFocus on every button and the window itself
  4. PYPERCLIP TYPING — clipboard paste handles all unicode/symbols
  5. PROPER QT SLOT — @pyqtSlot so invokeMethod works correctly
  6. RECT REFRESH — cache rebuilt after show, move, resize, re-render
"""

import time
import pyautogui
import pyperclip

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

WIDE_KEYS    = {"⌫":1.8,"⇪":1.8,"↵":2.2,"⇧":2.5,"SPACE":14}
SPECIAL_KEYS = {"⌫","⇪","↵","⇧","SPACE"}

PINCH_THRESHOLD = 0.18
PINCH_DEBOUNCE  = 6
KEY_HEIGHT      = 46
H_PADDING       = 8


def _type_char(char: str):
    """Type via clipboard — works for all unicode, symbols, brackets."""
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
        self.key_label = label
        self._hov_l    = False
        self._hov_r    = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(KEY_HEIGHT)
        # NoFocus: clicking a key never steals focus from the target app
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._apply_style()

    def set_hover(self, left: bool, right: bool):
        if left != self._hov_l or right != self._hov_r:
            self._hov_l = left
            self._hov_r = right
            self._apply_style()

    def _apply_style(self):
        special = self.key_label in SPECIAL_KEYS
        if self._hov_l and self._hov_r:
            bg, border, fw = "#7c3aed", "1px solid rgba(255,255,255,0.6)", "700"
        elif self._hov_l:
            bg, border, fw = "#2563eb", "1px solid rgba(255,255,255,0.5)", "600"
        elif self._hov_r:
            bg, border, fw = "#16a34a", "1px solid rgba(255,255,255,0.5)", "600"
        elif special:
            bg, border, fw = "rgba(255,255,255,0.07)", "none", "400"
        else:
            bg, border, fw = "rgba(255,255,255,0.11)", "none", "400"

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: rgba(255,255,255,0.92);
                border: {border};
                border-radius: 6px;
                font-size: 14px;
                font-family: 'Segoe UI';
                font-weight: {fw};
            }}
            QPushButton:pressed {{ background: rgba(255,255,255,0.30); }}
        """)


class OnScreenKeyboard(QWidget):

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shift = False
        self._caps  = False
        self._flat_buttons: list[KeyButton] = []

        # Cached button screen rects — rebuilt once, not every frame
        self._btn_rects: list[tuple[QRect, KeyButton]] = []
        self._rects_valid = False

        self._lframes = 0; self._lfired = False
        self._rframes = 0; self._rfired = False
        self._lhov: KeyButton | None = None
        self._rhov: KeyButton | None = None

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
                background: rgba(15, 15, 18, 245);
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,0.07);
            }
        """)
        outer.addWidget(self._root)

        vbox = QVBoxLayout(self._root)
        vbox.setContentsMargins(H_PADDING, 8, H_PADDING, 10)
        vbox.setSpacing(5)

        # Title bar
        tr = QHBoxLayout()
        tr.setSpacing(10)

        for color, text in [("#3b82f6","● Left hand"), ("#22c55e","● Right hand")]:
            l = QLabel(text)
            l.setStyleSheet(
                f"color:{color};font-size:11px;background:transparent;border:none;"
            )
            tr.addWidget(l)

        tr.addStretch()

        hint = QLabel("hover finger over key  •  pinch to press  •  or click with mouse")
        hint.setStyleSheet(
            "color:rgba(255,255,255,0.28);font-size:10px;"
            "background:transparent;border:none;"
        )
        tr.addWidget(hint)
        tr.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.setStyleSheet("""
            QPushButton {
                background:rgba(255,255,255,0.07);
                color:rgba(255,255,255,0.45);
                border:none; border-radius:11px; font-size:11px;
            }
            QPushButton:hover { background:#e5534b; color:white; }
        """)
        close_btn.clicked.connect(self.hide_keyboard)
        tr.addWidget(close_btn)
        vbox.addLayout(tr)

        self._key_vbox = QVBoxLayout()
        self._key_vbox.setSpacing(4)
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
        self._rects_valid = False

        rows = ROWS_SHIFT if (self._shift or self._caps) else ROWS_NORMAL
        for row_keys in rows:
            rl = QHBoxLayout()
            rl.setSpacing(4)
            for key in row_keys:
                btn = KeyButton(key)
                btn.clicked.connect(lambda chk=False, k=key: self._on_key(k))
                rl.addWidget(btn, int(WIDE_KEYS.get(key, 1) * 10))
                self._flat_buttons.append(btn)
            self._key_vbox.addLayout(rl)

        QTimer.singleShot(120, self._rebuild_rects)

    def _rebuild_rects(self):
        """Cache global screen rect of every button for O(1) hit testing."""
        self._btn_rects.clear()
        for btn in self._flat_buttons:
            if btn.isVisible():
                tl = btn.mapToGlobal(QPoint(0, 0))
                self._btn_rects.append((QRect(tl, btn.size()), btn))
        self._rects_valid = True

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(150, self._rebuild_rects)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._rects_valid = False
        QTimer.singleShot(50, self._rebuild_rects)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rects_valid = False
        QTimer.singleShot(50, self._rebuild_rects)

    # ── Two-hand update ───────────────────────────────────────────────────

    @pyqtSlot(object, object, float, float)
    def update_hands(self, left_screen, right_screen, left_pinch, right_pinch):
        if not self.isVisible():
            return
        if not self._rects_valid:
            self._rebuild_rects()

        new_l = self._btn_at(left_screen)
        new_r = self._btn_at(right_screen)

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

    def _btn_at(self, pos) -> KeyButton | None:
        if pos is None:
            return None
        pt = QPoint(int(pos[0]), int(pos[1]))
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

    # ── Key press ─────────────────────────────────────────────────────────

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

    # ── Visibility ────────────────────────────────────────────────────────

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
        """Span full screen width, sit at the very bottom."""
        screen = QApplication.primaryScreen().geometry()
        sw, sh = screen.width(), screen.height()

        # Force full width before measuring height
        self.setMinimumWidth(sw)
        self.adjustSize()

        h = self.sizeHint().height()
        # x=0, full width, 4px gap above taskbar
        self.setGeometry(0, sh - h - 4, sw, h)

        self._rects_valid = False
        QTimer.singleShot(150, self._rebuild_rects)