"""
CameraThread — Webcam → MediaPipe → Classify → GestureQueue.

Three-fingers toggle fix:
  - When keyboard is OPEN, we still run gesture classification on one hand
  - If three_fingers is detected → fire show_keyboard (closes keyboard)
  - All other gestures while keyboard is open are ignored (no accidental clicks)
  - Two-hand hover/pinch tracking still works on the other hand simultaneously
"""

import threading
import time
import cv2
import mediapipe as mp
from typing import Optional, Tuple, Callable

from core.gesture_queue import GestureQueue, GestureEvent
from gestures.classifier import GestureClassifier, CURSOR_MOVE, UNKNOWN
from gestures.landmark_utils import LandmarkUtils
from config.settings import Settings

KEYBOARD_TOGGLE_GESTURE = "three_fingers"


class CameraThread(threading.Thread):

    def __init__(self, gesture_queue: GestureQueue, settings: Settings):
        super().__init__(name="CameraThread")
        self.gesture_queue = gesture_queue
        self.settings      = settings
        self._stop_event   = threading.Event()
        self._paused       = False
        self._pause_lock   = threading.Lock()

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

        import pyautogui
        self.screen_w, self.screen_h = pyautogui.size()

        # Gesture debounce (used in both modes)
        self._pending_gesture: str = ""
        self._pending_frames:  int = 0
        self._last_fired:      str = ""
        self._cooldown_frames: int = 0

    def set_keyboard_fns(self, update_fn: Callable, visible_fn: Callable):
        self._keyboard_update_fn  = update_fn
        self._keyboard_visible_fn = visible_fn

    # ── Pause / Resume ────────────────────────────────────────────────────

    def pause(self):
        with self._pause_lock:
            self._paused = True
        self.gesture_queue.unlock_cursor()
        print("[CameraThread] Paused — camera released.")

    def resume(self):
        with self._pause_lock:
            self._paused = False
        print("[CameraThread] Resumed.")

    def is_paused(self) -> bool:
        with self._pause_lock:
            return self._paused

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
                    print(f"[CameraThread] ERROR: Cannot open camera {self.settings.camera_index}")
                    time.sleep(1)
                    cap = None
                    continue
                print(f"[CameraThread] Camera {self.settings.camera_index} opened.")

            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

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
        """
        Keyboard open — two jobs:
          1. Classify gestures — ONLY fire three_fingers to close keyboard.
             All other gestures ignored to prevent accidental clicks.
          2. Feed both hand positions to the keyboard for hover/pinch typing.
        """
        left_pos    = None
        right_pos   = None
        left_pinch  = 1.0
        right_pinch = 1.0

        if results.multi_hand_landmarks and results.multi_handedness:
            for hl, hd in zip(results.multi_hand_landmarks, results.multi_handedness):
                label = hd.classification[0].label  # 'Left' or 'Right' (pre-flip)

                tip = hl.landmark[8]   # index fingertip
                sx  = int(tip.x * self.screen_w)
                sy  = int(tip.y * self.screen_h)

                features   = LandmarkUtils.landmarks_to_features(hl)
                pinch_dist = float(features[-1])

                # ── Classify this hand — only care about toggle gesture ───
                gesture_name, confidence = self.classifier.predict(features)
                if gesture_name == KEYBOARD_TOGGLE_GESTURE:
                    # Debounce the close gesture same as open
                    self._debounce_and_fire(
                        KEYBOARD_TOGGLE_GESTURE, confidence, sx, sy
                    )
                else:
                    # Not a toggle gesture — reset debounce so it
                    # doesn't accumulate across different gestures
                    if self._pending_gesture == KEYBOARD_TOGGLE_GESTURE:
                        self._reset_debounce()

                # ── Hand position for hover detection ─────────────────────
                # After cv2.flip: MediaPipe 'Left' = user's right hand
                if label == "Left":
                    right_pos   = (sx, sy)
                    right_pinch = pinch_dist
                else:
                    left_pos   = (sx, sy)
                    left_pinch = pinch_dist

                if self.settings.show_debug_window:
                    self.mp_draw.draw_landmarks(
                        frame, hl, self.mp_hands.HAND_CONNECTIONS
                    )
                    color = (255, 80, 0) if label == "Left" else (0, 200, 80)
                    cv2.circle(frame,
                               (int(tip.x * 640), int(tip.y * 480)),
                               10, color, -1)
                    cv2.putText(
                        frame,
                        f"{'R' if label=='Left' else 'L'} {gesture_name} p={pinch_dist:.2f}",
                        (int(tip.x * 640) + 12, int(tip.y * 480)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1,
                    )

        if self._keyboard_update_fn is not None:
            self._keyboard_update_fn(left_pos, right_pos, left_pinch, right_pinch)

    # ── Gesture mode ──────────────────────────────────────────────────────

    def _process_gesture_mode(self, results, frame):
        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks[0]
            features  = LandmarkUtils.landmarks_to_features(hand_landmarks)
            tip       = hand_landmarks.landmark[8]
            cursor_x, cursor_y = self._map_cursor(tip.x, tip.y)
            gesture_name, confidence = self.classifier.predict(features)

            if gesture_name in (CURSOR_MOVE, UNKNOWN):
                self.gesture_queue.unlock_cursor()
                self.gesture_queue.put_cursor(cursor_x, cursor_y, confidence)
                self._reset_debounce()
            else:
                if self._pending_gesture != gesture_name:
                    self.gesture_queue.lock_cursor()
                self._debounce_and_fire(gesture_name, confidence, cursor_x, cursor_y)

            if self.settings.show_debug_window:
                self.mp_draw.draw_landmarks(
                    frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
                )
                label = (f"{gesture_name} {confidence:.2f} "
                         f"[{self._pending_frames}/{self.settings.hold_frames}]")
                cv2.putText(frame, label, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 120), 2)
        else:
            self._reset_debounce()
            self.gesture_queue.unlock_cursor()

    # ── Debounce ──────────────────────────────────────────────────────────

    def _debounce_and_fire(self, gesture: str, confidence: float, cx: int, cy: int):
        if self._cooldown_frames > 0:
            self._cooldown_frames -= 1
            return
        if gesture == self._pending_gesture:
            self._pending_frames += 1
        else:
            self._pending_gesture = gesture
            self._pending_frames  = 1
            self._last_fired      = ""
        if self._pending_frames >= self.settings.hold_frames:
            if gesture != self._last_fired:
                self._last_fired      = gesture
                self._pending_frames  = 0
                self._cooldown_frames = self.settings.action_cooldown_frames
                self.gesture_queue.put_action(GestureEvent(
                    name=gesture, confidence=confidence,
                    cursor_x=cx, cursor_y=cy,
                ))
                print(f"[Camera] Fired: {gesture} ({confidence:.2f})")

    def _reset_debounce(self):
        if self._pending_gesture != "":
            self.gesture_queue.unlock_cursor()
        self._pending_gesture = ""
        self._pending_frames  = 0
        self._last_fired      = ""
        self._cooldown_frames = 0

    def _map_cursor(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        margin    = 0.15
        clamped_x = max(margin, min(1 - margin, norm_x))
        clamped_y = max(margin, min(1 - margin, norm_y))
        mapped_x  = int((clamped_x - margin) / (1 - 2 * margin) * self.screen_w)
        mapped_y  = int((clamped_y - margin) / (1 - 2 * margin) * self.screen_h)
        return mapped_x, mapped_y

    def stop(self):
        self._stop_event.set()