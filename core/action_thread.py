"""
ActionThread — Phase 3

Now integrates:
  - Context-aware action resolution (browser/editor/media/presentation)
  - Air drawing letter → command dispatch
  - All previous gesture actions
"""

import subprocess
import threading
import time
import pyautogui
from typing import Optional, Callable

from core.gesture_queue import GestureQueue, GestureEvent
from core.context_manager import ContextManager
from config.settings import Settings
from gestures.air_drawing import DEFAULT_LETTER_ACTIONS

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0


class ActionThread(threading.Thread):

    def __init__(self, gesture_queue: GestureQueue, settings: Settings,
                 keyboard_toggle_fn: Optional[Callable] = None,
                 context_manager: Optional[ContextManager] = None):
        super().__init__(name="ActionThread")
        self.gesture_queue    = gesture_queue
        self.settings         = settings
        self._stop_event      = threading.Event()
        self._smooth_x: Optional[float] = None
        self._smooth_y: Optional[float] = None
        self._is_dragging     = False
        self._cursor_thread: Optional[threading.Thread] = None
        self._keyboard_toggle = keyboard_toggle_fn
        self._context_mgr     = context_manager

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

    # ── Cursor loop ───────────────────────────────────────────────────────

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

    # ── Action execution ──────────────────────────────────────────────────

    def _execute_action(self, event: GestureEvent):
        gesture = event.name

        # ── Air drawing letter dispatch ───────────────────────────────────
        if gesture.startswith("air_letter:"):
            letter = gesture.split(":")[1]
            self._execute_letter(letter)
            return

        # ── Gesture → action via bindings + context override ──────────────
        bindings       = self._get_bindings()
        default_action = bindings.get(gesture, gesture)

        # Context manager can override the action based on active app
        if self._context_mgr is not None:
            action = self._context_mgr.resolve_action(gesture, default_action)
        else:
            action = default_action

        x = int(self._smooth_x) if self._smooth_x is not None else None
        y = int(self._smooth_y) if self._smooth_y is not None else None

        self._run_action(action, gesture, x, y)

    def _run_action(self, action: str, gesture: str, x, y):
        if action == "cursor_move":
            pass
        elif action == "click":
            self._cancel_drag()
            pyautogui.click(x, y) if (x and y) else pyautogui.click()
            print(f"[Action] ✓ Click ({x},{y})")
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
            print("[Action] ✓ Typed")
        elif action.startswith("run:"):
            subprocess.Popen(action.replace("run:", ""), shell=True)
            print(f"[Action] ✓ Launched: {action[4:]}")
        else:
            print(f"[Action] Unknown: '{action}' for gesture '{gesture}'")

    def _execute_letter(self, letter: str):
        """
        Execute the command bound to an air-drawn letter.
        Reads from config/air_draw_bindings.py — user editable,
        changes apply instantly without restart.
        """
        action = self._get_air_draw_action(letter.upper())
        if action is None:
            print(f"[Action] Air letter '{letter}' has no binding")
            return

        if action.startswith("hotkey:"):
            keys = action.replace("hotkey:", "").split("+")
            pyautogui.hotkey(*keys)
            print(f"[Action] ✓ Air draw '{letter}' → {action}")
        elif action.startswith("run:"):
            subprocess.Popen(action.replace("run:", ""), shell=True)
            print(f"[Action] ✓ Air draw '{letter}' → {action}")
        elif action.startswith("type:"):
            pyautogui.typewrite(action.replace("type:", ""), interval=0.05)
            print(f"[Action] ✓ Air draw '{letter}' → typed")

    def _get_air_draw_action(self, letter: str):
        """Load bindings fresh so live edits to the config apply instantly."""
        try:
            import importlib
            import config.air_draw_bindings as adb
            importlib.reload(adb)
            return adb.AIR_DRAW_BINDINGS.get(letter)
        except Exception:
            from gestures.air_drawing import DEFAULT_LETTER_ACTIONS
            entry = DEFAULT_LETTER_ACTIONS.get(letter)
            if entry:
                kind, args = entry
                if kind == "hotkey":
                    return "hotkey:" + "+".join(args)
                elif kind == "run":
                    return "run:" + " ".join(args)
            return None

    def _cancel_drag(self):
        if self._is_dragging:
            pyautogui.mouseUp()
            self._is_dragging = False
            print("[Action] ✓ Drag released")

    def stop(self):
        self._cancel_drag()
        self._stop_event.set()