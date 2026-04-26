"""
Hybrid Bindings — Voice + Gesture combined commands.

Keys are (spoken_transcript, gesture_name) tuples.
Values are the action to execute when BOTH arrive within 2 seconds.

AUDIT FIX: Keys use the SPOKEN WORD (transcript), not the resolved action.
  Wrong: ("hotkey:ctrl+c", "click") — this is what the old code used
  Right: ("copy", "click")          — this is what the transcript matches

How it works:
  1. User says "copy" → stored in CommandQueue with transcript="copy"
  2. User makes a click gesture within 2 seconds
  3. IntentResolver looks up ("copy", "click") → finds "copy_at_cursor"
  4. Hybrid action fires instead of separate copy + click

Add your own hybrid commands below.
Format: ("spoken word or phrase", "gesture_name"): "action"
"""

HYBRID_BINDINGS: dict = {

    # ── Click-based hybrids ───────────────────────────────────────────────
    # Say a word, then click to apply it at cursor position

    ("copy",    "click"):         "hotkey:ctrl+c",   # say "copy" + click = copy selection
    ("paste",   "click"):         "hotkey:ctrl+v",   # say "paste" + click = paste at click pos
    ("cut",     "click"):         "hotkey:ctrl+x",   # say "cut" + click = cut selection
    ("delete",  "click"):         "hotkey:delete",   # say "delete" + click = delete item
    ("open",    "cursor_move"):   "hotkey:ctrl+o",   # say "open" + point = open file dialog

    # ── Scroll-based hybrids ──────────────────────────────────────────────
    # Say a direction, then scroll faster / to specific place

    ("scroll up",   "scroll_up"):   "scroll_up_fast",    # double-speed scroll up
    ("scroll down", "scroll_down"): "scroll_down_fast",  # double-speed scroll down
    ("top",         "scroll_up"):   "hotkey:ctrl+home",  # say "top" + scroll = go to top
    ("bottom",      "scroll_down"): "hotkey:ctrl+end",   # say "bottom" + scroll = go to end

    # ── Search hybrids ───────────────────────────────────────────────────
    # Say "find" or "search", then air draw a letter to search for it

    ("find",    "cursor_move"):   "hotkey:ctrl+f",   # say "find" + point = open find bar
    ("search",  "cursor_move"):   "hotkey:ctrl+f",   # alias

    # ── Window hybrids ───────────────────────────────────────────────────

    ("close",   "stop"):          "hotkey:ctrl+w",   # say "close" + palm = close tab
    ("save",    "stop"):          "hotkey:ctrl+s",   # say "save" + palm = save file
    ("undo",    "drag_start"):    "hotkey:ctrl+z",   # say "undo" + fist = undo

    # ── Urdu hybrids ─────────────────────────────────────────────────────

    ("کاپی",    "click"):         "hotkey:ctrl+c",   # Urdu "copy" + click
    ("پیسٹ",    "click"):         "hotkey:ctrl+v",   # Urdu "paste" + click
    ("بند کرو", "stop"):          "hotkey:ctrl+w",   # Urdu "close" + palm
    ("محفوظ",   "stop"):          "hotkey:ctrl+s",   # Urdu "save" + palm
}

# Custom speed-scroll actions (not standard pyautogui actions)
# ActionThread handles these specially
SPECIAL_HYBRID_ACTIONS = {
    "scroll_up_fast":   ("scroll", +6),   # 6 units instead of default 3
    "scroll_down_fast": ("scroll", -6),
}