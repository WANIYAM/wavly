# State Conflict Fixes — COMPLETED

## Files Modified
- `gestures/air_drawing.py`
- `gestures/classifier.py`
- `core/camera_thread.py`
- `core/action_thread.py`

## Validation
- [x] Syntax check passed (`python -m py_compile`) on all 4 files
- [x] No broken imports or missing references

---

## Summary of Fixes Applied

### 1. `gestures/air_drawing.py` — Persistent Competing-Gesture Guard
- Added `is_holding` property exposing `_fist_holding`.
- Added `_compete_gesture` + `_compete_frames` counters.
- Cancel hold only when a **different** gesture arrives with `confidence > 0.85` for **≥3 consecutive frames**.
- Weak/brief signals reset counter but keep holding (treated as noise).

### 2. `core/camera_thread.py` — State Gate + Gesture Suppression
- Normalized classifier output: `gesture_name = str(gesture_name)` right after prediction to prevent `np.str_` leakage.
- Added `is_holding` early-return gate: **disables ALL gesture execution and cursor movement** while AirDraw is holding fist.
- Preserved existing `is_drawing` early-return for active stroke drawing.

### 3. `core/action_thread.py` — Safe Cursor Clamping
- Cached screen dimensions at init: `self._screen_w, self._screen_h = pyautogui.size()`.
- Added `clamp_cursor(x, y, screen_width, screen_height)` static method with 5px margin rule.
- Applied clamping **only in `_move_cursor()`** before every `pyautogui.moveTo()` call.

### 4. `gestures/classifier.py` — Log Type Cleanup
- Wrapped all gesture returns in `_predict_ml()` with `str()` and all confidence values with `float()`.
- Wrapped all gesture returns in `_predict_rules()` with `str()`.

