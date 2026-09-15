"""Find / launch / focus the VRoid Studio window (platform facade).

Linux/Wayland: Hyprland via hyprctl.
macOS: Accessibility + NSWorkspace + Quartz window list.
"""
from __future__ import annotations

import sys

if sys.platform == "darwin":
    from .macos.window import *  # noqa: F403
else:
    from .wayland.window import *  # noqa: F403
