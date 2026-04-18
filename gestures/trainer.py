"""
Wavly Gesture Trainer — Improved
=================================
Records 300 samples per gesture, trains a VotingClassifier ensemble
(RandomForest + SVM + GradientBoosting), augments data for robustness.

Usage:
    python gestures/trainer.py

Tips for best accuracy:
  - Good lighting (face a window or lamp)
  - Keep your hand 40–60cm from the camera
  - Hold each gesture naturally — don't over-exaggerate
  - Record in the same conditions you'll use Wavly in
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import pickle
import numpy as np
import cv2
import mediapipe as mp

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.svm import SVC
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report

from gestures.landmark_utils import LandmarkUtils
from config.settings import Settings


# ── Gestures to train ────────────────────────────────────────────────────────
GESTURES = [
    ("cursor_move", "☝️  Point with INDEX finger only — others curled"),
    ("click",       "🤌  Pinch: bring THUMB + INDEX tips together"),
    ("scroll_up",   "✌️  INDEX + MIDDLE up, hand raised HIGH"),
    ("scroll_down", "✌️  INDEX + MIDDLE up, hand held LOW"),
    ("drag_start",  "✊  Closed FIST — all fingers curled"),
    ("stop",        "🖐️  Open PALM facing camera — all 5 fingers spread"),
]

SAMPLES     = 300   # per gesture
COUNTDOWN   = 3     # seconds before recording starts
AUG_FACTOR  = 2     # data augmentation multiplier (jitter copies)


# ── Recording ────────────────────────────────────────────────────────────────

def record_gesture(name, description, cap, hands):
    print(f"\n{'─'*52}")
    print(f"  Gesture : {name}")
    print(f"  Do this : {description}")
    print(f"{'─'*52}")
    input("  Press ENTER when ready...")

    for i in range(COUNTDOWN, 0, -1):
        print(f"  Starting in {i}...", end="\r", flush=True)
        time.sleep(1)
    print(f"  🔴 Recording {SAMPLES} frames...           ")

    samples = []
    mp_mod = mp.solutions.hands
    draw = mp.solutions.drawing_utils

    while len(samples) < SAMPLES:
        ret, frame = cap.read()
        if not ret:
            continue

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = hands.process(rgb)
        rgb.flags.writeable = True

        detected = False
        if results.multi_hand_landmarks:
            hl = results.multi_hand_landmarks[0]
            features = LandmarkUtils.landmarks_to_features(hl)
            samples.append(features)
            draw.draw_landmarks(frame, hl, mp_mod.HAND_CONNECTIONS)
            detected = True

        # Progress bar overlay
        pct = len(samples) / SAMPLES
        bar = int(pct * 28)
        bar_str = "█" * bar + "░" * (28 - bar)
        color = (0, 255, 100) if detected else (0, 80, 255)
        status = f"[{bar_str}] {len(samples)}/{SAMPLES}"
        cv2.putText(frame, name, (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        cv2.putText(frame, status, (10, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
        if not detected:
            cv2.putText(frame, "No hand detected", (10, 92),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 80, 255), 1)
        cv2.imshow("Wavly Trainer", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            print("\n  Aborted.")
            return []
        if key == ord("r"):
            print("\n  Restarting this gesture...")
            samples = []

    print(f"  ✓ {len(samples)} samples collected for '{name}'")
    return samples


# ── Augmentation ─────────────────────────────────────────────────────────────

def augment(samples: list, factor: int = AUG_FACTOR) -> np.ndarray:
    """
    Add small Gaussian noise to existing samples.
    Creates more variety without needing to re-record.
    Noise scale is small enough not to change the gesture class.
    """
    arr = np.array(samples)
    augmented = [arr]
    for _ in range(factor - 1):
        noise = np.random.normal(0, 0.012, arr.shape).astype(np.float32)
        augmented.append(arr + noise)
    return np.vstack(augmented)


# ── Training ──────────────────────────────────────────────────────────────────

def train(all_X, all_y, settings: Settings):
    print("\n" + "═" * 52)
    print("  Training ensemble model...")
    print("═" * 52)

    X = np.array(all_X, dtype=np.float32)
    y = np.array(all_y)

    le = LabelEncoder()
    y_enc = le.fit_transform(y)

    print(f"  Samples : {len(X)}")
    print(f"  Gestures: {list(le.classes_)}")
    print(f"  Features: {X.shape[1]}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=0.15, random_state=42, stratify=y_enc
    )

    # ── Ensemble: 3 diverse classifiers ──────────────────────────────────
    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_split=2,
        random_state=42,
        n_jobs=-1,
    )

    # SVC needs scaling — wrap in pipeline
    svm_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("svc", SVC(
            kernel="rbf",
            C=10,
            gamma="scale",
            probability=True,
            random_state=42,
        )),
    ])

    gb = GradientBoostingClassifier(
        n_estimators=150,
        learning_rate=0.1,
        max_depth=4,
        random_state=42,
    )

    ensemble = VotingClassifier(
        estimators=[("rf", rf), ("svm", svm_pipe), ("gb", gb)],
        voting="soft",   # uses predicted probabilities — more accurate than hard vote
        n_jobs=-1,
    )

    print("  Fitting ensemble (this takes ~30s)...")
    t0 = time.time()
    ensemble.fit(X_train, y_train)
    elapsed = time.time() - t0
    print(f"  Training time: {elapsed:.1f}s")

    # ── Evaluation ────────────────────────────────────────────────────────
    y_pred = ensemble.predict(X_test)
    accuracy = (y_pred == y_test).mean()

    print("\n── Per-gesture results ──")
    print(classification_report(y_test, y_pred, target_names=le.classes_))
    print(f"  Test accuracy : {accuracy * 100:.1f}%")

    # 5-fold CV on full dataset
    cv_scores = cross_val_score(ensemble, X, y_enc, cv=5, scoring="accuracy", n_jobs=-1)
    print(f"  CV accuracy   : {cv_scores.mean() * 100:.1f}% ± {cv_scores.std() * 100:.1f}%")

    # ── Save ──────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(os.path.abspath(settings.model_path)), exist_ok=True)
    with open(settings.model_path, "wb") as f:
        pickle.dump({"model": ensemble, "label_encoder": le}, f)
    print(f"\n  ✅ Model saved → {settings.model_path}")

    return accuracy, cv_scores.mean()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    settings = Settings()

    cap = cv2.VideoCapture(settings.camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print(f"ERROR: Cannot open camera {settings.camera_index}")
        return

    mp_mod = mp.solutions.hands
    hands = mp_mod.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.6,
    )

    print("═" * 52)
    print("  Wavly Gesture Trainer")
    print("═" * 52)
    print(f"  Gestures to record : {len(GESTURES)}")
    print(f"  Samples per gesture: {SAMPLES}")
    print(f"  Augmentation factor: {AUG_FACTOR}×  ({SAMPLES * AUG_FACTOR} effective samples)")
    print(f"  Total training data: {SAMPLES * AUG_FACTOR * len(GESTURES)} samples")
    print()
    print("  TIPS:")
    print("  • Good lighting is critical — face a window or lamp")
    print("  • Keep hand 40–60cm from camera")
    print("  • Hold naturally — don't over-exaggerate gestures")
    print("  • Press R during recording to restart a gesture")
    print("  • Press Q to abort")
    print("═" * 52)

    all_X = []
    all_y = []

    for name, description in GESTURES:
        samples = record_gesture(name, description, cap, hands)
        if not samples:
            print("[Trainer] Aborted by user.")
            cap.release()
            cv2.destroyAllWindows()
            return

        # Augment before adding
        augmented = augment(samples, factor=AUG_FACTOR)
        all_X.extend(augmented)
        all_y.extend([name] * len(augmented))
        print(f"  → {len(augmented)} total samples after augmentation")

    cap.release()
    cv2.destroyAllWindows()

    accuracy, cv_acc = train(all_X, all_y, settings)

    print()
    if cv_acc >= 0.95:
        print("  🎉 Excellent! Accuracy is very high. Run main.py to start Wavly.")
    elif cv_acc >= 0.87:
        print("  ✓  Good accuracy. Should work well in practice.")
        print("     If any gesture still misfires, re-run trainer.py just for that gesture.")
    else:
        print("  ⚠  Accuracy below target. Try:")
        print("     1. Better lighting (biggest impact)")
        print("     2. More consistent hand position during recording")
        print("     3. Re-run trainer.py")


if __name__ == "__main__":
    main()