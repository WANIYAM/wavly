"""
ActionThread — Cursor loop + Action execution.

Cursor lock is now handled upstream in camera_thread + gesture_queue,
so this thread just reads the (already-frozen) cursor position and
clicks at it. No race condition possible.
"""

import threading
import time
import pyautogui
from typing import Optional

from core.gesture_queue import GestureQueue, GestureEvent
from config.settings import Settings

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0


class ActionThread(threading.Thread):

    def __init__(self, gesture_queue: GestureQueue, settings: Settings):
        super().__init__(name="ActionThread")
        self.gesture_queue = gesture_queue
        self.settings = settings
        self._stop_event = threading.Event()

        self._smooth_x: Optional[float] = None
        self._smooth_y: Optional[float] = None
        self._is_dragging: bool = False
        self._cursor_thread: Optional[threading.Thread] = None

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
                print(f"[ActionThread] Error executing '{event.name}': {e}")

        print("[ActionThread] Stopped.")

    # ── Cursor loop ───────────────────────────────────────────────────────

    def _cursor_loop(self):
        """
        60fps cursor movement loop.
        gesture_queue.put_cursor() is already blocked by camera_thread
        when an action gesture is in progress, so the position we read
        here is guaranteed stable during a click.
        """
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

    # ── Action execution ──────────────────────────────────────────────────

    def _execute_action(self, event: GestureEvent):
        name = event.name

        # Get the current smoothed position — cursor is frozen at this point
        x = int(self._smooth_x) if self._smooth_x is not None else None
        y = int(self._smooth_y) if self._smooth_y is not None else None

        if name == "click":
            self._cancel_drag()
            if x and y:
                pyautogui.click(x, y)
                print(f"[Action] ✓ Click at ({x}, {y})")
            else:
                pyautogui.click()
                print("[Action] ✓ Click")

        elif name == "double_click":
            self._cancel_drag()
            if x and y:
                pyautogui.doubleClick(x, y)
            else:
                pyautogui.doubleClick()
            print(f"[Action] ✓ Double click at ({x}, {y})")

        elif name == "right_click":
            self._cancel_drag()
            if x and y:
                pyautogui.rightClick(x, y)
            else:
                pyautogui.rightClick()
            print(f"[Action] ✓ Right click at ({x}, {y})")

        elif name == "scroll_up":
            pyautogui.scroll(self.settings.scroll_speed)
            print("[Action] ✓ Scroll up")

        elif name == "scroll_down":
            pyautogui.scroll(-self.settings.scroll_speed)
            print("[Action] ✓ Scroll down")

        elif name == "drag_start":
            if not self._is_dragging:
                pyautogui.mouseDown()
                self._is_dragging = True
                print("[Action] ✓ Drag start")

        elif name == "drag_end":
            self._cancel_drag()

        elif name == "zoom_in":
            pyautogui.hotkey("ctrl", "+")
            print("[Action] ✓ Zoom in")

        elif name == "zoom_out":
            pyautogui.hotkey("ctrl", "-")
            print("[Action] ✓ Zoom out")

        elif name == "stop":
            self._cancel_drag()
            print("[Action] ✓ Stop")

        else:
            print(f"[Action] Unknown: {name}")

    def _cancel_drag(self):
        if self._is_dragging:
            pyautogui.mouseUp()
            self._is_dragging = False
            print("[Action] ✓ Drag released")

    def stop(self):
        self._cancel_drag()
        self._stop_event.set()