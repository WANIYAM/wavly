# CommandQueue Integration Audit

**Scope:** `core/command_queue.py`, `core/voice_thread.py`, `core/action_thread.py`  
**Date:** Audit Phase  
**Objective:** Verify VoiceThread → CommandQueue path and identify pipeline breaks.

---

## 1. VoiceThread calls CommandQueue.put_voice_event()?

**NO.**

`VoiceThread._dispatch()` (line ~291 in `voice_thread.py`) creates a `GestureEvent` and pushes it exclusively to `self.gesture_queue.put_action(event)`. It never touches `CommandQueue`.

```python
def _dispatch(self, action: str, transcript: str):
    event = GestureEvent(
        name=f"voice:{action}",
        confidence=1.0,
        metadata=transcript,
    )
    self.gesture_queue.put_action(event)   # ← Only destination
```

---

## 2. Why CommandQueue is bypassed

VoiceThread's constructor signature only accepts `gesture_queue: GestureQueue`. It has **no reference to CommandQueue** and receives none in `main.py`.

Its own docstring explicitly states the design choice:  
> "Fires GestureEvent through GestureQueue (same pipeline as gestures)"

VoiceThread treats voice commands as gesture events (`name="voice:{action}"`), routing them through the gesture pipeline rather than the hybrid-pending queue.

---

## 3. Conditions required for voice to enter CommandQueue

Voice reaches CommandQueue only via an **indirect, conditional path**:

| Step | Location | Condition |
|------|----------|-----------|
| 1 | `VoiceThread._dispatch()` | Voice event emitted to `GestureQueue` |
| 2 | `ActionThread.run()` | Event dequeued from `gesture_queue.get_action()` |
| 3 | `ActionThread._execute_action()` | Event name starts with `"voice:"` prefix |
| 4 | `ActionThread._handle_voice_event()` | Invoked with parsed voice action |
| 5 | `IntentResolver.is_hybrid_available(voice_phrase)` | Must return **`True`** |
| 6 | `ActionThread._handle_voice_event()` | Calls `self._command_queue.put_voice_event(...)` |

**Critical gate:** If `is_hybrid_available()` returns `False`, the voice command is executed immediately as voice-only via `_run_action()` and **never enters CommandQueue**.

---

## 4. ActionThread reads CommandQueue for hybrid resolution?

**YES.**

ActionThread reads from `CommandQueue` in two places:

1. **`_check_gesture_for_hybrid()`** — When a gesture arrives, it calls `peek_most_recent()` to check for pending voice commands. If a hybrid intent resolves successfully, it `consume()`s the command and executes the hybrid action.

2. **`_handle_expired_voice_commands()`** — Called every 500ms in the main loop. Retrieves expired commands via `get_and_clear_expired()` and executes them as voice-only fallbacks.

So ActionThread **both writes to and reads from** CommandQueue, but only for hybrid-eligible voice commands.

---

## 5. Pipeline Break Location

### Voice → CommandQueue direct path: **NO**

### Exact break location

**File:** `core/voice_thread.py`  
**Function:** `VoiceThread._dispatch()`

### Root cause

The `CommandQueue` docstring describes an intended timeline:

> t=0: Voice command "open" → stored in CommandQueue with timestamp

However, the actual implementation routes voice through `GestureQueue` first. Voice only enters `CommandQueue` after:
- `GestureQueue` enqueue/dequeue latency
- ActionThread prefix detection (`"voice:"`)
- `IntentResolver.is_hybrid_available()` eligibility check

This creates a **latency gap** and a **conditional entry gate** that prevents voice from entering CommandQueue immediately at recognition time.

Additionally, in `main.py`, `VoiceThread` and `ActionThread` do **not** share a `CommandQueue` instance. `ActionThread` constructs its own internally (`command_queue=None` → `CommandQueue()`), so VoiceThread has no object to call even if it were modified.

---

## Required Fix Area

**File:** `core/voice_thread.py`  
**Function:** `VoiceThread._dispatch()`

VoiceThread must be injected with a shared `CommandQueue` instance (wired through `main.py`) so it can call `put_voice_event()` immediately upon voice recognition, ensuring the 2-second pairing window starts at t=0 regardless of `GestureQueue` latency or hybrid eligibility pre-checks.

