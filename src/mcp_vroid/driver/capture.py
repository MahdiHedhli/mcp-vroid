"""Screenshot the VRoid window (platform facade).

Linux/Wayland: grim. macOS: screencapture / ScreenCaptureKit.
`Shot` is shared so OCR coordinates still map back to input.click().
"""
from __future__ import annotations

import sys

from .paths import CAPTURES, next_capture_path  # noqa: F401
from .types import Shot  # noqa: F401

if sys.platform == "darwin":
    from .macos.capture import grab_region, grab_screen, grab_window, output_scale
else:
    from .wayland.capture import grab_region, grab_screen, grab_window, output_scale

__all__ = [
    "CAPTURES", "Shot", "grab_region", "grab_screen", "grab_window",
    "next_capture_path", "output_scale",
]
