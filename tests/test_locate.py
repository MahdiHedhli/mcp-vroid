"""OCR helpers that do not need tesseract at import time."""
from __future__ import annotations

from mcp_vroid.driver.locate import Match, _norm


def test_match_center():
    m = Match("Eye", 90, 100, 40, 20, 10)
    assert m.center == (110, 45)


def test_norm_is_alnum_lower():
    assert _norm("Show Adam's Apple") == "showadamsapple"
    assert _norm("Chest Position (Y)") == "chestpositiony"
