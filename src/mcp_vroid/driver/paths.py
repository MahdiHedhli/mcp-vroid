"""Where the driver reads its helper binary and writes its artifacts.

Unlike the original spike (which kept everything next to the source tree),
an installed package must not scribble into site-packages, so every location
is overridable by environment variable and defaults to XDG state.

    MCP_VROID_CAPTURES  screenshots       default $XDG_STATE_HOME/mcp-vroid/captures
    MCP_VROID_OUT       exported files    default $XDG_STATE_HOME/mcp-vroid/out
    MCP_VROID_VPOINTER  the vpointer bin  default <repo>/native/vpointer, then $PATH
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent      # .../mcp_vroid
REPO = PACKAGE.parent.parent                          # .../<checkout>  (src layout)


def _state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")


def _dir(env: str, default: Path) -> Path:
    p = Path(os.environ.get(env) or default).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


CAPTURES = _dir("MCP_VROID_CAPTURES", _state_home() / "mcp-vroid/captures")
OUT = _dir("MCP_VROID_OUT", _state_home() / "mcp-vroid/out")


def next_capture_path(tag: str = "") -> Path:
    n = 0
    for p in CAPTURES.glob("[0-9][0-9][0-9]*.png"):
        try:
            n = max(n, int(p.name[:3]))
        except ValueError:
            pass
    name = f"{n + 1:03d}" + (f"-{tag}" if tag else "") + ".png"
    return CAPTURES / name


def _find_vpointer() -> Path:
    env = os.environ.get("MCP_VROID_VPOINTER")
    if env:
        return Path(env).expanduser()
    for cand in (REPO / "native" / "vpointer", PACKAGE / "native" / "vpointer"):
        if cand.exists():
            return cand
    which = shutil.which("vpointer")
    if which:
        return Path(which)
    return REPO / "native" / "vpointer"          # reported in the error message


VPOINTER = _find_vpointer()
NATIVE = VPOINTER.parent
