# Hybrid Execution Flow Trace

**Test Case:** Voice = `"copy"`, Gesture = `"click"`  
**Path:** VoiceThread → GestureQueue → ActionThread → CommandQueue → IntentResolver → HybridBindings  
**Date:** Auto-generated trace — no code changes made.

---

## 1. VoiceThread (`core/voice_thread.py`)

### `_process_audio(audio)`

| Variable | Value |
|----------|-------|
| `transcript` after `_transcribe()` | `"copy"` (lowercased, stripped) |
| `action = self._resolver.resolve("copy")` | `"hotkey:ctrl+c"` |

- `CommandResolver` loads `config/voice_bindings.py`
- Exact match: `"copy"` → `"hotkey:ctrl+c"`

### `_dispatch(action="hotkey:ctrl+c", transcript="copy")`

Constructs `GestureEvent`:

| Field | Value |
|-------|-------|
| `name` | `"voice:hotkey:ctrl+c"` |
| `confidence` | `1.0` |
| `metadata` | `"copy"` ← **original transcript preserved here** |

Calls `gesture_queue.put_action(event)`.

---

## 2. GestureQueue (`core/gesture_queue.py`)

### `put_action(event)`

Receives:

| Field | Value |
|-------|-------|
| `event.name` | `"voice:hotkey:ctrl+c"` |
| `event.metadata` | `"copy"` |
| `event.confidence` | `1.0` |

- Stores in `self._action_queue` (maxsize=20)
- Updates `self._latest_event`
- Notifies observers (AdaptiveEngine, overlay, etc.)

**Data state:** Original transcript `"copy"` intact in `metadata`; resolved action `"hotkey:ctrl+c"` now encoded in `name`.

---

## 3. ActionThread (`core/action_thread.py`)

### `run()` → `_execute_action(event)`

| Variable | Value |
|----------|-------|
| `gesture = event.name` | `"voice:hotkey:ctrl+c"` |
| Detects `"voice:"` prefix? | **Yes** |
| `action = gesture[6:]` | `"hotkey:ctrl+c"` |

Routes to `_handle_voice_event(action="hotkey:ctrl+c", event=event)`.

### `_handle_voice_event(voice_action="hotkey:ctrl+c", event)`

| Variable | Value |
|----------|-------|
| `voice_phrase = event.metadata or voice_action` | `"copy"` |
| `self._intent_resolver.is_hybrid_available("copy")` | **`False`** |

**Why `False`?** `HYBRID_BINDINGS` keys are:
- `("open","point")`
- `("search","air_letter")`
- `("scroll_up","scroll_up")`
- `("scroll_down","scroll_down")`
- `("click","point")`

No entry has voice_action `"copy"`.

**Result:** Skips `CommandQueue` entirely. Executes voice-only immediately.

Calls `_run_action(action="hotkey:ctrl+c", source="voice", x, y)`:
- Executes `pyautogui.hotkey("ctrl", "c")`
- Logs: `[Action] 🎤 Voice (no hybrid) → hotkey:ctrl+c`

---

## 4. CommandQueue (`core/command_queue.py`)

### Status for this test case

| Detail | Value |
|--------|-------|
| `put_voice_event()` called? | **NO** |
| `self._pending` state | Empty `{}` |
| `PendingVoiceCommand` created? | **NO** |

**Data state:** CommandQueue has zero knowledge that voice `"copy"` ever arrived.

---

## 5. IntentResolver (`core/intent_resolver.py`)

### Status for this test case

| Detail | Value |
|--------|-------|
| `is_hybrid_available("copy")` called? | **YES** |
| Return value | `False` |
| `resolve_hybrid()` called? | **NO** |
| `HybridIntent` created? | **NO** |

---

## 6. HybridBindings (`config/hybrid_bindings.py`)

### Status for this test case

| Detail | Value |
|--------|-------|
| `HYBRID_BINDINGS` looked up? | **NO** |
| Hypothetical key if it were queried | `("copy", "click")` |
| Key exists in bindings? | **NO** |

Even if `is_hybrid_available` had returned `True`, the lookup key used by `resolve_hybrid()` would be:
- `voice_action = "copy"` (from `pending.transcript`)
- `gesture_type = "click"` (from `GESTURE_TO_HYBRID` mapping)
- Key: `("copy", "click")` — **not present** in `HYBRID_BINDINGS`.

