"""
Settings — Central configuration for Wavly.
All tuneable parameters in one place.
"""

import os


class Settings:

    # ── Camera ───────────────────────────────────────────────────────────────
    camera_index: int = 0               # Webcam device index (0 = default)
    show_debug_window: bool = False     # Show OpenCV preview window

    # ── MediaPipe ────────────────────────────────────────────────────────────
    min_detection_confidence: float = 0.7
    min_tracking_confidence: float = 0.6

    # ── Gesture Debounce ──────────────────────────────────────────────────────
    # Number of consecutive frames a gesture must be held before firing.
    # 8 frames @ 30fps ≈ 267ms. Increase to reduce false triggers.
    hold_frames: int = 8

    # Frames to ignore after firing an action (prevents double-fires).
    # 15 frames @ 30fps = 500ms cooldown between same action.
    action_cooldown_frames: int = 15

    # ── Cursor ───────────────────────────────────────────────────────────────
    # Exponential moving average alpha for cursor smoothing.
    # Range: 0.1 (very smooth, laggy) – 1.0 (raw, jittery)
    cursor_smoothing: float = 0.35

    # ── Scrolling ────────────────────────────────────────────────────────────
    scroll_speed: int = 3               # PyAutoGUI scroll units per event

    # ── ML Model ─────────────────────────────────────────────────────────────
    model_path: str = os.path.join(
        os.path.dirname(__file__), "..", "models", "gesture_model.pkl"
    )
    # Minimum ML confidence before falling back to rule-based
    # Lowered from 0.65 — a 200-sample RF model rarely exceeds 0.65 per class.
    # At 0.45 the ML model is used when confident; rule-based catches the rest.
    # Ensemble model is well-calibrated — 0.35 is safe with VotingClassifier
    ml_confidence_threshold: float = 0.35

    # ── Context Awareness ────────────────────────────────────────────────────
    context_mode_enabled: bool = True