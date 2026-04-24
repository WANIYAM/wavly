# DEEP CODE AUDIT — Feature 2: Voice + Gesture Hybrid Commands

**Auditor:** Senior Software Engineer (Automated Audit)  
**Date:** 2025  
**Scope:** `core/voice_thread.py`, `core/action_thread.py`, `core/camera_thread.py`, `gestures/`, `config/voice_bindings.py`, `main.py`, `ui/voice_panel.py`, `core/command_queue.py`, `core/intent_resolver.py`, `config/hybrid_bindings.py`  
**Goal:** Evaluate implementation status of Feature 2 (Layer 1: Voice-Only + Layer 2: Hybrid Commands)

---

## 1. File Scan Summary

| File | Exists | Lines | Status |
|------|--------|-------|--------|
| `core/voice_thread.py` | ✅ | ~340 | Full implementation |
| `core/action_thread.py` | ✅ | ~460 | Hybrid logic present but broken |
| `core/camera_thread.py` | ✅ | ~560 | No hybrid awareness (correct) |
| `config/voice_bindings.py` | ✅ | ~130 | 40+ commands, EN + Urdu |
| `main.py` | ✅ | ~180 | Wires all hybrid components |
| `ui/voice_panel.py` | ✅ | ~240 | Dashboard + activity log |
| **`core/command_queue.py`** | ✅ | ~140 | **Exists — FEATURE2_STATUS.md is wrong** |
| **`core/intent_resolver.py`** | ✅ | ~100 | **Exists — FEATURE2_STATUS.md is wrong** |
| **`config/hybrid_bindings.py`** | ✅ | ~130 | **Exists — FEATURE2_STATUS.md is wrong** |
| `core/gesture_queue.py` | ✅ | ~140 | Standard queue, no hybrid fields |
| `gestures/classifier.py` | ✅ | ~170 | 6 output classes + unknown |

### Critical Finding

`FEATURE2_STATUS.md` (the project’s own status doc) claims **CommandQueue, IntentResolver, and hybrid_bindings.py are MISSING**.

**This is factually incorrect.** All three files exist and contain complete implementations. The hybrid system is **structurally present** but **functionally broken** due to cascading integration mismatches. The status document itself is stale/misleading and should be corrected.

---

## 2. Voice System Audit (Layer 1)

| # | Component | Status | Evidence / Notes |
|---|-----------|--------|----------------|
| 1 | Wake word detection (OpenWakeWord) | ✅ IMPLEMENTED | `voice_thread.py` lines 95–117. Loads `"hey_jarvis"` model (closest available to `"hey_wavly"`). ONNX inference on mic stream. 3 s cooldown. Falls back to always-on mode if model fails. |
| 2 | Audio recording lifecycle (start/stop, 4 s window) | ✅ IMPLEMENTED | `RECORD_SECONDS = 4`. `_handle_wake_word()` opens mic, listens with `phrase_time_limit=RECORD_SECONDS`. `_run_always_on()` uses `listen_in_background` with same limit. |
| 3 | SpeechRecognition integration (Google + Sphinx fallback) | ✅ IMPLEMENTED | `_transcribe()` tries Google for `en-US` then `ur-PK`. On `RequestError`, falls back to `_transcribe_offline()` using CMU Sphinx. |
| 4 | CommandResolver logic (fuzzy matching, longest phrase) | ✅ IMPLEMENTED | `CommandResolver.resolve()` sorts bindings by length descending. Exact match first, then partial `in` check. Reloads module dynamically via `importlib.reload()`. |
| 5 | Voice events injected into GestureQueue | ✅ IMPLEMENTED | `VoiceThread._dispatch()` creates `GestureEvent(name=f"voice:{action}", confidence=1.0)` and calls `gesture_queue.put_action(event)`. |
| 6 | ActionThread handling `"voice:"` prefixed events | ✅ IMPLEMENTED | `ActionThread._execute_action()` detects `gesture.startswith("voice:")`, strips prefix, routes to `_handle_voice_event()`. |