---

## 7. Gesture `"click"` Arrives (Separate Event)

### GestureQueue

Receives `GestureEvent(name="click", confidence=0.82)` from classifier.
Stored in queue normally.

### ActionThread `_execute_action(event)`

| Variable | Value |
|----------|-------|
| `gesture` | `"click"` |
| Starts with `"voice:"`? | **No** |

Calls `_check_gesture_for_hybrid("click", event)`.

### `_check_gesture_for_hybrid("click", event)`

| Variable | Value |
|----------|-------|
| `base_gesture = gesture_type.split("_")[0]` | `"click"` |
| `hybrid_gesture = GESTURE_TO_HYBRID.get("click", "click")` | `"click"` |
| `result = self._command_queue.peek_most_recent()` | **`None`** |

- Returns immediately because no pending voice command exists.

### Continues to normal gesture execution

- `bindings.get("click", "click")` → `"click"`
- `_run_action("click", "click", x, y)` → `pyautogui.click(x, y)`

---

## Summary Table

| Stage | `voice_action` Value | Transcript Preserved? | Gesture Type | Hybrid Key Used | Match Result | Data Modified / Lost |
|---|---|---|---|---|---|---|
| VoiceThread | Resolved: `"hotkey:ctrl+c"` | ✅ Yes in `metadata="copy"` | N/A | N/A | N/A | Original `"copy"` moved to `metadata`; resolved action `"hotkey:ctrl+c"` placed in `event.name` |
| GestureQueue | `event.name="voice:hotkey:ctrl+c"` | ✅ Yes | N/A | N/A | N/A | None — stored as-is |
| ActionThread | `"hotkey:ctrl+c"` (stripped prefix) | ✅ Yes (`voice_phrase="copy"`) | N/A | N/A | Hybrid eligibility: **FAIL** | Eligibility check uses `voice_phrase="copy"`, NOT resolved `"hotkey:ctrl+c"`. Voice-only path taken. |
| CommandQueue | **NEVER RECEIVED** | N/A | N/A | N/A | N/A | Voice command lost from hybrid pipeline because `is_hybrid_available` was `False` before storage |
| IntentResolver | `is_hybrid_available("copy")` called | N/A | N/A | N/A | **FAIL** (returns `False`) | `resolve_hybrid()` never invoked |
| HybridBindings | **NEVER QUERIED** | N/A | N/A | `("copy", "click")` would be key | N/A | No lookup performed |
| Gesture `"click"` | N/A (gesture-only path) | N/A | Classifier: `"click"`; Mapped: `"click"` | N/A | No pending voice in queue | Executes as normal `click` |

---

## Critical Findings (No Code Changes Made)

1. **Voice `"copy"` never enters the hybrid pipeline.**
   `is_hybrid_available("copy")` returns `False` because `HYBRID_BINDINGS` contains no voice action `"copy"`. The command executes immediately as `ctrl+c`.

2. **Transcript is preserved but eligibility logic blocks hybrid pairing.**
   The original `"copy"` survives in `event.metadata` and is passed as `voice_phrase` to `is_hybrid_available()`. However, since `"copy"` is absent from hybrid bindings, the pairing opportunity is discarded before `CommandQueue` or `IntentResolver` are involved.

3. **Gesture `"click"` finds an empty CommandQueue.**
   When the gesture arrives, `_check_gesture_for_hybrid()` peeks the queue, gets `None`, and falls through to standard gesture execution.

4. **`voice_action` vs `voice_phrase` mismatch potential.**
   `CommandQueue.put_voice_event()` would store `voice_action="hotkey:ctrl+c"` (resolved action) and `transcript="copy"` (original). If `"copy"` were added to `HYBRID_BINDINGS`, `resolve_hybrid()` would receive `voice_action="copy"` (the transcript), not `"hotkey:ctrl+c"`. The hybrid binding key must use the spoken word `"copy"`, not the resolved keyboard shortcut.

5. **Two separate executions occur:**
   - Voice `"copy"` → `pyautogui.hotkey("ctrl", "c")`
   - Gesture `"click"` → `pyautogui.click()`
   - **No unified hybrid action is triggered.**

