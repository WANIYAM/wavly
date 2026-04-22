"""
Settings — Central configuration for Wavly.
Phase 4: Added adaptive engine parameters.
"""

import os


class Settings:

    # ── Camera ───────────────────────────────────────────────────────────────
    camera_index: int = 0
    show_debug_window: bool = False

    # ── MediaPipe ────────────────────────────────────────────────────────────
    min_detection_confidence: float = 0.7
    min_tracking_confidence: float  = 0.6

    # ── Gesture Debounce ─────────────────────────────────────────────────────
    hold_frames: int            = 5     # Phase 4 adaptive engine tunes this per gesture
    action_cooldown_frames: int = 8

    # ── Cursor ───────────────────────────────────────────────────────────────
    cursor_smoothing: float = 0.35

    # ── Scrolling ────────────────────────────────────────────────────────────
    scroll_speed: int = 3

    # ── ML Model ─────────────────────────────────────────────────────────────
    model_path: str = os.path.join(
        os.path.dirname(__file__), "..", "models", "gesture_model.pkl"
    )
    ml_confidence_threshold: float = 0.55   # Phase 4 adaptive tunes this per gesture

    # ── Phase 3: Air Drawing ─────────────────────────────────────────────────
    air_drawing_enabled: bool  = True
    air_draw_buffer_frames: int = 45
    air_draw_min_stroke_length: float = 0.15
    air_draw_model_path: str = os.path.join(
        os.path.dirname(__file__), "..", "models", "air_draw_model.pkl"
    )

    # ── Phase 3: Context Awareness ───────────────────────────────────────────
    context_aware_enabled: bool   = True
    context_poll_interval: float  = 1.0

    # ── Phase 4: Adaptive Sensitivity ────────────────────────────────────────
    adaptive_enabled: bool = True
    # Path to learned user profile — persists across sessions
    adaptive_profile_path: str = os.path.join(
        os.path.dirname(__file__), "..", "models", "user_profile.json"
    )
    # How many gesture events between adaptation cycles
    adaptive_cycle_size: int = 50