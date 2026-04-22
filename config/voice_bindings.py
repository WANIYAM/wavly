"""
Voice Command Bindings — English + Urdu
Edit this file to add or change voice commands.
Changes apply on next Wavly restart.

Format:
  "spoken phrase": "action"

Action types (same as gesture_bindings.py):
  hotkey:ctrl+c       — keyboard shortcut
  run:notepad.exe     — open application
  type:Hello          — type text
  scroll_up           — scroll up
  scroll_down         — scroll down
  click               — left click
  show_keyboard       — toggle on-screen keyboard

Tips:
  - Phrases are matched case-insensitively
  - Shorter phrases trigger more reliably
  - Add both English AND Urdu for the same action
  - Google Speech handles Urdu well when language is set to ur-PK
"""

VOICE_BINDINGS: dict = {

    # ── Clipboard ─────────────────────────────────────────────────────────
    "copy":         "hotkey:ctrl+c",
    "کاپی":         "hotkey:ctrl+c",       # Urdu: copy

    "paste":        "hotkey:ctrl+v",
    "پیسٹ":         "hotkey:ctrl+v",       # Urdu: paste

    "cut":          "hotkey:ctrl+x",
    "کاٹو":         "hotkey:ctrl+x",       # Urdu: cut

    # ── Undo / Redo ───────────────────────────────────────────────────────
    "undo":         "hotkey:ctrl+z",
    "واپس":         "hotkey:ctrl+z",       # Urdu: back/undo

    "redo":         "hotkey:ctrl+y",
    "دوبارہ":       "hotkey:ctrl+y",       # Urdu: again/redo

    # ── File operations ───────────────────────────────────────────────────
    "save":         "hotkey:ctrl+s",
    "محفوظ کرو":    "hotkey:ctrl+s",       # Urdu: save

    "open":         "hotkey:ctrl+o",
    "کھولو":        "hotkey:ctrl+o",       # Urdu: open

    "new file":     "hotkey:ctrl+n",
    "نئی فائل":     "hotkey:ctrl+n",       # Urdu: new file

    "print":        "hotkey:ctrl+p",
    "پرنٹ":         "hotkey:ctrl+p",       # Urdu: print

    # ── Navigation ────────────────────────────────────────────────────────
    "scroll up":    "scroll_up",
    "اوپر":         "scroll_up",           # Urdu: up

    "scroll down":  "scroll_down",
    "نیچے":         "scroll_down",         # Urdu: down

    "go back":      "hotkey:alt+left",
    "پیچھے":        "hotkey:alt+left",     # Urdu: back

    "go forward":   "hotkey:alt+right",
    "آگے":          "hotkey:alt+right",    # Urdu: forward

    "refresh":      "hotkey:ctrl+r",
    "ریفریش":       "hotkey:ctrl+r",       # Urdu: refresh

    # ── Tabs ──────────────────────────────────────────────────────────────
    "new tab":      "hotkey:ctrl+t",
    "نئی ٹیب":      "hotkey:ctrl+t",       # Urdu: new tab

    "close tab":    "hotkey:ctrl+w",
    "بند کرو":      "hotkey:ctrl+w",       # Urdu: close

    "next tab":     "hotkey:ctrl+tab",
    "اگلی ٹیب":     "hotkey:ctrl+tab",     # Urdu: next tab

    # ── Apps ──────────────────────────────────────────────────────────────
    "open browser": "run:start chrome",
    "براؤزر کھولو": "run:start chrome",    # Urdu: open browser

    "open notepad": "run:notepad.exe",
    "نوٹ پیڈ":      "run:notepad.exe",     # Urdu: notepad

    "file explorer": "hotkey:win+e",
    "فائل کھولو":   "hotkey:win+e",        # Urdu: open files

    "task manager": "hotkey:ctrl+shift+esc",

    # ── Window management ─────────────────────────────────────────────────
    "minimise":     "hotkey:win+m",
    "چھوٹا کرو":    "hotkey:win+m",        # Urdu: minimise

    "maximise":     "hotkey:win+up",
    "بڑا کرو":      "hotkey:win+up",       # Urdu: maximise

    "screenshot":   "hotkey:win+shift+s",
    "اسکرین شاٹ":  "hotkey:win+shift+s",  # Urdu: screenshot

    # ── Wavly controls ────────────────────────────────────────────────────
    "keyboard":     "show_keyboard",
    "کی بورڈ":      "show_keyboard",       # Urdu: keyboard

    "click":        "click",
    "کلک":          "click",               # Urdu: click

    "select all":   "hotkey:ctrl+a",
    "سب منتخب کرو": "hotkey:ctrl+a",       # Urdu: select all

    "find":         "hotkey:ctrl+f",
    "تلاش":         "hotkey:ctrl+f",       # Urdu: search/find

    # ── Volume ────────────────────────────────────────────────────────────
    "volume up":    "hotkey:volumeup",
    "آواز بڑھاؤ":   "hotkey:volumeup",     # Urdu: increase volume

    "volume down":  "hotkey:volumedown",
    "آواز کم کرو":  "hotkey:volumedown",   # Urdu: decrease volume

    "mute":         "hotkey:volumemute",
    "خاموش":        "hotkey:volumemute",   # Urdu: silent/mute
}