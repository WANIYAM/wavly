"""
GestureClassifier — ML-first with rule-based fallback.

ML: VotingClassifier (RandomForest + SVM + GradientBoosting)
    Trained on YOUR hand — far more accurate than hardcoded thresholds.

Fallback: Ratio-based rules (relative, not absolute thresholds)
    Uses "is finger A more extended than finger B" logic —
    works for any hand size without tuning.
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

# Feature vector offsets (must match landmark_utils.py)
# [0:10]  bend angles
# [10:15] extension ratios: [index, middle, ring, pinky, thumb]
# [15:19] spread angles
# [19:61] flat xy
# [61]    pinch distance
EXT_INDEX  = 10
EXT_MIDDLE = 11
EXT_RING   = 12
EXT_PINKY  = 13
EXT_THUMB  = 14
PINCH_DIST = 60


class GestureClassifier:

    def __init__(self, settings: Settings):
        self.settings = settings
        self.ml_model = None
        self.label_encoder = None
        self._load_ml_model()

    def _load_ml_model(self):
        path = self.settings.model_path
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    saved = pickle.load(f)
                self.ml_model = saved["model"]
                self.label_encoder = saved["label_encoder"]
                print(f"[Classifier] ML model loaded — {len(self.label_encoder.classes_)} gestures: "
                      f"{list(self.label_encoder.classes_)}")
            except Exception as e:
                print(f"[Classifier] Failed to load model: {e}")
        else:
            print("[Classifier] No model found — using ratio-based rules.")
            print("             Run: python gestures/trainer.py")

    def predict(self, features: np.ndarray) -> Tuple[str, float]:
        if self.ml_model is not None:
            return self._predict_ml(features)
        return self._predict_rules(features)

    def _predict_ml(self, features: np.ndarray) -> Tuple[str, float]:
        try:
            proba = self.ml_model.predict_proba([features])[0]
            best_idx = int(np.argmax(proba))
            confidence = float(proba[best_idx])
            gesture = self.label_encoder.inverse_transform([best_idx])[0]

            if confidence >= self.settings.ml_confidence_threshold:
                return gesture, confidence

            # Below threshold — blend with rules
            rule_gesture, rule_conf = self._predict_rules(features)
            # Trust whichever is more confident
            if rule_conf > confidence:
                return rule_gesture, rule_conf
            return gesture, confidence

        except Exception as e:
            print(f"[Classifier] ML error: {e}")
            return self._predict_rules(features)

    def _predict_rules(self, features: np.ndarray) -> Tuple[str, float]:
        """
        Ratio-based rules — uses RELATIVE comparisons, not absolute values.
        Works regardless of hand size or camera distance.
        """
        i_ext  = features[EXT_INDEX]
        m_ext  = features[EXT_MIDDLE]
        r_ext  = features[EXT_RING]
        p_ext  = features[EXT_PINKY]
        th_ext = features[EXT_THUMB]
        pinch  = features[PINCH_DIST]

        # Relative comparisons — does this finger stick out more than others?
        # "Extended" = significantly longer than ring/pinky baseline
        baseline = (r_ext + p_ext) / 2.0   # ring + pinky avg as reference

        idx_up  = i_ext  > baseline * 1.4
        mid_up  = m_ext  > baseline * 1.4
        thb_up  = th_ext > baseline * 1.2
        all_up  = idx_up and mid_up and (r_ext > baseline * 1.2) and (p_ext > baseline * 1.2)
        all_dn  = (i_ext < baseline * 0.8) and (m_ext < baseline * 0.8)

        # STOP — all fingers extended (palm open)
        if all_up and thb_up:
            return STOP, 0.88

        # DRAG — all fingers folded (fist)
        if all_dn and th_ext < baseline * 0.9:
            return DRAG_START, 0.85

        # CLICK — thumb-index pinch
        # Pinch distance is already palm-normalised in feature extraction
        if pinch < 0.22 and not mid_up:
            return CLICK, 0.82

        # SCROLL — index + middle up, ring + pinky down
        if idx_up and mid_up and not (r_ext > baseline * 1.1) and not (p_ext > baseline * 1.1):
            # Scroll direction: use bend angle of index MCP (feature[0])
            # Lower angle = hand tilted up = scroll up
            index_mcp_angle = features[0]
            if index_mcp_angle < 0.4:
                return SCROLL_UP, 0.78
            else:
                return SCROLL_DOWN, 0.78

        # CURSOR MOVE — index only
        if idx_up and not mid_up:
            return CURSOR_MOVE, 0.85

        return UNKNOWN, 0.40