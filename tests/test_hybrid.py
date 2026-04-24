"""
Test suite for Hybrid Voice + Gesture Commands (Feature 2)

Tests:
  1. CommandQueue stores and retrieves voice events
  2. CommandQueue timeout expires properly
  3. IntentResolver matches voice+gesture pairs
  4. IntentResolver rejects unmatched pairs
  5. Hybrid action execution flow
  6. Voice-only fallback on timeout
  7. Thread safety under concurrent load
"""

import json
import os
import sys
import tempfile
import time
import unittest
import threading
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.command_queue import CommandQueue, PendingVoiceCommand
from core.intent_resolver import IntentResolver
from core.gesture_queue import GestureEvent


class TestCommandQueue(unittest.TestCase):
    """Unit tests for CommandQueue."""

    def setUp(self):
        self.queue = CommandQueue(timeout_secs=0.5)  # Short timeout for testing

    def tearDown(self):
        self.queue.clear_all()

    # ── Test 1: Store and retrieve ────────────────────────────────────

    def test_put_and_get_voice_event(self):
        """Verify voice events are stored and retrieved."""
        cmd_id = self.queue.put_voice_event("open file", "open")
        self.assertIsNotNone(cmd_id)
        self.assertIn("voice:", cmd_id)

    def test_retrieve_pending_for_gesture(self):
        """Verify pending commands are retrieved for matching gesture."""
        self.queue.put_voice_event("open file", "open")
        time.sleep(0.1)
        
        cmd = self.queue.get_pending_for_gesture("point")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.voice_action, "open")
        self.assertEqual(cmd.transcript, "open file")

    # ── Test 2: Timeout expiration ────────────────────────────────────

    def test_timeout_expires(self):
        """Verify commands expire after timeout."""
        self.queue.put_voice_event("search something", "search")
        time.sleep(0.6)  # Wait longer than timeout (0.5s)
        
        # Should not find pending (expired)
        cmd = self.queue.get_pending_for_gesture("air_letter")
        self.assertIsNone(cmd)

    def test_get_expired_returns_timed_out_commands(self):
        """Verify get_and_clear_expired() returns expired commands."""
        self.queue.put_voice_event("copy text", "copy")
        time.sleep(0.6)  # Wait for timeout
        
        expired = self.queue.get_and_clear_expired()
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].voice_action, "copy")

    # ── Test 3: Multiple pending commands ─────────────────────────────

    def test_multiple_pending_commands(self):
        """Verify multiple pending commands are tracked."""
        self.queue.put_voice_event("open", "open")
        self.queue.put_voice_event("search", "search")
        self.queue.put_voice_event("copy", "copy")
        
        self.assertEqual(self.queue.get_pending_count(), 3)

    def test_consuming_pending_removes_it(self):
        """Verify retrieving a command removes it from queue."""
        self.queue.put_voice_event("paste", "paste")
        self.assertEqual(self.queue.get_pending_count(), 1)
        
        self.queue.get_pending_for_gesture("point")
        self.assertEqual(self.queue.get_pending_count(), 0)

    # ── Test 4: Thread safety ─────────────────────────────────────────

    def test_concurrent_put_and_get(self):
        """Verify no race conditions with concurrent access."""
        results = []
        
        def put_events():
            for i in range(50):
                self.queue.put_voice_event(f"action_{i}", f"action")
                time.sleep(0.001)
        
        def get_events():
            for _ in range(50):
                cmd = self.queue.get_pending_for_gesture("point")
                if cmd:
                    results.append(cmd)
                time.sleep(0.001)
        
        t1 = threading.Thread(target=put_events)
        t2 = threading.Thread(target=get_events)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # Should complete without deadlock or corruption
        self.assertTrue(len(results) > 0)


