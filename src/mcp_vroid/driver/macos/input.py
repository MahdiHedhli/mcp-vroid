"""Pointer + keyboard injection via Quartz CGEvent on macOS.

Mouse, scroll and keys are posted to kCGHIDEventTap. Unity's canvas is not
an AX target, so there is no AXPress path for sliders — clicks land on the
real cursor. Select-all uses Command, not Control.

All public coordinates are window-relative layout units unless you pass
space="layout" or space="image" (image needs the Shot's scale).
"""
from __future__ import annotations

import time

from .. import window as W

BUTTONS = {"left": "left", "right": "right", "middle": "middle",
           1: "left", 2: "middle", 3: "right"}

_SAFE = True

# HID virtual keycodes (Events.h). Enough for parameter values and hotkeys.
_VK = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05,
    "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C,
    "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11, "1": 0x12,
    "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18,
    "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "o": 0x1F,
    "u": 0x20, "i": 0x22, "p": 0x23, "return": 0x24, "l": 0x25, "j": 0x26,
    "k": 0x28, ";": 0x29, "'": 0x27, ",": 0x2B, "/": 0x2C, "n": 0x2D, "m": 0x2E,
    ".": 0x2F, "tab": 0x30, "space": 0x31, "`": 0x32, "backspace": 0x33,
    "escape": 0x35, "command": 0x37, "shift": 0x38, "option": 0x3A,
    "alt": 0x3A, "control": 0x3B, "ctrl": 0x3B, "delete": 0x75,
    "home": 0x73, "end": 0x77, "pageup": 0x74, "pagedown": 0x79,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
    "enter": 0x24, "esc": 0x35, "cmd": 0x37,
}

_SHIFT_CHARS = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6",
    "&": "7", "*": "8", "(": "9", ")": "0", "_": "-", "+": "=",
    ":": ";", '"': "'", "<": ",", ">": ".", "?": "/",
}

# Quartz event types / buttons (CGEventTypes.h)
_MOUSE_MOVED = 5
_LEFT_DOWN, _LEFT_UP, _LEFT_DRAGGED = 1, 2, 6
_RIGHT_DOWN, _RIGHT_UP, _RIGHT_DRAGGED = 3, 4, 7
_OTHER_DOWN, _OTHER_UP, _OTHER_DRAGGED = 25, 26, 27
_BTN_LEFT, _BTN_RIGHT, _BTN_CENTER = 0, 1, 2
_HID_TAP = 0  # kCGHIDEventTap
_FLAG_SHIFT, _FLAG_CTRL, _FLAG_ALT, _FLAG_CMD = 0x020000, 0x040000, 0x080000, 0x100000


def set_safety(on: bool) -> None:
    global _SAFE
    _SAFE = on


def _guard() -> None:
    if not _SAFE:
        return
    W.assert_vroid_focused()


def _vroid_pid() -> int:
    win = W.find_window()
    if win is None or not win.pid:
        raise RuntimeError("VRoid Studio window not found")
    return int(win.pid)


def _qz():
    import Quartz
    return Quartz


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


def _cursor() -> tuple[float, float]:
    Q = _qz()
    ev = Q.CGEventCreate(None)
    loc = Q.CGEventGetLocation(ev)
    return float(loc.x), float(loc.y)


def _mouse_types(button: str) -> tuple[int, int, int, int]:
    b = BUTTONS.get(button, "left")
    if b == "right":
        return _RIGHT_DOWN, _RIGHT_UP, _RIGHT_DRAGGED, _BTN_RIGHT
    if b == "middle":
        return _OTHER_DOWN, _OTHER_UP, _OTHER_DRAGGED, _BTN_CENTER
    return _LEFT_DOWN, _LEFT_UP, _LEFT_DRAGGED, _BTN_LEFT


def _post(ev) -> None:
    Q = _qz()
    # HID tap moves the real cursor; PostToPid delivers to Unity even if a
    # CLI host has stolen frontmost status (common for MCP servers).
    Q.CGEventPost(_HID_TAP, ev)
    try:
        Q.CGEventPostToPid(_vroid_pid(), ev)
    except Exception:
        pass


def _post_mouse(kind: int, x: float, y: float, button: int) -> None:
    Q = _qz()
    ev = Q.CGEventCreateMouseEvent(None, kind, (x, y), button)
    _post(ev)


def move(x: float, y: float, space: str = "window", shot=None) -> None:
    lx, ly = _resolve(x, y, space, shot)
    _post_mouse(_MOUSE_MOVED, lx, ly, _BTN_LEFT)


def click(x: float, y: float, button: str = "left", space: str = "window",
          shot=None, settle: float = 0.35, moves: int = 3) -> None:
    """Move (in a few steps, so hover states fire) then click."""
    _guard()
    lx, ly = _resolve(x, y, space, shot)
    try:
        cx, cy = _cursor()
    except Exception:
        cx, cy = lx, ly
    down, up, _drag, btn = _mouse_types(button)
    for i in range(1, moves + 1):
        t = i / moves
        _post_mouse(_MOUSE_MOVED, cx + (lx - cx) * t, cy + (ly - cy) * t, btn)
        time.sleep(0.012)
    time.sleep(0.06)
    _post_mouse(down, lx, ly, btn)
    time.sleep(0.02)
    _post_mouse(up, lx, ly, btn)
    time.sleep(settle)


