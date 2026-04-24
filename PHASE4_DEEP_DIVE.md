# Phase 4 — Deep Dive

## Feature 1 — Adaptive Sensitivity Learning

**What it actually does:**
Wavly watches your gesture history in real time and notices patterns like "this user's click keeps misfiring as cursor_move" or "scroll_up needs 3 fewer hold frames for this hand". It quietly adjusts thresholds per gesture without you touching settings.

**How it works technically:**
- After every gesture fires, record whether it felt like a misfire (detectable by how quickly the next contradicting gesture appears)
- Store a rolling window of confidence scores per gesture class
- Every N gestures, recompute optimal `hold_frames` and `confidence_threshold` per class
- Save to a `models/user_profile.json` file so it persists across sessions

**What it needs:**
- No new ML model — pure statistics on existing predictions
- A background `AdaptiveEngine` thread that reads from `GestureQueue` and writes back to `Settings`
- A profile file per user (useful when multiple people use the same machine)

**Complexity:** Medium. Most of the work is in the math for computing optimal thresholds, not in new infrastructure.

**Risk:** If the adaptation logic is too aggressive it can make things worse. Needs a reset button and hard limits so it can't tune itself into broken territory.

---

## Feature 2 — Voice + Gesture Hybrid

**What it actually does:**
Adds a microphone listener running in a 4th thread. Voice alone triggers some commands, gesture alone triggers others, but combining both unlocks power commands neither can do alone.

**Examples of hybrid commands:**
- Say *"copy"* → Ctrl+C (voice only, no gesture needed)
- Say *"open"* + point at file = opens it
- Say *"search"* + air draw a letter = search for that letter
- Say *"go to"* + hold up fingers showing a number = go to line N in editor

**How it works technically:**
- `speech_recognition` library with Google or offline Vosk backend
- New `VoiceThread` runs Whisper/Vosk in a loop, puts voice events into a shared `CommandQueue`
- `IntentResolver` in `ActionThread` checks if a voice event + gesture event arrived within a 2-second window → hybrid command
- Standalone voice commands fire immediately without needing a gesture

**What it needs:**
- `pip install SpeechRecognition pyaudio` or `pip install vosk` (offline)
- New `VoiceThread`, `CommandQueue`, `IntentResolver` classes
- Config file for voice command → action mappings

**Complexity:** High. Microphone latency, background noise, and offline vs online tradeoffs are all real problems. Vosk is better for offline use but needs a model download (~50MB).

**Risk:** Microphone permissions, latency (~300-500ms for recognition), false triggers from ambient speech. Needs a push-to-listen mode to avoid constant listening.

---

## Feature 3 — Presentation Mode

**What it actually does:**
A dedicated operating mode that activates automatically when a presentation app is in focus. Completely replaces the default gesture set with presentation-specific controls.

**Gesture set in presentation mode:**

| Gesture | Action |
|---------|--------|
| ☝️ Point + move | Laser pointer dot on screen |
| 👈 Swipe left | Previous slide |
| 👉 Swipe right | Next slide |
| ✊ Fist | Black screen (B key) |
| 🖐️ Palm | Exit slideshow (Escape) |
| ✌️ Two fingers | Zoom into slide area |
| 🤟 Three fingers | Show/hide presenter notes |

**How it works technically:**
- Extends `ContextManager` with a `PresentationMode` class
- Laser pointer = a small always-on-top PyQt6 dot window that follows cursor
- Swipe detection = new temporal gesture (tracks direction of movement over 10 frames) — not in current classifier
- Auto-activates when PowerPoint/Keynote/Slides process is detected

**What it needs:**
- Swipe gesture detection (temporal — needs movement direction tracking, not just hand shape)
- Laser pointer overlay widget
- Slide-advance debounce so one swipe = one slide

**Complexity:** Medium-High. The laser pointer is easy. Swipe detection is the hard part because it requires temporal reasoning (movement over time) which the current frame-by-frame classifier doesn't handle.

---

## Comparison Table

| | Adaptive Sensitivity | Voice + Gesture | Presentation Mode |
|---|---|---|---|
| New dependencies | None | `SpeechRecognition`, `pyaudio`/`vosk` | None |
| New ML needed | No | Optional (Vosk model) | Yes (swipe detection) |
| Risk level | Low | High | Medium |
| Wow factor | Low (invisible) | Very High | High |
| Daily usefulness | High (always on) | High | Medium (situational) |
| Build time | 1-2 days | 3-5 days | 2-3 days |
| Breaks existing code | No | No | No |

---

## Recommended Build Order

**Start with Adaptive Sensitivity** — lowest risk, no new dependencies, builds on what already exists, and makes every other feature work better because the core gesture detection improves. It's also invisible to the user which means zero chance of breaking the experience.

**Then Presentation Mode** — self-contained, high wow factor, good for demos. The laser pointer alone is impressive. Swipe detection can be simplified to "fast cursor movement in one direction" without a full temporal classifier.

**Voice + Gesture last** — most impressive but highest risk. By the time you build it, the gesture engine will be more stable and you'll have a better sense of where voice adds the most value.
