"""
Wavly — AI-Powered Gesture Interface
Entry point. Starts all threads, tray icon, and optional overlay.
"""

import sys
import threading
from PyQt6.QtWidgets import QApplication

from core.camera_thread import CameraThread
from core.action_thread import ActionThread
from core.gesture_queue import GestureQueue
from ui.tray import WavlyTray
from ui.settings_window import SettingsWindow
from config.settings import Settings


def main():
    settings = Settings()
    gesture_queue = GestureQueue()

    camera_thread = CameraThread(gesture_queue, settings)
    action_thread = ActionThread(gesture_queue, settings)

    camera_thread.daemon = True
    action_thread.daemon = True
    camera_thread.start()
    action_thread.start()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # keep alive when settings window closes

    # System tray — the main user touchpoint
    tray = WavlyTray(
        camera_thread=camera_thread,
        action_thread=action_thread,
        settings_window_class=SettingsWindow,
        app=app,
    )

    # Show a startup notification
    tray.showMessage(
        "Wavly started",
        "Gesture control is active. Right-click the tray icon for options.",
        tray.MessageIcon.Information,
        3000,
    )

    print("[Wavly] Running — right-click the tray icon to open Settings.")

    try:
        exit_code = app.exec()
    finally:
        camera_thread.stop()
        action_thread.stop()
        print("[Wavly] Shutdown complete.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()