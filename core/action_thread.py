"""
ActionThread — Phase 4 Feature 2 (Hybrid fixed).

Hybrid pipeline fixes (from audit):

BUG 1 FIX — Consume-on-any-gesture:
  Old: Any gesture consumed the pending voice command.
  New: Only gestures that MATCH a hybrid binding consume the voice command.
       Non-matching gestures execute normally and leave voice command alive.

BUG 2 FIX — Starvation:
  Old: Only newest voice command checked.
  New: CommandQueue.find_and_consume() searches ALL pending commands.

BUG 3 FIX — Race condition:
  Old: Expiry checked in peek(), lock released, consume() could execute expired.
  New: find_and_consume() is atomic — expiry re-checked inside same lock.

Architecture:
  Voice arrives → IntentResolver.is_hybrid_eligible(transcript)?
    YES → store in CommandQueue, wait for matching gesture
    NO  → execute immediately as voice-only (no 2s delay)

  Gesture arrives → CommandQueue.find_and_consume(transcript)?
    FOUND → execute hybrid action
    NOT FOUND → execute gesture normally

  Every 500ms → CommandQueue.get_expired()?
    Returns expired voice commands → execute as voice-only fallback
"""

import subprocess
import threading
import time
import pyautogui
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
                 context_manager=None):
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

        # Hybrid pipeline components
        self._command_queue   = CommandQueue()
        self._intent_resolver = IntentResolver()
        self._last_expire_check = 0.0

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
            # Sweep expired voice commands every 500ms
            now = time.time()
            if now - self._last_expire_check >= 0.5:
                self._last_expire_check = now
                self._flush_expired_voice()

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
        x = int(self._smooth_x) if self._smooth_x is not None else None
        y = int(self._smooth_y) if self._smooth_y is not None else None

        # ── Air drawing letter ─────────────────────────────────────────────
        if gesture.startswith("air_letter:"):
            self._execute_letter(gesture.split(":")[1])
            return

        # ── Voice command ──────────────────────────────────────────────────
        if gesture.startswith("voice:"):
            voice_action = gesture[6:]           # e.g. "hotkey:ctrl+c"
            transcript   = getattr(event, "metadata", None) or voice_action

            # Is this transcript eligible for hybrid pairing?
            if self._intent_resolver.is_hybrid_eligible(transcript):
                # Store in CommandQueue — wait up to 2s for matching gesture
                self._command_queue.put(transcript, voice_action)
                print(f"[Action] 🎤 Voice '{transcript}' → waiting for gesture (2s)")
            else:
                # No hybrid binding exists — execute immediately as voice-only
                print(f"[Action] 🎤 Voice '{transcript}' → {voice_action} (immediate)")
                self._run_action(voice_action, "voice", x, y)
            return

        # ── Gesture — check for pending hybrid match FIRST ─────────────────
        # BUG 1 FIX: Only matching transcripts are consumed.
        #            Non-matching gestures fall through to normal execution.
        hybrid_result = self._try_hybrid(gesture, x, y)
        if hybrid_result:
            return   # hybrid action was executed

        # ── Normal gesture → action via bindings + context override ────────
        bindings       = self._get_bindings()
        default_action = bindings.get(gesture, gesture)

        if self._context_mgr is not None:
            action = self._context_mgr.resolve_action(gesture, default_action)
        else:
            action = default_action

        self._run_action(action, gesture, x, y)

    def _try_hybrid(self, gesture: str, x, y) -> bool:
        """
        Try to pair gesture with a pending voice command.

        Searches ALL pending voice commands (not just newest — BUG 2 FIX).
        Only consumes if a MATCH is found (not on any gesture — BUG 1 FIX).
        Expiry re-checked atomically inside find_and_consume (BUG 3 FIX).

        Returns True if a hybrid action was executed.
        """
        if self._command_queue.size() == 0:
            return False

        # Try each pending voice transcript against this gesture
        # We ask IntentResolver for the matching transcript
        bindings = self._load_hybrid_bindings()

        for (transcript_key, gesture_key), hybrid_action in bindings.items():
            if gesture_key != gesture:
                continue
            # This gesture COULD match transcript_key — check if it's pending
            cmd = self._command_queue.find_and_consume(transcript_key)
            if cmd:
                print(f"[Action] ⚡ HYBRID: '{cmd.transcript}' + '{gesture}' "
                      f"→ {hybrid_action} (age={cmd.age():.2f}s)")
                self._run_hybrid_action(hybrid_action, x, y)
                return True

        return False

    def _load_hybrid_bindings(self) -> dict:
        try:
            import importlib
            import config.hybrid_bindings as hb
            importlib.reload(hb)
            return hb.HYBRID_BINDINGS
        except Exception:
            return {}

    def _run_hybrid_action(self, action: str, x, y):
        """Execute a hybrid action — handles special scroll speeds."""
        try:
            import config.hybrid_bindings as hb
            special = hb.SPECIAL_HYBRID_ACTIONS.get(action)
            if special:
                kind, amount = special
                if kind == "scroll":
                    pyautogui.scroll(amount)
                    print(f"[Action] ✓ Hybrid scroll {amount}")
                return
        except Exception:
            pass
        # Regular action
        self._run_action(action, "hybrid", x, y)

    def _flush_expired_voice(self):
        """Execute expired voice commands as voice-only fallback."""
        expired = self._command_queue.get_expired()
        for cmd in expired:
            x = int(self._smooth_x) if self._smooth_x is not None else None
            y = int(self._smooth_y) if self._smooth_y is not None else None
            print(f"[Action] 🎤 Voice fallback (expired): "
                  f"'{cmd.transcript}' → {cmd.voice_action}")
            self._run_action(cmd.voice_action, "voice-fallback", x, y)

    # ── Standard action runner ────────────────────────────────────────────

    def _run_action(self, action: str, source: str, x, y):
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
            print(f"[Action] Unknown: '{action}' from {source}")

    # ── Air draw letter ───────────────────────────────────────────────────

    def _execute_letter(self, letter: str):
        action = self._get_air_draw_action(letter.upper())
        if action is None:
            print(f"[Action] Air letter '{letter}' has no binding")
            return
        if action.startswith("hotkey:"):
            pyautogui.hotkey(*action.replace("hotkey:", "").split("+"))
            print(f"[Action] ✓ Air draw '{letter}' → {action}")
        elif action.startswith("run:"):
            subprocess.Popen(action.replace("run:", ""), shell=True)
        elif action.startswith("type:"):
            pyautogui.typewrite(action.replace("type:", ""), interval=0.05)

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

    def stop(self):
        self._cancel_drag()
        self._command_queue.clear()
        self._stop_event.set()