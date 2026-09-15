"""GUI-automation driver for VRoid Studio.

The loop is: capture -> locate (tesseract OCR / cv2) -> act -> capture again.

Platform backends live in `wayland/` (Hyprland + grim + virtual pointer +
XTEST) and `macos/` (AX window chrome + screencapture + Quartz CGEvent).
`window`, `capture` and `input` are facades; VRoid-specific flows stay in
`actions.py` and do not branch on OS.
"""
from .paths import CAPTURES, OUT, VPOINTER  # noqa: F401
