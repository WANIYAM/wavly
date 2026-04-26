"""
Wavly — AI-Powered Gesture Interface
Single entry point for all phases.

Features active:
  ✓ Gesture control (cursor, click, scroll, drag)
  ✓ Two-hand on-screen keyboard
  ✓ Air drawing (letter → shortcut)
  ✓ Context awareness (auto-adjusts per app)
  ✓ Adaptive sensitivity (learns your hand)
  ✓ Voice commands (say 'Hey Wavly' + command)

Quit: Ctrl+Shift+Q | tray right-click → Quit | Settings → Quit
"""

import sys
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QTimer, QMetaObject, Qt, Q_ARG
from PyQt6.QtGui import QShortcut, QKeySequence

from core.camera_thread import CameraThread
from core.action_thread import ActionThread
from core.gesture_queue import GestureQueue
from core.adaptive_engine import AdaptiveEngine
from ui.tray import WavlyTray
from ui.settings_window import SettingsWindow
from ui.keyboard import OnScreenKeyboard
from ui.laser_pointer import LaserPointer
from core.presentation_mode import PresentationMode
from config.settings import Settings

# Optional features — fail gracefully if deps missing
try:
    from core.context_manager import ContextManager
    CONTEXT_OK = True
except ImportError:
    CONTEXT_OK = False
    print("[Wavly] Context manager unavailable (pip install pywin32 psutil)")

try:
    from core.voice_thread import VoiceThread
    VOICE_OK = True
except ImportError:
    VOICE_OK = False
    print("[Wavly] Voice unavailable (pip install SpeechRecognition pyaudio openwakeword sounddevice)")


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("[Wavly] ERROR: System tray not available.")
        sys.exit(1)

    settings      = Settings()
    gesture_queue = GestureQueue()

    # ── Phase 5: Laser pointer + Presentation mode ────────────────────────
    laser = LaserPointer(color="red")

    pres_mode = PresentationMode(
        laser_pointer=laser,
        on_action_fn=lambda action: print(f"[Pres] {action}"),
    )

    def on_context_change(context_name: str):
        """Auto-activate/deactivate presentation mode based on active app."""
        from PyQt6.QtCore import QTimer
        if context_name == "Presentation":
            QTimer.singleShot(0, pres_mode.activate)
            tray.set_presentation_active(True)
        else:
            QTimer.singleShot(0, pres_mode.deactivate)
            tray.set_presentation_active(False)

    # ── Adaptive Engine ───────────────────────────────────────────────────
    adaptive = AdaptiveEngine(
        settings=settings,
        profile_path=settings.adaptive_profile_path,
    )
    if settings.adaptive_enabled:
        gesture_queue.register_observer(adaptive.record_event)
        adaptive.start()
        print("[Wavly] ✓ Adaptive engine active")

    # ── Context Manager ───────────────────────────────────────────────────
    context_mgr = None
    if CONTEXT_OK and getattr(settings, "context_aware_enabled", True):
        context_mgr = ContextManager(
            poll_interval=getattr(settings, "context_poll_interval", 1.0),
            on_context_change=on_context_change,   # Phase 5
        )
        context_mgr.start()
        print("[Wavly] ✓ Context awareness active")

    # ── On-Screen Keyboard ────────────────────────────────────────────────
    keyboard = OnScreenKeyboard()

    def toggle_keyboard_safe():
        QTimer.singleShot(0, keyboard.toggle)

    def update_keyboard_safe(left_pos, right_pos, left_pinch, right_pinch):
        QMetaObject.invokeMethod(
            keyboard, "update_hands",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(object, left_pos),
            Q_ARG(object, right_pos),
            Q_ARG(float, float(left_pinch)),
            Q_ARG(float, float(right_pinch)),
        )

    def keyboard_is_visible() -> bool:
        return keyboard.isVisible()

    # ── Voice Thread ──────────────────────────────────────────────────────
    voice_thread = None
    if VOICE_OK and getattr(settings, "voice_enabled", True):

        def on_listening_safe():
            win = SettingsWindow._current_instance
            if win and hasattr(win, "_voice_panel"):
                QTimer.singleShot(0, win._voice_panel.on_listening)

        def on_heard_safe():
            win = SettingsWindow._current_instance
            if win and hasattr(win, "_voice_panel"):
                QTimer.singleShot(0, win._voice_panel.on_heard)

        def on_result_safe(transcript, action):
            win = SettingsWindow._current_instance
            if win and hasattr(win, "_voice_panel"):
                QTimer.singleShot(0, lambda: win._voice_panel.on_result(transcript, action))

        voice_thread = VoiceThread(
            gesture_queue=gesture_queue,
            on_listening_fn=on_listening_safe,
            on_heard_fn=on_heard_safe,
            on_result_fn=on_result_safe,
        )
        voice_thread.start()
        print("[Wavly] ✓ Voice thread active — say 'Hey Wavly' to use")

    # ── Action Thread ─────────────────────────────────────────────────────
    action_thread = ActionThread(
        gesture_queue, settings,
        keyboard_toggle_fn=toggle_keyboard_safe,
        context_manager=context_mgr,
    )

    # ── Camera Thread ─────────────────────────────────────────────────────
    camera_thread = CameraThread(
        gesture_queue, settings,
        adaptive_engine=adaptive,
        presentation_mode=pres_mode,   # Phase 5
    )
    camera_thread.set_keyboard_fns(
        update_fn=update_keyboard_safe,
        visible_fn=keyboard_is_visible,
    )

    camera_thread.daemon = True
    action_thread.daemon = True
    camera_thread.start()
    action_thread.start()
    print("[Wavly] ✓ Camera and action threads running")

    # ── Inject into SettingsWindow ────────────────────────────────────────
    SettingsWindow.camera_thread    = camera_thread
    SettingsWindow.adaptive_engine  = adaptive
    SettingsWindow.voice_thread     = voice_thread
    SettingsWindow._current_instance = None

    # ── Clean quit ────────────────────────────────────────────────────────
    def quit_wavly():
        print("[Wavly] Shutting down...")
        if voice_thread:
            voice_thread.stop()
        if context_mgr:
            context_mgr.stop()
        adaptive.stop()
        camera_thread.stop()
        action_thread.stop()
        app.quit()

    # ── Tray ──────────────────────────────────────────────────────────────
    tray = WavlyTray(
        camera_thread=camera_thread,
        action_thread=action_thread,
        settings_window_class=SettingsWindow,
        app=app,
        quit_fn=quit_wavly,
        presentation_mode=pres_mode,   # Phase 5: manual toggle
    )

    # ── Global quit shortcut ──────────────────────────────────────────────
    shortcut = QShortcut(QKeySequence("Ctrl+Shift+Q"), keyboard)
    shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut.activated.connect(quit_wavly)

    SettingsWindow.quit_fn = staticmethod(quit_wavly)

    print("[Wavly] Ready. Right-click tray icon for options.")
    print("[Wavly] Quit: Ctrl+Shift+Q  |  tray → Quit  |  Settings → Quit")

    try:
        exit_code = app.exec()
    finally:
        if voice_thread:
            voice_thread.stop()
        if context_mgr:
            context_mgr.stop()
        adaptive.stop()
        camera_thread.stop()
        action_thread.stop()
        print("[Wavly] Shutdown complete.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()