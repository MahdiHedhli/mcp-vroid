"""Pointer + keyboard injection.

Pointer: a small C helper (native/vpointer) speaking
zwlr_virtual_pointer_unstable_v1 to Hyprland. ydotool is not installed here
and /dev/uinput is root-only (0600 root:root), so evdev injection would need
sudo/a udev rule; the Wayland protocol needs neither.

Keyboard and wheel: X11 XTEST through Xwayland (`wtype` sends a throwaway
keymap that this Proton client mis-reads). Both go to whatever window has
focus, so every call re-checks that VRoid is focused first.

All public coordinates are *window-relative layout units* unless you pass
space="layout" or space="image" (image needs the Shot's scale).
"""
from __future__ import annotations

import subprocess
import time

from . import window as W
from .paths import VPOINTER

BUTTONS = {"left": "left", "right": "right", "middle": "middle",
           1: "left", 2: "middle", 3: "right"}

_SAFE = True   # module-level guard: verify VRoid focus before every action


def set_safety(on: bool) -> None:
    global _SAFE
    _SAFE = on


def _guard() -> None:
    if not _SAFE:
        return
    if not W.is_vroid_focused() and W.dismiss_screensaver():
        W.focus()
    W.assert_vroid_focused()


def _layout_extent() -> tuple[int, int]:
    mon = W.hyprctl_json("monitors")[0]
    scale = float(mon.get("scale", 1.0))
    return int(round(mon["width"] / scale)), int(round(mon["height"] / scale))


def _run_pointer(script: str) -> None:
    if not VPOINTER.exists():
        raise RuntimeError(
            f"{VPOINTER} missing - run native/build.sh")
    w, h = _layout_extent()
    subprocess.run([str(VPOINTER), "-W", str(w), "-H", str(h)],
                   input=script, text=True, check=True, capture_output=True)


def _resolve(x: float, y: float, space: str, shot=None) -> tuple[float, float]:
    if space == "layout":
        return x, y
    if space == "image":
        if shot is None:
            raise ValueError("space='image' needs shot=")
        return shot.to_layout(x, y)
    win = W.find_window()
    if win is None:
        raise RuntimeError("VRoid Studio window not found")
    return win.to_layout(x, y)


# --- pointer ----------------------------------------------------------------

def move(x: float, y: float, space: str = "window", shot=None) -> None:
    lx, ly = _resolve(x, y, space, shot)
    _run_pointer(f"move {lx:.0f} {ly:.0f}\n")


def click(x: float, y: float, button: str = "left", space: str = "window",
          shot=None, settle: float = 0.35, moves: int = 3) -> None:
    """Move (in a few steps, so hover states fire) then click."""
    _guard()
    lx, ly = _resolve(x, y, space, shot)
    cur = W.hyprctl("cursorpos").strip().split(",")
    try:
        cx, cy = float(cur[0]), float(cur[1])
    except (ValueError, IndexError):
        cx, cy = lx, ly
    lines = []
    for i in range(1, moves + 1):
        t = i / moves
        lines.append(f"move {cx + (lx - cx) * t:.0f} {cy + (ly - cy) * t:.0f}")
        lines.append("sleep 12")
    lines += ["sleep 60", f"click {BUTTONS.get(button, 'left')}"]
    _run_pointer("\n".join(lines) + "\n")
    time.sleep(settle)


def double_click(x: float, y: float, **kw) -> None:
    click(x, y, **kw)
    time.sleep(0.05)
    click(x, y, settle=kw.get("settle", 0.35))


def drag(x1: float, y1: float, x2: float, y2: float, button: str = "left",
         space: str = "window", shot=None, steps: int = 24,
         settle: float = 0.4) -> None:
    """Press at (x1,y1), glide to (x2,y2), release. Used for sliders."""
    _guard()
    ax, ay = _resolve(x1, y1, space, shot)
    bx, by = _resolve(x2, y2, space, shot)
    b = BUTTONS.get(button, "left")
    lines = [f"move {ax:.0f} {ay:.0f}", "sleep 120", f"down {b}", "sleep 120"]
    for i in range(1, steps + 1):
        t = i / steps
        lines.append(f"move {ax + (bx - ax) * t:.0f} {ay + (by - ay) * t:.0f}")
        lines.append("sleep 16")
    lines += ["sleep 150", f"up {b}"]
    _run_pointer("\n".join(lines) + "\n")
    time.sleep(settle)


def scroll(ticks: int, x: float | None = None, y: float | None = None,
           space: str = "window", shot=None, settle: float = 0.3,
           backend: str = "x11") -> None:
    """Wheel scroll. Negative = up/away, positive = down.

    Default backend is XTEST buttons 4/5: VRoid (a Proton/XWayland client)
    ignores zwlr_virtual_pointer axis events but honours X button events.
    """
    _guard()
    if x is not None and y is not None:
        move(x, y, space, shot)
        time.sleep(0.2)
    if backend == "x11":
        from Xlib import X
        from Xlib.ext import xtest
        d = _display()
        btn = 5 if ticks > 0 else 4
        for _ in range(abs(ticks)):
            xtest.fake_input(d, X.ButtonPress, btn); d.sync()
            xtest.fake_input(d, X.ButtonRelease, btn); d.sync()
            time.sleep(0.07)
    else:
        step = 1 if ticks > 0 else -1
        lines = []
        for _ in range(abs(ticks)):
            lines += [f"scroll {step}", "sleep 45"]
        _run_pointer("\n".join(lines) + "\n")
    time.sleep(settle)


