# Phase 3 Verification Audit

**Date:** Auto-generated  
**Scope:** Air Drawing, Context Awareness, On-Screen Keyboard  
**Status:** ✅ PHASE 3 READY

---

## Air Draw

### 1. Fist hold (1.5s) activates draw mode
- **Location:** `gestures/air_drawing.py` — `AirDrawManager`
- `START_GESTURE = "drag_start"` (fist)
- `HOLD_TO_DRAW_SECS = 1.5`
- `process()` tracks `_fist_hold_start`; when `held_secs >= 1.5`, sets `_drawing = True` and starts `StrokeBuffer`
- Competing-gesture guard (≥3 frames @ >0.85) cancels accidental holds
- **Result:** ✅ PASS

### 2. Stroke buffer collects points
- **Location:** `gestures/air_drawing.py` — `StrokeBuffer`
- `deque(maxlen=120)` stores `(x, y)` tuples while `_active = True`
- `add(x, y)` called every frame from `CameraThread` when `is_drawing`
- `MIN_POINTS = 12` prevents classification of too-short strokes
- **Result:** ✅ PASS

### 3. Model predicts letter
- **Location:** `gestures/air_drawing.py` — `AirDrawRecognizer`
- Loads `models/air_draw_model.pkl` (sklearn Pipeline: StandardScaler + SVC with `probability=True`)
- `predict()` converts stroke → 28×28 image → flattened features → `predict_proba`
- Confidence threshold `>= 0.60` required; returns `(letter, confidence)`
- Trainer script (`gestures/air_draw_trainer.py`) exists for retraining
- **Result:** ✅ PASS

### 4. Letter triggers action via `air_draw_bindings`
- **Location:** `core/action_thread.py` + `config/air_draw_bindings.py`
- `CameraThread._on_air_letter()` queues `GestureEvent(name=f"air_letter:{letter}")`
- `ActionThread._execute_action()` detects `air_letter:` prefix → `_execute_letter()`
- `_get_air_draw_action()` dynamically reloads `config.air_draw_bindings.AIR_DRAW_BINDINGS`
- Supports `hotkey:`, `run:`, `type:` action formats
- **Result:** ✅ PASS

---

## Context Awareness

### 1. Active window detection works (psutil / win32)
- **Location:** `core/context_manager.py` — `ContextManager`
- Platform-gated imports: `win32gui`, `win32process`, `psutil` (Windows)
- `_get_active_process()`:
  - `win32gui.GetForegroundWindow()` → hwnd
  - `win32process.GetWindowThreadProcessId()` → pid
  - `psutil.Process(pid).name().lower()` → process name
- Graceful fallback when deps missing (`WIN32_AVAILABLE = False` → default context)
- **Result:** ✅ PASS

### 2. Context profiles exist
- **Location:** `core/context_manager.py` — `CONTEXT_PROFILES`
- Five profiles defined:
  - `browser` — Chrome, Firefox, Edge, Brave, Opera
  - `editor` — VS Code, PyCharm, Sublime, Notepad++, Vim
  - `media` — Spotify, VLC, WMP, Groove, MusicBee
  - `presentation` — PowerPoint, LibreOffice, Keynote
  - `files` — Explorer, Nautilus, Dolphin, Thunar
- Each profile has `name`, `emoji`, `processes` list, and `overrides` dict
- `DEFAULT_CONTEXT` provided as fallback
- **Result:** ✅ PASS

### 3. Gesture behavior changes per app
- **Location:** `core/context_manager.py` + `core/action_thread.py`
- `ContextManager.resolve_action(gesture, default_action)` looks up override for current context
- `ActionThread._execute_action()` calls `self._context_mgr.resolve_action(gesture, default_action)` before executing
- Examples: `drag_start` → undo in editor, play/pause in media, previous slide in presentation
- Thread-safe: `_current` protected by `threading.Lock`
- **Result:** ✅ PASS

---

## On-Screen Keyboard

### 1. 3-finger gesture toggles keyboard
- **Location:** `core/camera_thread.py` + `config/gesture_bindings.py`
- `KEYBOARD_TOGGLE_GESTURE = "three_fingers"`
- Gesture bindings map `"three_fingers": "show_keyboard"`
- `ActionThread` handles `show_keyboard` action by calling `keyboard_toggle()`
- Works in both directions (open when closed, close when open)
- **Result:** ✅ PASS

### 2. Two-hand tracking works
- **Location:** `core/camera_thread.py` + `ui/keyboard.py`
- MediaPipe initialized with `max_num_hands=2`
- `_process_keyboard_mode()` iterates `multi_hand_landmarks` + `multi_handedness`
- Mirror-correct mapping: MediaPipe "Left" label → user's right hand, "Right" → user's left hand
- Positions & pinch distances passed to `OnScreenKeyboard.update_hands(left, right, left_pinch, right_pinch)` via `QMetaObject.invokeMethod` (thread-safe Qt slot)
- Keyboard UI shows blue dot for left hand, green dot for right hand
- **Result:** ✅ PASS

### 3. Pinch triggers key press
- **Location:** `ui/keyboard.py` — `OnScreenKeyboard._handle_pinch()`
- `PINCH_THRESHOLD = 0.18` (thumb-index distance, normalized by palm size from `LandmarkUtils`)
- `PINCH_DEBOUNCE = 6` frames (~200 ms) prevents accidental repeats
- Per-hand state tracking: `_lframes` / `_rframes` + `_lfired` / `_rfired`
- On confirmed pinch, `_on_key(btn.key_label)` executes:
  - Special keys: Backspace, Enter, Shift, Caps, Space via `pyautogui.press()`
  - Regular keys: `_type_char()` via clipboard paste (supports all Unicode)
- **Result:** ✅ PASS

---

## Summary

| Feature      | Status |
|--------------|--------|
| Air Draw     | ✅     |
| Context      | ✅     |
| Keyboard     | ✅     |

**FINAL VERDICT:** PHASE 3 READY

