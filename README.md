# Wavly 🖐️ — AI-Powered Gesture Interface

Touchless computer control using real-time hand tracking, gesture recognition, air drawing, context-aware automation, adaptive sensitivity, and voice commands.

---

## Project Structure

```
wavly/
├── main.py                          # Entry point — starts everything
│
├── core/
│   ├── camera_thread.py             # Webcam → MediaPipe → Gesture Queue
│   ├── action_thread.py             # Gesture Queue → PyAutoGUI actions
│   ├── gesture_queue.py             # Thread-safe event bridge
│   ├── adaptive_engine.py           # Phase 4: Learns your hand over time
│   ├── voice_thread.py              # Phase 4: Wake word + speech recognition
│   └── context_manager.py           # Phase 3: Active app detection
│
├── gestures/
│   ├── classifier.py                # ML + rule-based gesture classifier
│   ├── landmark_utils.py            # Feature engineering from landmarks
│   ├── trainer.py                   # Records + trains gesture model
│   ├── air_drawing.py               # Phase 3: Stroke buffer + recogniser
│   └── air_draw_trainer.py          # Phase 3: Records letter strokes
│
├── ui/
│   ├── tray.py                      # System tray icon (main user entry point)
│   ├── settings_window.py           # GUI settings — Gestures / Sensitivity / Adaptive / Voice
│   ├── keyboard.py                  # Two-hand floating on-screen keyboard
│   ├── adaptive_panel.py            # Phase 4: Learning stats + reset
│   ├── voice_panel.py               # Phase 4: Voice command log
│   └── overlay.py                   # Optional transparent HUD
│
├── config/
│   ├── settings.py                  # All tuneable parameters
│   ├── gesture_bindings.py          # Gesture → action mappings
│   ├── air_draw_bindings.py         # Phase 3: Letter → shortcut mappings
│   └── voice_bindings.py            # Phase 4: Spoken phrase → action mappings
│
└── models/
    ├── gesture_model.pkl            # Trained gesture model
    ├── air_draw_model.pkl           # Trained air draw model
    └── user_profile.json            # Phase 4: Adaptive learning profile
```

---

## Setup

### Requirements
- Python **3.11** — 3.12 not supported (no MediaPipe wheel)
- Windows 10/11
- A webcam

### 1. Create virtual environment

