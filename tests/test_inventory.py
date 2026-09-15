"""Pure inventory parsing: no live VRoid, no value mutations."""
from __future__ import annotations

from mcp_vroid.driver.inventory import (
    ObservedRow, merge_pages, parse_panel, row_from_cluster,
)
from mcp_vroid.driver.locate import Match, _norm


def _m(text, x, y, w=None):
    return Match(text, 90, x, y, w or max(8, 7 * len(text)), 12)


def test_row_keeps_axis_token_and_value():
    cluster = [
        _m("Eye", 100, 130), _m("Size", 140, 130), _m("X", 180, 130),
        _m("0.850", 400, 130),
    ]
    row = row_from_cluster(cluster)
    assert row is not None
    assert row.label == "Eye Size X"
    assert row.value == "0.850"
    assert row.control == "slider"
    assert row.numeric_entry is True
    assert row.key() == "eyesizex"
    assert row.key() != _norm("Eye Size Y")


def test_row_height_readout_keeps_cm():
    cluster = [
        _m("Model's", 100, 40), _m("Height", 160, 40), _m(":", 210, 40),
        _m("136.8", 360, 40), _m("cm", 410, 40),
    ]
    row = row_from_cluster(cluster)
    assert row is not None
    assert "Height" in row.label
    assert row.value is not None and "136.8" in row.value
    assert row.control == "readout"
    assert row.numeric_entry is False


def test_merge_pages_dedupes_scroll_overlap_keeps_xyz():
    p1 = [
        ObservedRow("Fem Height", "-0.132", 80, "slider", True),
        ObservedRow("Head Size", "-0.167", 200, "slider", True),
        ObservedRow("Eye Size X", "0.850", 300, "slider", True),
    ]
    p2 = [
        ObservedRow("Head Size", "-0.167", 40, "slider", True),  # overlap
        ObservedRow("Eye Size Y", "-0.100", 100, "slider", True),
        ObservedRow("Neck Length", "0.000", 180, "slider", True),
    ]
    merged = merge_pages([p1, p2])
    keys = [r.key() for r in merged]
    assert keys == ["femheight", "headsize", "eyesizex", "eyesizey", "necklength"]
    assert [r.label for r in merged if r.key().startswith("eyesize")] == [
        "Eye Size X", "Eye Size Y",
    ]


def test_parse_panel_skips_parameters_heading():
    matches = [
        _m("Parameters", 100, 20),
        _m("Fem", 100, 80), _m("Height", 140, 80), _m("-0.132", 400, 80),
    ]
    rows = parse_panel(matches)
    assert [r.label for r in rows] == ["Fem Height"]


def test_edit_texture_is_not_a_value_chip():
    matches = [
        _m("Edit", 1226, 135), _m("Texture", 1252, 135),
        _m("Fem", 1131, 308), _m("Height", 1160, 307), _m("-0.132", 1350, 308),
    ]
    rows = parse_panel(matches, value_x_min=int(1410 * 0.90))
    labels = [r.label for r in rows]
    assert "Fem Height" in labels
    assert all(r.label != "Edit" for r in rows)


def test_spatial_split_keeps_value_on_the_right():
    matches = [
        _m("Fem", 1131, 308), _m("Height", 1160, 307), _m("-0.132", 1350, 308),
        _m("Chest", 1130, 1357), _m("Split", 1167, 1357), _m("0.417", 1354, 1358),
    ]
    rows = parse_panel(matches, value_x_min=1300)
    by = {r.label: r.value for r in rows}
    assert by["Fem Height"] == "-0.132"
    assert by["Chest Split"] == "0.417"


def test_merge_upgrades_missing_value():
    p1 = [ObservedRow("Fem Height", None, 80, "unknown", False)]
    p2 = [ObservedRow("Fem Height", "-0.132", 80, "slider", True)]
    merged = merge_pages([p1, p2])
    assert merged[0].value == "-0.132"