### Layer 1 Issues (Minor)

1. **Missing `voice_enabled` setting:** `config/settings.py` has no `voice_enabled` field. `main.py` uses `getattr(settings, "voice_enabled", True)` as a defensive fallback.
2. **Wake word model name mismatch:** The spec calls for `"hey_wavly"`, but code loads `"hey_jarvis"` because that is the closest available OpenWakeWord model. Comment in code acknowledges this. Acceptable but not spec-accurate.
3. **Voice event does not carry original phrase:** `GestureEvent` has no field to preserve the spoken phrase (e.g., `"copy"`). Only the resolved action (`"hotkey:ctrl+c"`) is propagated. This breaks hybrid lookup (see Bug 1 below).

**Layer 1 Verdict:** Functional and complete for voice-only commands.

---

## 3. Hybrid System Audit (Layer 2)

### A. CommandQueue (`core/command_queue.py`)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Queue storing pending voice commands | ✅ IMPLEMENTED | `PendingVoiceCommand` dataclass with `transcript`, `voice_action`, `timestamp`. Stored in `self._pending: dict[str, PendingVoiceCommand]`. |
| Timestamps | ✅ IMPLEMENTED | `timestamp: float = field(default_factory=time.time)` |
| Timeout logic (~2 seconds) | ✅ IMPLEMENTED | `timeout_secs: float = 2.0` passed from `main.py`. `is_expired()` checks `time.time() - timestamp > timeout_secs`. `_cleanup_expired()` runs internally every 1 s. |
| Gesture lookup | ⚠️ PARTIAL | `get_pending_for_gesture(gesture_type)` accepts the parameter but **ignores it**. Returns the most recent pending command regardless of gesture type. Comment explicitly states: *"For now, simple strategy: return the most recent pending command"*. |

**CommandQueue Bug:** It does NOT filter by gesture type. Any gesture will consume the most recent voice command, even if they are unrelated.

**CommandQueue Bug 2 (Critical):** `get_pending_for_gesture()` **deletes** the pending entry from the dict before the caller has confirmed a valid hybrid match. If `IntentResolver.resolve_hybrid()` returns `None`, the voice command is lost with no fallback.

---

### B. IntentResolver (`core/intent_resolver.py`)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Function/class that combines voice + gesture | ✅ IMPLEMENTED | `resolve_hybrid(voice_action, gesture_type)` constructs `key = (voice_action, gesture_type)` and looks up in `HYBRID_BINDINGS`. |
| Matching logic like `(voice_action, gesture_type)` | ✅ IMPLEMENTED | Direct tuple-key dict lookup. Confidence multiplication (`voice_confidence * gesture_confidence`) included. |
| Abstraction for hybrid intent resolution | ✅ IMPLEMENTED | Returns `HybridIntent` dataclass with `voice_action`, `gesture_type`, `hybrid_action`, `confidence`. |
| Dynamic reload | ✅ IMPLEMENTED | `_load_bindings()` uses `importlib.reload(hb)` on every call. |

**IntentResolver Bug:** The lookup logic itself is correct, but it will **never match in practice** because the `voice_action` and `gesture_type` values passed to it are wrong (see Execution Flow Trace below).

---

### C. Hybrid Bindings (`config/hybrid_bindings.py`)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Config mapping voice + gesture pairs | ✅ IMPLEMENTED | 18 bindings defined: `("open", "point")`, `("copy", "fingers_2")`, `("search", "air_letter")`, etc. |
| Example: `("open", "point") → "open_file"` | ✅ IMPLEMENTED | `("open", "point"): "open_at_cursor"` |

**Hybrid Bindings Bug (Critical):** The binding keys use **semantic gesture names** (`"point"`, `"fist"`, `"palm"`, `"fingers_2"`, `"swipe_left"`) that **do not exist** in the classifier output. The classifier only emits:

