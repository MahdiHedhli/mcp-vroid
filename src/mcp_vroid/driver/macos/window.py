"""Find / launch / focus native VRoid Studio on macOS.

Window discovery uses the Quartz window list plus NSWorkspace. Raise/focus
uses Accessibility (AXRaise) and NSRunningApplication.activate. The Unity
canvas itself is not in the AX tree; see docs/macos-ax.md.
"""
from __future__ import annotations

import subprocess
import time

from ..types import Window

STEAM_APPID = "1486350"
BUNDLE_ID = "net.pixiv.vroid.macosx"
APP_NAME = "VRoid Studio"
CLASS_HINTS = ("vroidstudio", "vroid studio", BUNDLE_ID)
TITLE_HINTS = ("vroid",)
WORKSPACE = 0  # macOS has no Hyprland workspace; kept for the shared MCP API

_APP_PATHS = (
    "/Applications/VRoidStudio.app",
    "/Applications/VRoid Studio.app",
)


def _quartz():
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGNullWindowID,
        kCGWindowListExcludeDesktopElements,
        kCGWindowListOptionOnScreenOnly,
    )
    return (
        CGWindowListCopyWindowInfo,
        kCGNullWindowID,
        kCGWindowListExcludeDesktopElements,
        kCGWindowListOptionOnScreenOnly,
    )


def _running_app():
    from AppKit import NSWorkspace
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        bid = str(app.bundleIdentifier() or "")
        name = str(app.localizedName() or "")
        if bid == BUNDLE_ID or "vroid studio" in name.lower():
            return app
    return None


def _window_entries(on_screen_only: bool = True) -> list[dict]:
    (copy_info, null_id, exclude_desktop, on_screen) = _quartz()
    opts = exclude_desktop
    if on_screen_only:
        opts |= on_screen
    info = copy_info(opts, null_id) or []
    return list(info)


def _is_vroid_window(entry: dict) -> bool:
    owner = str(entry.get("kCGWindowOwnerName") or "")
    title = str(entry.get("kCGWindowName") or "")
    # kCGWindowOwnerName has been observed as both "VRoid Studio" and
    # "VRoidStudio" (e.g. after a login-time relaunch post-reboot) for the
    # same app; compare space-insensitively rather than matching one spelling.
    if owner.lower().replace(" ", "") != "vroidstudio":
        return False
    bounds = entry.get("kCGWindowBounds") or {}
    w = float(bounds.get("Width") or 0)
    h = float(bounds.get("Height") or 0)
    if w < 200 or h < 200:
        return False
    layer = int(entry.get("kCGWindowLayer") or 0)
    if layer != 0:
        return False
    # Prefer the titled editor window over unnamed Unity surfaces.
    if title and not title.lower().startswith("vroid studio"):
        return False
    return True


def _mk(entry: dict, focused: bool) -> Window:
    bounds = entry.get("kCGWindowBounds") or {}
    wid = int(entry.get("kCGWindowNumber") or 0)
    return Window(
        address=str(wid),
        cls=BUNDLE_ID,
        title=str(entry.get("kCGWindowName") or APP_NAME),
        x=int(bounds.get("X") or 0),
        y=int(bounds.get("Y") or 0),
        w=int(bounds.get("Width") or 0),
        h=int(bounds.get("Height") or 0),
        workspace=WORKSPACE,
        focused=focused,
        fullscreen=False,
        pid=int(entry.get("kCGWindowOwnerPID") or 0),
    )


def find_window() -> Window | None:
    """Return the VRoid Studio editor window, or None. Never matches anything else."""
    focused = is_vroid_focused()
    named = None
    fallback = None
    for entry in _window_entries(on_screen_only=True):
        if not _is_vroid_window(entry):
            continue
        title = str(entry.get("kCGWindowName") or "")
        win = _mk(entry, focused)
        if title.lower().startswith("vroid studio"):
            named = win
            break
        fallback = fallback or win
    return named or fallback


