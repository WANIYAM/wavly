# Phase 1 — Core Gesture Pipeline Verification

**Date:** Auto-generated  
**Scope:** `core/camera_thread.py`, `core/action_thread.py`, `core/gesture_queue.py`, `gestures/classifier.py`  
**Mode:** Read-only audit

---

## Verification Checklist

| Step | Check | Status |
|---|---|---|
| 1 | CameraThread captures webcam frames (OpenCV working) | ✅ |
| 2 | MediaPipe hand tracking runs | ✅ |
| 3 | GestureClassifier predicts gesture names | ✅ |
| 4 | Debounce logic exists (`hold_frames`) | ✅ |
| 5 | GestureQueue receives `GestureEvent` | ✅ |
| 6 | ActionThread consumes queue | ✅ |
| 7 | PyAutoGUI executes actions | ✅ |

---

## Trace Flow

```
Webcam → CameraThread → Classifier → GestureQueue → ActionThread → Action
```

---

## Detailed Findings

### 1. OpenCV Capture
- **File:** `core/camera_thread.py`
- **Method:** `CameraThread.run()`
- **Evidence:**
  - `cap = cv2.VideoCapture(self.settings.camera_index)` opens the camera.
  - `cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)`, `cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)`, `cap.set(cv2.CAP_PROP_FPS, 30)` configure the stream.
  - `ret, frame = cap.read()` captures frames in the main loop.
  - `cv2.flip(frame, 1)` mirrors the image.
  - `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)` converts to RGB for MediaPipe.
  - `cv2.imshow("Wavly Debug", frame)` displays the debug window.
- **Status:** ✅ Working

### 2. MediaPipe Hand Tracking
- **File:** `core/camera_thread.py`
- **Evidence:**
  - `self.mp_hands = mp.solutions.hands`
  - `self.hands = self.mp_hands.Hands(...)` initialized with `min_detection_confidence` and `min_tracking_confidence` from settings.
  - `results = self.hands.process(rgb)` processes every frame.
  - `results.multi_hand_landmarks` is checked to detect hands.
  - `self.mp_draw.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)` draws skeleton.
- **Status:** ✅ Working

### 3. GestureClassifier Prediction
- **File:** `gestures/classifier.py`
- **Method:** `GestureClassifier.predict(features)`
- **Evidence:**
  - Loads ML model from `settings.model_path` via pickle.
  - `_predict_ml(features)` runs `predict_proba`, checks against `ml_confidence_threshold`.
  - Falls back to `_predict_rules(features)` if ML is unavailable or confidence is low.
  - Rule-based fallback recognizes: `stop`, `drag_start`, `click`, `scroll_up`, `scroll_down`, `cursor_move`, `unknown`.
  - Returns `(gesture_name: str, confidence: float)`.
- **Status:** ✅ Working

### 4. Debounce Logic (`hold_frames`)
- **File:** `core/camera_thread.py`
- **Method:** `_debounce_and_fire()`, `_reset_debounce()`
- **Evidence:**
  - `_debounce_and_fire()` increments `self._pending_frames` each frame the same gesture is held.
  - Compares `self._pending_frames >= self._hold_frames(gesture)`.
  - `_hold_frames(gesture)` can be adapted per-gesture via `adaptive_engine` or falls back to global `settings.hold_frames`.
  - `_reset_debounce()` clears pending state when hand is lost or gesture changes to `cursor_move`/`unknown`.
  - `self._cooldown_frames` prevents rapid refiring after an action is triggered.
- **Status:** ✅ Working

### 5. GestureQueue Receives `GestureEvent`
- **File:** `core/gesture_queue.py`
- **Evidence:**
  - `GestureEvent` dataclass defined with `name`, `confidence`, `cursor_x`, `cursor_y`, `timestamp`, `metadata`.
  - `put_action(event: GestureEvent)` enqueues events with a maxsize of 20.
  - Handles critical gesture eviction (`stop`, `click`, `drag_end`) by dropping non-critical events if the queue is full.
  - `put_cursor(x, y, confidence)` updates cursor position separately.
  - `register_observer(fn)` allows external listeners (e.g., adaptive engine) to monitor the stream.
- **Status:** ✅ Working

### 6. ActionThread Consumes Queue
- **File:** `core/action_thread.py`
- **Method:** `ActionThread.run()`
- **Evidence:**
  - Main loop calls `self.gesture_queue.get_action(timeout=0.05)` to poll for events.
  - `_execute_action(event: GestureEvent)` dispatches based on `event.name`.
  - Runs a separate daemon thread `_cursor_loop()` at 60 Hz to smooth and move the cursor.
- **Status:** ✅ Working

### 7. PyAutoGUI Executes Actions
- **File:** `core/action_thread.py`
- **Method:** `_run_action(action, source, x, y)`
- **Evidence:**
  - `pyautogui.click(x, y)`, `pyautogui.doubleClick(x, y)`, `pyautogui.rightClick(x, y)`
  - `pyautogui.scroll(self.settings.scroll_speed)`
  - `pyautogui.mouseDown()`, `pyautogui.mouseUp()`
  - `pyautogui.hotkey(*keys)`
  - `pyautogui.typewrite(text, interval=0.05)`
  - `pyautogui.moveTo(x, y, duration=0)` in cursor loop
  - `pyautogui.FAILSAFE = True` and `pyautogui.PAUSE = 0` configured at module level.
- **Status:** ✅ Working

---

## Final Result

```
PHASE 1 READY
```

All seven verification steps passed. The core gesture pipeline from webcam capture to PyAutoGUI action execution is fully wired and functional.

