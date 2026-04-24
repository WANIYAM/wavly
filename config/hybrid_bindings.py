"""
Hybrid Voice + Gesture Command Bindings — Phase 4 Feature 2

Defines how voice commands combine with gestures to create powerful hybrid actions.

Format:
  ("voice_action", "gesture_type"): "hybrid_action"

Example:
  ("open", "point"): "open_pointed_file"
  
Gestures are named from GestureQueue events, typically:
  - "point" = index finger pointing (lateral hand position)
  - "air_letter:A" = drawing letter A
  - "fingers_2", "fingers_3", "fingers_4" = showing N fingers
  - "fist" = closed fist
  - "palm" = open palm
  - "pinch" = pinch gesture
  - "swipe_left", "swipe_right" = swiping motions

Voice actions are from config/voice_bindings.py, typically:
  - "open", "copy", "paste", "save", "scroll_up", "scroll_down", etc.

You can add any hybrid action name here — the meaning is defined by how
ActionThread implements it in _execute_hybrid_action().
"""

HYBRID_BINDINGS: dict = {

    # ── File Operations ───────────────────────────────────────────────────
    ("open", "point"):
        "open_at_cursor",     # Open file/folder at cursor position
    
    ("save", "fingers_2"):
        "save_as",            # Save as... with filename dialog
    
    ("delete", "fist"):
        "delete_confirmed",   # Delete with visual confirmation (closed fist = certain)


    # ── Search ────────────────────────────────────────────────────────────
    ("search", "air_letter"):
        "search_for_letter",  # Search for the air-drawn letter
    
    ("search", "fingers_3"):
        "search_for_word",    # Show search suggestions with 3 fingers = important
    
    ("find", "point"):
        "find_at_cursor",     # Find text at cursor location


    # ── Navigation ────────────────────────────────────────────────────────
    ("go_to", "fingers"):
        "go_to_line_number",  # Go to line shown by fingers (2→line 2, 3→line 3, etc)
    
    ("page_up", "palm"):
        "fast_page_up",       # Page up (open palm = emphatic, "push" up)
    
    ("page_down", "fist"):
        "fast_page_down",     # Page down (closed fist = emphatic, "push" down)
    
    ("go_back", "swipe_right"):
        "go_back_fast",       # Go back (right swipe reinforces direction)
    
    ("go_forward", "swipe_left"):
        "go_forward_fast",    # Go forward (left swipe reinforces direction)


    # ── Text Editing ──────────────────────────────────────────────────────
    ("select", "point"):
        "select_from_cursor", # Start selection from cursor
    
    ("copy", "fingers_2"):
        "copy_line",          # Copy current line (2 fingers = smaller scope)
    
    ("copy", "fingers_3"):
        "copy_paragraph",     # Copy current paragraph (3 fingers = larger scope)
    
    ("paste", "point"):
        "paste_at_cursor",    # Paste at cursor
    
    ("type", "air_letter"):
        "type_letter",        # Type the air-drawn letter directly


    # ── Voice Reinforcement (Same action + gesture = stronger signal) ────
    # These are lower-priority but provide reinforcement for the voice signal
    
    ("click", "point"):
        "click_at_point",     # Click where pointing (reinforces intent)
    
    ("scroll_up", "palm"):
        "scroll_up_fast",     # Scroll up faster (palm = push motion)
    
    ("scroll_down", "fist"):
        "scroll_down_fast",   # Scroll down faster (fist = push motion)

}

# ── Implementation hints for ActionThread._execute_hybrid_action() ────────
#
# When hybrid action is executed, ActionThread can call:
#
#   def _execute_hybrid_action(self, hybrid_action, voice_transcript, gesture_type):
#       if hybrid_action == "open_at_cursor":
#           x, y = self.gesture_queue.get_cursor()
#           # Find what's at (x, y) and open it
#           open_file_at_position(x, y)
#
#       elif hybrid_action == "search_for_letter":
#           letter = extract_letter_from_transcript(voice_transcript)
#           # Find gesture data to get drawn letter
#           # Combine both: search for drawn letter + voice confirmation
#           search(letter)
#
#       elif hybrid_action == "go_to_line_number":
#           number = extract_number_from_voice(voice_transcript)
#           # Or: count fingers from gesture
#           # Extract line number: "go to 42" → 42
#           go_to_line(number)
#
# The key insight: Hybrid actions can use BOTH the voice transcript
# AND the gesture data (position, shape, timing) to be more powerful
# than either alone.
#
