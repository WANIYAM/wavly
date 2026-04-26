# Voice ↔ Gesture Synchronization Audit

**Files analyzed:**
- `core/command_queue.py`
- `core/gesture_queue.py`
- `core/action_thread.py`

**Date:** Auto-generated audit

---

## 1. Voice Retention Window

| Parameter | Value |
|-----------|-------|
| Configured timeout | **2.0 seconds** (`CommandQueue.timeout_secs`) |
| Expiry check interval | **0.5 seconds** (`ActionThread._handle_expired_voice_commands`) |
| Cleanup throttle | **1.0 second** (`CommandQueue._cleanup_expired`) |
| **Effective voice retention** | **2.0–2.5 seconds** |

**Details:**
- Voice commands are stored with `timestamp = time.time()` on arrival.
- `is_expired()` uses strict `>` comparison: `time.time() - timestamp > 2.0`.
- `ActionThread` only scans for expired commands every **500 ms**.
- A command that expires at T+2.0 s may not be executed as voice-only fallback until T+2.5 s (worst case).
- `_cleanup_expired()` is throttled to once per second, so expired entries can linger in the internal dict until the next cleanup trigger.

---

## 2. Gesture Consumption Speed

| Parameter | Value |
|-----------|-------|
| Queue type | `queue.Queue(maxsize=20)` |
| Poll timeout | **50 ms** (`get_action(timeout=0.05)`) |
| Consumption pattern | FIFO with critical-gesture eviction |
| **Max latency (idle loop)** | **~50 ms** |
| **Max latency (gesture already queued)** | **Immediate** |

**Details:**
- `ActionThread.run()` blocks on `gesture_queue.get_action(timeout=0.05)`.
- If the queue is empty, the thread sleeps ~50 ms before retrying.
- If a gesture is already enqueued, it is consumed immediately (no timeout wait).
- Critical gestures (`stop`, `click`, `drag_end`) can evict non-critical events if the queue is full.
- Non-critical gestures are **silently dropped** when the queue is at capacity (`maxsize=20`).

---

## 3. Synchronization Possible?

**YES** — but with significant caveats.

The 2-second voice window and ~50 ms gesture polling create enough temporal overlap for hybrid pairing **in principle**. However, the implementation contains design-level issues that make reliable synchronization fragile.

---

## 4. Failure Reasons & Issues

### Issue A: Consume-on-Any-Gesture (FIX G) — **CRITICAL**
**Location:** `ActionThread._check_gesture_for_hybrid()` (else branch)

```python
else:
    # FIX G: no match → consume and execute voice-only fallback
    self._command_queue.consume(cmd_id)
    ...
    self._run_action(pending.voice_action, "voice", x, y)
```

**Impact:** Any gesture arriving within the 2-second window consumes the pending voice command, even if the gesture does **not** match the required hybrid binding. A subsequent matching gesture cannot pair because the voice command is already gone.

**Example:**
1. User says *"open"* → stored in `CommandQueue`.
2. User accidentally makes a *"scroll"* gesture at T+0.3 s.
3. Voice command is consumed and executed as voice-only.
4. User makes a *"point"* gesture at T+0.8 s.
5. No pending voice command exists → hybrid action is impossible.

**Severity:** High. This breaks the core premise of a 2-second pairing window.

---

### Issue B: `peek_most_recent()` Semantic Unreliability
**Location:** `CommandQueue.peek_most_recent()`

```python
cmd_id = list(self._pending.keys())[-1]  # most recent
```

**Impact:**
- Always returns the **most recently inserted** voice command, regardless of whether it is the semantically correct one to pair.
- If multiple voice commands are pending, older commands are **starved** — they will never be hybridized and will eventually time out as voice-only.
- Dictionary insertion order is guaranteed in Python 3.7+, so the mechanics are sound, but the **policy** is unreliable for multi-command scenarios.

