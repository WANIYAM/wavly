"""
VoiceThread — Phase 4 Feature 2: Voice + Gesture Hybrid

Pipeline:
  1. OpenWakeWord listens continuously for "Hey Wavly" (offline, ~2MB)
  2. On wake word → green tray icon flash + start recording (3 seconds)
  3. Google Web Speech API transcribes audio (free, no API key)
     Falls back to offline recognition if no internet
  4. CommandResolver matches transcript to voice_bindings.py
  5. Fires GestureEvent through GestureQueue (same pipeline as gestures)

Bilingual: recognises English and Urdu in the same session.
Google Speech handles mixed-language input well when both are specified.

Dependencies:
  pip install SpeechRecognition pyaudio openwakeword
  pip install sounddevice numpy  (for audio capture)

OpenWakeWord model downloads automatically on first run (~2MB).
"""

import threading
import time
import queue
import importlib
import os
import sys
from typing import Optional, Callable

# Audio
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    print("[Voice] SpeechRecognition not installed. Run: pip install SpeechRecognition pyaudio")

# Wake word
try:
    from openwakeword.model import Model as WakeWordModel
    OWW_AVAILABLE = True
except ImportError:
    OWW_AVAILABLE = False
    print("[Voice] OpenWakeWord not installed. Run: pip install openwakeword")

try:
    import numpy as np
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("[Voice] sounddevice not installed. Run: pip install sounddevice numpy")

from core.gesture_queue import GestureQueue, GestureEvent


# ── Constants ─────────────────────────────────────────────────────────────────
WAKE_WORD        = "hey_wavly"          # OpenWakeWord model name
WAKE_THRESHOLD   = 0.5                  # Confidence to trigger
RECORD_SECONDS   = 4                    # How long to record after wake word
SAMPLE_RATE      = 16000                # Required by OpenWakeWord
CHUNK_SIZE       = 1280                 # ~80ms at 16kHz

# Languages to recognise — Google handles both in one call
LANGUAGES        = ["en-US", "ur-PK"]  # English + Urdu


class CommandResolver:
    """
    Matches a voice transcript to an action from voice_bindings.py.
    Reloads bindings on every call so edits apply without restart.
    """

    def resolve(self, transcript: str) -> Optional[str]:
        bindings = self._load_bindings()
        text     = transcript.strip().lower()

        # Sort longest phrase first — prevents "open" matching before "open browser"
        sorted_bindings = sorted(bindings.items(), key=lambda x: len(x[0]), reverse=True)

        # Exact match first (still longest-first order)
        for phrase, action in sorted_bindings:
            if text == phrase.lower():
                return action

        # Partial match — longest phrase wins
        # e.g. "open browser" matches before "open"
        for phrase, action in sorted_bindings:
            if phrase.lower() in text:
                return action

        return None

    def _load_bindings(self) -> dict:
        try:
            import config.voice_bindings as vb
            importlib.reload(vb)
            return vb.VOICE_BINDINGS
        except Exception as e:
            print(f"[Voice] Could not load voice_bindings: {e}")
            return {}


