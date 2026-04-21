"""
WavlyTray — System tray icon for Wavly.

Right-click menu:
  Open Settings  → opens SettingsWindow
  Pause / Resume → pauses gesture recognition (releases camera)
  ─────────────
  Quit Wavly    → clean shutdown (no terminal needed)

Also: Ctrl+Shift+Q works globally from anywhere.
"""

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter, QBrush
from PyQt6.QtCore import Qt, QTimer
from typing import Callable, Optional


def _make_icon(active: bool = True) -> QIcon:
    size = 64
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#111111") if active else QColor("#aaaaaa")
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.PenStyle.NoPen)
    s = 2
    painter.drawRoundedRect(16*s, 18*s, 14*s, 12*s, 4*s, 4*s)
    painter.drawRoundedRect(16*s,  6*s,  4*s, 14*s, 2*s, 2*s)
    painter.drawRoundedRect(21*s,  4*s,  4*s, 16*s, 2*s, 2*s)
    painter.drawRoundedRect(26*s,  6*s,  4*s, 14*s, 2*s, 2*s)
    painter.drawRoundedRect(31*s,  9*s,  3*s, 11*s, 2*s, 2*s)
    painter.drawRoundedRect( 8*s, 20*s,  9*s,  5*s, 2*s, 2*s)
    painter.end()
    return QIcon(px)


class WavlyTray(QSystemTrayIcon):

    def __init__(self, camera_thread, action_thread, settings_window_class,
                 app, quit_fn: Optional[Callable] = None, parent=None):
        super().__init__(parent)
        self._camera_thread = camera_thread
        self._action_thread = action_thread
        self._settings_cls  = settings_window_class
        self._app           = app
        self._quit_fn       = quit_fn or self._default_quit
        self._settings_win  = None
        self._paused        = False

        settings_window_class.camera_thread = camera_thread

        self.setIcon(_make_icon(active=True))
        self.setToolTip("Wavly — gesture control active")
        self._build_menu()
        self.activated.connect(self._on_activated)
        self.show()

        QTimer.singleShot(800, self._startup_message)

    def _startup_message(self):
        if self.isSystemTrayAvailable() and self.isVisible():
            self.showMessage(
                "Wavly started",
                "Gesture control is active.\n"
                "Right-click this icon for options.\n"
                "Press Ctrl+Shift+Q to quit anytime.",
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )

    def _build_menu(self):
        menu = QMenu()

        header = menu.addAction("Wavly 🖐️")
        header.setEnabled(False)
        menu.addSeparator()

        settings_act = menu.addAction("⚙️  Open Settings")
        settings_act.triggered.connect(self._open_settings)

        self._pause_act = menu.addAction("⏸  Pause")
        self._pause_act.triggered.connect(self._toggle_pause)

        menu.addSeparator()

        quit_act = menu.addAction("✕  Quit Wavly")
        quit_act.triggered.connect(self._quit_fn)

        self.setContextMenu(menu)

    def _on_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self._open_settings()

    def _open_settings(self):
        if self._settings_win is None or not self._settings_win.isVisible():
            self._settings_win = self._settings_cls()
        self._settings_win.show()
        self._settings_win.raise_()
        self._settings_win.activateWindow()

    def _toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._camera_thread.pause()
            self._pause_act.setText("▶  Resume")
            self.setIcon(_make_icon(active=False))
            self.setToolTip("Wavly — paused")
            self.showMessage("Wavly", "Paused.", QSystemTrayIcon.MessageIcon.Information, 1500)
        else:
            self._camera_thread.resume()
            self._pause_act.setText("⏸  Pause")
            self.setIcon(_make_icon(active=True))
            self.setToolTip("Wavly — gesture control active")
            self.showMessage("Wavly", "Resumed.", QSystemTrayIcon.MessageIcon.Information, 1500)

    def _default_quit(self):
        self._camera_thread.stop()
        self._action_thread.stop()
        self._app.quit()