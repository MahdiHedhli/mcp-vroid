"""Pointer + keyboard injection (platform facade).

Linux/Wayland: zwlr_virtual_pointer + X11 XTEST.
macOS: Quartz CGEvent (HID tap).
"""
from __future__ import annotations

import sys

if sys.platform == "darwin":
    from .macos.input import *  # noqa: F403
else:
    from .wayland.input import *  # noqa: F403
