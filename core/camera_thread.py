"""
CameraThread — Phase 4 update.

Uses AdaptiveEngine to get per-gesture hold_frames and confidence
threshold instead of global settings values. Everything else unchanged.
"""

import threading
import time
import cv2
import mediapipe as mp
from typing import Optional, Tuple, Callable
from collections import Counter

from core.gesture_queue import GestureQueue, GestureEvent
from gestures.classifier import GestureClassifier, CURSOR_MOVE, UNKNOWN
from gestures.landmark_utils import LandmarkUtils
from config.settings import Settings

KEYBOARD_TOGGLE_GESTURE = "three_fingers"

try:
    from gestures.air_drawing import AirDrawManager
    AIR_DRAW_AVAILABLE = True
except ImportError:
    AIR_DRAW_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════
# STEP 9 — FUTURE ARCHITECTURE: Camera & Inference Separation
# ═══════════════════════════════════════════════════════════════════════════
#
# CURRENT STATE (Phase 4):
#   CameraThread.run() does EVERYTHING in one loop:
#       cap.read() → cv2.flip() → hands.process() → classify → debounce
#   If MediaPipe inference takes >33 ms, frames back up in the OS camera
#   buffer and latency grows uncontrollably.  Step 8 (frame skipping) is a
#   lightweight band-aid; this design is the proper cure.
#
# PROPOSED ARCHITECTURE (implement in a future phase):
#
#   ┌─────────────────┐     raw BGR frame      ┌──────────────────┐
#   │  CaptureThread  │ ──► (deque maxlen=1) ─►│ InferenceThread  │
#   │   (I/O bound)   │                        │  (CPU/GPU bound) │
#   └─────────────────┘                        └──────────────────┘
#                                                        │
#                                                        ▼
#                                               ┌──────────────────┐
#                                               │   GestureQueue   │
#                                               │  (GestureEvent)  │
#                                               └──────────────────┘
#
# WHY deque(maxlen=1)?
#   • Always keeps the NEWEST frame — never processes stale data.
#   • Memory is bounded to exactly one frame (~1.2 MB for 640×480 BGR).
#   • No locks needed on the consumer side; producer overwrites safely.
#
# CAPTURE THREAD PSEUDOCODE:
#   from collections import deque
#   frame_buffer = deque(maxlen=1)
#
#   while running:
#       ret, frame = cap.read()
#       if ret:
#           frame_buffer.append(frame)   # overwrites old if full
#
# INFERENCE THREAD PSEUDOCODE:
#   while running:
#       if not frame_buffer:
#           time.sleep(0.001)
#           continue
#       frame = frame_buffer.pop()       # always latest
#       rgb   = cv2.cvtColor(frame, ...)
#       results = hands.process(rgb)
#       # ... classify, debounce, enqueue ...
#
# BENEFITS:
#   1. Camera FPS is decoupled from inference FPS — capture never stalls.
#   2. On fast GPUs the inference thread can run at full speed; on slow
#      CPUs it simply processes fewer frames without lag buildup.
#   3. Easy to move inference to a separate process or GPU later.
#   4. Frame skipping (Step 8) becomes unnecessary and can be removed.
#
# MIGRATION NOTES:
#   • Extract all MediaPipe + classification logic from CameraThread.run()
#     into a new InferenceThread class.
#   • CameraThread becomes CaptureThread (or rename).
#   • GestureQueue, GestureTemporalFilter, and debounce state move to
#     InferenceThread since they depend on classification output.
#   • Keep the existing CameraThread API (pause/resume/stop) so callers
#     in main.py don't change.
#
# STATUS:  Design documented — NOT YET IMPLEMENTED.
# ═══════════════════════════════════════════════════════════════════════════


# ── Step 7: Gesture Priority Map ──────────────────────────────────────────
# Lower number = higher priority.  stop always wins over everything.
# This prevents ambiguous intermediate poses from firing conflicting actions.
GESTURE_PRIORITY = {
    "stop":        0,
    "click":       1,
    "drag_start":  2,
    "drag_end":    2,
    "scroll_up":   3,
    "scroll_down": 3,
    "cursor_move": 99,
    "unknown":     99,
}




