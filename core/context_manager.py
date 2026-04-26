"""
ContextManager — Phase 3

Detects the currently active application and returns a context profile
that changes what gestures do in different apps.

Examples:
  Browser  → scroll gesture scrolls page, swipe left/right = back/forward
  VS Code  → scroll = scroll editor, fist = run code
  Spotify  → fist = play/pause, scroll = volume

No AI needed — just psutil + win32gui (Windows) / xdotool (Linux)
mapped to a simple config dict.
"""

import time
import threading
import sys
from typing import Optional

# Platform-specific imports
if sys.platform == "win32":
    try:
        import win32gui
        import win32process
        import psutil
        WIN32_AVAILABLE = True
    except ImportError:
        WIN32_AVAILABLE = False
        print("[Context] win32gui not available. Install: pip install pywin32")
else:
    WIN32_AVAILABLE = False


# ── Context profiles ──────────────────────────────────────────────────────────
# Each profile overrides specific gesture actions for that app context.
# Gestures not listed fall through to the default gesture_bindings.py

CONTEXT_PROFILES = {
    # Browser — Chrome, Firefox, Edge
    "browser": {
        "name":     "Browser",
        "emoji":    "🌐",
        "processes": ["chrome", "firefox", "msedge", "brave", "opera"],
        "overrides": {
            "scroll_up":   "scroll_up",
            "scroll_down": "scroll_down",
            # Could add: "swipe_left": "hotkey:alt+left"  (back)
        },
    },

    # Code editor — VS Code, PyCharm, Sublime
    "editor": {
        "name":     "Code Editor",
        "emoji":    "💻",
        "processes": ["code", "pycharm", "sublime_text", "notepad++", "vim"],
        "overrides": {
            "scroll_up":   "scroll_up",
            "scroll_down": "scroll_down",
            "drag_start":  "hotkey:ctrl+z",    # fist = undo in editor
            "stop":        "stop",
        },
    },

    # Media player — Spotify, VLC, Windows Media Player
    "media": {
        "name":     "Media Player",
        "emoji":    "🎵",
        "processes": ["spotify", "vlc", "wmplayer", "groove", "musicbee"],
        "overrides": {
            "drag_start":  "hotkey:space",     # fist = play/pause
            "scroll_up":   "hotkey:ctrl+up",   # scroll up = volume up
            "scroll_down": "hotkey:ctrl+down", # scroll down = volume down
            "stop":        "hotkey:ctrl+right", # palm = next track
        },
    },

    # Presentation — PowerPoint, Google Slides (browser), Keynote
    "presentation": {
        "name":     "Presentation",
        "emoji":    "📊",
        "processes": ["powerpnt", "soffice", "keynote"],
        "overrides": {
            "click":       "hotkey:right",     # click = next slide
            "drag_start":  "hotkey:left",      # fist = previous slide
            "stop":        "hotkey:escape",    # palm = exit slideshow
            "scroll_up":   "hotkey:right",
            "scroll_down": "hotkey:left",
        },
    },

    # File manager
    "files": {
        "name":     "File Manager",
        "emoji":    "📁",
        "processes": ["explorer", "nautilus", "dolphin", "thunar"],
        "overrides": {},
    },
}

DEFAULT_CONTEXT = {
    "name":      "Default",
    "emoji":     "🖥️",
    "overrides": {},
}


class ContextManager:
    """
    Polls the active window every N seconds and resolves a context profile.
    Thread-safe: poll runs in background, get_context() is instant.

    Phase 5: on_context_change(context_name) callback fires when
    context switches — used to auto-activate presentation mode.
    """

    def __init__(self, poll_interval: float = 1.0,
                 on_context_change=None):
        self._poll_interval  = poll_interval
        self._current        = DEFAULT_CONTEXT
        self._current_proc   = ""
        self._lock           = threading.Lock()
        self._running        = False
        self._thread: Optional[threading.Thread] = None
        self._on_context_change = on_context_change   # Phase 5 callback

    def start(self):
        if not WIN32_AVAILABLE:
            print("[Context] Running in default mode (win32gui not available)")
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._poll_loop, daemon=True, name="ContextPoll"
        )
        self._thread.start()
        print("[Context] Context awareness started.")

    def stop(self):
        self._running = False

    def get_context(self) -> dict:
        with self._lock:
            return self._current

    def resolve_action(self, gesture: str, default_action: str) -> str:
        """
        Returns the context-overridden action for a gesture,
        or the default action if no override exists for this context.
        """
        ctx = self.get_context()
        return ctx.get("overrides", {}).get(gesture, default_action)

    def _poll_loop(self):
        while self._running:
            try:
                proc_name = self._get_active_process()
                if proc_name != self._current_proc:
                    self._current_proc = proc_name
                    ctx = self._match_context(proc_name)
                    with self._lock:
                        self._current = ctx
                    print(f"[Context] Active: {ctx['emoji']} {ctx['name']} ({proc_name})")
                    # Phase 5: notify main.py so it can activate/deactivate
                    # presentation mode automatically
                    if self._on_context_change:
                        try:
                            self._on_context_change(ctx["name"])
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(self._poll_interval)

    def _get_active_process(self) -> str:
        if not WIN32_AVAILABLE:
            return ""
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            return proc.name().lower().replace(".exe", "")
        except Exception:
            return ""

    def _match_context(self, proc_name: str) -> dict:
        for ctx in CONTEXT_PROFILES.values():
            if any(p in proc_name for p in ctx["processes"]):
                return ctx
        return DEFAULT_CONTEXT