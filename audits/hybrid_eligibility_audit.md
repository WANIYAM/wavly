# Hybrid Eligibility System Audit

## Scope
- `core/intent_resolver.py` — `is_hybrid_available()`
- `core/command_queue.py` — `PendingVoiceCommand` storage
- `config/hybrid_bindings.py` — `HYBRID_BINDINGS` keys
- `core/action_thread.py` — `_handle_voice_event()` and `_check_gesture_for_hybrid()`

---

## 1. Data Flow Trace

### VoiceThread → ActionThread
```
VoiceThread._process_audio()
  ↓ transcript = "scroll up"          (raw spoken phrase)
  ↓ action = "scroll_up"              (resolved from voice_bindings.py)
  ↓ _dispatch(action, transcript)
        GestureEvent(name="voice:scroll_up", metadata="scroll up")
              ↓
        ActionThread._execute_action()
              ↓
        gesture = "voice:scroll_up"
        action  = "scroll_up"         (gesture[6:])
        _handle_voice_event(action, event)
```

### ActionThread._handle_voice_event()
```python
def _handle_voice_event(self, voice_action: str, event: GestureEvent):
    voice_phrase = event.metadata or voice_action
    # voice_phrase = "scroll up"  (raw transcript)
    # voice_action = "scroll_up"  (resolved action)

    if self._intent_resolver.is_hybrid_available(voice_phrase):
        # ← CHECKS "scroll up" AGAINST HYBRID_BINDINGS
```

### IntentResolver.is_hybrid_available()
```python
def is_hybrid_available(self, voice_action: str) -> bool:
    for (v_act, _), _ in self._bindings.items():
        if v_act == voice_action:      # ← COMPARES "scroll up" == "scroll_up"
            return True
```

### HYBRID_BINDINGS Keys
```python
("open", "point")          → v_act = "open"
("search", "air_letter")   → v_act = "search"
("scroll_up", "scroll_up") → v_act = "scroll_up"
("scroll_down", "scroll_down") → v_act = "scroll_down"
("click", "point")         → v_act = "click"
```

---

## 2. Input Format Analysis

### Expected Input Format for Hybrid Check
`is_hybrid_available()` expects a **resolved voice action name** (snake_case) that matches the first element of `HYBRID_BINDINGS` tuples:
- `"open"`
- `"scroll_up"`
- `"scroll_down"`
- `"click"`
- `"search"`

### Actual Input Format Being Passed
`_handle_voice_event()` passes **`event.metadata`** — the **raw voice transcript** (may contain spaces, lowercase):
- `"open"` ✓ (coincidentally matches)
- `"scroll up"` ✗ (space vs underscore)
- `"scroll down"` ✗ (space vs underscore)
- `"click"` ✓ (coincidentally matches)
- `"search"` ✗ (no voice binding exists for this phrase)

---

## 3. Mismatch Verification

| Voice Phrase | Resolved Action | Passed to `is_hybrid_available()` | HYBRID_BINDINGS Key | Match? |
|--------------|----------------|-----------------------------------|---------------------|--------|
| `"open"` | `"hotkey:ctrl+o"` | `"open"` | `"open"` | **YES** ✓ |
| `"scroll up"` | `"scroll_up"` | `"scroll up"` | `"scroll_up"` | **NO** ✗ |
| `"scroll down"` | `"scroll_down"` | `"scroll down"` | `"scroll_down"` | **NO** ✗ |
| `"click"` | `"click"` | `"click"` | `"click"` | **YES** ✓ |
| `"search"` | N/A (no binding) | never reaches code | `"search"` | **NO** ✗ (dead binding) |

### Secondary Bug in `_check_gesture_for_hybrid()`
Even if eligibility check passed, hybrid resolution also uses the wrong field:

```python
voice_phrase = pending.transcript    # ← "scroll up"
intent = self._intent_resolver.resolve_hybrid(
    voice_action=voice_phrase,       # ← passed as "scroll up"
    gesture_type=hybrid_gesture,     # ← "scroll_up"
)
```

`resolve_hybrid()` constructs key `("scroll up", "scroll_up")` which does not exist in `HYBRID_BINDINGS`.

---

## 4. Results

| Item | Value |
|------|-------|
| **Expected input format** | Resolved action name (`"scroll_up"`, snake_case) |
| **Actual input format** | Raw transcript (`"scroll up"`, with spaces) |
| **Mismatch** | **YES** |
| **Root cause** | `_handle_voice_event()` passes `event.metadata` (raw transcript) to `is_hybrid_available()`, but `HYBRID_BINDINGS` keys use resolved action names. Transcripts with spaces (e.g., `"scroll up"`) fail snake_case equality checks. Additionally, the `"search"` hybrid binding is unreachable because no voice binding maps to `"search"`. |

---

## 5. Additional Finding: Dead Binding

`("search", "air_letter")` in `HYBRID_BINDINGS` can **never** be triggered:
- `voice_bindings.py` has no `"search"` phrase
- The closest is `"find"` → `"hotkey:ctrl+f"`
- Therefore `("search", "air_letter")` is unreachable dead code
