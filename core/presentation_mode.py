"""
PresentationMode — Phase 5

Activates automatically when PowerPoint is detected (or manually via tray).

Features:
  ☝️  Index finger       → Laser pointer (red dot follows fingertip)
  👈  Swipe right→left   → Previous slide
  👉  Swipe left→right   → Next slide
  ✊  Fist               → Black screen (B key)
  🖐️  Open palm          → Exit slideshow (Escape)
  🤟  Three fingers      → Zoom in (Ctrl++)
  ✌️  Two fingers        → Zoom out (Ctrl+-)

Swipe detection:
  Tracks fingertip X movement over SWIPE_FRAMES frames.
  If net displacement > SWIPE_THRESHOLD and velocity is consistent,
  fires left/right arrow key.
  No extra training — pure movement analysis.
"""

import time
import pyautogui
from collections import deque
from typing import Optional, Callable
from PyQt6.QtCore import QMetaObject, Qt, Q_ARG


# ── Swipe detection config ────────────────────────────────────────────────────
SWIPE_FRAMES    = 12    # frames of movement to analyse
SWIPE_THRESHOLD = 0.12  # normalised X displacement to count as swipe (0-1)
SWIPE_COOLDOWN  = 1.2   # seconds between swipes (prevents rapid multi-fire)

# ── Gesture → slide action mapping ───────────────────────────────────────────
PRES_GESTURE_MAP = {
    "drag_start":    "black_screen",    # ✊ fist = black screen (B key)
    "stop":          "exit_slideshow",  # 🖐️ palm = exit slideshow (Escape)
    "three_fingers": "zoom_in",         # 🤟 three fingers = zoom in
    "two_fingers":   "zoom_out",        # ✌️ two fingers = zoom out
    "scroll_down":   "zoom_out",        # scroll down also zooms out
    "click":         "next_slide",      # 🤌 click = next slide
    # Note: swipe left/right = prev/next slide (handled by SwipeDetector, not here)
}


class SwipeDetector:
    """
    Detects left/right swipe from a rolling window of X positions.
    Works on normalised (0-1) camera coordinates.
    """

    def __init__(self):
        self._history:     deque  = deque(maxlen=SWIPE_FRAMES)
        self._last_swipe:  float  = 0.0

    def update(self, norm_x: float) -> Optional[str]:
        """
        Feed normalised X coordinate every frame.
        Returns 'swipe_left', 'swipe_right', or None.
        """
        self._history.append(norm_x)

        if len(self._history) < SWIPE_FRAMES:
            return None

        now = time.time()
        if now - self._last_swipe < SWIPE_COOLDOWN:
            return None

        xs        = list(self._history)
        net_disp  = xs[-1] - xs[0]          # total displacement
        mid       = len(xs) // 2
        first_half = xs[mid] - xs[0]        # displacement in first half
        sec_half   = xs[-1] - xs[mid]       # displacement in second half

        # Both halves must agree on direction (consistent movement)
        consistent = (first_half * sec_half) > 0

        if abs(net_disp) >= SWIPE_THRESHOLD and consistent:
            self._last_swipe = now
            self._history.clear()
            # After flip: moving hand right in camera = moving right on screen
            return "swipe_right" if net_disp > 0 else "swipe_left"

        return None

    def reset(self):
        self._history.clear()


class PresentationMode:
    """
    Manages the full presentation mode lifecycle.

    Activated by ContextManager when powerpnt is detected,
    or manually via tray toggle.

    Communicates with:
      - CameraThread (receives fingertip positions + gestures)
      - LaserPointer (Qt widget, updated via invokeMethod)
      - ActionThread (fires slide commands via callback)
    """

    def __init__(self,
                 laser_pointer,
                 on_action_fn: Optional[Callable] = None):
        self._laser          = laser_pointer
        self._on_action      = on_action_fn   # fn(action_name)
        self._active         = False
        self._swipe          = SwipeDetector()
        self._last_gesture   = ""
        self._gesture_frames = 0

    @property
    def active(self) -> bool:
        return self._active

    def activate(self):
        if not self._active:
            self._active = True
            self._swipe.reset()
            if self._laser:
                QMetaObject.invokeMethod(
                    self._laser, "show_pointer",
                    Qt.ConnectionType.QueuedConnection,
                )
            print("[Presentation] Mode activated 📊")

    def deactivate(self):
        if self._active:
            self._active = False
            if self._laser:
                QMetaObject.invokeMethod(
                    self._laser, "hide_pointer",
                    Qt.ConnectionType.QueuedConnection,
                )
            print("[Presentation] Mode deactivated")

    def toggle(self):
        if self._active:
            self.deactivate()
        else:
            self.activate()

    # ── Frame processing (called from CameraThread) ───────────────────────

    def process_frame(self, gesture: str, confidence: float,
                      norm_x: float, norm_y: float,
                      screen_x: int, screen_y: int,
                      hand_detected: bool):
        """
        Called every frame from CameraThread when presentation mode is active.
        Returns action string to fire, or None.
        """
        if not self._active:
            return None

        # Update laser pointer position
        if self._laser:
            if hand_detected:
                QMetaObject.invokeMethod(
                    self._laser, "move_to",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(float, float(screen_x)),
                    Q_ARG(float, float(screen_y)),
                )
            else:
                QMetaObject.invokeMethod(
                    self._laser, "hand_lost",
                    Qt.ConnectionType.QueuedConnection,
                )

        if not hand_detected:
            self._swipe.reset()
            return None

        # Swipe detection (overrides gesture if swipe detected)
        swipe = self._swipe.update(norm_x)
        if swipe:
            action = "prev_slide" if swipe == "swipe_left" else "next_slide"
            print(f"[Presentation] Swipe → {action}")
            self._fire(action)
            return action

        # Gesture-based actions (with 8-frame hold to prevent accidental fires)
        mapped = PRES_GESTURE_MAP.get(gesture)
        if mapped and confidence > 0.6:
            if gesture == self._last_gesture:
                self._gesture_frames += 1
            else:
                self._last_gesture   = gesture
                self._gesture_frames = 1

            if self._gesture_frames == 8:   # held long enough
                self._fire(mapped)
                return mapped
        else:
            self._last_gesture   = ""
            self._gesture_frames = 0

        return None

    def _fire(self, action: str):
        """Execute a presentation action."""
        if action == "next_slide":
            pyautogui.press("right")
            print("[Presentation] → Next slide")

        elif action == "prev_slide":
            pyautogui.press("left")
            print("[Presentation] ← Previous slide")

        elif action == "black_screen":
            pyautogui.press("b")
            print("[Presentation] ■ Black screen")

        elif action == "exit_slideshow":
            pyautogui.press("escape")
            print("[Presentation] ✗ Exit slideshow")

        elif action == "zoom_in":
            pyautogui.hotkey("ctrl", "+")
            print("[Presentation] + Zoom in")

        elif action == "zoom_out":
            pyautogui.hotkey("ctrl", "-")
            print("[Presentation] - Zoom out")

        if self._on_action:
            self._on_action(action)