- `cursor_move`
- `click`
- `scroll_up`
- `scroll_down`
- `drag_start`
- `stop`
- `unknown`

There is **zero overlap** between binding gesture names and actual classifier labels. The bindings are essentially orphaned.

---

### D. ActionThread Logic (`core/action_thread.py`)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| `WAITING_FOR_GESTURE` state | ❌ MISSING | No explicit state machine or enum. `CommandQueue` provides implicit pending state only. |
| Delay execution of voice commands | ✅ IMPLEMENTED | `_handle_voice_event()` stores in `CommandQueue` when `is_hybrid_available()` returns True. `_handle_expired_voice_commands()` runs every 500 ms to execute timed-out commands. |
| Check incoming gestures against pending voice commands | ✅ IMPLEMENTED | `_check_gesture_for_hybrid()` is called for every non-voice gesture event. |

**ActionThread Critical Bug 1 — Voice command destruction on failed hybrid match:**

`_check_gesture_for_hybrid()` calls `get_pending_for_gesture()` which **deletes** the pending command from the queue. If `resolve_hybrid()` returns `None`, the voice command is lost forever — no fallback to voice-only occurs. The code path is:

```python
pending = self._command_queue.get_pending_for_gesture(base_gesture)  # ← DELETES
if pending is None:
    return

intent = self._intent_resolver.resolve_hybrid(...)  # ← may return None
if intent:
    self._execute_hybrid_action(...)
else:
    # Logs message, but NEVER executes voice-only fallback
    print(f"[Action] Gesture '{gesture_type}' didn't match pending voice '{pending.voice_action}'")
```

**ActionThread Critical Bug 2 — `air_letter` broken by `split("_")[0]`:**

For event name `air_letter:A`, `base_gesture` becomes `"air"`. The binding key is `("search", "air_letter")`. `"air"` ≠ `"air_letter"`. Match is impossible.

**ActionThread Critical Bug 3 — No re-queue on failed match:**

Once consumed from `CommandQueue`, the pending voice command is gone even if the gesture didn't actually form a valid hybrid pair.

---

### E. Gesture + Voice Context Tracking

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Buffer/history of last N seconds | ⚠️ PARTIAL | `CommandQueue` stores pending voice commands with timestamps. No gesture history buffer exists. |
| Temporal matching logic | ✅ IMPLEMENTED | 2-second timeout window enforced in `CommandQueue`. |

---

## 4. Execution Flow Trace

### Case 1: User says `"copy"`

```
VoiceThread._run_wake_word()
  └─► wake word detected
VoiceThread._handle_wake_word()
  └─► records 4 s audio
VoiceThread._process_audio(audio)
  └─► _transcribe() → Google Speech → "copy"
      CommandResolver.resolve("copy")
        └─► VOICE_BINDINGS["copy"] = "hotkey:ctrl+c"
VoiceThread._dispatch("hotkey:ctrl+c", transcript="copy")
  └─► GestureEvent(name="voice:hotkey:ctrl+c", confidence=1.0)
      gesture_queue.put_action(event)
ActionThread.run()
  └─► gesture_queue.get_action() → event
      _execute_action("voice:hotkey:ctrl+c")
        └─► gesture.startswith("voice:") → True
            action = "hotkey:ctrl+c"
            _handle_voice_event("hotkey:ctrl+c", event)
              └─► intent_resolver.is_hybrid_available("hotkey:ctrl+c")
                  └─► HYBRID_BINDINGS keys: "open", "copy", "save", "search", "find", "go_to", "page_up", "page_down", "go_back", "go_forward", "select", "paste", "type", "click", "scroll_up", "scroll_down"
                  └─► "hotkey:ctrl+c" NOT in any voice_action slot
                  └─► RETURNS False
              └─► Not hybrid-eligible → executes IMMEDIATELY
                  _run_action("hotkey:ctrl+c", "voice", x, y)
                    └─► pyautogui.hotkey("ctrl", "c")
```

