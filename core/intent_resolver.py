"""
IntentResolver — Matches voice + gesture pairs to hybrid actions.

AUDIT FIX: Uses spoken transcript as the key, not the resolved action.
  Old: resolve_hybrid(voice_action="hotkey:ctrl+c", gesture="click")
       → key ("hotkey:ctrl+c", "click") → never found in bindings
  New: resolve_hybrid(transcript="copy", gesture="click")
       → key ("copy", "click") → found → returns "hotkey:ctrl+c"

is_hybrid_eligible() checks if the transcript COULD pair with ANY gesture.
It's used to decide whether to store in CommandQueue at all.
Non-eligible voice commands execute immediately without waiting.
"""

import importlib
from typing import Optional


class IntentResolver:

    def is_hybrid_eligible(self, transcript: str) -> bool:
        """
        Returns True if this transcript has ANY hybrid binding.
        Used to decide whether to store in CommandQueue.

        Voice commands with no hybrid bindings execute immediately —
        no point storing them and waiting 2 seconds for nothing.
        """
        bindings = self._load_bindings()
        transcript_lower = transcript.lower().strip()
        for (voice_key, _) in bindings:
            if voice_key.lower() == transcript_lower:
                return True
        return False

    def resolve(self, transcript: str, gesture: str) -> Optional[str]:
        """
        Look up (transcript, gesture) in HYBRID_BINDINGS.
        Returns action string or None if no match.

        AUDIT FIX: Key uses transcript (spoken word), not resolved action.
        """
        bindings         = self._load_bindings()
        transcript_lower = transcript.lower().strip()

        # Exact match first
        action = bindings.get((transcript_lower, gesture))
        if action:
            return action

        # Try with spaces normalized to underscores
        normalized = transcript_lower.replace(" ", "_")
        action = bindings.get((normalized, gesture))
        if action:
            return action

        return None

    def _load_bindings(self) -> dict:
        try:
            import config.hybrid_bindings as hb
            importlib.reload(hb)
            return hb.HYBRID_BINDINGS
        except Exception as e:
            print(f"[IntentResolver] Could not load hybrid_bindings: {e}")
            return {}