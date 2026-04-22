"""
Air Draw Bindings — edit this file to change what each letter does.
Managed by Wavly Settings. You can also edit it manually.

Action types:
  hotkey:ctrl+c       — keyboard shortcut
  run:notepad.exe     — open an application
  type:Hello          — type a string

Letter ideas:
  C = Copy        (ctrl+c)
  V = Paste       (ctrl+v)
  X = Cut         (ctrl+x)
  Z = Undo        (ctrl+z)
  S = Save        (ctrl+s)
  A = Select All  (ctrl+a)
  F = Find        (ctrl+f)
  T = New Tab     (ctrl+t)
  W = Close Tab   (ctrl+w)
  N = New Window  (ctrl+n)
  O = Open File   (ctrl+o)
  R = Refresh     (ctrl+r)
  P = Print       (ctrl+p)
  M = Minimise    (win+m)
  E = File Explorer (win+e)
"""

AIR_DRAW_BINDINGS: dict = {
    "C": "hotkey:ctrl+c",     # Copy
    "V": "hotkey:ctrl+v",     # Paste
    "X": "hotkey:ctrl+x",     # Cut
    "Z": "hotkey:ctrl+z",     # Undo
    "S": "hotkey:ctrl+s",     # Save
    "A": "hotkey:ctrl+a",     # Select All
    "F": "hotkey:ctrl+f",     # Find
    "T": "hotkey:ctrl+t",     # New Tab
    "W": "hotkey:ctrl+w",     # Close Tab
    "N": "hotkey:ctrl+n",     # New Window
    "O": "hotkey:ctrl+o",     # Open File
    "R": "hotkey:ctrl+r",     # Refresh
    "P": "hotkey:ctrl+p",     # Print
    "M": "hotkey:win+m",      # Minimise all
    "E": "hotkey:win+e",      # File Explorer
}