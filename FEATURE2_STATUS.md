# Feature 2: Voice + Gesture Hybrid — STATUS CHECK

**Status:** ⚠️ PARTIALLY COMPLETE (Voice-only works, Hybrid commands missing)

---

## What's Implemented ✅

### VoiceThread Core (`core/voice_thread.py`)
- ✅ OpenWakeWord detection for "Hey Wavly" wake word (offline, ~2MB)
- ✅ SpeechRecognition integration with Google Web Speech API
- ✅ Automatic fallback to offline Sphinx if no internet
- ✅ Bilingual support: English + Urdu
- ✅ Real-time status callbacks (listening, heard, result)
- ✅ 4-second recording window after wake word
- ✅ Always-on mode fallback if wake word model unavailable

### Voice Command Bindings (`config/voice_bindings.py`)
- ✅ 40+ predefined voice commands
- ✅ English translations + Urdu equivalents
- ✅ Support for hotkeys, app launching, text typing, scrolling, clicking
- ✅ Live reload without restart
- ✅ CommandResolver for fuzzy matching (longest-phrase-first)

### Voice Panel UI (`ui/voice_panel.py`)
- ✅ Enable/Disable toggle
- ✅ Live status indicator (listening / recording / idle)
- ✅ Last heard transcript + matched action
- ✅ Language badges (EN / اردو)
- ✅ Activity log (last 10 commands)
- ✅ Link to edit bindings
- ✅ Status indicator updates in real time

### Main Integration
- ✅ VoiceThread initialized in main.py
- ✅ Callbacks for UI updates via QTimer (thread-safe)
- ✅ Voice events fire through GestureQueue as `voice:action` events
- ✅ ActionThread handles voice events like any other gesture

### Dependencies
- ✅ `SpeechRecognition` — transcription
- ✅ `pyaudio` / `sounddevice` — microphone capture
- ✅ `openwakeword` — offline wake word detection
- ✅ `numpy` — audio processing

---

## What's Missing ❌

### Hybrid Command Feature (Core to Feature 2)
According to PHASE4_DEEP_DIVE.md, this should support:

```
Examples:
- Say "open" + point at file  → opens it
- Say "search" + air draw letter → searches for that letter
- Say "go to" + hold fingers showing number → go to line N
```

**Not Implemented:**
1. **CommandQueue** — Separate queue to hold voice events pending gesture pairing
2. **IntentResolver** — Logic to match voice + gesture pairs within 2-second window
3. **Hybrid Action Bindings** — Config file for voice+gesture combos
4. **Gesture-Voice Context** — Tracking last N seconds of both voice and gesture events
5. **State Machine** — Managing waiting-for-gesture state after voice command

### Specific Missing Components

| Component | Required | Status |
|-----------|----------|--------|
| CommandQueue (voice pending queue) | Essential | ❌ Missing |
| IntentResolver (hybrid logic) | Essential | ❌ Missing |
| `config/hybrid_bindings.py` | Essential | ❌ Missing |
| 2-second event window tracking | Essential | ❌ Missing |
| Gesture-voice pairing in ActionThread | Essential | ❌ Missing |
| Hybrid command UI feedback | Nice-to-have | ❌ Missing |

---

## Current Voice Flow (Voice-Only)

```
Microphone
    ↓
OpenWakeWord detects "Hey Wavly"
    ↓
Recording starts (4 seconds) + on_listening callback
    ↓
Recording ends + on_heard callback
    ↓
Google Web Speech transcribes audio
    ↓
CommandResolver matches transcript → action
    ↓
VoiceThread fires GestureEvent("voice:action", confidence=1.0)
    ↓
GestureQueue.put_action(event)
    ↓
ActionThread receives event
    ↓
_execute_action() strips "voice:" prefix
    ↓
_run_action() executes the action (hotkey, launch app, etc.)
```

**This works great for voice-only commands!**

---

## What Hybrid Commands Need

### 1. CommandQueue (Separate Voice Queue)

```python
class CommandQueue:
    def __init__(self, timeout_secs=2.0):
        self._queue = queue.Queue()
        self._pending = {}  # {gesture_type: (transcript, action, timestamp)}
        self._timeout = timeout_secs
    
    def put_voice_event(self, transcript: str, action: str):
        """Store voice event waiting for gesture pairing."""
        
    def get_matching_gesture(self, gesture: str) -> Optional[tuple]:
        """Check if a gesture arrived within timeout window for this voice."""
```

