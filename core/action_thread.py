"""
ActionThread — Phase 4 Feature 2: Voice + Gesture Hybrid

Handles both voice and gesture events. When a voice event arrives:
  1. Check if it's eligible for hybrid pairing (has matching gestures)
  2. If yes: store in CommandQueue and wait for gesture (2-second window)
  3. If gesture arrives in time: resolve via IntentResolver → hybrid action
  4. If timeout: execute voice-only action

Context awareness works for voice, gesture, AND hybrid commands.
"""

import subprocess
import threading
import time
import pyautogui
import re
from typing import Optional, Callable

from core.gesture_queue import GestureQueue, GestureEvent
from core.command_queue import CommandQueue
from core.intent_resolver import IntentResolver
from config.settings import Settings

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0


class ActionThread(threading.Thread):

    def __init__(self, gesture_queue: GestureQueue, settings: Settings,
                 keyboard_toggle_fn: Optional[Callable] = None,
                 context_manager=None,
                 on_action_executed: Optional[Callable] = None,
                 command_queue: Optional[CommandQueue] = None,
                 intent_resolver: Optional[IntentResolver] = None):
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
        self._cursor_lock     = threading.Lock()
        self._on_action_executed = on_action_executed
        
        # Phase 4 Feature 2: Hybrid voice + gesture
        self._command_queue   = command_queue or CommandQueue()
        self._intent_resolver = intent_resolver or IntentResolver()
        self._last_timeout_check = time.time()

        # Cache screen dimensions for edge clamping
        self._screen_w, self._screen_h = pyautogui.size()

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
            # Check for expired voice commands (timeout fallback)
            self._handle_expired_voice_commands()
            
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

    @staticmethod
    def clamp_cursor(x: int, y: int, screen_width: int, screen_height: int) -> tuple[int, int]:
        """Clamp cursor to stay 5px away from screen edges."""
        x = max(5, min(screen_width - 5, x))
        y = max(5, min(screen_height - 5, y))
        return x, y

    def _move_cursor(self, target_x: int, target_y: int):
        alpha = self.settings.cursor_smoothing
        with self._cursor_lock:
            if self._smooth_x is None:
                self._smooth_x = float(target_x)
                self._smooth_y = float(target_y)
            else:
                self._smooth_x = alpha * target_x + (1 - alpha) * self._smooth_x
                self._smooth_y = alpha * target_y + (1 - alpha) * self._smooth_y
            x = int(self._smooth_x)
            y = int(self._smooth_y)
        x, y = self.clamp_cursor(x, y, self._screen_w, self._screen_h)
        try:
            pyautogui.moveTo(x, y, duration=0)
        except pyautogui.FailSafeException:
            pass

    # ── Action execution ──────────────────────────────────────────────────

    def _execute_action(self, event: GestureEvent):
        gesture = event.name

        # ── Air drawing letter ────────────────────────────────────────────
        if gesture.startswith("air_letter:"):
            letter = gesture.split(":")[1]
            self._execute_letter(letter)
            return

        # ── Voice command ─────────────────────────────────────────────────
        # VoiceThread fires events as "voice:action_string"
        # Check for hybrid pairing opportunity
        if gesture.startswith("voice:"):
            action = gesture[6:]   # remove "voice:" prefix
            self._handle_voice_event(action, event)
            return
        
        # ── Gesture event + check for hybrid match ────────────────────────
        # If a gesture arrives, check CommandQueue for pending voice commands
        self._check_gesture_for_hybrid(gesture, event)

        # ── Gesture → action via bindings + context override ──────────────
        bindings       = self._get_bindings()
        default_action = bindings.get(gesture, gesture)

        if self._context_mgr is not None:
            action = self._context_mgr.resolve_action(gesture, default_action)
        else:
            action = default_action

        with self._cursor_lock:
            x = int(self._smooth_x) if self._smooth_x is not None else None
            y = int(self._smooth_y) if self._smooth_y is not None else None

        self._run_action(action, gesture, x, y)

    def _run_action(self, action: str, source: str, x, y):
        success = True
        if action == "cursor_move":
            pass

        elif action == "click":
            self._cancel_drag()
            pyautogui.click(x, y) if (x and y) else pyautogui.click()
            print(f"[Action] ✓ Click ({source})")

        elif action == "double_click":
            self._cancel_drag()
            pyautogui.doubleClick(x, y) if (x and y) else pyautogui.doubleClick()
            print(f"[Action] ✓ Double click ({source})")

        elif action == "right_click":
            self._cancel_drag()
            pyautogui.rightClick(x, y) if (x and y) else pyautogui.rightClick()
            print(f"[Action] ✓ Right click ({source})")

        elif action == "scroll_up":
            pyautogui.scroll(self.settings.scroll_speed)
            print(f"[Action] ✓ Scroll up ({source})")

        elif action == "scroll_down":
            pyautogui.scroll(-self.settings.scroll_speed)
            print(f"[Action] ✓ Scroll down ({source})")

        elif action == "drag_start":
            if not self._is_dragging:
                pyautogui.mouseDown()
                self._is_dragging = True
                print(f"[Action] ✓ Drag start ({source})")

        elif action in ("drag_end", "stop"):
            self._cancel_drag()
            print(f"[Action] ✓ Stop ({source})")

        elif action == "zoom_in":
            pyautogui.hotkey("ctrl", "+")
            print(f"[Action] ✓ Zoom in ({source})")

        elif action == "zoom_out":
            pyautogui.hotkey("ctrl", "-")
            print(f"[Action] ✓ Zoom out ({source})")

        elif action == "show_keyboard":
            if self._keyboard_toggle:
                self._keyboard_toggle()
                print(f"[Action] ✓ Keyboard toggled ({source})")

        elif action.startswith("hotkey:"):
            keys = action.replace("hotkey:", "").split("+")
            pyautogui.hotkey(*keys)
            print(f"[Action] ✓ Hotkey {'+'.join(keys)} ({source})")

        elif action.startswith("type:"):
            pyautogui.typewrite(action.replace("type:", ""), interval=0.05)
            print(f"[Action] ✓ Typed ({source})")

        elif action.startswith("run:"):
            subprocess.Popen(action.replace("run:", ""), shell=True)
            print(f"[Action] ✓ Launched {action[4:]} ({source})")

        else:
            success = False
            print(f"[Action] Unknown: '{action}' from {source}")

        # Notify feedback listeners (overlay, activity log, etc.)
        if self._on_action_executed:
            try:
                self._on_action_executed(source, source, action, success)
            except Exception as e:
                print(f"[ActionThread] Feedback callback error: {e}")

    # ── Air draw letter ───────────────────────────────────────────────────

    def _execute_letter(self, letter: str):
        action = self._get_air_draw_action(letter.upper())
        if action is None:
            print(f"[Action] Air letter '{letter}' has no binding")
            if self._on_action_executed:
                try:
                    self._on_action_executed("air_draw", f"air_letter:{letter}", "no binding", False)
                except Exception as e:
                    print(f"[ActionThread] Feedback callback error: {e}")
            return
        if action.startswith("hotkey:"):
            keys = action.replace("hotkey:", "").split("+")
            pyautogui.hotkey(*keys)
            print(f"[Action] ✓ Air draw '{letter}' → {action}")
        elif action.startswith("run:"):
            subprocess.Popen(action.replace("run:", ""), shell=True)
        elif action.startswith("type:"):
            pyautogui.typewrite(action.replace("type:", ""), interval=0.05)

        if self._on_action_executed:
            try:
                self._on_action_executed("air_draw", f"air_letter:{letter}", action, True)
            except Exception as e:
                print(f"[ActionThread] Feedback callback error: {e}")

    def _get_air_draw_action(self, letter: str):
        try:
            import importlib
            import config.air_draw_bindings as adb
            importlib.reload(adb)
            return adb.AIR_DRAW_BINDINGS.get(letter)
        except Exception:
            return None

    def _cancel_drag(self):
        if self._is_dragging:
            pyautogui.mouseUp()
            self._is_dragging = False
            print("[Action] ✓ Drag released")

    # ── Hybrid voice + gesture handling ───────────────────────────────────

    def _handle_voice_event(self, voice_action: str, event: GestureEvent):
        """
        Handle a voice event. Check if it can be paired with a gesture.
        If yes: store in CommandQueue and wait for gesture.
        If no: execute voice-only immediately.
        """
        # Check if this voice action is eligible for hybrid pairing
        if self._intent_resolver.is_hybrid_available(voice_action):
            # Store in queue and wait for gesture
            print(f"[Action] 🎤 Storing voice '{voice_action}' — waiting for gesture (2s)")
            self._command_queue.put_voice_event(
                transcript=f"voice:{voice_action}",
                voice_action=voice_action
            )
        else:
            # No hybrid available — execute as voice-only immediately
            with self._cursor_lock:
                x = int(self._smooth_x) if self._smooth_x is not None else None
                y = int(self._smooth_y) if self._smooth_y is not None else None
            print(f"[Action] 🎤 Voice (no hybrid) → {voice_action}")
            self._run_action(voice_action, "voice", x, y)

    def _check_gesture_for_hybrid(self, gesture_type: str, event: GestureEvent):
        """
        When a gesture arrives, check if it matches a pending voice command.
        If yes: resolve as hybrid action. If no: continue as normal gesture.
        """
        # Extract base gesture type (e.g., "point" from "point" or "point_2")
        base_gesture = gesture_type.split("_")[0]
        
        # Check for pending voice command
        pending = self._command_queue.get_pending_for_gesture(base_gesture)
        if pending is None:
            return  # No pending voice command
        
        # Resolve hybrid intent
        intent = self._intent_resolver.resolve_hybrid(
            voice_action=pending.voice_action,
            gesture_type=base_gesture,
            voice_confidence=1.0,
            gesture_confidence=event.confidence
        )
        
        if intent:
            # Execute hybrid action
            with self._cursor_lock:
                x = int(self._smooth_x) if self._smooth_x is not None else None
                y = int(self._smooth_y) if self._smooth_y is not None else None
            
            print(f"[Action] 🎤+👆 Hybrid: {intent.voice_action} + {base_gesture} → {intent.hybrid_action}")
            self._execute_hybrid_action(
                hybrid_action=intent.hybrid_action,
                voice_transcript=pending.transcript,
                gesture_type=base_gesture,
                cursor_x=x,
                cursor_y=y
            )
        else:
            # Intent didn't resolve — just execute gesture normally
            # (The pending voice command has been consumed but didn't match)
            print(f"[Action] Gesture '{gesture_type}' didn't match pending voice '{pending.voice_action}'")

    def _execute_hybrid_action(self, hybrid_action: str, voice_transcript: str,
                               gesture_type: str, cursor_x: int, cursor_y: int):
        """
        Execute a hybrid action.
        These are application-specific behaviors that use both voice AND gesture data.
        """
        success = True
        
        if hybrid_action == "open_at_cursor":
            # Open file/folder at cursor position
            # In a real app: find what's under (cursor_x, cursor_y) and open it
            print(f"[Action] ✓ Hybrid: Open file at ({cursor_x}, {cursor_y})")
            pyautogui.click(cursor_x, cursor_y) if (cursor_x and cursor_y) else None
            pyautogui.hotkey("ctrl", "o")  # Open dialog
        
        elif hybrid_action == "search_for_letter":
            # Extract the air-drawn letter from the transcript or gesture
            # For now, use voice command as search term
            search_term = voice_transcript.replace("search ", "").strip()
            print(f"[Action] ✓ Hybrid: Search for '{search_term}'")
            pyautogui.hotkey("ctrl", "f")
            time.sleep(0.2)
            pyautogui.typewrite(search_term, interval=0.05)
        
        elif hybrid_action == "go_to_line_number":
            # Extract line number from voice transcript
            # "go to 42" → extract 42
            numbers = re.findall(r'\d+', voice_transcript)
            if numbers:
                line_num = numbers[0]
                print(f"[Action] ✓ Hybrid: Go to line {line_num}")
                pyautogui.hotkey("ctrl", "g")  # VS Code go-to-line
                time.sleep(0.2)
                pyautogui.typewrite(line_num, interval=0.05)
                pyautogui.press("enter")
            else:
                print(f"[Action] Hybrid: Could not extract line number from '{voice_transcript}'")
                success = False
        
        elif hybrid_action == "copy_line":
            # Copy current line (voice "copy" + gesture "fingers_2" = smaller scope)
            print(f"[Action] ✓ Hybrid: Copy line")
            pyautogui.hotkey("ctrl", "l")  # Select line
            pyautogui.hotkey("ctrl", "c")  # Copy
        
        elif hybrid_action == "copy_paragraph":
            # Copy current paragraph (voice "copy" + gesture "fingers_3" = larger scope)
            print(f"[Action] ✓ Hybrid: Copy paragraph")
            pyautogui.hotkey("ctrl", "a")  # Select all (in paragraph context)
            pyautogui.hotkey("ctrl", "c")
        
        elif hybrid_action == "scroll_up_fast":
            pyautogui.scroll(self.settings.scroll_speed * 2)
            print(f"[Action] ✓ Hybrid: Scroll up fast")
        
        elif hybrid_action == "scroll_down_fast":
            pyautogui.scroll(-self.settings.scroll_speed * 2)
            print(f"[Action] ✓ Hybrid: Scroll down fast")
        
        elif hybrid_action == "click_at_point":
            print(f"[Action] ✓ Hybrid: Click at point ({cursor_x}, {cursor_y})")
            if cursor_x and cursor_y:
                pyautogui.click(cursor_x, cursor_y)
        
        else:
            success = False
            print(f"[Action] Hybrid: Unknown action '{hybrid_action}'")
        
        # Notify listeners
        if self._on_action_executed:
            try:
                self._on_action_executed("hybrid", gesture_type, hybrid_action, success)
            except Exception as e:
                print(f"[ActionThread] Feedback callback error: {e}")

    def _handle_expired_voice_commands(self):
        """
        Periodically check for voice commands that have timed out.
        Execute them as voice-only fallback.
        """
        now = time.time()
        if now - self._last_timeout_check < 0.5:
            return  # Check at most every 500ms
        
        self._last_timeout_check = now
        
        expired = self._command_queue.get_and_clear_expired()
        for cmd in expired:
            with self._cursor_lock:
                x = int(self._smooth_x) if self._smooth_x is not None else None
                y = int(self._smooth_y) if self._smooth_y is not None else None
            
            print(f"[Action] 🎤 Voice timeout → executing as voice-only: {cmd.voice_action}")
            self._run_action(cmd.voice_action, "voice", x, y)

    def stop(self):
        self._cancel_drag()
        self._stop_event.set()