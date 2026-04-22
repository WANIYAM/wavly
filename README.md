# Wavly 🖐️ — AI-Powered Gesture Interface

Touchless computer control using real-time hand tracking, gesture recognition, air drawing, and context-aware automation.

---

## Project Structure

```
wavly/
├── main.py                        # Entry point — starts all threads + tray + keyboard
│
├── core/
│   ├── camera_thread.py           # Thread 1: Webcam → MediaPipe → Gesture Queue
│   ├── action_thread.py           # Thread 2: Gesture Queue → PyAutoGUI actions
│   ├── gesture_queue.py           # Thread-safe event bridge
│   └── context_manager.py        # Phase 3: Active app detection + gesture overrides
│
├── gestures/
│   ├── classifier.py              # ML + rule-based gesture classifier
│   ├── landmark_utils.py          # Feature engineering from MediaPipe landmarks
│   ├── trainer.py                 # Gesture trainer (cursor/click/scroll etc.)
│   ├── air_drawing.py             # Phase 3: Stroke buffer + letter recogniser
│   └── air_draw_trainer.py        # Phase 3: Records letter strokes, trains SVM
│
├── ui/
│   ├── tray.py                    # System tray icon — main user entry point
│   ├── settings_window.py         # GUI settings panel (no coding needed)
│   ├── keyboard.py                # Two-hand floating on-screen keyboard
│   └── overlay.py                 # Optional transparent HUD overlay
│
├── config/
│   ├── settings.py                # All tuneable parameters
│   ├── gesture_bindings.py        # Gesture → action mappings (managed by UI)
│   └── air_draw_bindings.py       # Phase 3: Letter → shortcut mappings
│
├── models/
│   ├── gesture_model.pkl          # Trained gesture model (from trainer.py)
│   └── air_draw_model.pkl         # Trained air draw model (from air_draw_trainer.py)
│
└── requirements.txt
```

---

## Setup

### 1. Requirements

- Python **3.11** (3.12 is NOT supported — no MediaPipe wheel)
- A webcam
- Windows 10/11 (Linux supported with minor changes)

### 2. Create virtual environment