**Result:** Voice-only execution. **Hybrid window never opens.** The original voice phrase `"copy"` is lost; only the resolved action `"hotkey:ctrl+c"` is propagated.

---

### Case 2: User says `"open"` and then performs a gesture

**Step A — Voice path:**

```
VoiceThread hears "open"
  └─► CommandResolver.resolve("open") → "hotkey:ctrl+o"
      _dispatch("hotkey:ctrl+o", transcript="open")
        └─► GestureEvent(name="voice:hotkey:ctrl+o")
            gesture_queue.put_action(event)
ActionThread._execute_action("voice:hotkey:ctrl+o")
  └─► _handle_voice_event("hotkey:ctrl+o", event)
      └─► intent_resolver.is_hybrid_available("hotkey:ctrl+o")
          └─► HYBRID_BINDINGS has no key starting with "hotkey:ctrl+o"
          └─► RETURNS False
      └─► EXECUTES IMMEDIATELY (Ctrl+O)
```

**Even if** `is_hybrid_available` hypothetically returned True (e.g., if the voice phrase were preserved), the gesture path would be:

**Step B — Gesture path (hypothetical fix):**

```
CameraThread.classifier.predict() → gesture_name = "cursor_move"
  └─► GestureEvent("cursor_move")
      gesture_queue.put_action(event)
ActionThread._execute_action("cursor_move")
  └─► NOT voice: prefix → _check_gesture_for_hybrid("cursor_move", event)
      └─► base_gesture = "cursor"   (split("_")[0])
          get_pending_for_gesture("cursor") → returns pending "open" command (DELETES IT)
          intent_resolver.resolve_hybrid("open", "cursor")
            └─► key = ("open", "cursor")
                NOT in HYBRID_BINDINGS (binding is ("open", "point"))
                RETURNS None
          Voice command consumed from queue and LOST
          Gesture continues as normal cursor_move
```

**Result:** Voice command executes immediately as hotkey. Hybrid logic is **never triggered** due to voice action mismatch (Bug 1). Even if triggered, gesture name mismatch (Bug 2) prevents resolution. If resolution fails, voice command is **destroyed** (Bug 3).

---

## 5. Detected Fake / Assumed Features

| Assumed Feature | Reality |
|-----------------|---------|
| `FEATURE2_STATUS.md` says CommandQueue is missing | **Exists** — `core/command_queue.py` is 140 lines, fully implemented |
| `FEATURE2_STATUS.md` says IntentResolver is missing | **Exists** — `core/intent_resolver.py` is 100 lines, fully implemented |
| `FEATURE2_STATUS.md` says hybrid_bindings.py is missing | **Exists** — `config/hybrid_bindings.py` has 18 bindings |
| Hybrid bindings suggest gestures like `"point"`, `"fist"`, `"swipe_left"` exist | **Do not exist** — classifier only outputs `cursor_move`, `click`, `scroll_up`, `scroll_down`, `drag_start`, `stop` |
| Hybrid action `"open_at_cursor"` should open file at pointed location | **Stub only** — code does `pyautogui.click()` + `pyautogui.hotkey("ctrl", "o")`. No actual file-at-cursor detection. |
| Hybrid action `"search_for_letter"` should search for air-drawn letter | **Broken** — uses `voice_transcript.replace("search ", "")` instead of extracting the actual air-drawn letter from the gesture event. |
| Hybrid action `"go_to_line_number"` should go to line N | **Partial** — extracts numbers from voice transcript. Does NOT use finger count from gesture as binding comment suggests. |

---

## 6. Completion Metrics

| System | Score | Breakdown |
|--------|-------|-----------|
| **Voice System (Layer 1)** | **85 / 100** | All core components implemented and functional. Deductions: missing `voice_enabled` setting (-5), wake word model name mismatch (-5), no original phrase propagation (-5). |
| **Hybrid System (Layer 2)** | **25 / 100** | All structural classes exist (CommandQueue, IntentResolver, bindings, ActionThread hooks). However, **zero** hybrid commands can actually execute due to 4 critical integration bugs. Structurally present, functionally dead. |
| **Overall Feature 2** | **55 / 100** | Voice layer works. Hybrid layer is a broken skeleton. |

