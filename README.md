# Wavly 🖐️ — AI-Powered Gesture Interface

Touchless computer control using real-time hand tracking, gesture recognition, air drawing, context-aware automation, adaptive sensitivity, voice commands, **hybrid voice+gesture commands**, and **presentation mode**.

---

## Project Structure

```
wavly/
├── main.py                          # Entry point — starts everything
│
├── core/                            # Runtime engine
│   ├── camera_thread.py             # Webcam → MediaPipe → Gesture Queue
│   ├── action_thread.py             # Gesture Queue → PyAutoGUI actions
│   ├── gesture_queue.py             # Thread-safe event bridge
│   ├── command_queue.py             # Phase 4: Voice events pending gesture pairing
│   ├── intent_resolver.py           # Phase 4: Maps voice+gesture → hybrid action
│   ├── adaptive_engine.py           # Phase 4: Learns your hand over time
│   ├── voice_thread.py              # Phase 4: Wake word + speech recognition
│   ├── context_manager.py           # Phase 3: Active app detection
│   └── presentation_mode.py         # Phase 5: Laser pointer + slide controls
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
│   ├── overlay.py                   # Optional transparent HUD
│   └── laser_pointer.py             # Phase 5: Always-on-top laser dot
│
├── config/
│   ├── settings.py                  # All tuneable parameters
│   ├── gesture_bindings.py          # Gesture → action mappings
│   ├── air_draw_bindings.py         # Phase 3: Letter → shortcut mappings
│   ├── voice_bindings.py            # Phase 4: Spoken phrase → action mappings
│   └── hybrid_bindings.py           # Phase 4: (voice, gesture) → hybrid action mappings
│
├── models/
│   ├── gesture_model.pkl            # Trained gesture model
│   ├── air_draw_model.pkl           # Trained air draw model
│   └── user_profile.json            # Phase 4: Adaptive learning profile
│
├── tests/
│   ├── test_hybrid.py               # Phase 4: Voice+Gesture unit tests
│   └── test_adaptive_engine.py      # Phase 4: Adaptive engine unit tests
│
├── audits/                          # Technical verification reports
│   ├── phase1_verification.md
│   ├── phase2_verification.md
│   ├── phase3_verification.md
│   ├── phase4_verification.md
│   ├── final_diagnostic.md
│   └── ...
│
├── requirements.txt                 # Full dependency list with pinned versions
├── REVIEW.md                        # Full technical audit & improvement roadmap
├── TODO.md                          # Current task tracking
└── PHASE4_DEEP_DIVE.md              # Deep-dive on Phase 4 features
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

### 2. Install dependencies

**Option A — Using requirements.txt:**
```powershell
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

**Option B — Manual install (order matters):**
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

## Hybrid Voice + Gesture Commands (Phase 4)

Combine voice and gesture for actions neither can do alone. Say a voice command, then perform a gesture within **2 seconds**.

### How it works

```
Voice: "open"  →  stored in CommandQueue (waits 2s)
Gesture: ☝️ point  →  IntentResolver matches ("open", "point")
Result: "open_at_cursor" action fires
```

If no matching gesture arrives within 2 seconds, the voice command executes as **voice-only**.

### Hybrid bindings

| Voice | Gesture | Result |
|-------|---------|--------|
| "open" | ☝️ Point | Open file/folder at cursor position |
| "search" | ✊ Air letter | Search for the drawn letter |
| "scroll up" | ✌️ Scroll up | Scroll up faster |
| "scroll down" | ✌️ Scroll down | Scroll down faster |
| "click" | ☝️ Point | Click where pointing (reinforces intent) |

Edit `config/hybrid_bindings.py` to add custom pairings — changes reload dynamically.

### Architecture

- `VoiceThread` → `CommandQueue` (stores pending voice events)
- `CameraThread` → gesture detected → `ActionThread` checks `CommandQueue`
- `IntentResolver` matches `(voice_action, gesture_type)` → hybrid action
- If no match: voice-only fallback executes automatically

---

## Presentation Mode (Phase 5)

A dedicated mode for giving presentations. Activates **automatically** when PowerPoint is in focus, or toggle manually via the tray icon.