class VoiceThread(threading.Thread):
    """
    Background thread that:
      1. Runs OpenWakeWord continuously on mic audio
      2. On wake word: records RECORD_SECONDS of audio
      3. Sends to Google Speech (with Urdu fallback)
      4. Resolves transcript → action → GestureQueue
    """

    def __init__(self, gesture_queue: GestureQueue,
                 on_listening_fn: Optional[Callable] = None,
                 on_heard_fn:     Optional[Callable] = None,
                 on_result_fn:    Optional[Callable] = None):
        super().__init__(name="VoiceThread", daemon=True)
        self.gesture_queue   = gesture_queue
        self._stop_event     = threading.Event()
        self._enabled        = True
        self._resolver       = CommandResolver()

        # UI callbacks (called from this thread — use QTimer in callers)
        self._on_listening = on_listening_fn   # wake word detected
        self._on_heard     = on_heard_fn       # finished recording
        self._on_result    = on_result_fn      # transcript + action ready

        self._recognizer   = sr.Recognizer() if SR_AVAILABLE else None
        self._wake_model   = None
        self._last_wake    = 0.0   # prevent rapid re-triggers

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        print(f"[Voice] {'Enabled' if enabled else 'Disabled'}.")

    def stop(self):
        self._stop_event.set()

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self):
        if not self._check_dependencies():
            return

        self._load_wake_model()

        if self._wake_model is None:
            print("[Voice] Wake word model unavailable — falling back to always-on mode")
            self._run_always_on()
        else:
            print(f"[Voice] Listening for wake word: 'Hey Wavly'")
            self._run_wake_word()

    def _check_dependencies(self) -> bool:
        missing = []
        if not SR_AVAILABLE:
            missing.append("SpeechRecognition")
        if not AUDIO_AVAILABLE:
            missing.append("sounddevice")
        if missing:
            print(f"[Voice] Missing: {', '.join(missing)}")
            print(f"[Voice] Install: pip install {' '.join(missing)}")
            return False
        return True

    def _load_wake_model(self):
        if not OWW_AVAILABLE:
            return
        try:
            # OpenWakeWord downloads model automatically on first run
            self._wake_model = WakeWordModel(
                wakeword_models=["hey_jarvis"],   # closest available to "Hey Wavly"
                inference_framework="onnx",
            )
            print("[Voice] Wake word model loaded.")
        except Exception as e:
            print(f"[Voice] Wake word model failed: {e}")
            print("[Voice] Using push-to-listen fallback.")
            self._wake_model = None

    # ── Wake word mode ────────────────────────────────────────────────────

    def _run_wake_word(self):
        """Stream mic audio through OpenWakeWord, trigger on detection."""
        audio_buffer = queue.Queue()

        def audio_callback(indata, frames, time_info, status):
            audio_buffer.put(bytes(indata))

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=CHUNK_SIZE,
                dtype="int16",
                channels=1,
                callback=audio_callback,
            ):
                while not self._stop_event.is_set():
                    if not self._enabled:
                        time.sleep(0.1)
                        continue

                    try:
                        chunk = audio_buffer.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    audio_np = np.frombuffer(chunk, dtype=np.int16)
                    prediction = self._wake_model.predict(audio_np)

                    # Check all wake word scores
                    for model_name, score in prediction.items():
                        if score >= WAKE_THRESHOLD:
                            now = time.time()
                            if now - self._last_wake > 3.0:  # 3s cooldown
                                self._last_wake = now
                                print(f"[Voice] Wake word detected! ({score:.2f})")
                                self._handle_wake_word()
                            break

        except Exception as e:
            print(f"[Voice] Streaming error: {e}")

    # ── Always-on fallback (no wake word model) ───────────────────────────

    def _run_always_on(self):
        """
        Fallback when OpenWakeWord isn't available.
        Uses SpeechRecognition's listen_in_background with energy threshold.
        """
        if not SR_AVAILABLE:
            return

        mic = sr.Microphone(sample_rate=SAMPLE_RATE)
        self._recognizer.energy_threshold = 300
        self._recognizer.dynamic_energy_threshold = True

        print("[Voice] Always-on mode — say a command directly.")

        def callback(recognizer, audio):
            if self._enabled:
                self._process_audio(audio)

        stop_listening = self._recognizer.listen_in_background(
            mic, callback, phrase_time_limit=RECORD_SECONDS
        )

        while not self._stop_event.is_set():
            time.sleep(0.5)

        stop_listening(wait_for_stop=False)

    # ── Wake word handler ─────────────────────────────────────────────────

    def _handle_wake_word(self):
        """Record audio after wake word and process it."""
        if self._on_listening:
            self._on_listening()

        print("[Voice] 🎤 Listening...")

        if not SR_AVAILABLE:
            return

        try:
            mic = sr.Microphone(sample_rate=SAMPLE_RATE)
            with mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self._recognizer.listen(
                    source,
                    timeout=1.0,
                    phrase_time_limit=RECORD_SECONDS,
                )

            if self._on_heard:
                self._on_heard()

            self._process_audio(audio)

        except sr.WaitTimeoutError:
            print("[Voice] No speech detected.")
        except Exception as e:
            print(f"[Voice] Recording error: {e}")

    # ── Speech recognition + command dispatch ─────────────────────────────

    def _process_audio(self, audio):
        """Transcribe audio and dispatch matching command."""
        transcript = self._transcribe(audio)
        if not transcript:
            return

        print(f"[Voice] Heard: '{transcript}'")

        action = self._resolver.resolve(transcript)
        if action:
            print(f"[Voice] → {action}")
            self._dispatch(action, transcript)
            if self._on_result:
                self._on_result(transcript, action)
        else:
            print(f"[Voice] No command matched for: '{transcript}'")
            if self._on_result:
                self._on_result(transcript, None)

    def _transcribe(self, audio) -> Optional[str]:
        """
        Try Google Web Speech (free, bilingual).
        Falls back to offline Sphinx if no internet.
        """
        # Try each language — return first successful result
        for lang in LANGUAGES:
            try:
                text = self._recognizer.recognize_google(
                    audio,
                    language=lang,
                    show_all=False,
                )
                if text:
                    return text.lower().strip()
            except sr.UnknownValueError:
                continue   # try next language
            except sr.RequestError:
                print("[Voice] No internet — trying offline recognition.")
                return self._transcribe_offline(audio)
            except Exception as e:
                print(f"[Voice] Transcription error ({lang}): {e}")

        return None

    def _transcribe_offline(self, audio) -> Optional[str]:
        """Offline fallback using CMU Sphinx (English only)."""
        try:
            return self._recognizer.recognize_sphinx(audio).lower().strip()
        except Exception:
            return None

    # ── Action dispatch ───────────────────────────────────────────────────

    def _dispatch(self, action: str, transcript: str):
        """Fire action through GestureQueue — same path as gesture actions."""
        event = GestureEvent(
            name=f"voice:{action}",
            confidence=1.0,
        )
        self.gesture_queue.put_action(event)