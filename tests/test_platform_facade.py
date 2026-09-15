"""Linux/Wayland remains the default backend except on Darwin."""
from __future__ import annotations

import sys

from mcp_vroid.driver import capture as C
from mcp_vroid.driver import window as W
from mcp_vroid.driver.wayland import capture as wayland_capture
from mcp_vroid.driver.wayland import input as wayland_input
from mcp_vroid.driver.wayland import window as wayland_window


def test_wayland_backend_keeps_hyprland_workspace():
    assert wayland_window.WORKSPACE == 9
    assert wayland_window.STEAM_APPID == "1486350"
    assert hasattr(wayland_window, "find_window")
    assert hasattr(wayland_window, "terminate")
    assert hasattr(wayland_window, "hyprctl_json")
    assert hasattr(wayland_window, "prepare")


def test_wayland_capture_still_exports_grim_api():
    assert hasattr(wayland_capture, "output_scale")
    assert hasattr(wayland_capture, "grab_window")
    assert hasattr(wayland_capture, "grab_region")
    assert hasattr(wayland_capture, "grab_screen")


def test_wayland_input_still_exports_pointer_api():
    assert callable(wayland_input.click)
    assert callable(wayland_input.drag)
    assert callable(wayland_input.scroll)
    assert callable(wayland_input.type_text)
    assert callable(wayland_input.clear_field)
    assert callable(wayland_input.hotkey)


def test_facade_selects_macos_only_on_darwin():
    if sys.platform == "darwin":
        assert W.WORKSPACE == 0
        assert W.BUNDLE_ID == "net.pixiv.vroid.macosx"
    else:
        assert W.WORKSPACE == 9
        assert W is not wayland_window  # facade module, not the backend module
        # Public names come from the Wayland backend.
        assert W.find_window is wayland_window.find_window
        assert C.grab_window is wayland_capture.grab_window


def test_shot_reexported_from_capture_facade():
    from mcp_vroid.driver.types import Shot as ShotT
    assert C.Shot is ShotT
