"""
ActionThread — Cursor loop + Action execution.
Reads gesture_bindings.py dynamically so settings UI changes apply instantly.
"""

import subprocess
import threading
import time
import pyautogui
from typing import Optional, Callable

from core.gesture_queue import GestureQueue, GestureEvent
from config.settings import Settings

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0


class ActionThread(threading.Thread):

    def __init__(self, gesture_queue: GestureQueue, settings: Settings,
                 keyboard_toggle_fn: Optional[Callable] = None):
        super().__init__(name="ActionThread")
        self.gesture_queue     = gesture_queue
        self.settings          = settings
        self._stop_event       = threading.Event()
        self._smooth_x: Optional[float] = None
        self._smooth_y: Optional[float] = None
        self._is_dragging      = False
        self._cursor_thread: Optional[threading.Thread] = None
        self._keyboard_toggle  = keyboard_toggle_fn

    def set_keyboard_toggle(self, fn: Callable):
        self._keyboard_toggle = fn

    def _get_bindings(self) -> dict:
        try:
            import importlib
            import config.gesture_bindings as gb
            importlib.reload(gb)
            return gb.GESTURE_BINDINGS
        except Exception as e:
            print(f"[ActionThread] Could not load gesture_bindings: {e}")
            return {}

    def run(self):
        print("[ActionThread] Ready.")
        self._cursor_thread = threading.Thread(
            target=self._cursor_loop, name="CursorLoop", daemon=True
        )
        self._cursor_thread.start()

        while not self._stop_event.is_set():
            event = self.gesture_queue.get_action(timeout=0.05)
            if event is None:
                continue
            try:
                self._execute_action(event)
            except Exception as e:
                print(f"[ActionThread] Error: '{event.name}': {e}")

        print("[ActionThread] Stopped.")

    def _cursor_loop(self):
        interval = 1.0 / 60.0
        while not self._stop_event.is_set():
            pos = self.gesture_queue.get_cursor()
            if pos is not None:
                self._move_cursor(pos[0], pos[1])
            time.sleep(interval)

    def _move_cursor(self, target_x: int, target_y: int):
        alpha = self.settings.cursor_smoothing
        if self._smooth_x is None:
            self._smooth_x = float(target_x)
            self._smooth_y = float(target_y)
        else:
            self._smooth_x = alpha * target_x + (1 - alpha) * self._smooth_x
            self._smooth_y = alpha * target_y + (1 - alpha) * self._smooth_y
        try:
            pyautogui.moveTo(int(self._smooth_x), int(self._smooth_y), duration=0)
        except pyautogui.FailSafeException:
            pass

    def _execute_action(self, event: GestureEvent):
        bindings = self._get_bindings()
        gesture  = event.name
        action   = bindings.get(gesture, gesture)

        x = int(self._smooth_x) if self._smooth_x is not None else None
        y = int(self._smooth_y) if self._smooth_y is not None else None

        if action == "cursor_move":
            pass
        elif action == "click":
            self._cancel_drag()
            pyautogui.click(x, y) if (x and y) else pyautogui.click()
            print(f"[Action] ✓ Click at ({x}, {y})")
        elif action == "double_click":
            self._cancel_drag()
            pyautogui.doubleClick(x, y) if (x and y) else pyautogui.doubleClick()
            print("[Action] ✓ Double click")
        elif action == "right_click":
            self._cancel_drag()
            pyautogui.rightClick(x, y) if (x and y) else pyautogui.rightClick()
            print("[Action] ✓ Right click")
        elif action == "scroll_up":
            pyautogui.scroll(self.settings.scroll_speed)
            print("[Action] ✓ Scroll up")
        elif action == "scroll_down":
            pyautogui.scroll(-self.settings.scroll_speed)
            print("[Action] ✓ Scroll down")
        elif action == "drag_start":
            if not self._is_dragging:
                pyautogui.mouseDown()
                self._is_dragging = True
                print("[Action] ✓ Drag start")
        elif action in ("drag_end", "stop"):
            self._cancel_drag()
            print("[Action] ✓ Stop")
        elif action == "zoom_in":
            pyautogui.hotkey("ctrl", "+")
            print("[Action] ✓ Zoom in")
        elif action == "zoom_out":
            pyautogui.hotkey("ctrl", "-")
            print("[Action] ✓ Zoom out")
        elif action == "show_keyboard":
            if self._keyboard_toggle:
                self._keyboard_toggle()
                print("[Action] ✓ Keyboard toggled")
        elif action.startswith("hotkey:"):
            keys = action.replace("hotkey:", "").split("+")
            pyautogui.hotkey(*keys)
            print(f"[Action] ✓ Hotkey: {'+'.join(keys)}")
        elif action.startswith("type:"):
            pyautogui.typewrite(action.replace("type:", ""), interval=0.05)
            print(f"[Action] ✓ Typed")
        elif action.startswith("run:"):
            subprocess.Popen(action.replace("run:", ""), shell=True)
            print(f"[Action] ✓ Launched: {action[4:]}")
        else:
            print(f"[Action] Unknown: '{action}'")

    def _cancel_drag(self):
        if self._is_dragging:
            pyautogui.mouseUp()
            self._is_dragging = False
            print("[Action] ✓ Drag released")

    def stop(self):
        self._cancel_drag()
        self._stop_event.set()