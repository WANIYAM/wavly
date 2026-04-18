"""
LandmarkUtils — Feature engineering from MediaPipe hand landmarks.

Feature vector (63 total):
  [0:10]   — finger bend angles at each joint (most discriminative)
  [10:15]  — finger extension ratios (tip-to-base / palm size)
  [15:19]  — inter-finger spread angles
  [19:63]  — normalized (x,y) positions for all 21 landmarks

Joint angles are invariant to hand size AND camera distance.
Extension ratios are invariant to hand size.
Together they work for any person at any reasonable camera distance.
"""

import numpy as np
from typing import List


class LandmarkUtils:

    # MediaPipe landmark indices
    WRIST = 0
    THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP       = 1, 2, 3, 4
    INDEX_MCP,  INDEX_PIP,  INDEX_DIP,  INDEX_TIP   = 5, 6, 7, 8
    MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP  = 9, 10, 11, 12
    RING_MCP,   RING_PIP,   RING_DIP,   RING_TIP    = 13, 14, 15, 16
    PINKY_MCP,  PINKY_PIP,  PINKY_DIP,  PINKY_TIP   = 17, 18, 19, 20

    # Each finger: (MCP, PIP, DIP, TIP) — angle measured at PIP joint
    FINGER_JOINTS = [
        (INDEX_MCP,  INDEX_PIP,  INDEX_DIP,  INDEX_TIP),
        (MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP),
        (RING_MCP,   RING_PIP,   RING_DIP,   RING_TIP),
        (PINKY_MCP,  PINKY_PIP,  PINKY_DIP,  PINKY_TIP),
        (THUMB_CMC,  THUMB_MCP,  THUMB_IP,   THUMB_TIP),
    ]

    # Tip + base for extension ratio
    EXTENSION_PAIRS = [
        (INDEX_TIP,  INDEX_MCP),
        (MIDDLE_TIP, MIDDLE_MCP),
        (RING_TIP,   RING_MCP),
        (PINKY_TIP,  PINKY_MCP),
        (THUMB_TIP,  THUMB_CMC),
    ]

    @staticmethod
    def landmarks_to_features(hand_landmarks) -> np.ndarray:
        lm = hand_landmarks.landmark
        pts = np.array([[l.x, l.y, l.z] for l in lm])  # (21, 3)

        # ── Normalise: translate to wrist origin, scale by palm size ──────
        wrist = pts[LandmarkUtils.WRIST].copy()
        pts -= wrist
        palm_size = np.linalg.norm(pts[LandmarkUtils.MIDDLE_MCP, :2])
        if palm_size < 1e-6:
            palm_size = 1.0
        pts /= palm_size

        # ── Feature group 1: joint bend angles (10 values) ────────────────
        # Two angles per finger: MCP bend + PIP bend
        # Angle between vectors A→B and B→C gives the bend at joint B
        bend_angles = []
        for mcp, pip, dip, tip in LandmarkUtils.FINGER_JOINTS:
            # MCP bend: wrist→MCP→PIP
            v1 = pts[mcp, :2] - pts[LandmarkUtils.WRIST, :2]
            v2 = pts[pip, :2] - pts[mcp, :2]
            bend_angles.append(LandmarkUtils._angle_between(v1, v2))

            # PIP bend: MCP→PIP→DIP
            v3 = pts[pip, :2] - pts[mcp, :2]
            v4 = pts[dip, :2] - pts[pip, :2]
            bend_angles.append(LandmarkUtils._angle_between(v3, v4))

        bend_angles = np.array(bend_angles, dtype=np.float32)  # 10 values

        # ── Feature group 2: extension ratios (5 values) ──────────────────
        extensions = []
        for tip_idx, base_idx in LandmarkUtils.EXTENSION_PAIRS:
            dist = np.linalg.norm(pts[tip_idx, :2] - pts[base_idx, :2])
            extensions.append(dist)
        extensions = np.array(extensions, dtype=np.float32)  # 5 values

        # ── Feature group 3: inter-finger spread angles (4 values) ────────
        mcp_pts = [pts[i, :2] for i in [5, 9, 13, 17]]
        spread_angles = []
        for i in range(len(mcp_pts) - 1):
            v = mcp_pts[i + 1] - mcp_pts[i]
            spread_angles.append(float(np.arctan2(v[1], v[0])))
        spread_angles = np.array(spread_angles, dtype=np.float32)  # 4 values

        # ── Feature group 4: normalised (x,y) positions (44 values) ───────
        flat_xy = pts[:, :2].flatten().astype(np.float32)  # 42 values

        # Thumb-index tip distance (pinch detector) — 1 value
        thumb_tip = pts[LandmarkUtils.THUMB_TIP, :2]
        index_tip = pts[LandmarkUtils.INDEX_TIP, :2]
        pinch_dist = np.array(
            [float(np.linalg.norm(thumb_tip - index_tip))], dtype=np.float32
        )

        features = np.concatenate([
            bend_angles,    # 10
            extensions,     # 5
            spread_angles,  # 3
            flat_xy,        # 42
            pinch_dist,     # 1
        ])  # total: 61

        return features

    @staticmethod
    def _angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
        """Angle in radians between two 2D vectors. Returns 0–π."""
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 < 1e-6 or n2 < 1e-6:
            return 0.0
        cos_a = np.dot(v1, v2) / (n1 * n2)
        cos_a = np.clip(cos_a, -1.0, 1.0)
        return float(np.arccos(cos_a))

    @staticmethod
    def get_finger_states(hand_landmarks) -> List[bool]:
        """Quick boolean finger-up check. Used by classifier fallback."""
        lm = hand_landmarks.landmark
        pts = np.array([[l.x, l.y] for l in lm])
        wrist = pts[LandmarkUtils.WRIST]
        palm = np.linalg.norm(pts[LandmarkUtils.MIDDLE_MCP] - wrist)
        if palm < 1e-6:
            palm = 1.0
        result = []
        for tip_idx, base_idx in LandmarkUtils.EXTENSION_PAIRS:
            d = np.linalg.norm(pts[tip_idx] - pts[base_idx]) / palm
            result.append(d > 0.30)
        return result  # [index, middle, ring, pinky, thumb]