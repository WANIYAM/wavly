"""
Wavly — Phase 4 Complete
Gesture + Air Drawing + Context + Adaptive Sensitivity + Voice Commands
"""

import sys
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QTimer, QMetaObject, Qt, Q_ARG
from PyQt6.QtGui import QShortcut, QKeySequence

from core.camera_thread import CameraThread
from core.action_thread import ActionThread
from core.gesture_queue import GestureQueue
from core.adaptive_engine import AdaptiveEngine
from core.voice_thread import VoiceThread
from ui.tray import WavlyTray
from ui.settings_window import SettingsWindow
from ui.keyboard import OnScreenKeyboard
from config.settings import Settings

try:
    from core.context_manager import ContextManager
    CONTEXT_AVAILABLE = True
except ImportError:
    CONTEXT_AVAILABLE = False


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("[Wavly] ERROR: System tray not available.")
        sys.exit(1)

    settings      = Settings()
    gesture_queue = GestureQueue()

    # ── Phase 4a: Adaptive Engine ─────────────────────────────────────────
    adaptive = AdaptiveEngine(
        settings=settings,
        profile_path=settings.adaptive_profile_path,
    )
    if settings.adaptive_enabled:
        gesture_queue.register_observer(adaptive.record_event)
        adaptive.start()
        print("[Wavly] Adaptive engine active.")

    # ── Phase 3: Context Manager ──────────────────────────────────────────
    context_mgr = None
    if CONTEXT_AVAILABLE and settings.context_aware_enabled:
        context_mgr = ContextManager(poll_interval=settings.context_poll_interval)
        context_mgr.start()

    # ── Keyboard ──────────────────────────────────────────────────────────
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

    # ── Phase 4b: Voice Thread ────────────────────────────────────────────
    # Voice callbacks must update Qt widgets — post to main thread via QTimer

    def on_listening_safe():
        QTimer.singleShot(0, lambda: _update_voice_panel("listening"))

    def on_heard_safe():
        QTimer.singleShot(0, lambda: _update_voice_panel("heard"))

    def on_result_safe(transcript, action):
        QTimer.singleShot(0, lambda: _update_voice_panel("result", transcript, action))

    def _update_voice_panel(event, transcript=None, action=None):
        win = SettingsWindow._current_instance
        if win and hasattr(win, "_voice_panel"):
            if event == "listening":
                win._voice_panel.on_listening()
            elif event == "heard":
                win._voice_panel.on_heard()
            elif event == "result":
                win._voice_panel.on_result(transcript, action)

    voice_thread = VoiceThread(
        gesture_queue=gesture_queue,
        on_listening_fn=on_listening_safe,
        on_heard_fn=on_heard_safe,
        on_result_fn=on_result_safe,
    )

    if getattr(settings, "voice_enabled", True):
        voice_thread.start()
        print("[Wavly] Voice thread active — say 'Hey Wavly' to use voice commands.")

    # ── Threads ───────────────────────────────────────────────────────────
    action_thread = ActionThread(
        gesture_queue, settings,
        keyboard_toggle_fn=toggle_keyboard_safe,
        context_manager=context_mgr,
    )
    camera_thread = CameraThread(
        gesture_queue, settings,
        adaptive_engine=adaptive,
    )
    camera_thread.set_keyboard_fns(
        update_fn=update_keyboard_safe,
        visible_fn=keyboard_is_visible,
    )

    camera_thread.daemon = True
    action_thread.daemon = True
    camera_thread.start()
    action_thread.start()

    # ── Inject into SettingsWindow ────────────────────────────────────────
    SettingsWindow.adaptive_engine = adaptive
    SettingsWindow.voice_thread    = voice_thread
    SettingsWindow._current_instance = None   # set when window opens

    # ── Clean quit ────────────────────────────────────────────────────────
    def quit_wavly():
        print("[Wavly] Shutting down...")
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
    )

    shortcut = QShortcut(QKeySequence("Ctrl+Shift+Q"), keyboard)
    shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut.activated.connect(quit_wavly)

    SettingsWindow.quit_fn = staticmethod(quit_wavly)

    print("[Wavly] Phase 4 complete — all features active.")
    print("[Wavly] Voice: say 'Hey Wavly' then your command (English or Urdu)")
    print("[Wavly] Quit: Ctrl+Shift+Q  |  tray → Quit  |  Settings → Quit")

    try:
        exit_code = app.exec()
    finally:
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