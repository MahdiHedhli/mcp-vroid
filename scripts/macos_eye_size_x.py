#!/usr/bin/env python3
"""Milestone 1: locate Eye Size X on the open Lyra model, type 0.850, verify.

Does not open or write Lyra.vroid. Uses the same set_param path as
vroid_set_slider. Run with VRoid Studio already showing the editor:

    uv run python scripts/macos_eye_size_x.py
"""
from __future__ import annotations

import json
import sys

from mcp_vroid.driver import actions as A
from mcp_vroid.driver import capture as C
from mcp_vroid.driver import locate as L
from mcp_vroid.driver import window as W


def main() -> int:
    win = W.find_window()
    if win is None:
        print("VRoid Studio window not found", file=sys.stderr)
        return 1
    print(f"window title={win.title!r} geometry={win.geometry} address={win.address}")
    W.focus(win)
    W.assert_vroid_focused()

    screen = A.current_screen()
    print(f"screen={screen}")
    if screen != "editor":
        print("expected the editor screen", file=sys.stderr)
        return 1

    # Face tab holds Eye Size X; open it if the strip is visible.
    try:
        A.open_tab("Face")
    except RuntimeError as exc:
        print(f"open_tab Face: {exc} (continuing if already on Face)")

    before = A.read_param("Eye Size X")
    print(f"read before: {before!r}")

    shot = A.set_param("Eye Size X", 0.850)
    print(f"set_param capture: {shot.path}")

    after = A.read_param("Eye Size X")
    print(f"read after: {after!r}")

    verify = C.grab_window(tag="eye-size-x-verify")
    hits = L.find_text(verify, "Eye Size X", all_matches=True) or []
    print(f"locate Eye Size X: {len(hits)} hit(s)")
    for h in hits[:3]:
        print(f"  {h}")

    out = {
        "title": win.title,
        "before": before,
        "after": after,
        "target": 0.850,
        "capture": str(shot.path),
        "verify": str(verify.path),
        "located": bool(hits),
    }
    print(json.dumps(out, indent=2))
    if not hits:
        print("failed to locate Eye Size X after set", file=sys.stderr)
        return 1
    # Accept OCR noise around the stored 0.850
    blob = (after or "").replace(" ", "")
    if "0.85" not in blob and "085" not in blob:
        print(f"value OCR {after!r} does not look like 0.850", file=sys.stderr)
        return 1
    print("milestone 1 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
