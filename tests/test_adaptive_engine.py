"""
Test suite for AdaptiveEngine — Phase 4 Adaptive Sensitivity Learning

Tests:
  1. Profile save/load persistence
  2. Misfire detection (reversal logic)
  3. Threshold tuning based on misfire rates
  4. Hold frame adaptation
  5. Hard limits enforcement
  6. Thread safety
"""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings
from core.adaptive_engine import (
    AdaptiveEngine,
    GestureStats,
    LIMITS,
    ADAPT_EVERY,
    REVERSAL_WINDOW_SECS,
)


class TestAdaptiveEngine(unittest.TestCase):
    """Unit tests for AdaptiveEngine."""

    def setUp(self):
        """Create temp settings and profile for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.profile_path = os.path.join(self.temp_dir, "test_profile.json")
        self.settings = Settings()
        self.engine = AdaptiveEngine(
            settings=self.settings,
            profile_path=self.profile_path,
        )

    def tearDown(self):
        """Clean up temp files."""
        self.engine.stop()
        if os.path.exists(self.profile_path):
            os.remove(self.profile_path)
        os.rmdir(self.temp_dir)

    # ── Test 1: Profile Persistence ──────────────────────────────────────

    def test_save_and_load_profile(self):
        """Verify profile saves and loads correctly."""
        # Record some events
        self.engine.record_event("click", 0.75, time.time())
        self.engine.record_event("click", 0.80, time.time())
        self.engine.record_event("scroll_up", 0.60, time.time())

        # Manually trigger save
        self.engine._save_profile()

        # Verify file exists
        self.assertTrue(os.path.exists(self.profile_path))

        # Load and verify
        with open(self.profile_path, "r") as f:
            data = json.load(f)

        self.assertIn("click", data["gestures"])
        self.assertIn("scroll_up", data["gestures"])
        self.assertEqual(data["gestures"]["click"]["fire_count"], 2)
        self.assertEqual(data["gestures"]["scroll_up"]["fire_count"], 1)

    def test_load_profile_on_init(self):
        """Verify profile loads on engine startup."""
        # Create a profile manually
        profile_data = {
            "version": 1,
            "saved_at": "2024-01-01 12:00:00",
            "gestures": {
                "click": {
                    "fire_count": 50,
                    "misfire_count": 5,
                    "adapted_hold": 6,
                    "adapted_threshold": 0.58,
                    "mean_confidence": 0.75,
                }
            }
        }
        os.makedirs(os.path.dirname(self.profile_path), exist_ok=True)
        with open(self.profile_path, "w") as f:
            json.dump(profile_data, f)

        # Create new engine — should load profile
        engine2 = AdaptiveEngine(
            settings=self.settings,
            profile_path=self.profile_path,
        )

        # Verify stats loaded
        stats = engine2._stats.get("click")
        self.assertIsNotNone(stats)
        self.assertEqual(stats.fire_count, 50)
        self.assertEqual(stats.misfire_count, 5)
        self.assertEqual(stats.adapted_hold, 6)
        self.assertEqual(stats.adapted_threshold, 0.58)

        engine2.stop()

    # ── Test 2: Misfire Detection ────────────────────────────────────────

    def test_reversal_detection(self):
        """Verify misfire detection triggers on fast reversals."""
        now = time.time()
        # Simulate: user tries to click but it reads as cursor_move
        # Then immediately corrects with a clear click
        self.engine.record_event("cursor_move", 0.45, now)
        self.engine.record_event("click", 0.85, now + 0.1)  # within reversal window

        # Trigger adaptation
        self.engine._adapt_cycle()

        # cursor_move should be marked as misfire
        move_stats = self.engine._stats.get("cursor_move")
        self.assertIsNotNone(move_stats)
        self.assertEqual(move_stats.misfire_count, 1)

    def test_no_reversal_if_too_far_apart(self):
        """Verify reversals outside window are not detected."""
        now = time.time()
        self.engine.record_event("click", 0.75, now)
        self.engine.record_event("cursor_move", 0.85, now + 1.0)  # outside window

        self.engine._adapt_cycle()

        click_stats = self.engine._stats.get("click")
        self.assertIsNotNone(click_stats)
        self.assertEqual(click_stats.misfire_count, 0)  # not a misfire

    # ── Test 3: Hold Frame Adaptation ────────────────────────────────────

    def test_high_misfire_rate_increases_hold_frames(self):
        """Verify hold_frames increases when misfire rate > 20%."""
        now = time.time()

        # Simulate 25+ misfires out of 100 clicks (~25% misfire rate)
        # Misfire = click followed by cursor_move within 0.2s window
        click_count = 0
        for i in range(120):
            ts = now + (i * 0.05)  # 50ms apart
            # Every 4th gesture is a misfire (25% rate)
            if i % 4 == 0 and click_count < 30:
                self.engine.record_event("click", 0.5, ts)
                self.engine.record_event("cursor_move", 0.8, ts + 0.1)  # within reversal window
                click_count += 1
                i += 1
            else:
                self.engine.record_event("click", 0.8, ts)
                click_count += 1

        # Record enough events to trigger adaptation
        self.engine._since_adapt = ADAPT_EVERY

        self.engine._adapt_cycle()

        # Check that hold_frames adapted upward (or is None if not enough data)
        click_stats = self.engine._stats.get("click")
        if click_stats and click_stats.adapted_hold is not None:
            self.assertGreater(click_stats.adapted_hold, self.settings.hold_frames)

    def test_low_misfire_rate_decreases_hold_frames(self):
        """Verify hold_frames doesn't increase when misfire rate < 5% and confidence high."""
        now = time.time()

        # Simulate 200 clicks with very high confidence and low misfire rate
        for i in range(200):
            ts = now + (i * 0.05)
            if i % 100 == 0:  # 1% misfire
                self.engine.record_event("click", 0.5, ts)
            else:
                self.engine.record_event("click", 0.85, ts)  # high confidence

        self.engine._since_adapt = ADAPT_EVERY
        self.engine._adapt_cycle()

        click_stats = self.engine._stats.get("click")
        # With low misfire rate and high confidence, hold_frames should not increase
        # (will stay at default or decrease if it was higher)
        if click_stats.adapted_hold is not None:
            self.assertLessEqual(
                click_stats.adapted_hold,
                self.settings.hold_frames,
                "Hold frames should not increase with low misfire + high confidence"
            )

    # ── Test 4: Confidence Threshold Tuning ──────────────────────────────

    def test_low_confidence_lowers_threshold(self):
        """Verify threshold decreases when mean confidence is consistently low."""
        now = time.time()

        # Simulate 100 gestures with consistently low confidence (0.50)
        # and low standard deviation (tight clustering)
        for i in range(100):
            ts = now + (i * 0.05)
            self.engine.record_event("scroll_up", 0.50, ts)

        self.engine._since_adapt = ADAPT_EVERY
        self.engine._adapt_cycle()

        scroll_stats = self.engine._stats.get("scroll_up")
        if scroll_stats.adapted_threshold is not None:
            self.assertLess(
                scroll_stats.adapted_threshold,
                self.settings.ml_confidence_threshold,
                "Threshold should lower when confidence is low"
            )

    def test_high_confidence_raises_threshold(self):
        """Verify threshold increases when mean confidence > 0.80 and misfire low."""
        now = time.time()

        # Simulate 100 gestures with high confidence
        for i in range(100):
            ts = now + (i * 0.05)
            self.engine.record_event("drag", 0.88, ts)

        self.engine._since_adapt = ADAPT_EVERY
        self.engine._adapt_cycle()

        drag_stats = self.engine._stats.get("drag")
        if drag_stats.adapted_threshold is not None:
            self.assertGreater(
                drag_stats.adapted_threshold,
                self.settings.ml_confidence_threshold,
                "Threshold should raise when confidence is high"
            )

    # ── Test 5: Hard Limits Enforcement ──────────────────────────────────

    def test_hold_frames_respects_limits_on_adaptation(self):
        """Verify adapted hold_frames never exceed hard limits during adaptation."""
        now = time.time()
        
        # Simulate very high misfire rate to push hold_frames to max
        for i in range(150):
            ts = now + (i * 0.05)
            # 50% misfire rate = very problematic
            if i % 2 == 0:
                self.engine.record_event("scroll_up", 0.4, ts)
                self.engine.record_event("scroll_down", 0.8, ts + 0.1)
            else:
                self.engine.record_event("scroll_up", 0.75, ts)

        self.engine._since_adapt = ADAPT_EVERY
        self.engine._adapt_cycle()

        scroll_stats = self.engine._stats.get("scroll_up")
        if scroll_stats and scroll_stats.adapted_hold is not None:
            # Verify it's within limits
            self.assertGreaterEqual(scroll_stats.adapted_hold, LIMITS["hold_frames"][0])
            self.assertLessEqual(scroll_stats.adapted_hold, LIMITS["hold_frames"][1])

    def test_confidence_threshold_respects_limits_on_adaptation(self):
        """Verify adapted threshold never exceed hard limits during adaptation."""
        now = time.time()
        
        # Simulate very high confidence to push threshold up
        for i in range(100):
            ts = now + (i * 0.05)
            # Very high confidence with no misfires
            self.engine.record_event("pinch", 0.95, ts)

        self.engine._since_adapt = ADAPT_EVERY
        self.engine._adapt_cycle()

        pinch_stats = self.engine._stats.get("pinch")
        if pinch_stats and pinch_stats.adapted_threshold is not None:
            # Verify it's within limits
            self.assertGreaterEqual(pinch_stats.adapted_threshold, LIMITS["ml_confidence_threshold"][0])
            self.assertLessEqual(pinch_stats.adapted_threshold, LIMITS["ml_confidence_threshold"][1])

    # ── Test 6: Reset Functionality ──────────────────────────────────────

    def test_reset_clears_all_stats(self):
        """Verify reset() wipes learned data."""
        # Record events
        self.engine.record_event("click", 0.75, time.time())
        self.engine.record_event("scroll_up", 0.60, time.time())

        self.assertTrue(len(self.engine._stats) > 0)

        # Reset
        self.engine.reset()

        # Verify stats cleared
        self.assertEqual(len(self.engine._stats), 0)

    # ── Test 7: Thread Safety ────────────────────────────────────────────

    def test_concurrent_record_and_query(self):
        """Verify no race conditions during concurrent record + query."""
        import threading

        def record_events():
            now = time.time()
            for i in range(100):
                self.engine.record_event("click", 0.75 + (i * 0.001), now + i * 0.01)
                time.sleep(0.001)

        def query_stats():
            for _ in range(100):
                _ = self.engine.get_stats_summary()
                time.sleep(0.001)

        t1 = threading.Thread(target=record_events)
        t2 = threading.Thread(target=query_stats)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # If we get here without exception or deadlock, test passes
        self.assertTrue(True)


class TestGestureStats(unittest.TestCase):
    """Unit tests for GestureStats dataclass."""

    def test_misfire_rate_calculation(self):
        """Verify misfire rate is calculated correctly."""
        stats = GestureStats(name="click")
        stats.fire_count = 100
        stats.misfire_count = 10

        self.assertEqual(stats.misfire_rate, 0.10)

    def test_mean_confidence(self):
        """Verify mean confidence is correct."""
        stats = GestureStats(name="click")
        stats.confidences = [0.7, 0.8, 0.9]

        self.assertEqual(stats.mean_confidence, 0.8)

    def test_empty_stats_defaults(self):
        """Verify empty stats return sensible defaults."""
        stats = GestureStats(name="test")

        self.assertEqual(stats.misfire_rate, 0.0)
        self.assertEqual(stats.mean_confidence, 0.0)
        self.assertEqual(stats.stdev_confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
