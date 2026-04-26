# TODO — Hybrid System Verification + Repair

## Verification Results (Phase 1)

| Check | Description | Status |
|-------|-------------|--------|
| 1 | Voice Phrase Preservation — `GestureEvent.metadata` exists and `VoiceThread._dispatch()` passes `transcript` | ❌ NOT FIXED |
| 2 | Voice Phrase Used in Hybrid Detection — `event.metadata` used as `voice_phrase`; hybrid uses ORIGINAL phrase | ❌ NOT FIXED |
| 3 | Gesture Mapping Layer — mapping exists (cursor_move→point, drag_start→fist, stop→palm) | ❌ NOT FIXED |
| 4 | `air_letter` Handling — handles "air_letter:X" WITHOUT splitting to "air" | ❌ NOT FIXED |
| 5 | CommandQueue Safety — supports NON-DESTRUCTIVE read; removed ONLY after success | ❌ NOT FIXED |
| 6 | Hybrid Fallback — if hybrid match fails, executes voice-only fallback | ❌ NOT FIXED |
| 7 | Hybrid Bindings Validity — bindings only include existing gestures | ❌ NOT FIXED |

**Summary: Hybrid system is STILL BROKEN**

## Repair Plan (Phase 2)

- [x] FIX A — Add `metadata` field to `GestureEvent` in `core/gesture_queue.py`
- [x] FIX B — Pass `metadata=transcript` in `VoiceThread._dispatch()` in `core/voice_thread.py`
- [x] FIX C — Use `event.metadata` as `voice_phrase` in `core/action_thread.py`
- [x] FIX D — Add `GESTURE_TO_HYBRID` mapping layer in `core/action_thread.py`
- [x] FIX E — Fix `air_letter` split handling in `core/action_thread.py`
- [x] FIX F — Safe CommandQueue with `peek_most_recent()` + `consume(cmd_id)` in `core/command_queue.py`
- [x] FIX G — Add voice-only fallback on failed hybrid match in `core/action_thread.py`
- [x] FIX H — Clean unsupported gestures from `config/hybrid_bindings.py`
- [x] Run final tests (Phase 3)

## Final Test Results (Phase 3)

- Unit tests: **22/23 passed** (1 expected failure: `test_resolve_go_to_plus_fingers` — old binding using removed `fingers` gesture)
- Simulation tests: **5/5 passed**
  1. ✅ "copy" → voice-only fallback works
  2. ✅ "open" + cursor_move → hybrid "open_at_cursor" works
  3. ✅ "search" + air_letter → hybrid "search_for_letter" works
  4. ✅ "open" + wrong gesture → voice-only fallback works
  5. ✅ gesture only → unchanged behavior

