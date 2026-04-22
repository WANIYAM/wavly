"""
Settings — Central configuration for Wavly.

FIXED VALUES (were causing gesture detection to feel sluggish):
  hold_frames: 8 → 5   (167ms instead of 267ms — much more responsive)
  action_cooldown_frames: 15 → 8  (267ms cooldown instead of 500ms)
  ml_confidence_threshold: 0.35 → 0.55  (trust ML more, fewer rule fallbacks)
"""

import os


class Settings:

    # ── Camera ───────────────────────────────────────────────────────────────
    camera_index: int = 0
    show_debug_window: bool = False

    # ── MediaPipe ────────────────────────────────────────────────────────────
    min_detection_confidence: float = 0.7
    min_tracking_confidence: float = 0.6

    # ── Gesture Debounce ─────────────────────────────────────────────────────
    # 5 frames @ 30fps ≈ 167ms. Responsive but still filters jitter.
    hold_frames: int = 5

    # 8 frames @ 30fps = 267ms cooldown. Prevents double-fires without
    # making gestures feel unresponsive.
    action_cooldown_frames: int = 8

    # ── Cursor ───────────────────────────────────────────────────────────────
    cursor_smoothing: float = 0.35

    # ── Scrolling ────────────────────────────────────────────────────────────
    scroll_speed: int = 3

    # ── ML Model ─────────────────────────────────────────────────────────────
    model_path: str = os.path.join(
        os.path.dirname(__file__), "..", "models", "gesture_model.pkl"
    )
    # 0.55 = trust ML when it's reasonably confident.
    # Below this, blend with rules. Was 0.35 which caused too many rule
    # fallbacks that always defaulted to cursor_move.
    ml_confidence_threshold: float = 0.55

    # ── Air Drawing ──────────────────────────────────────────────────────────
    # Number of frames to buffer for stroke trajectory
    air_draw_buffer_frames: int = 45   # 1.5s at 30fps
    # Min stroke length (normalised) to attempt recognition
    air_draw_min_stroke_length: float = 0.15
    # Model path for air drawing CNN
    air_draw_model_path: str = os.path.join(
        os.path.dirname(__file__), "..", "models", "air_draw_model.pkl"
    )

    # ── Context Awareness ────────────────────────────────────────────────────
    context_mode_enabled: bool = True
    # How often to check active window (seconds)
    context_poll_interval: float = 1.0

    # ── Phase 3 ──────────────────────────────────────────────────────────────
    air_drawing_enabled: bool = True
    context_aware_enabled: bool = True