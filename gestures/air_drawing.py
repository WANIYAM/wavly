"""
AirDrawing — Phase 3 Module

Tracks the index fingertip trajectory over time, normalizes it into a
28x28 raster image, and classifies it using a trained sklearn SVM.

Workflow:
  1. User holds a "draw" pose (index up, fist-like, or configurable)
  2. Fingertip trajectory is recorded frame by frame
  3. On "done" signal (open palm / timeout), stroke is classified
  4. Mapped command is executed

Default letter → command mappings (fully user-configurable):
  C → Open browser (Ctrl+T)
  M → Open mail
  V → Paste (Ctrl+V)
  Z → Undo (Ctrl+Z)
  S → Save (Ctrl+S)

Training:
  Run: python gestures/air_draw_trainer.py
"""

import os
import time
import pickle
import numpy as np
import cv2
from typing import Optional, Callable
from collections import deque

from config.settings import Settings


# ── Default letter → action bindings ─────────────────────────────────────────
DEFAULT_LETTER_ACTIONS = {
    # Letter = what it stands for — intuitive for everyday use
    "C": ("hotkey", ["ctrl", "c"]),       # C = Copy
    "V": ("hotkey", ["ctrl", "v"]),       # V = Paste
    "X": ("hotkey", ["ctrl", "x"]),       # X = Cut
    "Z": ("hotkey", ["ctrl", "z"]),       # Z = Undo
    "S": ("hotkey", ["ctrl", "s"]),       # S = Save
    "A": ("hotkey", ["ctrl", "a"]),       # A = Select All
    "F": ("hotkey", ["ctrl", "f"]),       # F = Find
    "P": ("hotkey", ["ctrl", "p"]),       # P = Print
    "T": ("hotkey", ["ctrl", "t"]),       # T = new Tab
    "W": ("hotkey", ["ctrl", "w"]),       # W = close Window/tab
    "N": ("hotkey", ["ctrl", "n"]),       # N = New file/window
    "O": ("hotkey", ["ctrl", "o"]),       # O = Open file
    "R": ("hotkey", ["ctrl", "r"]),       # R = Refresh/Reload
    "M": ("hotkey", ["win",  "m"]),       # M = Minimise all windows
    "E": ("hotkey", ["win",  "e"]),       # E = open Explorer/Files
}

RASTER_SIZE = 28   # normalise all strokes to 28x28


class StrokeBuffer:
    """Accumulates fingertip positions while user is drawing."""

    def __init__(self, max_frames: int = 90):
        self._pts: deque = deque(maxlen=max_frames)
        self._active = False
        self._start_time = 0.0

    def start(self):
        self._pts.clear()
        self._active    = True
        self._start_time = time.time()

    def stop(self) -> list:
        self._active = False
        return list(self._pts)

    def add(self, x: float, y: float):
        if self._active:
            self._pts.append((x, y))

    @property
    def active(self) -> bool:
        return self._active

    @property
    def duration(self) -> float:
        return time.time() - self._start_time if self._active else 0.0

    def __len__(self):
        return len(self._pts)


class StrokeNormalizer:
    """Converts a list of (x,y) points into a 28x28 binary image."""

    @staticmethod
    def to_image(pts: list, size: int = RASTER_SIZE) -> Optional[np.ndarray]:
        if len(pts) < 8:
            return None

        arr = np.array(pts, dtype=np.float32)

        # Centre and scale to [0, size-1]
        mn = arr.min(axis=0)
        mx = arr.max(axis=0)
        span = mx - mn
        if span[0] < 1e-4 or span[1] < 1e-4:
            return None

        arr = (arr - mn) / span * (size - 1)

        # Rasterize by drawing polyline onto blank canvas
        img = np.zeros((size, size), dtype=np.uint8)
        pts_int = arr.astype(np.int32)
        for i in range(len(pts_int) - 1):
            cv2.line(img, tuple(pts_int[i]), tuple(pts_int[i + 1]), 255, 2)

        return img

    @staticmethod
    def to_features(pts: list, size: int = RASTER_SIZE) -> Optional[np.ndarray]:
        img = StrokeNormalizer.to_image(pts, size)
        if img is None:
            return None
        return img.flatten().astype(np.float32) / 255.0