# ── Step 5: Temporal Gesture Filter ───────────────────────────────────────

class GestureTemporalFilter:
    """
    Maintains a rolling buffer of the last N raw predictions and returns
    the majority-vote winner.  This absorbs single-frame misclassifications
    and prevents phantom gestures from entering the debounce pipeline.

    * cursor_move is included in the buffer (not ignored)
    * "stop" bypasses the buffer for immediate emergency response
    * If no strict majority exists, the previous stable output is held
      (hysteresis) to avoid flickering.
    """

    def __init__(self, buffer_size: int = 5, majority_threshold: int = 3):
        self.buffer: list[str] = []
        self.buffer_size = buffer_size
        self.majority_threshold = majority_threshold
        self.last_stable: str = UNKNOWN

    def update(self, gesture: str) -> str:
        # Emergency pass-through: stop always wins immediately
        if gesture == "stop":
            self.buffer = ["stop"] * self.buffer_size
            self.last_stable = "stop"
            return "stop"

        self.buffer.append(gesture)
        if len(self.buffer) > self.buffer_size:
            self.buffer.pop(0)

        # Not enough history yet — hold previous stable output
        if len(self.buffer) < self.buffer_size:
            return self.last_stable

        counts = Counter(self.buffer)
        most_common, count = counts.most_common(1)[0]

        if count >= self.majority_threshold:
            self.last_stable = most_common
            return most_common

        return self.last_stable

    def reset(self):
        self.buffer.clear()
        self.last_stable = UNKNOWN


