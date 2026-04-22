"""
Air Draw Trainer — Phase 3

Records stroke samples for each letter/shape and trains an SVM classifier.

Usage:
    python gestures/air_draw_trainer.py

How to record:
  - Press SPACE to start drawing a stroke
  - Draw the letter in the air with your index finger
  - Press SPACE again to commit the stroke
  - Press R to redo the last stroke
  - Repeat SAMPLES_PER_LETTER times per letter

Tips:
  - Draw at a consistent size
  - Start from the same position each time
  - Keep wrist still, only move finger
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import pickle
import numpy as np
import cv2
import mediapipe as mp

from sklearn.svm import SVC
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import classification_report

from gestures.air_drawing import StrokeNormalizer
from config.settings import Settings


# ── Letters to train ──────────────────────────────────────────────────────────
LETTERS = ["C", "V", "X", "Z", "S"]   # most used daily shortcuts — add more after training
# Full set available: A F P T W N O R M E
# Add letters one batch at a time for best accuracy

SAMPLES_PER_LETTER = 10    # 30 strokes per letter is enough for SVM
RASTER_SIZE        = 28


def collect_strokes(letter: str, cap, hands, mp_mod, draw_utils) -> list:
    samples  = []
    drawing  = False
    cur_pts  = []

    print(f"\n{'─'*50}")
    print(f"  Letter : {letter}")
    print(f"  Target : {SAMPLES_PER_LETTER} strokes")
    print(f"  SPACE  : start / commit stroke")
    print(f"  R      : redo last stroke")
    print(f"  Q      : quit")
    print(f"{'─'*50}")

    while len(samples) < SAMPLES_PER_LETTER:
        ret, frame = cap.read()
        if not ret:
            continue

        frame = cv2.flip(frame, 1)
        h, w  = frame.shape[:2]
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = hands.process(rgb)
        rgb.flags.writeable = True

        tip_pt = None
        if results.multi_hand_landmarks:
            hl     = results.multi_hand_landmarks[0]
            tip    = hl.landmark[8]
            tip_pt = (tip.x, tip.y)
            draw_utils.draw_landmarks(frame, hl, mp_mod.HAND_CONNECTIONS)
            cx, cy = int(tip.x * w), int(tip.y * h)
            cv2.circle(frame, (cx, cy), 8,
                       (0, 255, 0) if drawing else (0, 120, 255), -1)

        # Draw stroke trail on frame
        if drawing and len(cur_pts) > 1:
            for i in range(len(cur_pts) - 1):
                p1 = (int(cur_pts[i][0] * w),   int(cur_pts[i][1] * h))
                p2 = (int(cur_pts[i+1][0] * w), int(cur_pts[i+1][1] * h))
                cv2.line(frame, p1, p2, (0, 255, 180), 2)

        if drawing and tip_pt:
            cur_pts.append(tip_pt)

        # Status overlay
        pct     = len(samples) / SAMPLES_PER_LETTER
        bar_len = int(pct * 30)
        bar     = "█" * bar_len + "░" * (30 - bar_len)
        status  = "● RECORDING" if drawing else "○ Ready (SPACE)"
        color   = (0, 255, 100) if drawing else (200, 200, 200)

        cv2.putText(frame, f"Letter: {letter}", (10, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.putText(frame, status, (10, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)
        cv2.putText(frame, f"[{bar}] {len(samples)}/{SAMPLES_PER_LETTER}",
                    (10, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (200, 200, 200), 1)

        cv2.imshow("Air Draw Trainer", frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            return []

        elif key == ord(" "):
            if not drawing:
                # Start stroke
                cur_pts = []
                drawing = True
            else:
                # Commit stroke
                drawing = False
                features = StrokeNormalizer.to_features(cur_pts, RASTER_SIZE)
                if features is not None:
                    samples.append(features)
                    print(f"  ✓ Stroke {len(samples)}/{SAMPLES_PER_LETTER}")
                    cur_pts = []
                else:
                    print("  ✗ Stroke too short — try again")
                    cur_pts = []

        elif key == ord("r") and len(samples) > 0:
            samples.pop()
            print(f"  ↩ Removed last stroke ({len(samples)} remain)")

    print(f"  ✓ {len(samples)} strokes collected for '{letter}'")
    return samples


def train(all_X: list, all_y: list, settings: Settings):
    print("\n" + "═" * 50)
    print("  Training air-draw classifier...")
    print("═" * 50)

    X = np.array(all_X, dtype=np.float32)
    y = np.array(all_y)

    le    = LabelEncoder()
    y_enc = le.fit_transform(y)

    print(f"  Samples : {len(X)}")
    print(f"  Letters : {list(le.classes_)}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=0.2, random_state=42, stratify=y_enc
    )

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("svm",    SVC(kernel="rbf", C=10, gamma="scale",
                       probability=True, random_state=42)),
    ])

    model.fit(X_train, y_train)

    y_pred   = model.predict(X_test)
    accuracy = (y_pred == y_test).mean()

    print("\n── Per-letter results ──")
    print(classification_report(y_test, y_pred, target_names=le.classes_))
    print(f"  Test accuracy : {accuracy * 100:.1f}%")

    cv = cross_val_score(model, X, y_enc, cv=5, scoring="accuracy")
    print(f"  CV accuracy   : {cv.mean() * 100:.1f}% ± {cv.std() * 100:.1f}%")

    os.makedirs(os.path.dirname(os.path.abspath(settings.air_draw_model_path)),
                exist_ok=True)
    with open(settings.air_draw_model_path, "wb") as f:
        pickle.dump({"model": model, "label_encoder": le}, f)
    print(f"\n  ✅ Model saved → {settings.air_draw_model_path}")
    return cv.mean()


def main():
    settings = Settings()

    cap = cv2.VideoCapture(settings.camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("ERROR: Cannot open camera")
        return

    mp_mod     = mp.solutions.hands
    draw_utils = mp.solutions.drawing_utils
    hands      = mp_mod.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.6,
    )

    print("═" * 50)
    print("  Wavly Air Draw Trainer")
    print("═" * 50)
    print(f"  Letters to train : {LETTERS}")
    print(f"  Strokes per letter: {SAMPLES_PER_LETTER}")
    print()
    print("  HOW TO DRAW:")
    print("  • Point index finger, curl other fingers")
    print("  • Press SPACE to start, draw in the air")
    print("  • Press SPACE again when done")
    print("  • Keep consistent size and starting position")
    print("═" * 50)

    all_X, all_y = [], []

    for letter in LETTERS:
        strokes = collect_strokes(letter, cap, hands, mp_mod, draw_utils)
        if not strokes:
            print("Aborted.")
            cap.release()
            cv2.destroyAllWindows()
            return
        all_X.extend(strokes)
        all_y.extend([letter] * len(strokes))

    cap.release()
    cv2.destroyAllWindows()

    acc = train(all_X, all_y, settings)
    print()
    if acc >= 0.90:
        print("  🎉 Excellent accuracy! Air drawing is ready.")
    elif acc >= 0.75:
        print("  ✓  Good accuracy. Try drawing more consistently.")
    else:
        print("  ⚠  Low accuracy. Record more samples and draw consistently.")


if __name__ == "__main__":
    main()