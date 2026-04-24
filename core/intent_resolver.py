"""
IntentResolver — Phase 4 Feature 2: Voice + Gesture Hybrid

Maps voice + gesture pairs to hybrid actions.
Resolves intent from the combination of both signals.

Example:
  Voice: "open"
  Gesture: "point"
  → Hybrid Action: "open_file" (open file at pointed location)

Reloads bindings dynamically so changes apply without restart.
"""

import importlib
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class HybridIntent:
    """Result of hybrid intent resolution."""
    voice_action: str
    gesture_type: str
    hybrid_action: str
    confidence: float = 1.0  # Could be used for conflict resolution


class IntentResolver:
    """
    Matches (voice_action, gesture_type) pairs to hybrid actions.
    
    Workflow:
      1. Voice command "open" arrives with transcript "open file"
      2. User makes gesture "point" (pointing at a file)
      3. IntentResolver.resolve_hybrid("open", "point") → "open_file"
      4. ActionThread executes "open_file" action (application-specific)
    
    Thread-safe. Bindings are reloaded on each call.
    """

    def __init__(self):
        self._bindings = {}
        self._load_bindings()

    def resolve_hybrid(self, voice_action: str, gesture_type: str,
                     voice_confidence: float = 1.0,
                     gesture_confidence: float = 0.9) -> Optional[HybridIntent]:
        """
        Resolve a hybrid intent from voice + gesture.
        
        Args:
            voice_action: Action from voice command (e.g., "open")
            gesture_type: Type of gesture detected (e.g., "point")
            voice_confidence: Confidence of voice recognition (0-1)
            gesture_confidence: Confidence of gesture detection (0-1)
        
        Returns:
            HybridIntent with the matched action, or None if no match.
        """
        self._load_bindings()  # reload in case config changed
        
        key = (voice_action, gesture_type)
        if key in self._bindings:
            hybrid_action = self._bindings[key]
            combined_conf = voice_confidence * gesture_confidence
            
            intent = HybridIntent(
                voice_action=voice_action,
                gesture_type=gesture_type,
                hybrid_action=hybrid_action,
                confidence=combined_conf,
            )
            print(f"[IntentResolver] Hybrid match: {voice_action} + {gesture_type} "
                  f"→ {hybrid_action} ({combined_conf:.1%})")
            return intent
        
        return None

    def is_hybrid_available(self, voice_action: str) -> bool:
        """
        Check if this voice action can be paired with a gesture.
        Used to decide whether to wait for a gesture or execute voice-only.
        """
        self._load_bindings()
        # Check if any gesture can pair with this voice action
        for (v_act, _), _ in self._bindings.items():
            if v_act == voice_action:
                return True
        return False

    def _load_bindings(self):
        """Load bindings from config/hybrid_bindings.py. Reloads dynamically."""
        try:
            import config.hybrid_bindings as hb
            importlib.reload(hb)
            self._bindings = hb.HYBRID_BINDINGS
        except ImportError:
            print("[IntentResolver] hybrid_bindings.py not found — no hybrid commands available")
            self._bindings = {}
        except Exception as e:
            print(f"[IntentResolver] Error loading bindings: {e}")
            self._bindings = {}
