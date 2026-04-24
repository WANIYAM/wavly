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
    hold_frames: int            = 3     # 3 frames = 100ms, fast but filters noise
    action_cooldown_frames: int = 6  # 200ms cooldown, prevents double-fire

    # ── Phase 2: Gesture Stability ───────────────────────────────────────────
    temporal_filter_size: int      = 5     # rolling buffer length
    temporal_filter_majority: int  = 3     # min votes to switch stable output
    global_cooldown_frames: int    = 2     # refractory after ANY fire
    per_gesture_cooldown_frames: int = 6   # same-gesture cooldown
    gesture_release_frames: int    = 3     # neutral frames to release active lock

    # ── Cursor ───────────────────────────────────────────────────────────────
    cursor_smoothing: float = 0.35

    # ── Scrolling ────────────────────────────────────────────────────────────
    scroll_speed: int = 3

    # ── ML Model ─────────────────────────────────────────────────────────────
    model_path: str = os.path.join(
        os.path.dirname(__file__), "..", "models", "gesture_model.pkl"
    )
    ml_confidence_threshold: float = 0.45  # Lowered: fewer UNKNOWN fallbacks

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

    # ── Phase 3: Performance ─────────────────────────────────────────────────
    skip_frames_when_lagging: bool = True

    # ── Phase 4: Adaptive Sensitivity ────────────────────────────────────────
    adaptive_enabled: bool = True
    # Path to learned user profile — persists across sessions
    adaptive_profile_path: str = os.path.join(
        os.path.dirname(__file__), "..", "models", "user_profile.json"
    )
    # How many gesture events between adaptation cycles
    adaptive_cycle_size: int = 50