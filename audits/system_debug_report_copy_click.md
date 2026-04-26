# System Debug Report — Wavly Multimodal Pipeline

**Test Case:** Voice = `"copy"`, Gesture = `"click"`  
**Date:** Auto-generated diagnostic  
**Scope:** VoiceThread → GestureQueue → ActionThread → CommandQueue → IntentResolver → HybridBindings

---

## STEP 1 — TRACE VOICE FLOW

**VOICE ENTRY POINT:** `VoiceThread._process_audio()` → `VoiceThread._dispatch()`

**TRANSCRIPT:** `"copy"` (lowercased, stripped)

**RESOLVED ACTION:** `"hotkey:ctrl+c"` (from `config/voice_bindings.py`)

**EVENT NAME:** `"voice:hotkey:ctrl+c"`

**METADATA:** `"copy"` ← original transcript preserved in `GestureEvent.metadata`

**COMMANDQUEUE ENTRY:** **NO**

---

## STEP 2 — TRACE GESTURE FLOW

**GESTURE:** `"click"`

**CONFIDENCE:** `0.82`

**QUEUE INSERTION:** `GestureQueue.put_action(GestureEvent(name="click", confidence=0.82))` — standard FIFO insertion into `GestureQueue._action_queue` (maxsize=20)

**HYBRID CHECK TRIGGERED:** **YES** — `ActionThread._check_gesture_for_hybrid("click", event)` is invoked for every non-voice gesture

---

## STEP 3 — HYBRID ELIGIBILITY CHECK

**INPUT TO HYBRID CHECK:** `"copy"` — raw transcript from `event.metadata` (not the resolved action `"hotkey:ctrl+c"`)

**EXPECTED FORMAT:** Voice action key matching the first element of `HYBRID_BINDINGS` tuples (snake_case strings: `"open"`, `"scroll_up"`, `"click"`, etc.)

**FORMAT MISMATCH:** **NO** for this specific token — `"copy"` is already a single snake_case word with no spaces/underscores discrepancy. However, the *source* is semantically incorrect (raw transcript passed instead of the resolved action or canonical voice binding key).

**BINDING MATCH:** **NO** — `"copy"` is absent from all `HYBRID_BINDINGS` keys: `("open",...)`, `("search",...)`, `("scroll_up",...)`, `("scroll_down",...)`, `("click",...)`

**RESULT:** **FAIL**

---

## STEP 4 — COMMANDQUEUE INTEGRATION

**DIRECT ENTRY:** **NO** — `VoiceThread._dispatch()` has no reference to `CommandQueue`; it pushes exclusively to `GestureQueue`

**ENTRY STAGE:** Voice **never reaches** `CommandQueue` for this test case

**PIPELINE BREAK LOCATION:** `ActionThread._handle_voice_event()` line containing `if self._intent_resolver.is_hybrid_available(voice_phrase):` — the condition evaluates to `False`, so execution falls through to the `else` branch (`_run_action(voice_action, "voice", x, y)`), and `CommandQueue.put_voice_event()` is **never called**

---

## STEP 5 — HYBRID KEY VALIDATION

**EXPECTED KEY:** `("copy", "click")`

**ACTUAL KEY:** `("copy", "click")` — this is the exact tuple `IntentResolver.resolve_hybrid()` would construct via `key = (voice_action, gesture_type)` if it were ever reached

**MATCH IN BINDINGS:** **NO** — `("copy", "click")` is **not present** in `HYBRID_BINDINGS`

**Does resolver ever reach lookup?** **NO** — `is_hybrid_available()` returned `False` before storage; `resolve_hybrid()` is never invoked because `CommandQueue.peek_most_recent()` returns `None` when the gesture arrives

---

## STEP 6 — SYNCHRONIZATION ANALYSIS

**SYNC POSSIBLE:** **NO** — for this test case, temporal overlap is architecturally impossible

**FAILURE POINT:** Voice command is consumed **immediately** as voice-only (`ctrl+c`) in `ActionThread._handle_voice_event()` due to the failed eligibility check. The 2-second voice retention window in `CommandQueue` is **never initialized**. When gesture `"click"` arrives milliseconds or seconds later, `CommandQueue` is empty (`peek_most_recent()` → `None`), so there is no pending voice to pair with. The voice is destroyed too early — before any pairing opportunity can exist.

---

## STEP 7 — FAILURE CLASSIFICATION

**FAILURE TYPES:**
1. **Data Flow Failure** — VoiceThread routes voice exclusively through `GestureQueue`; `CommandQueue` is bypassed entirely because ActionThread's conditional eligibility gate blocks entry before the hybrid retention window can begin.
2. **Semantic Mismatch** — `HYBRID_BINDINGS` lacks the `("copy", "click")` key. Even if the voice command had reached `CommandQueue` and the gesture had successfully peeked it, `IntentResolver.resolve_hybrid()` would return `None` and fall back to non-hybrid execution.
3. **Architectural Design Failure** — The hybrid pipeline structurally prevents voice from entering `CommandQueue` at recognition time. Voice must first transit `GestureQueue`, wait for ActionThread dequeue, pass prefix detection (`"voice:"`), and survive an eligibility pre-check against a sparse binding dictionary — a coupled, fragile gate that creates a dead-end for any voice command not explicitly pre-defined in `HYBRID_BINDINGS`.

---

## STEP 8 — FINAL SYSTEM VERDICT

**STATUS:** **BROKEN**

**ROOT CAUSE:**
The hybrid pipeline is architecturally dead for voice "copy" because ActionThread's eligibility check returns False before CommandQueue is ever populated, and the ("copy", "click") binding is absent from HYBRID_BINDINGS.

**TOP 3 FAILURES:**
1. Voice "copy" never enters CommandQueue — `is_hybrid_available("copy")` returns `False`, triggering immediate voice-only execution (`ctrl+c`) and bypassing the 2-second hybrid retention window entirely.
2. `HYBRID_BINDINGS` lacks the `("copy", "click")` key — even if voice had reached `CommandQueue`, `IntentResolver.resolve_hybrid()` would find no match and fall back to separate voice-only and gesture-only executions.
3. VoiceThread has no direct `CommandQueue` injection path — voice is routed through `GestureQueue` first, introducing unnecessary latency and a conditional eligibility gate that structurally prevents immediate hybrid pairing at the moment of voice recognition.

---

## OPTIONAL DEBUG MODE

**EXPECTED:** `("copy", "click")`

**ACTUAL:** `("copy", "click")`

**MATCH:** **NO**