def hscroll(ticks: int, x: float | None = None, y: float | None = None,
            space: str = "window", shot=None, settle: float = 0.3) -> None:
    """Horizontal wheel (XTEST buttons 6/7). Negative = left, positive = right.

    Rarely useful in VRoid - the panels only scroll vertically - but the
    export screen's wide accordions and the Wine file list accept it.
    """
    _guard()
    if x is not None and y is not None:
        move(x, y, space, shot)
        time.sleep(0.2)
    from Xlib import X
    from Xlib.ext import xtest
    d = _display()
    btn = 7 if ticks > 0 else 6
    for _ in range(abs(ticks)):
        xtest.fake_input(d, X.ButtonPress, btn); d.sync()
        xtest.fake_input(d, X.ButtonRelease, btn); d.sync()
        time.sleep(0.07)
    time.sleep(settle)


# --- keyboard ---------------------------------------------------------------
#
# wtype (zwp_virtual_keyboard) does NOT work against this app: VRoid runs
# under Proton/XWayland and the X server keeps a stale copy of wtype's
# throwaway keymap, so "SpikeAvatar" arrives as a single "1". XTEST through
# Xwayland uses the real keymap and lands correctly, so keyboard input goes
# over X11 while the pointer stays on the Wayland virtual-pointer protocol.

_XK_ALIASES = {
    "enter": "Return", "return": "Return", "esc": "Escape", "escape": "Escape",
    "tab": "Tab", "backspace": "BackSpace", "delete": "Delete",
    "space": "space", "up": "Up", "down": "Down", "left": "Left",
    "right": "Right", "home": "Home", "end": "End", "pageup": "Prior",
    "pagedown": "Next", "ctrl": "Control_L", "control": "Control_L",
    "shift": "Shift_L", "alt": "Alt_L", "super": "Super_L", "meta": "Super_L",
}

_dpy = None


def _display():
    global _dpy
    if _dpy is None:
        import os
        from Xlib import display
        os.environ.setdefault("DISPLAY", ":0")
        _dpy = display.Display(os.environ["DISPLAY"])
    return _dpy


def _keysym(name: str) -> int:
    from Xlib import XK
    name = _XK_ALIASES.get(name.lower(), name)
    ks = XK.string_to_keysym(name)
    if ks == 0 and len(name) == 1:
        ks = ord(name)
        if ks > 0x7F:  # unicode keysym encoding
            ks += 0x01000000
    return ks


def _keycode(ks: int) -> tuple[int, bool]:
    """(keycode, needs_shift) for a keysym on the *current* layout."""
    d = _display()
    code = d.keysym_to_keycode(ks)
    if code == 0:
        return 0, False
    # is it the shifted level?
    try:
        base = d.keycode_to_keysym(code, 0)
    except Exception:
        base = ks
    return code, base != ks


def _tap(code: int, mods: list[int], hold: float = 0.02) -> None:
    from Xlib import X
    from Xlib.ext import xtest
    d = _display()
    for m in mods:
        xtest.fake_input(d, X.KeyPress, m)
    d.sync()
    xtest.fake_input(d, X.KeyPress, code)
    d.sync()
    time.sleep(hold)
    xtest.fake_input(d, X.KeyRelease, code)
    d.sync()
    for m in reversed(mods):
        xtest.fake_input(d, X.KeyRelease, m)
    d.sync()


def _remap_spare(ks: int) -> int:
    """Bind a keysym the layout lacks onto a scratch keycode."""
    d = _display()
    code = 250  # high, unused on a normal xkb map
    d.change_keyboard_mapping(code, [[ks, ks, ks, ks]])
    d.sync()
    time.sleep(0.03)
    return code


def type_text(text: str, delay_ms: int = 22) -> None:
    """Type a literal string into the focused widget (XTEST)."""
    _guard()
    d = _display()
    shift = d.keysym_to_keycode(_keysym("Shift_L"))
    spare_used = False
    for ch in text:
        if ch == "\n":
            key("Return")
            continue
        ks = _keysym(ch)
        code, need_shift = _keycode(ks)
        if code == 0:
            code, need_shift, spare_used = _remap_spare(ks), False, True
        _tap(code, [shift] if need_shift else [])
        time.sleep(delay_ms / 1000.0)
    if spare_used:
        d.change_keyboard_mapping(250, [[0, 0, 0, 0]])
        d.sync()
    time.sleep(0.15)


def key(name: str, mods: list[str] | None = None, times: int = 1) -> None:
    """Press a named key: Return, Escape, Tab, BackSpace, a, ... with mods."""
    _guard()
    d = _display()
    ks = _keysym(name)
    code, need_shift = _keycode(ks)
    if code == 0:
        raise ValueError(f"no keycode for {name!r}")
    mod_codes = [d.keysym_to_keycode(_keysym(m)) for m in (mods or [])]
    if need_shift:
        mod_codes.append(d.keysym_to_keycode(_keysym("Shift_L")))
    for _ in range(times):
        _tap(code, mod_codes)
        time.sleep(0.06)
    time.sleep(0.12)


def clear_field() -> None:
    """Select-all + delete in the focused text field."""
    key("a", mods=["ctrl"])
    key("BackSpace")


def hotkey(combo: str) -> None:
    """'ctrl+shift+s' -> modifier-held keypress."""
    *mods, k = combo.split("+")
    key(k, mods=mods)


def x_focus_ok() -> bool:
    """True when the X input focus is on the VRoid window."""
    try:
        name = _display().get_input_focus().focus.get_wm_name() or ""
    except Exception:
        return False
    return "vroid" in name.lower()