### Presentation gestures

| Gesture | Action |
|---------|--------|
| ☝️ Index finger move | Laser pointer dot follows fingertip |
| 👈 Swipe left | Previous slide |
| 👉 Swipe right | Next slide |
| 🤌 Click / pinch | Next slide |
| ✊ Fist | Black screen (B key) |
| 🖐️ Open palm | Exit slideshow (Escape) |
| 🤟 Three fingers | Zoom in (Ctrl++) |
| ✌️ Two fingers | Zoom out (Ctrl+−) |

### Laser pointer

- Small glowing always-on-top red dot
- Smooth exponential moving average tracking
- Fades out when hand leaves frame
- Never steals focus from PowerPoint
- Color configurable (red/green)

### Swipe detection

Tracks fingertip X movement over 12 frames. If consistent displacement exceeds the threshold, a slide change fires with a 1.2-second cooldown to prevent rapid multi-fire.

---

## Context Awareness (Phase 3)

Wavly automatically detects the active app and adjusts gesture behaviour:

| App | Changed behaviour |
|-----|------------------|
| 🎵 Spotify / VLC | Fist = play/pause, Scroll = volume |
| 📊 PowerPoint | Auto-activates **Presentation Mode** |
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
| `temporal_filter_size` | 5 | Rolling buffer for gesture stability filtering |
| `temporal_filter_majority` | 3 | Min votes to switch stable output |
| `skip_frames_when_lagging` | True | Drop frames if inference falls behind |
| `adaptive_cycle_size` | 50 | Gesture events between adaptation cycles |
| `context_poll_interval` | 1.0 | Seconds between active window checks |

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
               │  Presentation  → swipe detection + laser pointer        │
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
               │  → CommandQueue → IntentResolver → ActionThread         │
               └─────────────────────────────────────────────────────────┘

               ┌─────────────────────────────────────────────────────────┐
               │  PresentationMode (auto-activated)                       │
               │  LaserPointer + SwipeDetector + slide controls          │
               └─────────────────────────────────────────────────────────┘

               ┌─────────────────────────────────────────────────────────┐
               │  Qt Main Thread                                          │
               │  WavlyTray          system tray icon                    │
               │  SettingsWindow     4-tab settings panel                │
               │  OnScreenKeyboard   full-width two-hand keyboard        │
               │  LaserPointer       always-on-top dot                   │
               └─────────────────────────────────────────────────────────┘
```

---

## Tests

Run the test suite:

```powershell
python -m unittest discover tests/
```

### Test coverage

| File | What it tests |
|------|--------------|
| `tests/test_hybrid.py` | CommandQueue, IntentResolver, voice-only fallback, thread safety |
| `tests/test_adaptive_engine.py` | Adaptive threshold tuning, profile save/load |

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

**Hybrid commands not firing**
→ Make sure you perform the gesture within 2 seconds of saying the voice command
→ Check `config/hybrid_bindings.py` for valid pairings
→ Verify voice command exists in `config/voice_bindings.py`

**Presentation mode not activating**
→ Manually toggle via tray icon → "Presentation Mode"
→ Ensure PowerPoint window title contains "PowerPoint"
→ Laser pointer requires hand to be detected (check debug window)

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
- [x] Phase 4 — Adaptive sensitivity + voice commands (English + Urdu) + hybrid voice+gesture
- [x] Phase 5 — Presentation mode (laser pointer, swipe slides, zoom)
- [ ] Phase 6 — Gesture macros (record sequences like "fist → palm → fist" = custom action)
- [ ] Phase 7 — Plugin system + headless mode
- [ ] Phase 8 — AR/VR integration

---

## Additional Documentation

| File | Contents |
|------|----------|
| `REVIEW.md` | Full technical audit with critical issues, performance fixes, and AI improvements |
| `PHASE4_DEEP_DIVE.md` | Detailed design docs for adaptive sensitivity, voice+gesture hybrid, and presentation mode |
| `TODO.md` | Current task tracking and verification results |
| `audits/` | Phase-by-phase verification reports and diagnostic logs |

---

*Wavly — Control your computer without touching it.*