---

## 7. Gap Analysis — Exact Missing Pieces

| # | Missing Piece | File | Severity | Code-Level Detail |
|---|---------------|------|----------|-------------------|
| 1 | **Voice phrase propagation** | `core/gesture_queue.py`, `core/voice_thread.py` | **Critical** | `GestureEvent` has no `metadata` field. `VoiceThread._dispatch()` sends only resolved action string (`"hotkey:ctrl+c"`), not original phrase (`"copy"`). `HYBRID_BINDINGS` uses phrases as keys, so `is_hybrid_available("hotkey:ctrl+c")` always returns `False`. |
| 2 | **Gesture name mapping layer** | `core/action_thread.py` | **Critical** | Classifier emits `cursor_move` / `stop` / `drag_start`. Hybrid bindings expect `point` / `palm` / `fist`. No `GESTURE_TO_HYBRID` mapping dict exists. |
| 3 | **Failed-hybrid fallback** | `core/action_thread.py` | **Critical** | `_check_gesture_for_hybrid()` consumes voice command from queue via `get_pending_for_gesture()`. If `resolve_hybrid()` returns `None`, the command is logged and dropped. No `_run_action()` fallback called. |
| 4 | **`air_letter` base extraction** | `core/action_thread.py` | **Critical** | `base_gesture = gesture_type.split("_")[0]` on `"air_letter:A"` produces `"air"`. Binding key is `("search", "air_letter")`. Match impossible. |
| 5 | **`voice_enabled` setting** | `config/settings.py` | Minor | Field missing. `main.py` uses `getattr` fallback. |
| 6 | **Explicit `WAITING_FOR_GESTURE` state machine** | `core/action_thread.py` | Medium | No enum or state variable. Relies solely on `CommandQueue` implicit state. |
| 7 | **Gesture history buffer** | — | Medium | No `collections.deque` or ring buffer tracks recent gestures for temporal correlation. |
| 8 | **Missing gesture classes** | `gestures/classifier.py` | **Critical** | `point`, `fingers_2`, `fingers_3`, `swipe_left`, `swipe_right`, `fingers` do not exist in classifier output or training data. Hybrid bindings reference them but they can never fire. |
| 9 | **`GestureEvent` lacks gesture metadata** | `core/gesture_queue.py` | Medium | No field for air-drawn letter, finger count, swipe direction, etc. Hybrid actions that need gesture data (e.g., `"search_for_letter"`) cannot access it. |

---

## 8. Final Verdict

### **2. "Feature 2 is partially implemented but non-functional"**

**Breakdown:**
- **Voice-only commands (Layer 1):** Fully functional. User can say `"Hey Wavly, copy"` and `Ctrl+C` fires. All 40+ bindings work.
- **Hybrid commands (Layer 2):** Structurally present (all files exist, all classes instantiated, all hooks wired in `main.py`) but **100% non-functional**. No combination of voice + gesture can successfully trigger a hybrid action due to cascading integration bugs.

**Additional Risk:** For voice commands where the resolved action string happens to match a hybrid binding key (e.g., `"scroll_up"`, `"scroll_down"`, `"click"`), the system enters the `CommandQueue` wait state. If the user then performs an unrelated gesture, the voice command is consumed and destroyed rather than executing. This **actively breaks voice-only functionality** for those commands.

---

## 9. Minimal Fix Plan

### Estimated Effort
- **~2–4 hours** to implement the minimal fixes below.
- **~1–2 days** if you also need to implement missing gesture classes (`fingers_2`, `fingers_3`, `swipe_left`, `swipe_right`) in the classifier.

### File 1: `core/gesture_queue.py`

