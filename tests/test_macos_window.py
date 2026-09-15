"""macOS window matching does not require a live VRoid process."""
from __future__ import annotations

from mcp_vroid.driver.macos.window import _is_vroid_window, _mk, BUNDLE_ID


def _entry(**kw):
    base = {
        "kCGWindowOwnerName": "VRoid Studio",
        "kCGWindowName": "VRoid Studio 2.14.0 - Lyra.vroid*",
        "kCGWindowBounds": {"X": -1411, "Y": -175, "Width": 1410, "Height": 2295},
        "kCGWindowLayer": 0,
        "kCGWindowNumber": 18184,
        "kCGWindowOwnerPID": 84030,
    }
    base.update(kw)
    return base


def test_accepts_titled_editor_window():
    assert _is_vroid_window(_entry()) is True


def test_rejects_safari_or_wrong_owner():
    assert _is_vroid_window(_entry(**{"kCGWindowOwnerName": "Safari"})) is False


def test_rejects_tiny_or_menu_surfaces():
    assert _is_vroid_window(_entry(
        **{"kCGWindowBounds": {"X": 0, "Y": 0, "Width": 500, "Height": 30},
           "kCGWindowName": ""},
    )) is False
    assert _is_vroid_window(_entry(**{"kCGWindowLayer": 3})) is False


def test_mk_copies_quartz_geometry():
    win = _mk(_entry(), focused=True)
    assert win.address == "18184"
    assert win.cls == BUNDLE_ID
    assert win.pid == 84030
    assert win.geometry == (-1411, -175, 1410, 2295)
    assert win.focused is True
    assert win.to_layout(10, 20) == (-1401, -155)