**Example:**
1. Voice command *"copy"* stored at T=0.
2. Voice command *"paste"* stored at T=0.5.
3. Gesture *"fingers_2"* arrives at T=1.0.
4. `peek_most_recent()` returns *"paste"*, pairing it with the gesture.
5. *"copy"* remains pending until timeout.

**Severity:** Medium. Problematic for rapid sequential voice commands.

---

### Issue C: Theoretical Race Between Peek and Consume
**Location:** `ActionThread._check_gesture_for_hybrid()`

```python
result = self._command_queue.peek_most_recent()   # Lock held, then released
# ... intent resolution (no lock) ...
self._command_queue.consume(cmd_id)               # Lock re-acquired
```

**Impact:**
- `peek_most_recent()` validates expiry **inside** the lock, then returns.
- The lock is released during `IntentResolver.resolve_hybrid()`.
- `consume()` re-acquires the lock and deletes by `cmd_id` without re-checking expiry.
- If the voice command crosses the 2.0-second boundary in the microsecond gap between `peek_most_recent()` and `consume()`, an **already-expired** command could be executed as a hybrid action.

**Likelihood:** Very low (microsecond window), but architecturally unsound.

**Severity:** Low.

---

### Issue D: Stale Cleanup State
**Location:** `CommandQueue._cleanup_expired()` vs `get_and_clear_expired()`

- `_cleanup_expired()` tracks `_last_cleanup` and throttles to 1 Hz.
- `get_and_clear_expired()` (called every 0.5 s by `ActionThread`) independently deletes expired entries but **does not update `_last_cleanup`**.
- Result: `_cleanup_expired()` may skip work based on a stale `_last_cleanup`, then redundantly scan an already-empty dict later.

**Impact:** Inefficiency and confusing state. Not a direct data race, but indicates unsynchronized maintenance paths.

**Severity:** Low.

---

### Issue E: Gesture Starvation During Voice Fallback Execution
**Location:** `ActionThread.run()`

```python
while not self._stop_event.is_set():
    self._handle_expired_voice_commands()   # May call _run_action() → blocking I/O
    event = self.gesture_queue.get_action(timeout=0.05)
    if event is None:
        continue
    self._execute_action(event)             # May call _run_action() → blocking I/O
```

**Impact:**
- `_run_action()` executes `pyautogui` calls, `subprocess.Popen`, and `typewrite` on the **same thread**.
- While `ActionThread` is blocked executing a voice-only fallback, new gestures accumulate in `GestureQueue`.
- If the queue fills (20 events), subsequent gestures are **dropped**.
- During heavy voice fallback activity, the gesture pipeline can lose events.

**Severity:** Medium. Breaks the assumption that gestures are consumed promptly.

---

## 5. `peek_most_recent()` Reliability Verdict

| Criterion | Verdict |
|-----------|---------|
| Thread-safety | ✅ **Yes** — protected by `self._lock` |
| Insertion-order correctness | ✅ **Yes** — relies on Python 3.7+ dict ordering |
| Expiry filtering | ✅ **Yes** — re-checks `is_expired()` inside lock |
| Semantic correctness | ⚠️ **No** — always favors newest command; starves older pending commands |
| Race-free consume | ⚠️ **Partial** — expiry not re-checked at `consume()` time |

**Overall:** Mechanically reliable for single-pending-command scenarios. Unreliable when multiple voice commands overlap within the 2-second window.

---

## Summary Table

| Metric | Value |
|--------|-------|
| **Voice retention window** | 2.0 s (up to 2.5 s effective) |
| **Gesture consumption speed** | ~50 ms polling interval; immediate if queued |
| **Synchronization possible?** | **YES** — temporal overlap exists |
| **Primary failure reason** | **Consume-on-any-gesture (FIX G):** Any gesture within the 2 s window destroys the pending voice command, preventing later correct matches. |
| **Secondary failure reason** | **`peek_most_recent()` starvation:** Only the newest voice command is ever eligible for hybrid pairing. |
| **Tertiary failure reason** | **Single-threaded blocking:** Voice fallback execution blocks gesture consumption, causing queue overflow and dropped gestures. |

---

*End of audit.*