def is_vroid_focused() -> bool:
    """True when VRoid Studio is the frontmost application.

    NSRunningApplication.isActive() is unreliable for this Unity build when
    a CLI host immediately becomes key again; also check the workspace
    frontmost app and the AXFrontmost flag.
    """
    app = _running_app()
    if app is None:
        return False
    if bool(app.isActive()):
        return True
    try:
        from AppKit import NSWorkspace
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front is not None:
            bid = str(front.bundleIdentifier() or "")
            name = str(front.localizedName() or "")
            if bid == BUNDLE_ID or name.lower() == APP_NAME.lower():
                return True
    except Exception:
        pass
    try:
        from ApplicationServices import (
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
            kAXFrontmostAttribute,
        )
        el = AXUIElementCreateApplication(int(app.processIdentifier()))
        err, val = AXUIElementCopyAttributeValue(el, kAXFrontmostAttribute, None)
        if err == 0 and val:
            return True
    except Exception:
        pass
    return False


def assert_vroid_focused() -> None:
    """Refuse to act unless a VRoid window exists; activate it if needed.

    A non-bundled CLI host (MCP client, uv, Terminal) often becomes
    frontmost again before the next statement, so `isActive()` is not a
    reliable gate. Events are posted to VRoid's pid (see macos.input).
    """
    win = find_window()
    if win is None:
        raise RuntimeError(
            "refusing to act: VRoid Studio is not running "
            "(no Quartz window owned by net.pixiv.vroid.macosx)"
        )
    if not is_vroid_focused():
        focus(win)


def terminate() -> None:
    """Quit a running VRoid Studio. Unsaved work is lost."""
    app = _running_app()
    if app is not None:
        app.terminate()
        time.sleep(1.0)
    subprocess.run(["pkill", "-f", "VRoid Studio"], capture_output=True)


def launch() -> None:
    from AppKit import NSWorkspace
    for path in _APP_PATHS:
        ok = NSWorkspace.sharedWorkspace().launchApplication_(path)
        if ok:
            return
    subprocess.Popen(
        ["open", "-a", APP_NAME],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def wait_for_window(timeout: float = 180.0, poll: float = 2.0) -> Window:
    deadline = time.time() + timeout
    while time.time() < deadline:
        w = find_window()
        if w and w.w > 200 and w.h > 200:
            return w
        time.sleep(poll)
    raise TimeoutError(f"VRoid Studio window did not appear within {timeout}s")


def launch_and_wait(timeout: float = 240.0) -> Window:
    w = find_window()
    if w:
        return w
    launch()
    return wait_for_window(timeout)


def hyprctl_json(*args: str):
    raise NotImplementedError("hyprctl is Hyprland-only")


def active_workspace() -> int:
    return WORKSPACE


def park(win: Window, workspace: int = WORKSPACE) -> None:
    """No-op on macOS (no Hyprland workspace)."""
    return None


def enter(workspace: int = WORKSPACE) -> int:
    """Activate VRoid. Returns the dummy previous workspace id."""
    prev = active_workspace()
    focus()
    return prev


def leave(prev: int) -> None:
    """No-op: VRoid stays in the foreground until the human switches away."""
    return None


def dismiss_screensaver() -> bool:
    return False


def _ax_raise(pid: int) -> None:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        AXUIElementPerformAction,
        kAXRaiseAction,
        kAXWindowsAttribute,
    )
    app_el = AXUIElementCreateApplication(pid)
    err, windows = AXUIElementCopyAttributeValue(app_el, kAXWindowsAttribute, None)
    if err != 0 or not windows:
        return
    AXUIElementPerformAction(windows[0], kAXRaiseAction)


def focus(win: Window | None = None) -> Window:
    win = win or find_window()
    if win is None:
        raise RuntimeError("VRoid Studio window not found")
    app = _running_app()
    if app is not None:
        # NSApplicationActivateAllWindows | NSApplicationActivateIgnoringOtherApps
        app.activateWithOptions_(1 | 2)
    # AppleScript activate is more reliable from a non-bundled CLI host.
    subprocess.run(
        ["osascript", "-e", f'tell application "{APP_NAME}" to activate'],
        capture_output=True, text=True,
    )
    if win.pid:
        try:
            _ax_raise(win.pid)
        except Exception:
            pass
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if is_vroid_focused():
            break
        time.sleep(0.05)
    return find_window() or win


def fullscreen(win: Window | None = None) -> Window:
    """Focus only — do not toggle macOS fullscreen (geometry is already stable)."""
    return focus(win)


def prepare(timeout: float = 240.0) -> tuple[Window, int]:
    """Launch if needed and focus. Returns (window, previous_workspace)."""
    win = launch_and_wait(timeout)
    prev = enter()
    win = focus(win)
    assert_vroid_focused()
    return win, prev
