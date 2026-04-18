 
"""
Wavly — AI-Powered Gesture Interface
Entry point. Starts all threads and the PyQt6 overlay.
"""

import sys
import threading
from PyQt6.QtWidgets import QApplication

from core.camera_thread import CameraThread
from core.action_thread import ActionThread
from core.gesture_queue import GestureQueue
from ui.overlay import WavlyOverlay
from config.settings import Settings


def main():
    settings = Settings()

    # Shared queue between vision thread and action thread
    gesture_queue = GestureQueue()

    # Thread 1: Camera → MediaPipe → Gesture detection → Queue
    camera_thread = CameraThread(gesture_queue, settings)

    # Thread 2: Queue → PyAutoGUI system actions
    action_thread = ActionThread(gesture_queue, settings)

    # Start background threads
    camera_thread.daemon = True
    action_thread.daemon = True
    camera_thread.start()
    action_thread.start()

    # Thread 3: PyQt6 transparent overlay UI
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    overlay = WavlyOverlay(gesture_queue, settings)
    overlay.show()

    print("[Wavly] Started. Press Ctrl+C or close overlay to exit.")

    try:
        exit_code = app.exec()
    finally:
        camera_thread.stop()
        action_thread.stop()
        print("[Wavly] Shutdown complete.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()