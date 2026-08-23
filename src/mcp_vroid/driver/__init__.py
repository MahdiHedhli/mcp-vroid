"""GUI-automation driver for VRoid Studio on Hyprland/Wayland.

The loop is: capture (grim) -> locate (tesseract OCR / cv2 template match)
-> act (wlr virtual pointer for the mouse, X11 XTEST for keys/wheel)
-> capture again.

Originally written as the `tools/vroid-driver` spike in the author's
`arrakis` project; vendored here as the engine under the MCP server.
"""
from .paths import CAPTURES, OUT, VPOINTER  # noqa: F401
