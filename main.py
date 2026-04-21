"""
Wavly — AI-Powered Gesture Interface
Entry point. Starts all threads + system tray + two-hand on-screen keyboard.

How to quit Wavly (no terminal needed):
  1. Right-click tray icon → Quit Wavly
  2. Press Ctrl+Shift+Q anywhere
  3. Settings window → Quit button (bottom left)
"""

import sys
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QTimer, QMetaObject, Qt, Q_ARG
from PyQt6.QtGui import QShortcut, QKeySequence

from core.camera_thread import CameraThread
from core.action_thread import ActionThread
from core.gesture_queue import GestureQueue
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

    action_thread = ActionThread(
        gesture_queue, settings,
        keyboard_toggle_fn=toggle_keyboard_safe,
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

    # ── Clean quit function shared by tray, shortcut, settings ───────────
    def quit_wavly():
        print("[Wavly] Shutting down...")
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

    # ── Global quit shortcut: Ctrl+Shift+Q ───────────────────────────────
    # QShortcut on a hidden widget so it works app-wide even without a
    # focused window. Qt.ShortcutContext.ApplicationShortcut makes it
    # fire regardless of which window has focus.
    _shortcut_widget = keyboard   # any persistent QWidget works as parent
    shortcut = QShortcut(QKeySequence("Ctrl+Shift+Q"), _shortcut_widget)
    shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut.activated.connect(quit_wavly)

    # Pass quit_fn into SettingsWindow so the button there works too
    SettingsWindow.quit_fn = staticmethod(quit_wavly)

    print("[Wavly] Running.")
    print("[Wavly] Quit: right-click tray icon → Quit  |  or press Ctrl+Shift+Q")

    try:
        exit_code = app.exec()
    finally:
        camera_thread.stop()
        action_thread.stop()
        print("[Wavly] Shutdown complete.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()