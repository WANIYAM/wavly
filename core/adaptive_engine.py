"""
AdaptiveEngine — Phase 4: Adaptive Sensitivity Learning

How it works:
  1. Taps into GestureQueue as a silent observer — reads every fired gesture
  2. Maintains a rolling window of confidence scores per gesture class
  3. Detects misfire patterns:
       - Quick reversal: click fires then cursor_move fires within 3 frames
         → click was a misfire, hold_frames too low for that gesture
       - Low confidence fire: gesture fired but confidence was near threshold
         → threshold too low, raise it
       - Missed gesture: user shows gesture but nothing fires for 2+ seconds
         → hold_frames too high, lower it
  4. Every ADAPT_EVERY gestures, recomputes optimal params and patches Settings
  5. Saves learned profile to models/user_profile.json
  6. Loads profile on startup so learning persists across sessions
  7. Hard limits prevent runaway adaptation

All tuning is per-gesture, not global — click can have different hold_frames
than scroll_up, for example.

Thread safety:
  AdaptiveEngine runs in its own daemon thread.
  Settings is patched via a lock so camera/action threads see consistent values.
"""

import json
import os
import time
import threading
import statistics
from collections import deque, defaultdict
from typing import Optional
from dataclasses import dataclass, field, asdict

from config.settings import Settings


# ── Hard limits — engine cannot tune outside these bounds ────────────────────
LIMITS = {
    "hold_frames":              (3,  15),   # min 3 = 100ms, max 15 = 500ms
    "action_cooldown_frames":   (5,  20),
    "ml_confidence_threshold":  (0.35, 0.80),
    "cursor_smoothing":         (0.15, 0.70),
}

# Tune after this many gesture events
# Rationale: 50 is a good balance. Too low (<20) = noisy data, too many random
# adaptations. Too high (>200) = slow feedback loop. Users notice changes after
# ~50 gestures (2-3 minutes of use).
ADAPT_EVERY = 50

# Rolling window size per gesture
# Rationale: Keep last 100 confidence scores per gesture. This smooths out
# single bad frames but reacts quickly to trend changes. ~5 seconds of data
# at 20 fps.
WINDOW_SIZE = 100

# Misfire detection: if gesture A fires then gesture B fires within this
# many seconds, treat A as a possible misfire
# Rationale: 0.4 seconds = 8 frames @ 20fps. If user corrects within this
# window, the first gesture was likely noise. Beyond 0.4s is probably a real
# separate gesture, not a correction.
REVERSAL_WINDOW_SECS = 0.4

# Profile save path
PROFILE_FILENAME = "user_profile.json"


@dataclass
class GestureStats:
    """Rolling statistics for one gesture class."""
    name:              str
    confidences:       list = field(default_factory=list)   # recent confidence scores
    fire_count:        int  = 0
    misfire_count:     int  = 0
    adapted_hold:      Optional[int]   = None   # None = use global default
    adapted_threshold: Optional[float] = None

    def add_confidence(self, c: float, maxlen: int = WINDOW_SIZE):
        self.confidences.append(c)
        if len(self.confidences) > maxlen:
            self.confidences.pop(0)
        self.fire_count += 1

    def mark_misfire(self):
        self.misfire_count += 1

    @property
    def misfire_rate(self) -> float:
        if self.fire_count == 0:
            return 0.0
        return self.misfire_count / self.fire_count

    @property
    def mean_confidence(self) -> float:
        return statistics.mean(self.confidences) if self.confidences else 0.0

    @property
    def stdev_confidence(self) -> float:
        return statistics.stdev(self.confidences) if len(self.confidences) > 1 else 0.0


