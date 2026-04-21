"""
Gesture Bindings — managed by Wavly Settings.
You can also edit this file manually.

Action types:
  cursor_move, click, right_click, double_click,
  scroll_up, scroll_down, drag_start, stop,
  zoom_in, zoom_out, show_keyboard,
  hotkey:ctrl+z   — any keyboard shortcut
  type:Hello!     — type a string
  run:notepad.exe — open an application
"""

GESTURE_BINDINGS: dict = {
    "cursor_move":   "cursor_move",
    "click":         "click",
    "scroll_up":     "scroll_up",
    "scroll_down":   "scroll_down",
    "drag_start":    "drag_start",
    "stop":          "stop",
    "three_fingers": "show_keyboard",   # ✌️+ring = keyboard toggle
}