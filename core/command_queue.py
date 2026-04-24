"""
CommandQueue — Phase 4 Feature 2: Voice + Gesture Hybrid

Holds pending voice commands waiting for a matching gesture within 2 seconds.
If no gesture arrives by timeout, the voice command executes as voice-only.

Thread-safe with locks.
"""

import time
import threading
from typing import Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class PendingVoiceCommand:
    """A voice command waiting for a gesture pair."""
    transcript: str
    voice_action: str
    timestamp: float = field(default_factory=time.time)
    
    def is_expired(self, timeout_secs: float = 2.0) -> bool:
        return time.time() - self.timestamp > timeout_secs


class CommandQueue:
    """
    Holds voice events pending gesture pairing.
    
    Timeline:
      t=0: Voice command "open" → stored in CommandQueue with timestamp
      t=0-2s: User makes gesture "point"
      t<2s: IntentResolver checks ("open", "point") and finds match → hybrid action
      t>2s: Auto-timeout → execute voice-only action
    
    Thread-safe. Multiple threads can check/timeout simultaneously.
    """

    def __init__(self, timeout_secs: float = 2.0):
        self.timeout_secs = timeout_secs
        self._pending: dict[str, PendingVoiceCommand] = {}  # {gesture_type → command}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def put_voice_event(self, transcript: str, voice_action: str) -> str:
        """
        Store a voice command waiting for gesture pairing.
        Returns command_id for tracking.
        """
        with self._lock:
            # Clean expired entries first
            self._cleanup_expired()
            
            # Store new pending command (keyed by action for uniqueness)
            cmd_id = f"voice:{voice_action}:{time.time()}"
            self._pending[cmd_id] = PendingVoiceCommand(
                transcript=transcript,
                voice_action=voice_action,
            )
            print(f"[CommandQueue] Stored: {voice_action} (waiting for gesture...)")
            return cmd_id

    def get_pending_for_gesture(self, gesture_type: str) -> Optional[PendingVoiceCommand]:
        """
        Check if any pending voice command matches this gesture.
        Returns the command if found, None otherwise.
        
        Called by ActionThread when a gesture fires.
        """
        with self._lock:
            self._cleanup_expired()
            
            # For now, simple strategy: return the most recent pending command
            # (In future: could implement more sophisticated matching based on
            # gesture_type, context, confidence, etc.)
            if self._pending:
                cmd_id = list(self._pending.keys())[-1]  # most recent
                cmd = self._pending[cmd_id]
                if not cmd.is_expired(self.timeout_secs):
                    print(f"[CommandQueue] Matched: {cmd.voice_action} + {gesture_type}")
                    del self._pending[cmd_id]
                    return cmd
        
        return None

    def get_and_clear_expired(self) -> list[PendingVoiceCommand]:
        """
        Return all expired commands (for voice-only fallback).
        This is called periodically to auto-execute timed-out voice commands.
        """
        with self._lock:
            expired = []
            to_delete = []
            
            for cmd_id, cmd in self._pending.items():
                if cmd.is_expired(self.timeout_secs):
                    expired.append(cmd)
                    to_delete.append(cmd_id)
            
            for cmd_id in to_delete:
                del self._pending[cmd_id]
                print(f"[CommandQueue] Expired (voice-only): {cmd.voice_action}")
            
            return expired

    def _cleanup_expired(self):
        """Internal cleanup without double-locking."""
        now = time.time()
        if now - self._last_cleanup < 1.0:
            return  # cleanup at most once per second
        
        to_delete = []
        for cmd_id, cmd in self._pending.items():
            if cmd.is_expired(self.timeout_secs):
                to_delete.append(cmd_id)
        
        for cmd_id in to_delete:
            del self._pending[cmd_id]
        
        self._last_cleanup = now

    def get_pending_count(self) -> int:
        """For debugging/UI."""
        with self._lock:
            return len(self._pending)

    def clear_all(self):
        """Clear all pending commands."""
        with self._lock:
            self._pending.clear()
