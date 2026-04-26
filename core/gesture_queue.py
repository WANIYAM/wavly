"""
GestureQueue — Thread-safe bridge between vision and action threads.

Phase 4 addition:
  register_observer(fn) — registers a callable that gets notified every
  time a gesture fires. AdaptiveEngine uses this to silently monitor
  the gesture stream without interfering with the main pipeline.
"""

import queue
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable
import time


@dataclass
class GestureEvent:
    name:       str
    confidence: float
    cursor_x:   Optional[int]  = None
    cursor_y:   Optional[int]  = None
    timestamp:  float          = field(default_factory=time.time)
    metadata:   Optional[str]  = None   # stores transcript for voice hybrid matching


class GestureQueue:

    def __init__(self):
        self._cursor_x: Optional[int] = None
        self._cursor_y: Optional[int] = None
        self._cursor_lock   = threading.Lock()
        self._cursor_locked: bool = False

        self._action_queue: queue.Queue = queue.Queue(maxsize=20)

        self._latest_event: Optional[GestureEvent] = None
        self._latest_lock   = threading.Lock()

        # Phase 4: observer callbacks — called on every put_action()
        self._observers: list[Callable] = []
        self._observers_lock = threading.Lock()

    # ── Observer API (Phase 4) ────────────────────────────────────────────

    def register_observer(self, fn: Callable):
        """
        Register a callback invoked every time a discrete gesture fires.
        Signature: fn(gesture_name: str, confidence: float, timestamp: float)
        Callbacks are called synchronously in the camera thread — keep them fast.
        """
        with self._observers_lock:
            self._observers.append(fn)

    def _notify_observers(self, event: GestureEvent):
        with self._observers_lock:
            observers = list(self._observers)
        for fn in observers:
            try:
                fn(event.name, event.confidence, event.timestamp)
            except Exception as e:
                print(f"[GestureQueue] Observer error: {e}")

    # ── Cursor channel ────────────────────────────────────────────────────

    def put_cursor(self, x: int, y: int, confidence: float = 0.9):
        with self._cursor_lock:
            if not self._cursor_locked:
                self._cursor_x = x
                self._cursor_y = y
        with self._latest_lock:
            self._latest_event = GestureEvent(
                name="cursor_move", confidence=confidence,
                cursor_x=x, cursor_y=y
            )

    def lock_cursor(self):
        with self._cursor_lock:
            self._cursor_locked = True

    def unlock_cursor(self):
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
        # Notify observers (adaptive engine, overlay, etc.)
        self._notify_observers(event)

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
            self._cursor_x      = None
            self._cursor_y      = None
            self._cursor_locked = False
        while not self._action_queue.empty():
            try:
                self._action_queue.get_nowait()
            except queue.Empty:
                break
        with self._latest_lock:
            self._latest_event = None