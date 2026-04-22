"""
Wavly — Phase 3
Gesture control + Air Drawing + Context Awareness + Two-hand Keyboard
"""

import sys
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QTimer, QMetaObject, Qt, Q_ARG
from PyQt6.QtGui import QShortcut, QKeySequence

from core.camera_thread import CameraThread
from core.action_thread import ActionThread
from core.gesture_queue import GestureQueue
from core.context_manager import ContextManager
from ui.tray import WavlyTray
from ui.settings_window import SettingsWindow
from ui.keyboard import OnScreenKeyboard
from config.settings import Settings


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("[Wavly] ERROR: System tray not available.")
        sys.exit(1)

    settings      = Settings()
    gesture_queue = GestureQueue()

    # ── Phase 3: Context awareness ────────────────────────────────────────
    context_mgr = ContextManager(poll_interval=settings.context_poll_interval)
    if settings.context_aware_enabled:
        context_mgr.start()

    # ── Keyboard ──────────────────────────────────────────────────────────
    keyboard = OnScreenKeyboard()

    def toggle_keyboard_safe():
        QTimer.singleShot(0, keyboard.toggle)

    def update_keyboard_safe(left_pos, right_pos, left_pinch, right_pinch):
        QMetaObject.invokeMethod(
            keyboard,
            "update_hands",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(object, left_pos),
            Q_ARG(object, right_pos),
            Q_ARG(float, float(left_pinch)),
            Q_ARG(float, float(right_pinch)),
        )

    def keyboard_is_visible() -> bool:
        return keyboard.isVisible()

    # ── Threads ───────────────────────────────────────────────────────────
    action_thread = ActionThread(
        gesture_queue, settings,
        keyboard_toggle_fn=toggle_keyboard_safe,
        context_manager=context_mgr,
    )
    camera_thread = CameraThread(gesture_queue, settings)
    camera_thread.set_keyboard_fns(
        update_fn=update_keyboard_safe,
        visible_fn=keyboard_is_visible,
    )

    camera_thread.daemon = True
    action_thread.daemon = True
    camera_thread.start()
    action_thread.start()

    # ── Clean quit ────────────────────────────────────────────────────────
    def quit_wavly():
        print("[Wavly] Shutting down...")
        context_mgr.stop()
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

    # ── Global quit shortcut ──────────────────────────────────────────────
    shortcut = QShortcut(QKeySequence("Ctrl+Shift+Q"), keyboard)
    shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut.activated.connect(quit_wavly)

    SettingsWindow.quit_fn = staticmethod(quit_wavly)

    print("[Wavly] Phase 3 running.")
    print("[Wavly] Gestures: cursor / click / scroll / drag / stop / three_fingers")
    print("[Wavly] Air draw: train with python gestures/air_draw_trainer.py")
    print("[Wavly] Context: auto-detects browser / editor / media / presentation")
    print("[Wavly] Quit: Ctrl+Shift+Q  |  tray → Quit  |  Settings → Quit")

    try:
        exit_code = app.exec()
    finally:
        context_mgr.stop()
        camera_thread.stop()
        action_thread.stop()
        print("[Wavly] Shutdown complete.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()