```powershell
cd D:\wavly
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install dependencies (order matters)

```powershell
pip install --upgrade pip setuptools wheel
pip install protobuf==3.20.3
pip install numpy==1.26.4
pip install mediapipe==0.10.14
pip install opencv-python==4.10.0.84 pyautogui==0.9.54 PyQt6==6.7.0
pip install scikit-learn==1.5.1 pillow==10.4.0 pyperclip
pip install pywin32 psutil
pip install SpeechRecognition pyaudio openwakeword sounddevice
```

> Voice dependencies are optional — Wavly works without them.
> If `pyaudio` fails: `pip install pipwin` then `pipwin install pyaudio`

### 3. Train gestures (required, ~5 minutes)

```powershell
python gestures/trainer.py
```

Record these 7 gestures when prompted:

| Gesture | How to do it |
|---------|-------------|
| `cursor_move` | ☝️ Index finger up, others curled |
| `click` | 🤌 Pinch thumb + index together |
| `scroll_up` | ✌️ Index + middle up, hand raised HIGH |
| `scroll_down` | ✌️ Index + middle up, hand held LOW |
| `drag_start` | ✊ Closed fist |
| `stop` | 🖐️ Open palm facing camera |
| `three_fingers` | 🤟 Index + middle + ring up |

### 4. Run Wavly

```powershell
python main.py
```

A hand icon appears in the system tray. If hidden, click `^` to reveal it.

---

## Core Gestures

| Gesture | Action |
|---------|--------|
| ☝️ Index finger | Move cursor |
| 🤌 Thumb + index pinch | Left click |
| ✌️ Two fingers raised | Scroll up |
| ✌️ Two fingers lowered | Scroll down |
| ✊ Fist (quick tap) | Start drag |
| 🖐️ Open palm | Stop / release drag |
| 🤟 Three fingers | Toggle on-screen keyboard |

---

## On-Screen Keyboard

Triggered by showing 🤟 three fingers. Show three fingers again to close.

- **Left hand** highlights keys in blue (Q W E R T side)
- **Right hand** highlights keys in green (Y U I O P side)
- **Pinch** with either hand to type the highlighted key
- Mouse clicking also works on all keys
- Full screen width, sits at bottom of screen

---

## Air Drawing (Phase 3)

Draw letters in the air to trigger keyboard shortcuts.

### How to use

| Step | Action |
|------|--------|
| 1 | ✊ **Hold fist still for 1.5 seconds** — draw mode activates |
| 2 | Move fist to trace a letter shape in the air |
| 3 | 🖐️ Open **palm** — letter is recognised and shortcut fires |

> Quick fist tap = normal drag (unchanged). Only a 1.5s hold enters draw mode.

### Train air drawing (one-time)

```powershell
python gestures/air_draw_trainer.py
```

Press **Space** to start a stroke, draw the letter, press **Space** to commit.

### Letter → shortcut bindings

| Draw | Action | Draw | Action |
|------|--------|------|--------|
| C | Copy (Ctrl+C) | N | New window (Ctrl+N) |
| V | Paste (Ctrl+V) | O | Open file (Ctrl+O) |
| X | Cut (Ctrl+X) | R | Refresh (Ctrl+R) |
| Z | Undo (Ctrl+Z) | P | Print (Ctrl+P) |
| S | Save (Ctrl+S) | T | New tab (Ctrl+T) |
| A | Select all (Ctrl+A) | W | Close tab (Ctrl+W) |
| F | Find (Ctrl+F) | M | Minimise all (Win+M) |
|   |                | E | File Explorer (Win+E) |

Edit `config/air_draw_bindings.py` to change any binding — changes apply instantly.

---

## Voice Commands (Phase 4)

Say **"Hey Wavly"** then speak your command. Supports English and Urdu.

### Examples

| Say (English) | Say (Urdu) | Action |
|--------------|------------|--------|
| "copy" | "کاپی" | Ctrl+C |
| "paste" | "پیسٹ" | Ctrl+V |
| "undo" | "واپس" | Ctrl+Z |
| "save" | "محفوظ کرو" | Ctrl+S |
| "scroll up" | "اوپر" | Scroll up |
| "new tab" | "نئی ٹیب" | Ctrl+T |
| "close" | "بند کرو" | Ctrl+W |
| "screenshot" | "اسکرین شاٹ" | Win+Shift+S |

Edit `config/voice_bindings.py` to add or change commands.

---

## Context Awareness (Phase 3)

Wavly automatically detects the active app and adjusts gesture behaviour:

| App | Changed behaviour |
|-----|------------------|
| 🎵 Spotify / VLC | Fist = play/pause, Scroll = volume |
| 📊 PowerPoint | Click = next slide, Fist = previous, Palm = exit |
| 💻 VS Code | Fist = undo (Ctrl+Z) |
| 🌐 Browser | Normal scroll |

Switching is automatic — no configuration needed. Customise in `core/context_manager.py` → `CONTEXT_PROFILES`.

---

## Adaptive Sensitivity (Phase 4)

Wavly silently watches your gestures and auto-tunes sensitivity over time:

- **High misfire rate** on a gesture → hold threshold increases automatically
- **Reliable gesture with high confidence** → hold threshold decreases (faster response)
- **Low confidence consistently** → confidence threshold adjusts down

Learning is saved to `models/user_profile.json` and reloaded on every startup.

View stats and reset in **Settings → Adaptive ✨** tab.

---

## Adding Custom Gestures

1. Open Settings → click **"+ Record gesture"**
2. Wavly pauses, trainer opens in a terminal
3. Record the gesture following the prompts
4. Wavly resumes, new gesture appears in the list
5. Pick an action from the dropdown → **Save changes**

### Action types

| Syntax | Example | Effect |
|--------|---------|--------|
| Built-in | `click`, `scroll_up` | Standard actions |
| `show_keyboard` | — | Toggle keyboard |
| `hotkey:keys` | `hotkey:ctrl+z` | Keyboard shortcut |
| `type:text` | `type:Hello!` | Type a string |
| `run:command` | `run:notepad.exe` | Open an app |

---

## Configuration

Edit `config/settings.py`:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `hold_frames` | 3 | Frames before gesture fires (lower = faster) |
| `action_cooldown_frames` | 6 | Frames between gesture fires (prevents double-fire) |
| `cursor_smoothing` | 0.35 | 0.1=smooth/laggy, 1.0=raw/fast |
| `ml_confidence_threshold` | 0.45 | Min ML confidence before rule fallback |
| `scroll_speed` | 3 | Lines per scroll event |
| `show_debug_window` | False | OpenCV preview with gesture labels |
| `air_drawing_enabled` | True | Enable/disable air drawing |
| `context_aware_enabled` | True | Enable/disable context switching |
| `adaptive_enabled` | True | Enable/disable adaptive learning |
| `voice_enabled` | True | Enable/disable voice commands |

---

## How to Quit

| Method | How |
|--------|-----|
| Tray icon | Right-click → ✕ Quit Wavly |
| Settings | Open Settings → Quit Wavly (bottom left) |
| Shortcut | `Ctrl+Shift+Q` from anywhere |

---

## Architecture

```
┌──────────┐   ┌─────────────────────────────────────────────────────────┐
│  Webcam  │──▶│  CameraThread                                           │
└──────────┘   │  OpenCV → MediaPipe (1 or 2 hands)                      │
               │  Gesture mode  → classify → debounce → GestureQueue     │
               │  Keyboard mode → 2-hand hover + pinch → keyboard        │
               │  Air draw mode → hold fist 1.5s → stroke → letter       │
               └─────────────────────────┬───────────────────────────────┘
                                         │ GestureEvent
               ┌─────────────────────────▼───────────────────────────────┐
               │  GestureQueue  (observer pattern)                        │
               │  → ActionThread    (executes actions)                    │
               │  → AdaptiveEngine  (silent observer, tunes thresholds)   │
               └─────────────────────────────────────────────────────────┘

               ┌─────────────────────────────────────────────────────────┐
               │  VoiceThread (daemon)                                    │
               │  OpenWakeWord → "Hey Wavly" → Google Speech → command   │
               │  → GestureQueue (same pipeline as gestures)             │
               └─────────────────────────────────────────────────────────┘

               ┌─────────────────────────────────────────────────────────┐
               │  Qt Main Thread                                          │
               │  WavlyTray          system tray icon                    │
               │  SettingsWindow     4-tab settings panel                │
               │  OnScreenKeyboard   full-width two-hand keyboard        │
               └─────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

