"""
GestureClassifier — ML-first with rule-based fallback.

FIX: The rule-based fallback was too aggressive about returning cursor_move
for ambiguous poses. Tightened thresholds and added a dead-zone so
ambiguous poses return UNKNOWN instead of cursor_move, which prevents
the debounce from resetting constantly.
"""

import os
import numpy as np
import pickle
from typing import Tuple

from config.settings import Settings

CURSOR_MOVE  = "cursor_move"
CLICK        = "click"
SCROLL_UP    = "scroll_up"
SCROLL_DOWN  = "scroll_down"
DRAG_START   = "drag_start"
STOP         = "stop"
UNKNOWN      = "unknown"

EXT_INDEX  = 10
EXT_MIDDLE = 11
EXT_RING   = 12
EXT_PINKY  = 13
EXT_THUMB  = 14
PINCH_DIST = 60


class GestureClassifier:

    def __init__(self, settings: Settings):
        self.settings      = settings
        self.ml_model      = None
        self.label_encoder = None
        self._load_ml_model()

    def _load_ml_model(self):
        path = self.settings.model_path
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    saved = pickle.load(f)
                self.ml_model      = saved["model"]
                self.label_encoder = saved["label_encoder"]
                print(f"[Classifier] ML model loaded — "
                      f"{len(self.label_encoder.classes_)} gestures: "
                      f"{list(self.label_encoder.classes_)}")
            except Exception as e:
                print(f"[Classifier] Failed to load model: {e}")
        else:
            print("[Classifier] No model found — using ratio-based rules.")

    def reload(self):
        """Reload model from disk — called after retraining."""
        self._load_ml_model()

    def predict(self, features: np.ndarray) -> Tuple[str, float]:
        if self.ml_model is not None:
            return self._predict_ml(features)
        return self._predict_rules(features)

    def _predict_ml(self, features: np.ndarray) -> Tuple[str, float]:
        try:
            proba      = self.ml_model.predict_proba([features])[0]
            best_idx   = int(np.argmax(proba))
            confidence = float(proba[best_idx])
            gesture    = self.label_encoder.inverse_transform([best_idx])[0]

            if confidence >= self.settings.ml_confidence_threshold:
                return gesture, confidence

            # Below threshold — blend with rules
            rule_gesture, rule_conf = self._predict_rules(features)
            if rule_conf > confidence:
                return rule_gesture, rule_conf
            return gesture, confidence

        except Exception as e:
            print(f"[Classifier] ML error: {e}")
            return self._predict_rules(features)

    def _predict_rules(self, features: np.ndarray) -> Tuple[str, float]:
        """
        Tightened rule-based fallback.

        KEY FIX: ambiguous poses now return UNKNOWN instead of cursor_move.
        This stops the camera thread from calling _reset_debounce() on
        every ambiguous frame, which was preventing other gestures from
        accumulating their hold_frames count.
        """
        i_ext  = features[EXT_INDEX]
        m_ext  = features[EXT_MIDDLE]
        r_ext  = features[EXT_RING]
        p_ext  = features[EXT_PINKY]
        th_ext = features[EXT_THUMB]
        pinch  = features[PINCH_DIST]

        baseline = (r_ext + p_ext) / 2.0

        # Protect against degenerate baseline
        if baseline < 1e-4:
            return UNKNOWN, 0.30

        idx_up = i_ext  > baseline * 1.5   # tightened from 1.4
        mid_up = m_ext  > baseline * 1.5
        thb_up = th_ext > baseline * 1.2
        rng_up = r_ext  > baseline * 1.2
        pky_up = p_ext  > baseline * 1.2

        all_up = idx_up and mid_up and rng_up and pky_up
        all_dn = (i_ext < baseline * 0.7) and (m_ext < baseline * 0.7)

        # STOP — all 5 fingers clearly extended
        if all_up and thb_up:
            return STOP, 0.88

        # DRAG — clear fist
        if all_dn and th_ext < baseline * 0.8:
            return DRAG_START, 0.85

        # CLICK — tight pinch, middle finger down
        if pinch < 0.18 and not mid_up:
            return CLICK, 0.82

        # SCROLL — index + middle clearly up, ring + pinky clearly down
        if (idx_up and mid_up
                and r_ext < baseline * 0.95
                and p_ext < baseline * 0.95):
            index_mcp_angle = features[0]
            if index_mcp_angle < 0.4:
                return SCROLL_UP, 0.78
            else:
                return SCROLL_DOWN, 0.78

        # CURSOR MOVE — index clearly up, middle clearly down
        # Tighter: require middle to be well below threshold
        if idx_up and m_ext < baseline * 0.9:
            return CURSOR_MOVE, 0.80

        # Anything ambiguous → UNKNOWN (not cursor_move!)
        # This is the key fix — UNKNOWN triggers _reset_debounce only
        # if we were tracking a non-cursor gesture, not every frame.
        return UNKNOWN, 0.35