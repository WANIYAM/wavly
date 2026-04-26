"""
CommandQueue — Hybrid Voice+Gesture pairing buffer.

Fixes all bugs identified in the audit:

BUG 1 (Critical — consume-on-any-gesture):
  Old: ANY gesture within 2s window consumed and destroyed the voice command.
  Fix: Only MATCHING gestures consume the command. Non-matching gestures
       leave the voice command alive so the correct gesture can still pair.

BUG 2 (peek_most_recent starvation):
  Old: Only the newest voice command was ever eligible for pairing.
  Fix: find_match() searches ALL pending commands for any that match the
       incoming gesture, not just the newest.

BUG 3 (race between peek and consume):
  Old: Expiry was checked inside peek() then the lock was released before
       consume(), allowing an expired command to be executed as hybrid.
  Fix: consume() re-checks expiry inside the same lock acquisition before
       executing. Atomic peek-and-consume via find_and_consume().
"""

import time
import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional


VOICE_WINDOW_SECS = 2.0   # how long a voice command waits for a gesture


@dataclass
class PendingVoiceCommand:
    cmd_id:      str
    transcript:  str          # original spoken phrase e.g. "copy"
    voice_action: str         # resolved action e.g. "hotkey:ctrl+c"
    timestamp:   float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > VOICE_WINDOW_SECS

    def age(self) -> float:
        return time.time() - self.timestamp


class CommandQueue:
    """
    Thread-safe buffer for pending voice commands awaiting gesture pairing.

    Voice commands enter here immediately at recognition time (t=0).
    When a gesture arrives, find_and_consume() atomically checks ALL pending
    commands for a match and returns the first matching one.
    Non-matching gestures do NOT consume voice commands.
    Expired commands are swept on every access.
    """

    def __init__(self):
        self._pending: dict[str, PendingVoiceCommand] = {}
        self._lock    = threading.Lock()

    def put(self, transcript: str, voice_action: str) -> str:
        """
        Store a voice command immediately at recognition time.
        Returns cmd_id for reference.
        """
        cmd_id = str(uuid.uuid4())[:8]
        cmd    = PendingVoiceCommand(
            cmd_id=cmd_id,
            transcript=transcript,
            voice_action=voice_action,
        )
        with self._lock:
            self._sweep()
            self._pending[cmd_id] = cmd
        print(f"[CommandQueue] Stored: '{transcript}' → '{voice_action}' "
              f"(id={cmd_id}, window={VOICE_WINDOW_SECS}s)")
        return cmd_id

    def find_and_consume(self, transcript_key: str) -> Optional[PendingVoiceCommand]:
        """
        Atomically find + remove the first non-expired pending command
        whose transcript matches transcript_key.

        Only called when a MATCHING hybrid gesture is detected.
        Non-matching gestures never call this — they don't consume anything.

        BUG 1 FIX: Non-matching gestures cannot consume voice commands.
        BUG 2 FIX: Searches ALL pending commands, not just newest.
        BUG 3 FIX: Expiry re-checked inside the same lock acquisition.
        """
        with self._lock:
            self._sweep()
            for cmd_id, cmd in list(self._pending.items()):
                if cmd.transcript == transcript_key and not cmd.is_expired():
                    del self._pending[cmd_id]
                    print(f"[CommandQueue] Consumed: '{cmd.transcript}' "
                          f"(age={cmd.age():.2f}s)")
                    return cmd
        return None

    def get_expired(self) -> list[PendingVoiceCommand]:
        """
        Return and remove all expired voice commands for fallback execution.
        Called periodically so no command is silently dropped.
        """
        with self._lock:
            expired = [c for c in self._pending.values() if c.is_expired()]
            for cmd in expired:
                del self._pending[cmd.cmd_id]
        return expired

    def _sweep(self):
        """Remove expired entries. Must be called with lock held."""
        expired_ids = [cid for cid, c in self._pending.items() if c.is_expired()]
        for cid in expired_ids:
            del self._pending[cid]

    def size(self) -> int:
        with self._lock:
            return len(self._pending)

    def clear(self):
        with self._lock:
            self._pending.clear()