**Gestures feel slow**
→ Lower `hold_frames` to 2 in `config/settings.py`
→ Lower `ml_confidence_threshold` to 0.40
→ Retrain — more samples = more consistent predictions

**Only cursor moves, other gestures don't fire**
→ Set `show_debug_window = True` to see what's being detected
→ Retrain with better lighting (face a window or lamp)
→ Check `models/gesture_model.pkl` exists

**Air drawing triggers during normal drag**
→ Hold fist for less than 1.5s for a normal drag
→ Only hold fist still for 1.5s+ when you want to draw

**Voice not working**
→ Check mic is not muted and is set as default input device
→ Verify deps: `python -c "import speech_recognition, openwakeword, sounddevice"`
→ Voice works without internet for matching but needs internet for Google transcription

**Keyboard hover not working**
→ Enable `show_debug_window = True` — dots show where fingertips are detected
→ Bring hands closer to camera so fingertips are clearly visible
→ Toggle keyboard off and on again to rebuild button rect cache

**Tray icon not visible**
→ Click `^` in Windows taskbar to show hidden icons

**`ModuleNotFoundError`**
→ Activate venv: `.venv\Scripts\activate`

**Low gesture accuracy after training**
→ Record in the same lighting you use Wavly in
→ Record 300 samples per gesture (default) — don't rush
→ Retrain including `three_fingers` gesture

---

## Roadmap

- [x] Phase 1 — Core gesture pipeline
- [x] Phase 2 — ML classifier + settings UI + custom gestures
- [x] Phase 3 — Air drawing + context awareness + two-hand keyboard
- [x] Phase 4 — Adaptive sensitivity + voice commands (English + Urdu)
- [ ] Phase 5 — Presentation mode (laser pointer, swipe slides)
- [ ] Phase 6 — Voice + gesture hybrid commands
- [ ] Phase 7 — AR/VR integration