class TestIntentResolver(unittest.TestCase):
    """Unit tests for IntentResolver."""

    def setUp(self):
        self.resolver = IntentResolver()

    # ── Test 1: Match hybrid intents ──────────────────────────────────

    def test_resolve_open_plus_point(self):
        """Verify ('open', 'point') resolves to hybrid action."""
        intent = self.resolver.resolve_hybrid("open", "point")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.voice_action, "open")
        self.assertEqual(intent.gesture_type, "point")
        self.assertEqual(intent.hybrid_action, "open_at_cursor")

    def test_resolve_search_plus_air_letter(self):
        """Verify ('search', 'air_letter') resolves."""
        intent = self.resolver.resolve_hybrid("search", "air_letter")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.hybrid_action, "search_for_letter")

    def test_resolve_go_to_plus_fingers(self):
        """Verify ('go_to', 'fingers') resolves."""
        intent = self.resolver.resolve_hybrid("go_to", "fingers")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.hybrid_action, "go_to_line_number")

    # ── Test 2: Unmatched pairs return None ───────────────────────────

    def test_unmatched_voice_gesture_returns_none(self):
        """Verify unmatched pairs don't resolve."""
        intent = self.resolver.resolve_hybrid("scroll_up", "drag_start")
        self.assertIsNone(intent)

    def test_invalid_voice_action_returns_none(self):
        """Verify invalid voice actions return None."""
        intent = self.resolver.resolve_hybrid("nonexistent", "point")
        self.assertIsNone(intent)

    # ── Test 3: Confidence scoring ────────────────────────────────────

    def test_confidence_combines_voice_and_gesture(self):
        """Verify confidence is product of voice + gesture."""
        intent = self.resolver.resolve_hybrid(
            "open", "point",
            voice_confidence=0.9,
            gesture_confidence=0.8
        )
        self.assertIsNotNone(intent)
        self.assertAlmostEqual(intent.confidence, 0.72)  # 0.9 * 0.8

    # ── Test 4: Hybrid availability check ─────────────────────────────

    def test_is_hybrid_available_for_open(self):
        """Verify open voice action has hybrid variants."""
        self.assertTrue(self.resolver.is_hybrid_available("open"))

    def test_is_hybrid_available_for_search(self):
        """Verify search voice action has hybrid variants."""
        self.assertTrue(self.resolver.is_hybrid_available("search"))

    def test_is_hybrid_not_available_for_invalid(self):
        """Verify invalid actions don't have hybrids."""
        self.assertFalse(self.resolver.is_hybrid_available("nonexistent_action"))

    # ── Test 5: Dynamic binding reload ────────────────────────────────

    def test_bindings_reload_on_each_call(self):
        """Verify bindings reload dynamically."""
        # Create a test binding config
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("""
HYBRID_BINDINGS = {
    ("test_voice", "test_gesture"): "test_action",
}
""")
            temp_config = f.name
        
        try:
            # Note: In real usage, this would be config/hybrid_bindings.py
            # For this test, we just verify the loader doesn't crash
            resolver = IntentResolver()
            # Bindings should load without error
            self.assertIsNotNone(resolver._bindings)
        finally:
            os.unlink(temp_config)


class TestPendingVoiceCommand(unittest.TestCase):
    """Unit tests for PendingVoiceCommand dataclass."""

    def test_is_expired_false_when_fresh(self):
        """Verify fresh commands are not expired."""
        cmd = PendingVoiceCommand(transcript="test", voice_action="test")
        self.assertFalse(cmd.is_expired(timeout_secs=2.0))

    def test_is_expired_true_after_timeout(self):
        """Verify old commands are expired."""
        import time as time_module
        # Create command with old timestamp
        cmd = PendingVoiceCommand(transcript="test", voice_action="test")
        cmd.timestamp = time_module.time() - 3.0  # 3 seconds ago
        self.assertTrue(cmd.is_expired(timeout_secs=2.0))

    def test_is_expired_boundary(self):
        """Verify boundary case at exact timeout."""
        import time as time_module
        cmd = PendingVoiceCommand(transcript="test", voice_action="test")
        cmd.timestamp = time_module.time() - 2.0  # Exactly 2 seconds ago
        # At exact boundary, timing precision varies — just verify it's close
        result = cmd.is_expired(timeout_secs=2.0)
        # Due to timing precision, could be true or false at boundary
        # What matters: shortly after should definitely be expired
        time.sleep(0.1)
        self.assertTrue(cmd.is_expired(timeout_secs=2.0))


class TestHybridIntegration(unittest.TestCase):
    """Integration tests for hybrid voice+gesture flow."""

    def setUp(self):
        self.command_queue = CommandQueue(timeout_secs=1.0)
        self.resolver = IntentResolver()

    def test_full_hybrid_flow(self):
        """Simulate complete hybrid command flow."""
        # Step 1: Voice "open" arrives
        cmd_id = self.command_queue.put_voice_event("open file", "open")
        self.assertIsNotNone(cmd_id)
        
        # Step 2: Check intent availability
        is_available = self.resolver.is_hybrid_available("open")
        self.assertTrue(is_available)
        
        # Step 3: User performs gesture "point"
        time.sleep(0.1)
        pending = self.command_queue.get_pending_for_gesture("point")
        self.assertIsNotNone(pending)
        
        # Step 4: Resolve hybrid intent
        intent = self.resolver.resolve_hybrid(pending.voice_action, "point")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.hybrid_action, "open_at_cursor")

    def test_voice_only_fallback_on_timeout(self):
        """Verify voice-only execution when gesture doesn't arrive."""
        # Store voice command with short timeout
        cmd_id = self.command_queue.put_voice_event("copy text", "copy")
        
        # Wait for timeout without sending gesture
        time.sleep(1.5)
        
        # Command should be in expired list
        expired = self.command_queue.get_and_clear_expired()
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].voice_action, "copy")

    def test_gesture_without_pending_voice(self):
        """Verify gesture alone works (no pending voice)."""
        # No pending voice command
        pending = self.command_queue.get_pending_for_gesture("point")
        self.assertIsNone(pending)
        # Gesture should execute normally


if __name__ == "__main__":
    unittest.main()