class AirDrawRecognizer:
    """Loads trained model and predicts letter from stroke features."""

    def __init__(self, settings: Settings):
        self.settings   = settings
        self._model     = None
        self._encoder   = None
        self._load()

    def _load(self):
        path = self.settings.air_draw_model_path
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    saved = pickle.load(f)
                self._model   = saved["model"]
                self._encoder = saved["label_encoder"]
                print(f"[AirDraw] Model loaded — "
                      f"letters: {list(self._encoder.classes_)}")
            except Exception as e:
                print(f"[AirDraw] Failed to load model: {e}")
        else:
            print("[AirDraw] No model found. Run: python gestures/air_draw_trainer.py")

    def predict(self, pts: list) -> Optional[tuple[str, float]]:
        """Returns (letter, confidence) or None if unrecognised."""
        if self._model is None:
            return None
        features = StrokeNormalizer.to_features(pts)
        if features is None:
            return None
        try:
            proba      = self._model.predict_proba([features])[0]
            best_idx   = int(np.argmax(proba))
            confidence = float(proba[best_idx])
            letter     = self._encoder.inverse_transform([best_idx])[0]
            if confidence >= 0.60:
                return letter, confidence
        except Exception as e:
            print(f"[AirDraw] Predict error: {e}")
        return None


class AirDrawManager:
    """
    Manages the full air-drawing lifecycle.

    CONFLICT FIX:
      Previously used drag_start (fist) to enter draw mode — this caused
      every normal drag to accidentally start air drawing.

      New behaviour:
        - HOLD fist for HOLD_TO_DRAW_SECS (1.5s) → enter draw mode
        - TAP fist briefly (< 1.5s) → normal drag, air draw ignored
        - Open palm → commit stroke (if drawing) OR release drag (if dragging)

      This means normal drag still works perfectly.
      Air draw only activates when you clearly hold the fist still.
    """

    START_GESTURE      = "drag_start"  # fist (held long = draw, tapped = drag)
    END_GESTURE        = "stop"        # open palm = commit stroke
    HOLD_TO_DRAW_SECS  = 1.5          # hold fist THIS long to enter draw mode
    TIMEOUT_SECS       = 4.0          # auto-commit after 4s of drawing
    MIN_POINTS         = 12

    def __init__(self, settings: Settings,
                 on_letter_fn: Optional[Callable] = None):
        self.settings      = settings
        self._recognizer   = AirDrawRecognizer(settings)
        self._buffer       = StrokeBuffer(max_frames=120)
        self._on_letter_fn = on_letter_fn
        self._drawing      = False

        # How long fist has been held (for hold-to-draw detection)
        self._fist_hold_start: float = 0.0
        self._fist_holding:    bool  = False

    @property
    def is_drawing(self) -> bool:
        return self._drawing

    @property
    def fist_hold_progress(self) -> float:
        """0.0 → 1.0 progress toward entering draw mode. For UI feedback."""
        if not self._fist_holding:
            return 0.0
        elapsed = time.time() - self._fist_hold_start
        return min(elapsed / self.HOLD_TO_DRAW_SECS, 1.0)

    def process(self, gesture: str, tip_x: float, tip_y: float,
                confidence: float) -> Optional[str]:
        """
        Called every frame from CameraThread.
        Returns status string for debug overlay, or None.
        """
        now = time.time()

        if not self._drawing:
            # Track how long fist is being held
            if gesture == self.START_GESTURE and confidence > 0.6:
                if not self._fist_holding:
                    self._fist_holding   = True
                    self._fist_hold_start = now

                held_secs = now - self._fist_hold_start
                if held_secs >= self.HOLD_TO_DRAW_SECS:
                    # Fist held long enough — enter draw mode
                    self._buffer.start()
                    self._drawing      = True
                    self._fist_holding = False
                    print(f"[AirDraw] Draw mode entered (held {held_secs:.1f}s)")
                    return "draw_start"
                else:
                    # Still holding — show progress but don't block drag
                    return f"holding ({held_secs:.1f}s / {self.HOLD_TO_DRAW_SECS}s)"
            else:
                # Fist released before threshold — was a normal drag tap
                self._fist_holding = False
                return None

        else:
            # Currently drawing — add point
            self._buffer.add(tip_x, tip_y)

            timed_out  = self._buffer.duration >= self.TIMEOUT_SECS
            end_signal = gesture == self.END_GESTURE and confidence > 0.6

            if (end_signal or timed_out) and len(self._buffer) >= self.MIN_POINTS:
                pts = self._buffer.stop()
                self._drawing = False
                self._classify(pts)
                return "done"
            elif timed_out:
                self._buffer.stop()
                self._drawing = False
                print("[AirDraw] Timeout — stroke discarded (too short)")
                return "cancelled"

            return f"drawing ({len(self._buffer)} pts)"

    def _classify(self, pts: list):
        result = self._recognizer.predict(pts)
        if result:
            letter, conf = result
            print(f"[AirDraw] Recognised: '{letter}' ({conf:.2f})")
            if self._on_letter_fn:
                self._on_letter_fn(letter, conf)
        else:
            print("[AirDraw] Stroke not recognised")

    def get_stroke_pts(self) -> list:
        """For drawing preview on overlay."""
        return list(self._buffer._pts)