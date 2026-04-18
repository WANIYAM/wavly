"""
GestureQueue — Thread-safe bridge between vision and action threads.

Two channels:
  - cursor: latest position, overwrite-only (no queue)
  - actions: discrete gesture events (click, scroll etc.) FIFO

Cursor lock: camera thread calls lock_cursor() the moment a non-cursor
gesture starts building up. This freezes the cursor at its current
position so it doesn't drift during the debounce window.
"""

import queue
import threading
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class GestureEvent:
    name: str
    confidence: float
    cursor_x: Optional[int] = None
    cursor_y: Optional[int] = None
    timestamp: float = field(default_factory=time.time)


class GestureQueue:

    def __init__(self):
        # Latest cursor position — overwrite only
        self._cursor_x: Optional[int] = None
        self._cursor_y: Optional[int] = None
        self._cursor_lock = threading.Lock()

        # Cursor locked: True = don't update cursor position
        self._cursor_locked: bool = False

        # Discrete action events
        self._action_queue: queue.Queue = queue.Queue(maxsize=20)

        # Latest event for UI
        self._latest_event: Optional[GestureEvent] = None
        self._latest_lock = threading.Lock()

    # ── Cursor channel ────────────────────────────────────────────────────

    def put_cursor(self, x: int, y: int, confidence: float = 0.9):
        """Update cursor position. Ignored if cursor is locked."""
        with self._cursor_lock:
            if not self._cursor_locked:
                self._cursor_x = x
                self._cursor_y = y

        with self._latest_lock:
            self._latest_event = GestureEvent(
                name="cursor_move", confidence=confidence, cursor_x=x, cursor_y=y
            )

    def lock_cursor(self):
        """Freeze cursor at current position. Called when action gesture starts."""
        with self._cursor_lock:
            self._cursor_locked = True

    def unlock_cursor(self):
        """Resume cursor updates."""
        with self._cursor_lock:
            self._cursor_locked = False

    def get_cursor(self) -> Optional[tuple]:
        with self._cursor_lock:
            if self._cursor_x is not None:
                return (self._cursor_x, self._cursor_y)
        return None

    # ── Action channel ────────────────────────────────────────────────────

    def put_action(self, event: GestureEvent):
        with self._latest_lock:
            self._latest_event = event
        try:
            self._action_queue.put_nowait(event)
        except queue.Full:
            pass

    def get_action(self, timeout: float = 0.05) -> Optional[GestureEvent]:
        try:
            return self._action_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def peek_latest(self) -> Optional[GestureEvent]:
        with self._latest_lock:
            return self._latest_event

    def clear(self):
        with self._cursor_lock:
            self._cursor_x = None
            self._cursor_y = None
            self._cursor_locked = False
        while not self._action_queue.empty():
            try:
                self._action_queue.get_nowait()
            except queue.Empty:
                break
        with self._latest_lock:
            self._latest_event = None