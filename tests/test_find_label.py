"""_find_label must keep 1-letter tokens so Eye Size X ≠ Eye Size Y."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image

from mcp_vroid.driver.locate import Match, _norm
from mcp_vroid.driver.types import Shot
from mcp_vroid.driver import actions as A


def _shot(w=1410, h=2295) -> Shot:
    return Shot(Image.new("RGB", (w, h), "white"), Path("/tmp/t.png"), 0, 0, 1.0)


def _m(text: str, x: int, y: int) -> Match:
    return Match(text, 90.0, x, y, max(8, 8 * len(text)), 12)


def test_norm_strips_punctuation():
    assert _norm("Eye Size X") == "eyesizex"
    assert _norm("Head Tip (Y)") == "headtipy"


def test_find_label_distinguishes_x_and_y():
    """Regression: skipping tokens shorter than 3 chars collapsed Eye Size X/Y."""
    rows = {
        "Eye": [_m("Eye", 1130, 127), _m("Eye", 1130, 197)],
        "Size": [_m("Size", 1154, 126), _m("Size", 1154, 196)],
        "X": [_m("X", 1188, 127)],
        "Y": [_m("Y", 1188, 197)],
        "Eye Size X": [],
        "Eye Size Y": [],
    }

    def fake_find_text(s, needle, *, exact=False, all_matches=False, region=None, **kw):
        hits = list(rows.get(needle, []))
        if all_matches:
            return hits
        return hits[0] if hits else None

    with patch("mcp_vroid.driver.actions.L.find_text", side_effect=fake_find_text):
        x = A._find_label(_shot(), "Eye Size X")
        y = A._find_label(_shot(), "Eye Size Y")
    assert x is not None and y is not None
    assert x.center[1] == 133  # 127 + 12//2
    assert y.center[1] == 203
    assert x.center[1] != y.center[1]


def test_find_label_head_tip_y_keeps_axis_token():
    rows = {
        "Head": [_m("Head", 1130, 400), _m("Head", 1130, 500)],
        "Tip": [_m("Tip", 1170, 400)],
        "Y": [_m("Y", 1210, 400)],
        "Width": [_m("Width", 1170, 500)],
        "Head Tip (Y)": [],
        "Head Width": [],
    }

    def fake_find_text(s, needle, *, exact=False, all_matches=False, region=None, **kw):
        hits = list(rows.get(needle, []))
        if all_matches:
            return hits
        return hits[0] if hits else None

    with patch("mcp_vroid.driver.actions.L.find_text", side_effect=fake_find_text):
        tip = A._find_label(_shot(), "Head Tip (Y)")
        width = A._find_label(_shot(), "Head Width")
    assert tip is not None and width is not None
    assert abs(tip.center[1] - 406) <= 2
    assert abs(width.center[1] - 506) <= 2
