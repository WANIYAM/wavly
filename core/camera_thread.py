"""
CameraThread — Webcam → MediaPipe → Classify → GestureQueue.

KEY FIX: Cursor is locked the moment a non-cursor gesture starts
accumulating debounce frames. This means the cursor is frozen at the
intended target position for the entire debounce window (8 frames),
not just after the click fires.

Flow:
  cursor_move detected → put_cursor() → cursor moves freely
  click detected frame 1 → lock_cursor() → cursor freezes HERE
  click detected frame 2–8 → cursor stays frozen
  click fires → put_action() → action thread clicks frozen position
  gesture released → unlock_cursor() → cursor moves freely again
"""

import threading
import time
import cv2
import mediapipe as mp
from typing import Optional, Tuple

from core.gesture_queue import GestureQueue, GestureEvent
from gestures.classifier import GestureClassifier, CURSOR_MOVE, UNKNOWN
from gestures.landmark_utils import LandmarkUtils
from config.settings import Settings


class CameraThread(threading.Thread):

    def __init__(self, gesture_queue: GestureQueue, settings: Settings):
        super().__init__(name="CameraThread")
        self.gesture_queue = gesture_queue
        self.settings = settings
        self._stop_event = threading.Event()

        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=settings.min_detection_confidence,
            min_tracking_confidence=settings.min_tracking_confidence,
        )

        self.classifier = GestureClassifier(settings)

        import pyautogui
        self.screen_w, self.screen_h = pyautogui.size()

        # Debounce state
        self._pending_gesture: str = ""
        self._pending_frames: int = 0
        self._last_fired: str = ""
        self._cooldown_frames: int = 0

    def run(self):
        cap = cv2.VideoCapture(self.settings.camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)

        if not cap.isOpened():
            print(f"[CameraThread] ERROR: Cannot open camera {self.settings.camera_index}")
            return

        print(f"[CameraThread] Camera {self.settings.camera_index} opened.")

        while not self._stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = self.hands.process(rgb)
            rgb.flags.writeable = True

            if results.multi_hand_landmarks:
                hand_landmarks = results.multi_hand_landmarks[0]
                features = LandmarkUtils.landmarks_to_features(hand_landmarks)

                tip = hand_landmarks.landmark[8]
                cursor_x, cursor_y = self._map_cursor(tip.x, tip.y)
                gesture_name, confidence = self.classifier.predict(features)

                if gesture_name == CURSOR_MOVE or gesture_name == UNKNOWN:
                    # Free cursor movement
                    self.gesture_queue.unlock_cursor()
                    self.gesture_queue.put_cursor(cursor_x, cursor_y, confidence)
                    self._reset_debounce()
                else:
                    # Action gesture — lock cursor on FIRST frame of detection
                    # so it doesn't drift during the debounce window
                    if self._pending_gesture != gesture_name:
                        # New action gesture starting — lock now
                        self.gesture_queue.lock_cursor()

                    self._debounce_and_fire(gesture_name, confidence, cursor_x, cursor_y)

                if self.settings.show_debug_window:
                    self.mp_draw.draw_landmarks(
                        frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
                    )
                    label = f"{gesture_name} {confidence:.2f} [{self._pending_frames}/{self.settings.hold_frames}]"
                    cv2.putText(frame, label, (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 120), 2)
            else:
                self._reset_debounce()
                self.gesture_queue.unlock_cursor()

            if self.settings.show_debug_window:
                cv2.imshow("Wavly Debug", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        cap.release()
        cv2.destroyAllWindows()
        print("[CameraThread] Stopped.")

    def _debounce_and_fire(self, gesture: str, confidence: float, cx: int, cy: int):
        if self._cooldown_frames > 0:
            self._cooldown_frames -= 1
            return

        if gesture == self._pending_gesture:
            self._pending_frames += 1
        else:
            self._pending_gesture = gesture
            self._pending_frames = 1
            self._last_fired = ""

        if self._pending_frames >= self.settings.hold_frames:
            if gesture != self._last_fired:
                self._last_fired = gesture
                self._pending_frames = 0
                self._cooldown_frames = self.settings.action_cooldown_frames

                self.gesture_queue.put_action(GestureEvent(
                    name=gesture,
                    confidence=confidence,
                    cursor_x=cx,
                    cursor_y=cy,
                ))
                print(f"[Camera] Fired: {gesture} ({confidence:.2f})")

    def _reset_debounce(self):
        if self._pending_gesture != "":
            # Was tracking an action gesture — unlock cursor on release
            self.gesture_queue.unlock_cursor()
        self._pending_gesture = ""
        self._pending_frames = 0
        self._last_fired = ""
        self._cooldown_frames = 0

    def _map_cursor(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        margin = 0.15
        clamped_x = max(margin, min(1 - margin, norm_x))
        clamped_y = max(margin, min(1 - margin, norm_y))
        mapped_x = int((clamped_x - margin) / (1 - 2 * margin) * self.screen_w)
        mapped_y = int((clamped_y - margin) / (1 - 2 * margin) * self.screen_h)
        return mapped_x, mapped_y

    def stop(self):
        self._stop_event.set()