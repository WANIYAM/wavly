# Wavly Keyboard Hover Fix Progress

## Approved Plan Steps:
- [x] Step 1: Add debug prints to ui/keyboard.py (update_hands, _btn_at_screen) and core/camera_thread.py (_process_keyboard_mode)
- [x] Step 1.5: Throttled logs to reduce spam, added window geometry logs
- [ ] Step 2: User tests app, toggles keyboard (3-finger), hovers hands, shares console output
- [ ] Step 3: Analyze logs, propose/apply fixes (e.g., hand label swap, pinch threshold, pos scaling)
- [ ] Step 4: Test hover visuals + pinch typing + mouse fallback
- [ ] Step 5: Remove debug prints, finalize