class CameraThread(threading.Thread):

    def __init__(self, gesture_queue: GestureQueue, settings: Settings,
                 adaptive_engine=None):
        super().__init__(name="CameraThread")
        self.gesture_queue   = gesture_queue
        self.settings        = settings
        self._adaptive       = adaptive_engine   # Phase 4
        self._stop_event     = threading.Event()
        self._paused         = False
        self._pause_lock     = threading.Lock()

        self._keyboard_update_fn:  Optional[Callable] = None
        self._keyboard_visible_fn: Optional[Callable] = None

        self.mp_hands = mp.solutions.hands
        self.mp_draw  = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=settings.min_detection_confidence,
            min_tracking_confidence=settings.min_tracking_confidence,
        )

        self.classifier = GestureClassifier(settings)

        if AIR_DRAW_AVAILABLE:
            self._air_draw = AirDrawManager(
                settings,
                on_letter_fn=self._on_air_letter,
            )
        else:
            self._air_draw = None

        import pyautogui
        self.screen_w, self.screen_h = pyautogui.size()

        self._pending_gesture: str = ""
        self._pending_frames:  int = 0
        self._last_fired:      str = ""
        self._cam_failures:    int = 0

        # Step 5: temporal filter
        self._temporal_filter = GestureTemporalFilter(
            buffer_size=self.settings.temporal_filter_size,
            majority_threshold=self.settings.temporal_filter_majority,
        )

        # Step 6: cooldown state
        self._global_cooldown: int = 0
        self._per_gesture_cooldowns: dict[str, int] = {}

        # Step 7: active gesture lock + safety timeout
        self._active_gesture: str = ""                 # currently locked-in gesture
        self._active_gesture_ts: float = 0.0           # timestamp for timeout safety
        self._release_frame_count: int = 0             # neutral frames counter

        # Step 8: frame-skipping flag (lightweight, no lock needed)
        self._processing: bool = False

    def set_keyboard_fns(self, update_fn: Callable, visible_fn: Callable):
        self._keyboard_update_fn  = update_fn
        self._keyboard_visible_fn = visible_fn

    # ── Adaptive helpers ──────────────────────────────────────────────────

    def _hold_frames(self, gesture: str) -> int:
        """Per-gesture hold_frames from adaptive engine, or global default."""
        if self._adaptive:
            return self._adaptive.get_hold_frames(gesture, self.settings.hold_frames)
        return self.settings.hold_frames

    def _conf_threshold(self, gesture: str) -> float:
        """Per-gesture confidence threshold, or global default."""
        if self._adaptive:
            return self._adaptive.get_confidence_threshold(
                gesture, self.settings.ml_confidence_threshold
            )
        return self.settings.ml_confidence_threshold

    def _priority(self, gesture: str) -> int:
        """Return priority rank for a gesture (lower = higher priority)."""
        return GESTURE_PRIORITY.get(gesture, 50)

    # ── Pause / Resume ────────────────────────────────────────────────────

    def pause(self):
        with self._pause_lock:
            self._paused = True
        self.gesture_queue.unlock_cursor()
        print("[CameraThread] Paused.")

    def resume(self):
        with self._pause_lock:
            self._paused = False
        self.classifier.reload()
        print("[CameraThread] Resumed.")

    def is_paused(self) -> bool:
        with self._pause_lock:
            return self._paused

    def _on_air_letter(self, letter: str, confidence: float):
        self.gesture_queue.put_action(GestureEvent(
            name=f"air_letter:{letter}",
            confidence=confidence,
        ))

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self):
        cap = None

        while not self._stop_event.is_set():

            if self.is_paused():
                if cap is not None:
                    cap.release()
                    cap = None
                time.sleep(0.1)
                continue

            if cap is None:
                cap = cv2.VideoCapture(self.settings.camera_index)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                if not cap.isOpened():
                    print(f"[CameraThread] ERROR: Cannot open camera")
                    time.sleep(1)
                    cap = None
                    continue
                print(f"[CameraThread] Camera {self.settings.camera_index} opened.")

            ret, frame = cap.read()
            if not ret:
                self._cam_failures += 1
                backoff = min(0.05 * (1.5 ** self._cam_failures), 1.0)
                time.sleep(backoff)
                if self._cam_failures > 30:
                    print(f"[CameraThread] Camera read failed {self._cam_failures} times, releasing and reinitializing.")
                    cap.release()
                    cap = None
                    self._cam_failures = 0
                continue
            self._cam_failures = 0

            # ── Step 8: Optional Frame Skipping ───────────────────────────────
            if self.settings.skip_frames_when_lagging and self._processing:
                # Inference is still running — drop this frame to keep latency low
                if self.settings.show_debug_window:
                    cv2.putText(frame, "DROPPED", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    cv2.imshow("Wavly Debug", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                continue

            self._processing = True
            try:
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results = self.hands.process(rgb)
                rgb.flags.writeable = True

                keyboard_open = (
                    self._keyboard_visible_fn is not None and
                    self._keyboard_visible_fn()
                )

                if keyboard_open:
                    self._process_keyboard_mode(results, frame)
                else:
                    self._process_gesture_mode(results, frame)
            finally:
                self._processing = False

            if self.settings.show_debug_window:
                cv2.imshow("Wavly Debug", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        print("[CameraThread] Stopped.")

    # ── Keyboard mode ─────────────────────────────────────────────────────

    def _process_keyboard_mode(self, results, frame):
        left_pos    = None
        right_pos   = None
        left_pinch  = 1.0
        right_pinch = 1.0

        if results.multi_hand_landmarks and results.multi_handedness:
            for hl, hd in zip(results.multi_hand_landmarks, results.multi_handedness):
                label    = hd.classification[0].label
                tip      = hl.landmark[8]
                sx       = int(tip.x * self.screen_w)
                sy       = int(tip.y * self.screen_h)
                features = LandmarkUtils.landmarks_to_features(hl)
                pinch    = float(features[-1])

                gesture_name, confidence = self.classifier.predict(features)
                if gesture_name == KEYBOARD_TOGGLE_GESTURE:
                    self._debounce_and_fire(KEYBOARD_TOGGLE_GESTURE, confidence, sx, sy)
                else:
                    if self._pending_gesture == KEYBOARD_TOGGLE_GESTURE:
                        self._reset_debounce()

                if label == "Left":
                    right_pos, right_pinch = (sx, sy), pinch
                else:
                    left_pos,  left_pinch  = (sx, sy), pinch

        if self._keyboard_update_fn:
            self._keyboard_update_fn(left_pos, right_pos, left_pinch, right_pinch)

    # ── Gesture mode ──────────────────────────────────────────────────────

    def _process_gesture_mode(self, results, frame):
        if not results.multi_hand_landmarks:
            self._reset_debounce()
            self.gesture_queue.unlock_cursor()
            return

        hand_landmarks           = results.multi_hand_landmarks[0]
        features                 = LandmarkUtils.landmarks_to_features(hand_landmarks)
        tip                      = hand_landmarks.landmark[8]
        cursor_x, cursor_y       = self._map_cursor(tip.x, tip.y)
        gesture_name, confidence = self.classifier.predict(features)
        gesture_name = str(gesture_name)  # Normalize np.str_ → str

        # ── Air drawing intercept (FIXED: hold-to-draw, no conflict) ─────
        if self._air_draw and getattr(self.settings, 'air_drawing_enabled', True):
            draw_status = self._air_draw.process(
                gesture_name, tip.x, tip.y, confidence
            )
            # Block normal processing when ACTIVELY drawing a stroke
            if self._air_draw.is_drawing:
                if self.settings.show_debug_window:
                    pts = self._air_draw.get_stroke_pts()
                    h, w = frame.shape[:2]
                    for i in range(len(pts) - 1):
                        p1 = (int(pts[i][0]*w), int(pts[i][1]*h))
                        p2 = (int(pts[i+1][0]*w), int(pts[i+1][1]*h))
                        cv2.line(frame, p1, p2, (0, 200, 255), 2)
                    cv2.putText(frame, f"Drawing... {len(pts)} pts",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                                0.65, (0, 200, 255), 2)
                return  # skip normal gesture while stroke active

            # Block ALL gesture execution and cursor while holding fist
            if self._air_draw.is_holding:
                if self.settings.show_debug_window:
                    progress = self._air_draw.fist_hold_progress
                    cv2.putText(frame,
                                f"AirDraw hold: {progress*100:.0f}%",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                                0.65, (0, 200, 255), 2)
                return  # disable gestures + cursor during hold countdown

        # ── Per-gesture confidence threshold from adaptive engine ─────────
        adapted_threshold = self._conf_threshold(gesture_name)
        if confidence < adapted_threshold and gesture_name not in (CURSOR_MOVE, UNKNOWN):
            gesture_name = UNKNOWN

        # ── Step 5: Temporal filtering ────────────────────────────────────
        gesture_name = self._temporal_filter.update(gesture_name)

        # ── Step 7: Priority-based collision prevention ─────────────────
        # Safety timeout: force-release active gesture if stuck >1s
        if self._active_gesture and (time.time() - self._active_gesture_ts > 1.0):
            print(f"[Camera] Timeout released active gesture '{self._active_gesture}'")
            self._active_gesture = ""
            self._release_frame_count = 0

        incoming_priority = self._priority(gesture_name)
        active_priority   = self._priority(self._active_gesture)

        if gesture_name in (CURSOR_MOVE, UNKNOWN):
            # Count neutral frames; release lock after threshold
            self._release_frame_count += 1
            if self._release_frame_count >= self.settings.gesture_release_frames:
                if self._active_gesture:
                    print(f"[Camera] Released '{self._active_gesture}' after {self._release_frame_count} neutral frames")
                    self._active_gesture = ""
                if self._pending_gesture not in ("", CURSOR_MOVE):
                    self._reset_debounce()
                self._pending_gesture = CURSOR_MOVE
                self.gesture_queue.unlock_cursor()
            self.gesture_queue.put_cursor(cursor_x, cursor_y, confidence)

        else:
            self._release_frame_count = 0

            # Lower number = higher priority.
            # Only allow switch if incoming has strictly higher priority,
            # OR no active gesture is locked, OR same gesture continues.
            if (self._active_gesture == "" or
                gesture_name == self._active_gesture or
                incoming_priority < active_priority):

                if self._pending_gesture != gesture_name:
                    self.gesture_queue.lock_cursor()
                    self._pending_gesture = gesture_name
                    self._pending_frames  = 0
                    self._last_fired      = ""
                self._debounce_and_fire(gesture_name, confidence, cursor_x, cursor_y)

            else:
                # Suppressed by active higher-priority gesture
                if self.settings.show_debug_window:
                    cv2.putText(frame,
                                f"suppressed:{gesture_name} (active:{self._active_gesture})",
                                (10, 60), cv2.FONT_HERSHEY_SIMPLEX,
                                0.55, (0, 0, 255), 2)

        if self.settings.show_debug_window:
            self.mp_draw.draw_landmarks(
                frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
            )
            # Show adapted hold_frames in debug overlay
            adapted_hold = self._hold_frames(gesture_name)
            label = (f"{gesture_name} {confidence:.2f} "
                     f"[{self._pending_frames}/{adapted_hold}]")
            cv2.putText(frame, label, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 120), 2)

    # ── Debounce — uses per-gesture hold_frames from adaptive engine ──────

    def _debounce_and_fire(self, gesture: str, confidence: float, cx: int, cy: int):
        """
        Increments frame counter and fires when hold threshold reached.
        Called every frame the gesture is detected, including the first.

        Step 6: Two-tier cooldown
          * Global cooldown (2 frames) blocks ALL gestures after any fire,
            preventing rapid alternation between different gestures.
          * Per-gesture cooldown (6 frames) blocks the SAME gesture from
            re-firing, eliminating double-clicks while leaving other gestures
            available (e.g., scroll_up → scroll_down is still fast).
        """
        # Global refractory period
        if self._global_cooldown > 0:
            self._global_cooldown -= 1
            return

        # Per-gesture cooldown
        if self._per_gesture_cooldowns.get(gesture, 0) > 0:
            self._per_gesture_cooldowns[gesture] -= 1
            return

        self._pending_frames += 1
        hold_needed = self._hold_frames(gesture)

        if self._pending_frames >= hold_needed:
            if gesture != self._last_fired:
                self._last_fired      = gesture
                self._pending_frames  = 0
                self._global_cooldown = self.settings.global_cooldown_frames
                self._per_gesture_cooldowns[gesture] = self.settings.per_gesture_cooldown_frames
                # Step 7: lock this gesture as active until neutral frames release it
                self._active_gesture    = gesture
                self._active_gesture_ts = time.time()
                self.gesture_queue.put_action(GestureEvent(
                    name=gesture, confidence=confidence,
                    cursor_x=cx, cursor_y=cy,
                ))
                print(f"[Camera] Fired: {gesture} ({confidence:.2f}) "
                      f"hold={hold_needed}")

    def _reset_debounce(self):
        if self._pending_gesture not in ("", CURSOR_MOVE):
            self.gesture_queue.unlock_cursor()
        self._pending_gesture = ""
        self._pending_frames  = 0
        self._last_fired      = ""
        self._global_cooldown = 0
        self._per_gesture_cooldowns.clear()
        self._temporal_filter.reset()
        # Step 7: clear active gesture lock on hand-loss / full reset
        self._active_gesture = ""
        self._release_frame_count = 0

    def _map_cursor(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        margin    = 0.15
        clamped_x = max(margin, min(1 - margin, norm_x))
        clamped_y = max(margin, min(1 - margin, norm_y))
        mapped_x  = int((clamped_x - margin) / (1 - 2 * margin) * self.screen_w)
        mapped_y  = int((clamped_y - margin) / (1 - 2 * margin) * self.screen_h)
        return mapped_x, mapped_y

    def stop(self):
        self._stop_event.set()