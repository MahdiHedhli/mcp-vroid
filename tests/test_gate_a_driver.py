"""Gate A driver repairs: precision compare, pre-mutation rejections,
duplicate-aware inventory, ambiguity-aware locate, bounded observation.

No live VRoid. Desktop I/O (screenshots, OCR, input) is patched at the
`actions` boundary; the plan/apply/merge logic under test is production code.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from mcp_vroid.driver import actions as A
from mcp_vroid.driver import manifest as M
from mcp_vroid.driver.inventory import ObservedRow, merge_pages
from mcp_vroid.driver.locate import Match
from mcp_vroid.driver.types import Shot


def _shot(w=1410, h=2295, name="t.png") -> Shot:
    return Shot(Image.new("RGB", (w, h), "white"), Path("/tmp") / name, 0, 0, 1.0)


def _m(text: str, x: int, y: int) -> Match:
    return Match(text, 90.0, x, y, max(8, 8 * len(text)), 12)


# --- precision -------------------------------------------------------------

def test_values_match_is_decimal_aware_at_three_places():
    assert M.values_match(0.12, 0.120)
    assert M.values_match("0.120", 0.12)
    assert M.values_match(-0.399, -0.399)
    # A blanket 0.02 tolerance accepted these; the UI shows the difference.
    assert not M.values_match(0.119, 0.120)
    assert not M.values_match(0.13, 0.12)
    assert not M.values_match(None, 0.12)
    assert not M.values_match(float("nan"), 0.12)
    assert not M.values_match(float("inf"), float("inf"))


def test_parse_value_handles_cm_and_garbage():
    assert M.parse_value("0.720") == 0.72
    assert M.parse_value("136.8 cm") == 136.8
    assert M.parse_value("") is None
    assert M.parse_value("(Y) -0.573") is None
    assert M.parse_value("nan") is None


def test_parse_chip_handles_cm_and_hallucinated_units():
    # lyra-sculpt-0021 (candidate-006): OCR returned "0.360 nm" / "0.300 nm"
    # for a plain, unitless Face slider -- no unit text was actually on
    # screen. _parse_chip must not whitelist units one at a time; it takes
    # the leading numeric token and ignores any trailing suffix.
    assert A._parse_chip("0.360 nm") == 0.36
    assert A._parse_chip("0.300 nm") == 0.3
    assert A._parse_chip("1.250cm") == 1.25  # existing Body case, no regression
    assert A._parse_chip("0.260") == 0.26  # existing plain case, no regression
    assert A._parse_chip("-0.573") == -0.573
    assert A._parse_chip("") is None
    assert A._parse_chip(None) is None
    assert A._parse_chip("nm") is None
    assert A._parse_chip("(Y) -0.573") is None


# --- plan rejections -------------------------------------------------------

def _inv(rows):
    return {"section": "Body", "control_set": "Whole Body", "parameters": rows}


def _row(label, value, **kw):
    base = {"label": label, "value": value, "y": 100, "control": "slider",
            "numeric_entry": value is not None, "page": 0, "shot": "s.png"}
    base.update(kw)
    return base


def test_plan_rejects_non_finite_before_mutation():
    plan = M.plan_params({"section": "Body", "parameters": {"Chest Size": float("nan")}},
                         current=_inv([_row("Chest Size", "0.500")]))
    assert plan["ok"] is False
    assert plan["unresolved"][0]["reason"] == "non_finite"
    assert plan["would_mutate"] is False


def test_plan_rejects_unreadable_prior_before_mutation():
    plan = M.plan_params({"section": "Body", "parameters": {"Chest Size": 0.7}},
                         current=_inv([_row("Chest Size", None, control="unknown")]))
    assert plan["unresolved"][0]["reason"] in ("prior_unreadable", "not_numeric")
    assert plan["would_mutate"] is False


def test_plan_rejects_value_conflict_prior():
    plan = M.plan_params({"section": "Body", "parameters": {"Chest Size": 0.7}},
                         current=_inv([_row("Chest Size", "0.500", value_conflict=True)]))
    assert plan["unresolved"][0]["reason"] == "prior_unreadable"


def test_plan_rejects_duplicate_caption_as_ambiguous():
    catalog = [{"section": "Face", "control_set": "Face Sets", "label": "Nose Size",
                "numeric_entry": True, "control": "slider"}]
    inv = {"section": "Face", "control_set": "Face Sets", "parameters": [
        _row("Nose Size", "0.000", y=1951, duplicate=True),
        _row("Nose Size", "1.000", y=2091, duplicate=True),
    ]}
    plan = M.plan_params({"section": "Face", "control_set": "Face Sets",
                          "parameters": {"Nose Size": 0.2}}, current=inv, catalog=catalog)
    assert plan["ok"] is False
    u = plan["unresolved"][0]
    assert u["reason"] == "ambiguous_duplicate"
    assert [o["value"] for o in u["observed"]] == ["0.000", "1.000"]


# --- inventory merge -------------------------------------------------------

def _orow(label, value, page, y, prev=None, nxt=None):
    return ObservedRow(label, value, y, "slider", value is not None, page=page,
                       shot=f"p{page}.png", prev_label=prev, next_label=nxt)


def test_same_page_duplicate_captions_are_distinct_controls():
    p0 = [
        _orow("Nose Size", "0.000", 0, 1951, "Eyebrows Length", "Nose Width"),
        _orow("Nose Width", "0.167", 0, 2021, "Nose Size", "Nose Tip Position (Y)"),
        _orow("Nose Tip Position (Y)", "0.264", 0, 2091, "Nose Width", "Nose Size"),
        _orow("Nose Size", "1.000", 0, 2161, "Nose Tip Position (Y)", "Nose Bridge Prominence"),
    ]
    merged = merge_pages([p0])
    sizes = [r for r in merged if r.key() == "nosesize"]
    assert len(sizes) == 2
    assert all(r.duplicate for r in sizes)
    assert [r.value for r in sizes] == ["0.000", "1.000"]
    assert not any(r.duplicate for r in merged if r.key() != "nosesize")


def test_overlapping_page_reread_is_merged_not_duplicated():
    p0 = [_orow("Head Size", "-0.167", 0, 2100, "Body Size", "Head Width")]
    p1 = [_orow("Head Size", "-0.167", 1, 300, "Body Size", "Head Width"),
          _orow("Head Width", "-0.399", 1, 370, "Head Size", "Head Tip (Y)")]
    merged = merge_pages([p0, p1])
    assert [r.label for r in merged] == ["Head Size", "Head Width"]
    assert merged[0].duplicate is False
    assert merged[0].seen_on_pages == [0, 1]


def test_overlapping_reread_with_different_value_is_a_conflict_not_a_silent_pick():
    p0 = [_orow("Chest Size", "0.500", 0, 2100, "Chest Prominence", None)]
    p1 = [_orow("Chest Size", "0.508", 1, 300, "Chest Prominence", "Chest Position (Y)")]
    merged = merge_pages([p0, p1])
    assert len(merged) == 1
    assert merged[0].value_conflict is True
    assert merged[0].numeric_entry is False   # prior unreadable → plan blocks it


def test_different_context_same_caption_across_pages_is_duplicate():
    p0 = [_orow("Nose Size", "0.000", 0, 2000, "Eyebrows Length", "Nose Width")]
    p1 = [_orow("Nose Size", "1.000", 1, 400, "Nose Tip Position (Y)", "Nose Bridge Prominence")]
    merged = merge_pages([p0, p1])
    assert len(merged) == 2 and all(r.duplicate for r in merged)


def test_legacy_rows_without_provenance_still_merge_by_position():
    p1 = [ObservedRow("Head Size", "-0.167", 200, "slider", True)]
    p2 = [ObservedRow("Head Size", "-0.167", 40, "slider", True),
          ObservedRow("Eye Size Y", "-0.100", 100, "slider", True)]
    merged = merge_pages([p1, p2])
    assert [r.key() for r in merged] == ["headsize", "eyesizey"]


# --- locate / observe ------------------------------------------------------

def test_locate_param_refuses_ambiguous_target():
    s = _shot()
    two = [_m("Nose", 1130, 1951), _m("Nose", 1130, 2161)]
    sizes = [_m("Size", 1170, 1951), _m("Size", 1170, 2161)]

    def fake_find_text(img, needle, *, exact=False, all_matches=False, region=None, **kw):
        hits = {"Nose": two, "Size": sizes}.get(needle, [])
        return list(hits) if all_matches else (hits[0] if hits else None)

    with patch("mcp_vroid.driver.actions.find_param", return_value=(s, two[0])), \
            patch("mcp_vroid.driver.actions.L.find_text", side_effect=fake_find_text):
        with pytest.raises(A.AmbiguousTarget):
            A.locate_param("Nose Size")


def test_observe_param_reports_unreadable_without_typing():
    s = _shot()
    m = _m("Chest", 1130, 1151)
    with patch("mcp_vroid.driver.actions._find_label", return_value=m), \
            patch("mcp_vroid.driver.actions._ocr_value", return_value=""), \
            patch("mcp_vroid.driver.actions._type_value") as typed, \
            patch("mcp_vroid.driver.actions.find_param") as fp:
        obs = A.observe_param("Chest Size", s)
    assert obs["status"] == "unreadable" and obs["value"] is None
    typed.assert_not_called()
    fp.assert_not_called()


def test_observe_param_reports_not_visible_when_locate_disabled():
    s = _shot()
    with patch("mcp_vroid.driver.actions._find_label", return_value=None), \
            patch("mcp_vroid.driver.actions.find_param") as fp:
        obs = A.observe_param("Chest Size", s, locate=False)
    assert obs["status"] == "not_visible"
    fp.assert_not_called()


def test_observe_value_retries_only_unreadable_and_is_bounded():
    seq = [
        {"status": "unreadable", "raw": "", "value": None, "shot": "a", "row_y": 1},
        {"status": "unreadable", "raw": "", "value": None, "shot": "b", "row_y": 1},
        {"status": "unreadable", "raw": "", "value": None, "shot": "c", "row_y": 1},
        {"status": "readable", "raw": "0.720", "value": 0.72, "shot": "d", "row_y": 1},
    ]
    with patch("mcp_vroid.driver.manifest.A.observe_param", side_effect=seq) as op:
        out = M.observe_value("Chest Size", None, retries=2, settle=0)
    assert out["status"] == "unreadable"
    assert len(out["attempts"]) == 3          # 1 + 2 retries, never a 4th
    assert op.call_count == 3


def test_observe_value_stops_at_first_readable():
    seq = [
        {"status": "unreadable", "raw": "", "value": None, "shot": "a", "row_y": 1},
        {"status": "readable", "raw": "0.720", "value": 0.72, "shot": "b", "row_y": 1},
    ]
    with patch("mcp_vroid.driver.manifest.A.observe_param", side_effect=seq):
        out = M.observe_value("Chest Size", None, retries=2, settle=0)
    assert out["status"] == "readable" and out["value"] == 0.72
    assert len(out["attempts"]) == 2


# --- server-side apply_params stops on failure ----------------------------

def _plan_two():
    return {"section": "Body", "control_set": "Whole Body", "ok": True, "unresolved": [],
            "changes": [
                {"label": "Chest Size", "old": 0.5, "requested": 0.72},
                {"label": "Waist Width", "old": 0.517, "requested": 0.36},
            ]}


def test_apply_params_mismatch_stops_further_writes():
    dispatched = []
    obs = iter([{"status": "readable", "value": 0.7, "raw": "0.700", "shot": "x",
                 "attempts": [{}]}])
    with patch("mcp_vroid.driver.manifest.A.navigate_scope"), \
            patch("mcp_vroid.driver.manifest.A.locate_param", return_value=(_shot(), _m("Chest", 1, 1))), \
            patch("mcp_vroid.driver.manifest.A.dispatch_value",
                  side_effect=lambda s, m, v: dispatched.append(v)), \
            patch("mcp_vroid.driver.manifest.observe_value", side_effect=lambda *a, **k: next(obs)):
        out = M.apply_params({"section": "Body"}, plan=_plan_two())
    assert dispatched == [0.72]
    assert out["outcome"] == "mismatch" and out["aborted"] is True
    assert out["verified"][0]["outcome"] == "mismatch"


def test_apply_params_unreadable_after_budget_stops_and_is_uncertain():
    dispatched = []
    with patch("mcp_vroid.driver.manifest.A.navigate_scope"), \
            patch("mcp_vroid.driver.manifest.A.locate_param", return_value=(_shot(), _m("Chest", 1, 1))), \
            patch("mcp_vroid.driver.manifest.A.dispatch_value",
                  side_effect=lambda s, m, v: dispatched.append(v)), \
            patch("mcp_vroid.driver.manifest.observe_value",
                  return_value={"status": "unreadable", "value": None, "raw": "",
                                "shot": "x", "attempts": [{}, {}, {}]}):
        out = M.apply_params({"section": "Body"}, plan=_plan_two())
    assert dispatched == [0.72]
    assert out["outcome"] == "unreadable"
    assert out["verified"][0]["outcome"] == "uncertain"


def test_apply_params_noop_is_not_typed():
    plan = _plan_two()
    plan["changes"][0]["requested"] = 0.5
    obs = {"status": "readable", "value": 0.36, "raw": "0.360", "shot": "x", "attempts": [{}]}
    dispatched = []
    with patch("mcp_vroid.driver.manifest.A.navigate_scope"), \
            patch("mcp_vroid.driver.manifest.A.locate_param", return_value=(_shot(), _m("W", 1, 1))), \
            patch("mcp_vroid.driver.manifest.A.dispatch_value",
                  side_effect=lambda s, m, v: dispatched.append(v)), \
            patch("mcp_vroid.driver.manifest.observe_value", return_value=obs):
        out = M.apply_params({"section": "Body"}, plan=plan)
    assert dispatched == [0.36]
    assert out["ok"] is True
    assert out["verified"][0]["outcome"] == "verified_noop"
    assert out["verified"][1]["outcome"] == "verified_change"


# --- coverage claims -------------------------------------------------------

from mcp_vroid.driver.inventory import coverage_report  # noqa: E402
from mcp_vroid.driver.scope import load_catalog  # noqa: E402


def _body_rows(skip=()):
    rows = []
    for r in load_catalog():
        if r["section"] == "Body" and r["control_set"] == "Whole Body" and r["numeric_entry"]:
            if r["label"] in skip:
                continue
            rows.append(ObservedRow(r["label"], "0.000", 100 + 40 * len(rows), "slider", True,
                                    page=0, shot="p0.png"))
    return rows


def test_coverage_max_pages_is_never_verified_even_if_everything_was_seen():
    cov = coverage_report("Body", "Whole Body", _body_rows(), "max_pages", 24, 24)
    assert cov["termination"] == "max_pages"
    assert cov["verified"] is False
    assert cov["catalog"]["missing"] == []
    assert [e["kind"] for e in cov["end_evidence"]] == ["all_catalogued_labels_observed"]


def test_coverage_unchanged_frame_is_weak_evidence_and_needs_catalog_corroboration():
    cov = coverage_report("Body", "Whole Body", _body_rows(), "unchanged_panel", 3, 24)
    kinds = [e["kind"] for e in cov["end_evidence"]]
    assert kinds == ["frame_unchanged_after_wheel", "all_catalogued_labels_observed"]
    assert [e["strength"] for e in cov["end_evidence"]] == ["weak", "corroborating"]
    assert cov["verified"] is True
    assert cov["claim"].startswith("verified")


def test_coverage_missing_catalog_label_is_partial():
    cov = coverage_report("Body", "Whole Body", _body_rows(skip=("Chest Size",)),
                          "unchanged_panel", 3, 24)
    assert cov["verified"] is False
    assert cov["catalog"]["missing"] == ["Chest Size"]
    assert cov["claim"].startswith("partial")


def test_coverage_problematic_rows_block_the_verified_claim_but_are_kept():
    rows = _body_rows()
    rows[0].duplicate = True
    rows[1].value_conflict = True
    cov = coverage_report("Body", "Whole Body", rows, "panel_end_visible", 1, 24)
    assert cov["verified"] is False
    assert cov["problematic"]["duplicate"] == 1
    assert cov["problematic"]["value_conflict"] == 1
    assert cov["catalog"]["missing"] == []          # they were observed, just not clean


def test_export_params_carries_coverage_and_problem_lists():
    rows = _body_rows()
    rows[0].duplicate = True
    inv = __import__("mcp_vroid.driver.inventory", fromlist=["build_inventory"]).build_inventory(
        "Body", "Whole Body", "Whole Body", [rows], rows, "unchanged_panel", 24)
    with patch("mcp_vroid.driver.manifest.INV.inventory_section", return_value=inv):
        man = M.export_params("Body", "Whole Body")
    assert man["inventory"]["coverage"]["verified"] is False
    assert len(man["duplicates"]) == 1
    assert rows[0].label not in man["parameters"]     # duplicate never becomes a restore value


def test_overlap_reread_with_noisy_neighbour_caption_is_merged_not_duplicated():
    """Gate B pre-inventory: 'ar} Eyebrows Length' vs 'Eyebrows Length' is the
    same neighbour; Eyebrows Arch on pages 0 and 1 is one control."""
    p0 = [_orow("Eyebrows Arch", "0.100", 0, 1811, "Rotate Eyebrows (Y)", "ar} Eyebrows Length"),
          _orow("Nose Size", "0.000", 0, 1951, "ar} Eyebrows Length", "Nose Width"),
          _orow("Nose Size", "1.000", 0, 2161, "Nose Tip Position (Y)", "Nose Bridge Prominence")]
    p1 = [_orow("Eyebrows Arch", "0.100", 1, 1411, "Rotate Eyebrows (Y)", "Eyebrows Length"),
          _orow("Nose Size", "0.000", 1, 1551, "Eyebrows Length", "Nose Width")]
    merged = merge_pages([p0, p1])
    arch = [r for r in merged if r.key() == "eyebrowsarch"]
    assert len(arch) == 1 and arch[0].duplicate is False and arch[0].seen_on_pages == [0, 1]
    sizes = [r for r in merged if r.key() == "nosesize"]
    assert len(sizes) == 2 and all(r.duplicate for r in sizes)
    assert sizes[0].seen_on_pages == [0, 1] and sizes[1].seen_on_pages == [0]


def test_overlap_reread_where_both_neighbours_disagree_stays_duplicate():
    p0 = [_orow("Nose Size", "0.000", 0, 2000, "Eyebrows Length", "Nose Width")]
    p1 = [_orow("Nose Size", "0.000", 1, 400, "Nose Tip Position (Y)", "Nose Bridge Prominence")]
    merged = merge_pages([p0, p1])
    assert len(merged) == 2 and all(r.duplicate for r in merged)