def double_click(x: float, y: float, **kw) -> None:
    click(x, y, **kw)
    time.sleep(0.05)
    click(x, y, settle=kw.get("settle", 0.35))


def drag(x1: float, y1: float, x2: float, y2: float, button: str = "left",
         space: str = "window", shot=None, steps: int = 24,
         settle: float = 0.4) -> None:
    _guard()
    ax, ay = _resolve(x1, y1, space, shot)
    bx, by = _resolve(x2, y2, space, shot)
    down, up, dragged, btn = _mouse_types(button)
    _post_mouse(_MOUSE_MOVED, ax, ay, btn)
    time.sleep(0.12)
    _post_mouse(down, ax, ay, btn)
    time.sleep(0.12)
    for i in range(1, steps + 1):
        t = i / steps
        _post_mouse(dragged, ax + (bx - ax) * t, ay + (by - ay) * t, btn)
        time.sleep(0.016)
    time.sleep(0.15)
    _post_mouse(up, bx, by, btn)
    time.sleep(settle)


def scroll(ticks: int, x: float | None = None, y: float | None = None,
           space: str = "window", shot=None, settle: float = 0.3,
           backend: str = "quartz") -> None:
    """Wheel scroll. Negative = up/away, positive = down (matches Wayland API)."""
    _guard()
    if x is not None and y is not None:
        move(x, y, space, shot)
        time.sleep(0.2)
    Q = _qz()
    # CGEvent: positive line delta scrolls up. Invert to match the driver API.
    step = -1 if ticks > 0 else 1
    for _ in range(abs(ticks)):
        ev = Q.CGEventCreateScrollWheelEvent(None, 1, 1, step)  # line units
        _post(ev)
        time.sleep(0.07)
    time.sleep(settle)


def hscroll(ticks: int, x: float | None = None, y: float | None = None,
            space: str = "window", shot=None, settle: float = 0.3) -> None:
    _guard()
    if x is not None and y is not None:
        move(x, y, space, shot)
        time.sleep(0.2)
    Q = _qz()
    step = 1 if ticks > 0 else -1
    for _ in range(abs(ticks)):
        # wheelCount=2, wheel1=0 (vertical), wheel2=horizontal
        ev = Q.CGEventCreateScrollWheelEvent(None, 0, 2, 0, step)
        _post(ev)
        time.sleep(0.07)
    time.sleep(settle)


def _flags_for(mods: list[str]) -> int:
    flags = 0
    for m in mods:
        k = m.lower()
        if k in ("shift",):
            flags |= _FLAG_SHIFT
        elif k in ("ctrl", "control"):
            # Native VRoid uses Command for app shortcuts; keep Control if asked.
            flags |= _FLAG_CTRL
        elif k in ("alt", "option"):
            flags |= _FLAG_ALT
        elif k in ("cmd", "command", "super", "meta"):
            flags |= _FLAG_CMD
    return flags


def _tap(keycode: int, flags: int = 0, hold: float = 0.02) -> None:
    Q = _qz()
    down = Q.CGEventCreateKeyboardEvent(None, keycode, True)
    up = Q.CGEventCreateKeyboardEvent(None, keycode, False)
    if flags:
        Q.CGEventSetFlags(down, flags)
        Q.CGEventSetFlags(up, flags)
    _post(down)
    time.sleep(hold)
    _post(up)


def _vk(name: str) -> int:
    key = _VK.get(name.lower())
    if key is None:
        raise ValueError(f"no keycode for {name!r}")
    return key


def type_text(text: str, delay_ms: int = 22) -> None:
    """Type a literal string into the focused widget (Quartz keycodes)."""
    _guard()
    for ch in text:
        if ch == "\n":
            key("Return")
            continue
        if ch == " ":
            _tap(_vk("space"))
        elif ch in _SHIFT_CHARS:
            _tap(_vk(_SHIFT_CHARS[ch]), _FLAG_SHIFT)
        elif ch.isupper():
            _tap(_vk(ch.lower()), _FLAG_SHIFT)
        elif ch.lower() in _VK:
            _tap(_vk(ch.lower()))
        else:
            # Last resort: unicode string event (Unity often ignores these).
            Q = _qz()
            ev = Q.CGEventCreateKeyboardEvent(None, 0, True)
            Q.CGEventKeyboardSetUnicodeString(ev, 1, ch)
            _post(ev)
            ev_up = Q.CGEventCreateKeyboardEvent(None, 0, False)
            _post(ev_up)
        time.sleep(delay_ms / 1000.0)
    time.sleep(0.15)


def key(name: str, mods: list[str] | None = None, times: int = 1) -> None:
    _guard()
    aliases = {"enter": "return", "esc": "escape"}
    n = aliases.get(name.lower(), name.lower())
    flags = _flags_for(mods or [])
    code = _vk(n)
    for _ in range(times):
        _tap(code, flags)
        time.sleep(0.06)
    time.sleep(0.12)


def clear_field() -> None:
    """Select-all + delete in the focused text field (macOS Command+A)."""
    key("a", mods=["command"])
    key("BackSpace")


def hotkey(combo: str) -> None:
    """'ctrl+shift+s' -> modifier-held keypress. ctrl is mapped to command."""
    *mods, k = combo.split("+")
    mapped = []
    for m in mods:
        mapped.append("command" if m.lower() in ("ctrl", "control") else m)
    key(k, mods=mapped)


def x_focus_ok() -> bool:
    """True when VRoid Studio is the frontmost app."""
    return W.is_vroid_focused()