```powershell
cd D:\wavly
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies (order matters)

```powershell
pip install --upgrade pip setuptools wheel
pip install protobuf==3.20.3
pip install numpy==1.26.4
pip install mediapipe==0.10.14
pip install opencv-python==4.10.0.84 pyautogui==0.9.54 PyQt6==6.7.0
pip install scikit-learn==1.5.1 pillow==10.4.0 pyperclip pywin32 psutil
```

### 4. Train gestures (required — takes ~5 minutes)

```powershell
python gestures/trainer.py
```

Record these 7 gestures when prompted:

| Gesture | How to do it |
|---------|-------------|
| `cursor_move` | ☝️ Index finger pointing up, others curled |
| `click` | 🤌 Pinch thumb + index together |
| `scroll_up` | ✌️ Index + middle up, hand raised HIGH |
| `scroll_down` | ✌️ Index + middle up, hand held LOW |
| `drag_start` | ✊ Closed fist |
| `stop` | 🖐️ Open palm facing camera |
| `three_fingers` | 🤟 Index + middle + ring up, pinky + thumb curled |

### 5. Run Wavly

```powershell
python main.py
```

A hand icon appears in the system tray (bottom-right taskbar). If hidden, click `^` to reveal it.

---

## Core Gestures

| Gesture | Action |
|---------|--------|
| ☝️ Index finger pointing | Move cursor |
| 🤌 Thumb + index pinch | Left click |
| ✌️ Two fingers up, raised | Scroll up |
| ✌️ Two fingers up, lowered | Scroll down |
| ✊ Closed fist | Start drag |
| 🖐️ Open palm | Stop / release drag |
| 🤟 Three fingers up | Toggle on-screen keyboard |

---

## On-Screen Keyboard (Two-Hand Typing)

Triggered by showing three fingers (🤟). Show three fingers again to close.

While the keyboard is open:
- **Left hand** highlights keys in **blue** (left side: Q W E R T / A S D F G)
- **Right hand** highlights keys in **green** (right side: Y U I O P / H J K L)
- **Pinch** with either hand to type the highlighted key
- Mouse clicking also works on all keys

---

## Phase 3 — Air Drawing

Draw letters in the air to trigger keyboard shortcuts. No extra gesture training needed — uses gestures you already recorded.

### Train air drawing (one-time setup)

```powershell
python gestures/air_draw_trainer.py
```

Draws 5 letters by default: C, V, X, Z, S. Press Space to start/commit each stroke.

### How to use

| Step | Action |
|------|--------|
| 1 | ✊ Make a **fist** — drawing mode starts |
| 2 | Move fist to draw a letter shape in the air |
| 3 | 🖐️ Open **palm** — stroke commits and shortcut fires |

### Default letter bindings

| Draw | Shortcut | Action |
|------|----------|--------|
| C | Ctrl+C | Copy |
| V | Ctrl+V | Paste |
| X | Ctrl+X | Cut |
| Z | Ctrl+Z | Undo |
| S | Ctrl+S | Save |
| A | Ctrl+A | Select All |
| F | Ctrl+F | Find |
| T | Ctrl+T | New Tab |
| W | Ctrl+W | Close Tab |
| N | Ctrl+N | New Window |
| O | Ctrl+O | Open File |
| R | Ctrl+R | Refresh |
| P | Ctrl+P | Print |
| M | Win+M | Minimise all |
| E | Win+E | File Explorer |

To change any binding, edit `config/air_draw_bindings.py` — changes apply instantly without restart.

---

## Phase 3 — Context Awareness

Wavly automatically detects your active application and adjusts gesture behavior:

| App | Gesture override |
|-----|-----------------|
| 🎵 Spotify / VLC | Fist = play/pause, Scroll = volume |
| 📊 PowerPoint | Click = next slide, Fist = previous, Palm = exit |
| 💻 VS Code | Fist = undo (Ctrl+Z) |
| 🌐 Browser | Normal scroll behavior |

Context switching is silent and automatic — no configuration needed. To customise, edit `core/context_manager.py` → `CONTEXT_PROFILES`.

---

## Adding Custom Gestures (No Coding)

1. Open Settings → click **"+ Record gesture"**
2. Wavly pauses, trainer opens in a terminal
3. Record the gesture following the prompts
4. Wavly resumes, new gesture appears in Settings
5. Pick an action from the dropdown → **Save changes**

### Available action types

| Syntax | Example | Effect |
|--------|---------|--------|
| Built-in | `click`, `scroll_up` | Standard actions |
| `show_keyboard` | — | Toggle on-screen keyboard |
| `hotkey:keys` | `hotkey:ctrl+z` | Keyboard shortcut |
| `type:text` | `type:Hello!` | Type a string |
| `run:command` | `run:notepad.exe` | Open an app |

---

## Configuration

Edit `config/settings.py`:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `hold_frames` | 5 | Frames before gesture fires (lower = faster) |
| `cursor_smoothing` | 0.35 | 0.1=smooth/laggy, 1.0=raw/fast |
| `scroll_speed` | 3 | Lines scrolled per gesture |
| `ml_confidence_threshold` | 0.55 | Min ML confidence before rule fallback |
| `show_debug_window` | False | Show OpenCV landmark + gesture preview |
| `air_drawing_enabled` | True | Enable/disable air drawing |
| `context_aware_enabled` | True | Enable/disable context switching |

---

## How to Quit

Three ways — no terminal needed:

| Method | How |
|--------|-----|
| Tray icon | Right-click → ✕ Quit Wavly |
| Settings | Open Settings → Quit Wavly button (bottom left) |
| Shortcut | `Ctrl+Shift+Q` from anywhere |

---

## Architecture

```
┌─────────────┐    ┌──────────────────────────────────────────────────────┐
│  Webcam     │───▶│  CameraThread                                        │
└─────────────┘    │  OpenCV → MediaPipe (1 or 2 hands)                   │
                   │  Gesture mode  → classify → debounce → GestureQueue  │
                   │  Keyboard mode → 2-hand hover + pinch → keyboard     │
                   │  Air draw mode → stroke buffer → letter event        │
                   └──────────────────────┬───────────────────────────────┘
                                          │ GestureEvent
                                          ▼
                              ┌───────────────────────┐
                              │      GestureQueue     │
                              └───────────┬───────────┘
                                          │
                   ┌──────────────────────▼──────────────────────────────┐
                   │  ActionThread                                         │
                   │  cursor_move   → PyAutoGUI.moveTo (60fps smoothed)   │
                   │  gesture       → context_manager → resolved action   │
                   │  air_letter:X  → air_draw_bindings → hotkey/run      │
                   │  show_keyboard → signals Qt main thread              │
                   └─────────────────────────────────────────────────────┘

                   ┌─────────────────────────────────────────────────────┐
                   │  Qt Main Thread                                       │
                   │  WavlyTray          — system tray icon               │
                   │  SettingsWindow     — gesture binding GUI            │
                   │  OnScreenKeyboard   — two-hand floating keyboard     │
                   └─────────────────────────────────────────────────────┘
```

---

## Troubleshooting

**No tray icon visible**
→ Click the `^` arrow in your Windows taskbar to show hidden icons

**`ModuleNotFoundError`**
→ Make sure venv is active: `.venv\Scripts\activate`
→ Trainer always uses the same Python as Wavly automatically

**Gestures feel slow / only cursor works**
→ Lower `hold_frames` to 4 in Settings → Sensitivity
→ Retrain with better lighting — face a window or lamp

**Air drawing not recognising letters**
→ Draw bigger and slower
→ Start and end at consistent positions
→ Retrain with more samples (increase `SAMPLES_PER_LETTER` in `air_draw_trainer.py`)

**Keyboard hover not working**
→ Enable `show_debug_window = True` to see fingertip dots
→ Bring hands closer to camera so fingertips are clearly visible

**Camera won't open**
→ Close Teams, Zoom, or any other app using the camera first

**Low gesture accuracy**
→ Retrain in the same lighting you use Wavly in
→ Record 300 samples per gesture (default) — don't rush

---

## Roadmap

- [x] Phase 1 — Core gesture pipeline (cursor, click, scroll, drag)
- [x] Phase 2 — ML gesture classifier + custom gesture training + settings UI
- [x] Phase 3 — Air drawing (letter → shortcut) + context awareness + two-hand keyboard
- [ ] Phase 4 — Adaptive sensitivity learning per user
- [ ] Phase 5 — Voice + gesture hybrid mode
- [ ] Phase 6 — AR/VR integration