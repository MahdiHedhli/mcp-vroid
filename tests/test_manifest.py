"""plan/apply abort rules — no live VRoid."""
from __future__ import annotations

from unittest.mock import patch

from mcp_vroid.driver.manifest import (
    apply_params, manifest_from_inventory, plan_many, plan_params,
)


def _inv():
    return {
        "schema_version": 1,
        "vroid_version": "2.14.0",
        "section": "Body",
        "control_set": "Whole Body",
        "subsection": "Whole Body",
        "parameters": [
            {"label": "Fem Height", "value": "-0.132", "y": 80,
             "control": "slider", "numeric_entry": True},
            {"label": "Head Size", "value": "-0.167", "y": 120,
             "control": "slider", "numeric_entry": True},
            {"label": "Chest Size", "value": "0.500", "y": 200,
             "control": "slider", "numeric_entry": True},
        ],
    }


def _face_inv():
    return {
        "schema_version": 1,
        "vroid_version": "2.14.0",
        "section": "Face",
        "control_set": "Face Sets",
        "parameters": [
            {"label": "Eye Size X", "value": "0.850", "y": 80,
             "control": "slider", "numeric_entry": True},
            {"label": "Sunken Cheeks", "value": "0.313", "y": 400,
             "control": "slider", "numeric_entry": True},
            {"label": "Chin Length", "value": "0.282", "y": 440,
             "control": "slider", "numeric_entry": True},
            {"label": "Nose Width", "value": "0.167", "y": 200,
             "control": "slider", "numeric_entry": True},
        ],
    }


def test_manifest_from_inventory_skips_non_numeric():
    inv = _inv()
    inv["parameters"].append({
        "label": "Show Height Panel", "value": None, "y": 40,
        "control": "checkbox", "numeric_entry": False,
    })
    man = manifest_from_inventory(inv)
    assert man["section"] == "Body"
    assert man["parameters"]["Fem Height"] == -0.132
    assert "Show Height Panel" not in man["parameters"]


def test_plan_reports_old_to_requested():
    man = {"schema_version": 1, "vroid_version": "2.14.0", "section": "Body",
           "parameters": {"Fem Height": -0.2, "Head Size": -0.167}}
    plan = plan_params(man, current=_inv())
    assert plan["ok"] is True
    by = {c["label"]: c for c in plan["changes"]}
    assert by["Fem Height"]["old"] == -0.132
    assert by["Fem Height"]["requested"] == -0.2
    assert by["Head Size"]["old"] == -0.167


def test_plan_rejects_unknown_label_before_mutation():
    man = {"section": "Body", "parameters": {"Not A Param": 0.1}}
    plan = plan_params(man, current=_inv())
    assert plan["ok"] is False
    assert plan["would_mutate"] is False
    assert plan["unresolved"][0]["reason"] == "not_found"


def test_mixed_face_body_resolves_before_writes():
    face = {"section": "Face", "control_set": "Face Sets",
            "parameters": {"Sunken Cheeks": 0.220, "Chin Length": 0.400,
                           "Eye Size X": 0.850}}
    body = {"section": "Body", "control_set": "Whole Body",
            "parameters": {"Chest Size": 0.720, "Fem Height": 0.420}}
    bundled = plan_many([face, body], currents=[_face_inv(), _inv()])
    assert bundled["ok"] is True
    assert bundled["would_mutate"] is True
    labels = [c["label"] for p in bundled["plans"] for c in p["changes"]]
    assert "Sunken Cheeks" in labels and "Chest Size" in labels
    assert all(c.get("control_set") for p in bundled["plans"] for c in p["changes"])


def test_missing_parameter_zero_writes():
    face = {"section": "Face", "control_set": "Face Sets",
            "parameters": {"Sunken Cheeks": 0.220, "Not A Face Param": 0.1}}
    body = {"section": "Body", "control_set": "Whole Body",
            "parameters": {"Chest Size": 0.720}}
    bundled = plan_many([face, body], currents=[_face_inv(), _inv()])
    assert bundled["ok"] is False
    assert bundled["would_mutate"] is False
    with patch("mcp_vroid.driver.manifest.A.set_param") as sp, \
            patch("mcp_vroid.driver.manifest.A.navigate_scope"):
        out = apply_params(face, plan=bundled["plans"][0])
    assert out["aborted"] is True
    assert out["applied"] is False
    sp.assert_not_called()


def test_wrong_navigation_scope_zero_writes():
    man = {"section": "Body", "control_set": "Whole Body",
           "parameters": {"Sunken Cheeks": 0.220}}
    plan = plan_params(man, current=_inv())
    assert plan["ok"] is False
    assert plan["would_mutate"] is False
    assert plan["unresolved"][0]["reason"] == "wrong_scope"
    with patch("mcp_vroid.driver.manifest.A.set_param") as sp, \
            patch("mcp_vroid.driver.manifest.A.navigate_scope"):
        out = apply_params(man, plan=plan)
    assert out["aborted"] is True
    sp.assert_not_called()


def test_scoped_duplicate_label_is_not_ambiguous():
    catalog = [
        {"section": "Face", "control_set": "Face Sets", "label": "Width",
         "numeric_entry": True, "control": "slider"},
        {"section": "Body", "control_set": "Whole Body", "label": "Width",
         "numeric_entry": True, "control": "slider"},
    ]
    face_inv = {"section": "Face", "control_set": "Face Sets", "parameters": [
        {"label": "Width", "value": "0.1", "numeric_entry": True, "control": "slider"},
    ]}
    body_inv = {"section": "Body", "control_set": "Whole Body", "parameters": [
        {"label": "Width", "value": "0.4", "numeric_entry": True, "control": "slider"},
    ]}
    fp = plan_params({"section": "Face", "control_set": "Face Sets",
                      "parameters": {"Width": 0.2}},
                     current=face_inv, catalog=catalog)
    bp = plan_params({"section": "Body", "control_set": "Whole Body",
                      "parameters": {"Width": 0.5}},
                     current=body_inv, catalog=catalog)
    assert fp["ok"] and bp["ok"]
    assert fp["changes"][0]["old"] == 0.1
    assert bp["changes"][0]["old"] == 0.4


def test_manifest_from_inventory_keeps_control_set():
    man = manifest_from_inventory(_face_inv())
    assert man["control_set"] == "Face Sets"
    assert "Sunken Cheeks" in man["parameters"]