### 2. IntentResolver (Hybrid Logic)

```python
class IntentResolver:
    def resolve_hybrid(self, voice_event, gesture_event, timeout_secs=2.0):
        """
        Given voice_event and gesture_event, check if they form a valid hybrid:
        - "open" (voice) + point at file (gesture) = open file
        - "search" (voice) + air_letter:A (gesture) = search A
        - "go to" (voice) + fingers_3 (gesture) = go to line 3
        """
```

### 3. Hybrid Bindings Config

```python
# config/hybrid_bindings.py
HYBRID_BINDINGS = {
    ("open", "point"): "open_file",
    ("search", "air_letter"): "search_for_letter",
    ("go to", "fingers"): "go_to_line",
    # ...
}
```

### 4. ActionThread State Machine

```
State 1: IDLE
    ↓
Voice command "open" received
    ↓ Store in CommandQueue, set state → WAITING_FOR_GESTURE (2s timeout)
    ↓
User makes gesture "point"
    ↓ IntentResolver checks: ("open", "point") in HYBRID_BINDINGS? YES
    ↓
Execute hybrid action: open_file
    ↓ State → IDLE

---

If no gesture arrives within 2s:
    ↓ Execute voice-only action: open (hotkey Ctrl+O)
```

---

## File-by-File Status

| File | Status | What's There |
|------|--------|---|
| `core/voice_thread.py` | ✅ Complete | Wake word, transcription, callbacks |
| `config/voice_bindings.py` | ✅ Complete | 40+ English + Urdu commands |
| `ui/voice_panel.py` | ✅ Complete | Dashboard with activity log |
| `core/action_thread.py` | ⚠️ Partial | Handles voice-only, no hybrid logic |
| **`core/command_queue.py`** | ❌ **Missing** | **Need to create** |
| **`core/intent_resolver.py`** | ❌ **Missing** | **Need to create** |
| **`config/hybrid_bindings.py`** | ❌ **Missing** | **Need to create** |
| `main.py` | ⚠️ Partial | Initializes voice, no hybrid setup |

---

## Dependencies

### Already Installed (check requirements.txt)
```
pip install SpeechRecognition
pip install pyaudio
pip install openwakeword
pip install sounddevice
pip install numpy
```

If missing, update requirements.txt with voice section.

---

## What Needs to Happen to Complete Feature 2

### Step 1: Create CommandQueue
- Store pending voice events (transcript, action, timestamp)
- Time-out after 2 seconds if no matching gesture
- Auto-execute as voice-only if timeout

### Step 2: Create IntentResolver
- Map (voice_action, gesture_type) pairs to hybrid actions
- Match gesture within 2-second window
- Fall back to voice-only on timeout

### Step 3: Create Hybrid Bindings Config
- Define all voice + gesture combinations
- Example: `("open", "point"): "open_file"`

### Step 4: Modify ActionThread
- Add state machine for WAITING_FOR_GESTURE state
- Check CommandQueue on gesture arrival
- Execute hybrid vs voice-only accordingly

### Step 5: Add Hybrid UI Feedback
- Show "Waiting for gesture..." message
- Highlight matching gestures
- Countdown timer

---

## Summary

**Voice-only commands: ~90% complete** ✅
- Say "copy" → Ctrl+C (works)
- Say "open notepad" → launches notepad (works)
- Say "scroll up" → scrolls (works)

**Hybrid commands: 0% complete** ❌
- Say "open" + point at file → should open it (NOT IMPLEMENTED)
- Say "search" + air draw letter → should search (NOT IMPLEMENTED)
- Say "go to" + fingers showing number → should go to line (NOT IMPLEMENTED)

**To enable full Feature 2, need ~3-4 days of work** for the hybrid command infrastructure.

---

## Recommendation

**Option A:** Keep Feature 2 as-is (voice-only) and mark as ~60% complete
- Users get voice commands immediately
- No dependency on gesture timing/accuracy
- Lower complexity, lower risk

**Option B:** Complete Feature 2 to spec (add hybrid commands)
- More powerful use cases
- Higher complexity, more moving parts
- 3-5 days of development + testing

Which would you like to do?
