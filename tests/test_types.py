"""Platform-independent geometry types."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from mcp_vroid.driver.types import Shot, Window


def test_window_geometry_and_to_layout():
    w = Window(
        address="0x1", cls="steam_app_1486350", title="VRoid Studio 2.14.0",
        x=10, y=20, w=2560, h=1440, workspace=9, focused=True,
    )
    assert w.geometry == (10, 20, 2560, 1440)
    assert w.to_layout(5, 7) == (15, 27)


def test_shot_scale_mapping():
    img = Image.new("RGB", (200, 100), "white")
    s = Shot(img, Path("/tmp/x.png"), ox=10, oy=20, scale=2.0)
    assert s.to_window(40, 10) == (20.0, 5.0)
    assert s.to_layout(40, 10) == (30.0, 25.0)
    c = s.crop((10, 0, 50, 20))
    assert c.ox == 15
    assert c.oy == 20
    assert c.scale == 2.0
    assert c.image.size == (40, 20)