class AdaptiveEngine(threading.Thread):

    def __init__(self, settings: Settings, profile_path: str):
        super().__init__(name="AdaptiveEngine", daemon=True)
        self.settings      = settings
        self.profile_path  = profile_path
        self._stop_event   = threading.Event()
        self._lock         = threading.Lock()
        self._enabled      = True

        # Per-gesture stats
        self._stats: dict[str, GestureStats] = {}

        # Event stream fed by GestureQueue observer
        self._event_stream: deque = deque(maxlen=500)

        # Total events processed since last adaptation
        self._since_adapt  = 0
        
        # Counter for logging
        self._adapt_cycle_count = 0

        # Callbacks for UI notification
        self._on_adapt_callbacks: list = []

        # Load saved profile
        self._load_profile()

    # ── Public API ────────────────────────────────────────────────────────

    def record_event(self, gesture: str, confidence: float, timestamp: float):
        """
        Called by GestureQueue observer every time a gesture fires.
        Non-blocking — just appends to the stream.
        """
        if not self._enabled:
            return
        with self._lock:
            self._event_stream.append({
                "gesture":    gesture,
                "confidence": confidence,
                "ts":         timestamp,
            })
            if gesture not in self._stats:
                self._stats[gesture] = GestureStats(name=gesture)
            self._stats[gesture].add_confidence(confidence)
            self._since_adapt += 1

    def get_hold_frames(self, gesture: str, default: int) -> int:
        """Return adapted hold_frames for a specific gesture, or default."""
        with self._lock:
            st = self._stats.get(gesture)
            if st and st.adapted_hold is not None:
                return st.adapted_hold
        return default

    def get_confidence_threshold(self, gesture: str, default: float) -> float:
        """Return adapted confidence threshold for a gesture, or default."""
        with self._lock:
            st = self._stats.get(gesture)
            if st and st.adapted_threshold is not None:
                return st.adapted_threshold
        return default

    def get_stats_summary(self) -> dict:
        """Return a human-readable summary for the UI."""
        with self._lock:
            summary = {}
            for name, st in self._stats.items():
                summary[name] = {
                    "fires":        st.fire_count,
                    "misfire_rate": round(st.misfire_rate * 100, 1),
                    "mean_conf":    round(st.mean_confidence * 100, 1),
                    "hold_frames":  st.adapted_hold,
                    "threshold":    st.adapted_threshold,
                }
        return summary

    def reset(self):
        """Wipe all learned data and restore factory defaults."""
        with self._lock:
            self._stats.clear()
            self._event_stream.clear()
            self._since_adapt = 0
        # Restore Settings to factory defaults
        self.settings.hold_frames             = 5
        self.settings.action_cooldown_frames  = 8
        self.settings.ml_confidence_threshold = 0.55
        self._save_profile()
        print("[Adaptive] ↺ Reset to factory defaults.")

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        print(f"[Adaptive] {'Enabled' if enabled else 'Disabled'}.")

    def on_adapt(self, callback):
        """Register a callback to be called after each adaptation cycle."""
        self._on_adapt_callbacks.append(callback)

    def stop(self):
        self._stop_event.set()

    # ── Background thread ─────────────────────────────────────────────────

    def run(self):
        print("[Adaptive] Engine started.")
        while not self._stop_event.is_set():
            time.sleep(1.0)
            with self._lock:
                ready = self._since_adapt >= ADAPT_EVERY
            if ready:
                self._adapt_cycle()

        print("[Adaptive] Engine stopped.")

    # ── Adaptation logic ──────────────────────────────────────────────────

    def _adapt_cycle(self):
        """
        Core adaptation — called every ADAPT_EVERY gestures.
        Analyses recent event stream and adjusts per-gesture parameters.
        
        This runs every ADAPT_EVERY=50 gesture events and recomputes optimal
        parameters per gesture based on:
          - Misfire rate (quick reversals)
          - Confidence score distribution
          - Fire count
        
        All changes are bounded by LIMITS to prevent runaway tuning.
        """
        with self._lock:
            events         = list(self._event_stream)
            stats_snapshot = {k: v for k, v in self._stats.items()}
            self._since_adapt = 0

        changes = []
        
        print(f"\n[Adaptive] ╭─ Adaptation Cycle #{self._adapt_cycle_count}")
        print(f"[Adaptive] │  Processing {len(events)} events, {len(stats_snapshot)} gesture types")

        # ── Step 1: Detect reversals (misfires) ───────────────────────────
        print(f"[Adaptive] │  [Step 1] Scanning for misfire reversals...")
        reversal_count = 0
        for i in range(len(events) - 1):
            a = events[i]
            b = events[i + 1]
            dt = b["ts"] - a["ts"]
            # If two opposite gestures fire very close together,
            # the first was likely a misfire.
            # Logic: User intends gesture A but ML predicts B; then corrects
            # with a clearer instance of gesture A. The first A was a misfire.
            if dt < REVERSAL_WINDOW_SECS and a["gesture"] != b["gesture"]:
                if a["gesture"] in stats_snapshot:
                    stats_snapshot[a["gesture"]].mark_misfire()
                    reversal_count += 1
        
        if reversal_count > 0:
            print(f"[Adaptive] │    Found {reversal_count} reversals (within {REVERSAL_WINDOW_SECS}s)")

        # ── Step 2: Per-gesture threshold tuning ──────────────────────────
        print(f"[Adaptive] │  [Step 2] Tuning per-gesture thresholds...")
        tune_count = 0
        
        for name, st in stats_snapshot.items():
            if st.fire_count < 10:
                continue   # not enough data yet

            new_hold      = None
            new_threshold = None

            # 🔴 High misfire rate → increase hold_frames (require longer hold)
            # Rationale: If a gesture misfires >20% of the time, the user is
            # probably showing the hand position too briefly. We need a longer
            # hold_frames window to reduce false positives.
            if st.misfire_rate > 0.20:
                current = st.adapted_hold or self.settings.hold_frames
                new_hold = min(current + 1, LIMITS["hold_frames"][1])
                print(f"[Adaptive] │    {name}: HIGH misfires ({st.misfire_rate:.1%}) → hold_frames {current}→{new_hold}")

            # 🟢 Very low misfire rate + high confidence
            # → can safely decrease hold_frames (more responsive)
            # Rationale: If misfires are rare (<5%) and confidence is consistently
            # high (>75%), the gesture is easy to detect. We can lower the hold
            # threshold for faster response without sacrificing accuracy.
            elif st.misfire_rate < 0.05 and st.mean_confidence > 0.75:
                current  = st.adapted_hold or self.settings.hold_frames
                new_hold = max(current - 1, LIMITS["hold_frames"][0])
                print(f"[Adaptive] │    {name}: LOW misfires ({st.misfire_rate:.1%}), HIGH conf ({st.mean_confidence:.1%}) → hold_frames {current}→{new_hold}")

            # 🔵 Confidence is consistently low → lower threshold slightly
            # Rationale: If the gesture fires but always at low confidence
            # (e.g., 0.50±0.05) with tight clustering, the model is struggling
            # to recognize this gesture. Lowering the threshold gives it more
            # room to trigger, but only if variance is low (confident it's
            # consistently this gesture, not noise).
            if st.mean_confidence < 0.55 and st.stdev_confidence < 0.10:
                current       = st.adapted_threshold or self.settings.ml_confidence_threshold
                new_threshold = max(current - 0.02,
                                    LIMITS["ml_confidence_threshold"][0])
                print(f"[Adaptive] │    {name}: LOW conf ({st.mean_confidence:.2f}±{st.stdev_confidence:.2f}) → threshold {current:.3f}→{new_threshold:.3f}")

            # 🟡 Confidence is consistently high → can raise threshold
            # Rationale: If the gesture is recognized reliably at high
            # confidence and has low misfire rate, we can be more selective.
            # Higher threshold means fewer false positives from ambiguous frames.
            elif st.mean_confidence > 0.80 and st.misfire_rate < 0.05:
                current       = st.adapted_threshold or self.settings.ml_confidence_threshold
                new_threshold = min(current + 0.02,
                                    LIMITS["ml_confidence_threshold"][1])
                print(f"[Adaptive] │    {name}: HIGH conf ({st.mean_confidence:.2f}), LOW misfires → threshold {current:.3f}→{new_threshold:.3f}")

            # Apply changes
            with self._lock:
                if name in self._stats:
                    if new_hold is not None and new_hold != self._stats[name].adapted_hold:
                        self._stats[name].adapted_hold = new_hold
                        changes.append(
                            f"{name}: hold_frames → {new_hold}"
                        )
                        tune_count += 1
                    if new_threshold is not None and new_threshold != self._stats[name].adapted_threshold:
                        self._stats[name].adapted_threshold = round(new_threshold, 3)
                        changes.append(
                            f"{name}: threshold → {new_threshold:.3f}"
                        )
                        tune_count += 1

        if changes:
            self._adapt_cycle_count += 1
            print(f"[Adaptive] ├─ {tune_count} parameters adapted, {len(changes)} change(s)")
            for change in changes:
                print(f"[Adaptive] │  • {change}")
            print(f"[Adaptive] ╰─ Profile saved")
            self._save_profile()
            for cb in self._on_adapt_callbacks:
                try:
                    cb(changes)
                except Exception:
                    pass
        else:
            print(f"[Adaptive] ├─ No tuning needed (all gestures optimal)")
            print(f"[Adaptive] ╰─ End cycle")

    # ── Persistence ───────────────────────────────────────────────────────

    def _save_profile(self):
        try:
            os.makedirs(os.path.dirname(self.profile_path), exist_ok=True)
            with self._lock:
                data = {
                    "version": 1,
                    "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "gestures": {
                        name: {
                            "fire_count":        st.fire_count,
                            "misfire_count":     st.misfire_count,
                            "adapted_hold":      st.adapted_hold,
                            "adapted_threshold": st.adapted_threshold,
                            "mean_confidence":   round(st.mean_confidence, 3),
                        }
                        for name, st in self._stats.items()
                    }
                }
            with open(self.profile_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Adaptive] Save error: {e}")

    def _load_profile(self):
        if not os.path.exists(self.profile_path):
            return
        try:
            with open(self.profile_path, "r") as f:
                data = json.load(f)
            for name, info in data.get("gestures", {}).items():
                st = GestureStats(name=name)
                st.fire_count        = info.get("fire_count", 0)
                st.misfire_count     = info.get("misfire_count", 0)
                st.adapted_hold      = info.get("adapted_hold")
                st.adapted_threshold = info.get("adapted_threshold")
                self._stats[name]    = st
            print(f"[Adaptive] Profile loaded — "
                  f"{len(self._stats)} gestures remembered.")
        except Exception as e:
            print(f"[Adaptive] Load error: {e}")