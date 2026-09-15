"""plan/apply abort rules — no live VRoid."""
from __future__ import annotations

from mcp_vroid.driver.manifest import manifest_from_inventory, plan_params


def _inv():
    return {
        "schema_version": 1,
        "vroid_version": "2.14.0",
        "section": "Body",
        "parameters": [
            {"label": "Fem Height", "value": "-0.132", "y": 80,
             "control": "slider", "numeric_entry": True},
            {"label": "Head Size", "value": "-0.167", "y": 120,
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