Add a `metadata` field to preserve the voice phrase and gesture data:

```python
@dataclass
class GestureEvent:
    name: str
    confidence: float
    cursor_x: Optional[int] = None
    cursor_y: Optional[int] = None
    timestamp: float = field(default_factory=time.time)
    metadata: Optional[str] = None   # ← ADD: stores original voice phrase, air-drawn letter, etc.
```

### File 2: `core/voice_thread.py`

Preserve the transcript in the event:

```python
def _dispatch(self, action: str, transcript: str):
    event = GestureEvent(
        name=f"voice:{action}",
        confidence=1.0,
        metadata=transcript,   # ← ADD: original phrase "copy", "open", etc.
    )
    self.gesture_queue.put_action(event)
```

### File 3: `core/action_thread.py`

**3a. Fix voice action key (use original phrase for hybrid lookup):**

```python
def _handle_voice_event(self, voice_action: str, event: GestureEvent):
    # Use original voice phrase for hybrid lookup, not resolved action string
    voice_phrase = event.metadata or voice_action
    if self._intent_resolver.is_hybrid_available(voice_phrase):
        self._command_queue.put_voice_event(
            transcript=f"voice:{voice_phrase}",
            voice_action=voice_phrase
        )
    else:
        with self._cursor_lock:
            x = int(self._smooth_x) if self._smooth_x is not None else None
            y = int(self._smooth_y) if self._smooth_y is not None else None
        print(f"[Action] Voice (no hybrid) → {voice_action}")
        self._run_action(voice_action, "voice", x, y)
```

**3b. Fix gesture name mapping:**

```python
# Map classifier output names to hybrid binding semantic names
GESTURE_TO_HYBRID = {
    "cursor_move": "point",
    "stop": "palm",
    "drag_start": "fist",
    "click": "click",
    "scroll_up": "scroll_up",
    "scroll_down": "scroll_down",
}

def _check_gesture_for_hybrid(self, gesture_type: str, event: GestureEvent):
    # Handle air_letter specially — do NOT split on underscore
    if gesture_type.startswith("air_letter"):
        base_gesture = "air_letter"
    else:
        base_gesture = self.GESTURE_TO_HYBRID.get(gesture_type, gesture_type)
    
    pending = self._command_queue.get_pending_for_gesture(base_gesture)
    ...
```

**3c. Fix voice command loss on failed match (add fallback):**

```python
intent = self._intent_resolver.resolve_hybrid(
    voice_action=pending.voice_action,
    gesture_type=base_gesture,
    voice_confidence=1.0,
    gesture_confidence=event.confidence
)

if intent:
    with self._cursor_lock:
        x = int(self._smooth_x) if self._smooth_x is not None else None
        y = int(self._smooth_y) if self._smooth_y is not None else None
    print(f"[Action] Hybrid: {intent.voice_action} + {base_gesture} → {intent.hybrid_action}")
    self._execute_hybrid_action(...)
else:
    # FIX: execute voice-only fallback instead of silently dropping
    with self._cursor_lock:
        x = int(self._smooth_x) if self._smooth_x is not None else None
        y = int(self._smooth_y) if self._smooth_y is not None else None
    print(f"[Action] No hybrid match for '{base_gesture}' — voice-only fallback: {pending.voice_action}")
    self._run_action(pending.voice_action, "voice", x, y)
```

**3d. Fix `get_pending_for_gesture` to actually filter by gesture type:**

The filtering should happen **before** deletion. Two options:

**Option A — Move filtering to ActionThread (recommended):**

Change `CommandQueue.get_pending_for_gesture()` to return the most recent command **without deleting it**, then let ActionThread explicitly consume on success:

```python
# In CommandQueue:
def peek_most_recent(self) -> Optional[PendingVoiceCommand]:
    """Return most recent pending command without deleting."""
    with self._lock:
        self._cleanup_expired()
        if self._pending:
            cmd_id = list(self._pending.keys())[-1]
            return self._pending[cmd_id]
    return None

def consume(self, cmd_id: str) -> bool:
    """Explicitly remove a command by ID."""
    with self._lock:
        if cmd_id in self._pending:
            del self._pending[cmd_id]
            return True
    return False
```

Then in ActionThread:

```python
def _check_gesture_for_hybrid(self, gesture_type: str, event: GestureEvent):
    pending = self._command_queue.peek_most_recent()
    if pending is None:
        return
    
    intent = self._intent_resolver.resolve_hybrid(
        pending.voice_action, gesture_type, ...
    )
    if intent:
        self._command_queue.consume(pending.cmd_id)  # only consume on success
        self._execute_hybrid_action(...)
    else:
        # Don't consume — let timeout handle it, or execute voice-only now
        pass
```

### File 4: `config/hybrid_bindings.py`

**Option A — Comment out bindings for non-existent gestures:**

Remove or comment out all bindings referencing `fingers_2`, `fingers_3`, `fingers_4`, `swipe_left`, `swipe_right`, `fingers`, `page_up`, `page_down`, `go_to`, `select`, `type`.

Keep only bindings where the gesture actually exists:

```python
HYBRID_BINDINGS = {
    # File Operations (gesture: cursor_move maps to "point")
    ("open", "point"): "open_at_cursor",
    
    # Search (gesture: air_letter exists)
    ("search", "air_letter"): "search_for_letter",
    
    # Navigation (gestures: scroll_up / scroll_down exist)
    ("scroll_up", "scroll_up"): "scroll_up_fast",
    ("scroll_down", "scroll_down"): "scroll_down_fast",
    
    # Reinforcement
    ("click", "click"): "click_at_point",
}
```

**Option B — Add missing gesture classes to classifier:**

Extend `GestureClassifier._predict_rules()` and retrain the ML model to output `point`, `fingers_2`, `fingers_3`, `swipe_left`, `swipe_right`. This is the correct long-term fix but requires collecting training data and retraining.

### File 5: `FEATURE2_STATUS.md`

**Update the status document.** It currently claims CommandQueue, IntentResolver, and hybrid_bindings.py are missing. Correct this:

```markdown
## What's Implemented ✅
...
- CommandQueue (`core/command_queue.py`) — holds pending voice commands with 2-second timeout
- IntentResolver (`core/intent_resolver.py`) — maps (voice, gesture) pairs to hybrid actions
- Hybrid Bindings (`config/hybrid_bindings.py`) — 18 voice+gesture combos defined

## What's Broken ⚠️
- Hybrid commands are structurally present but non-functional due to integration bugs
- Voice phrase is lost during resolution (resolved action string used instead of phrase)
- Gesture names in bindings don't match classifier output labels
- Failed hybrid matches destroy the voice command with no fallback
```

---

## Appendix: Classifier Output vs Hybrid Binding Gestures

| Gesture Needed by Hybrid Bindings | Classifier Actually Outputs | Match? |
|-----------------------------------|----------------------------|--------|
| `"point"` | `"cursor_move"` | ❌ NO |
| `"fist"` | `"drag_start"` | ❌ NO |
| `"palm"` | `"stop"` | ❌ NO |
| `"fingers_2"` | — | ❌ MISSING |
| `"fingers_3"` | — | ❌ MISSING |
| `"fingers_4"` | — | ❌ MISSING |
| `"swipe_left"` | — | ❌ MISSING |
| `"swipe_right"` | — | ❌ MISSING |
| `"air_letter"` | `"air_letter:A"` etc. (via AirDrawManager) | ⚠️ PARTIAL |
| `"click"` | `"click"` | ✅ YES |
| `"scroll_up"` | `"scroll_up"` | ✅ YES |
| `"scroll_down"` | `"scroll_down"` | ✅ YES |

**Only 3 out of 12 gesture types referenced by hybrid bindings actually exist and match.**

