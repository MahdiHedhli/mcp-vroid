"""Screenshot the VRoid window on macOS.

Primary capture is `/usr/sbin/screencapture -l<CGWindowID>`, which goes
through ScreenCaptureKit on modern macOS (CGWindowListCreateImage is
obsoleted as of macOS 15). Requires Screen Recording permission for the
process that hosts this server.

Coordinate space: Quartz global points, origin at the top-left of the main
display, y down. Image pixels are `scale` times those points (1.0 on the
portrait display used for recon; 2.0 on Retina).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from .. import window as W
from ..paths import next_capture_path
from ..types import Shot


def output_scale() -> float:
    win = W.find_window()
    if win is None or not win.w:
        return 1.0
    shot = grab_window(win, tag="scale")
    return shot.scale


def _screencapture(*args: str) -> None:
    cmd = ["/usr/sbin/screencapture", "-x", *args]
    # Never text=True: if the path is omitted or rejected, screencapture
    # writes a PNG (magic 0x89) to stdout and would crash MCP stdio.
    r = subprocess.run(cmd, capture_output=True)
    dest = Path(args[-1]) if args else None
    if r.stdout.startswith(b"\x89PNG") and dest is not None:
        dest.write_bytes(r.stdout)
        return
    if r.returncode != 0 or (dest is not None and not dest.exists()):
        err = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()
        err = err or f"exit {r.returncode}"
        raise RuntimeError(
            f"screencapture failed ({err}). Grant Screen Recording to the "
            "process that runs this server (System Settings → Privacy & "
            "Security → Screen Recording)."
        )


def grab_region(x: int, y: int, w: int, h: int, tag: str = "",
                path: Path | None = None) -> Shot:
    path = path or next_capture_path(tag)
    _screencapture("-R", f"{x},{y},{w},{h}", str(path))
    img = Image.open(path).convert("RGB")
    scale = (img.width / w) if w else 1.0
    return Shot(img, path, x, y, scale)


def grab_window(win: W.Window | None = None, tag: str = "") -> Shot:
    win = win or W.find_window()
    if win is None:
        raise RuntimeError("VRoid Studio window not found")
    path = next_capture_path(tag)
    try:
        wid = int(win.address)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid VRoid window id {win.address!r}") from exc
    # -o: no window shadow, so image size matches kCGWindowBounds.
    _screencapture("-o", "-l", str(wid), str(path))
    img = Image.open(path).convert("RGB")
    scale = (img.width / win.w) if win.w else 1.0
    return Shot(img, path, win.x, win.y, scale)


def grab_screen(tag: str = "") -> Shot:
    path = next_capture_path(tag)
    _screencapture(str(path))
    img = Image.open(path).convert("RGB")
    return Shot(img, path, 0, 0, 1.0)
