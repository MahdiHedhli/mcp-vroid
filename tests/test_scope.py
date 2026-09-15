"""Navigation-scoped parameter addresses. No live VRoid."""
from __future__ import annotations

from mcp_vroid.driver.scope import (
    DEFAULT_CONTROL_SET, catalog_addresses, control_set_of, resolve_in_catalog,
)


def test_sunken_cheeks_is_face_face_sets():
    addrs = catalog_addresses("Sunken Cheeks")
    assert ("Face", "Face Sets") in addrs
    r = resolve_in_catalog("Face", "Face Sets", "Sunken Cheeks")
    assert r["ok"] is True
    assert r["section"] == "Face"
    assert r["control_set"] == "Face Sets"


def test_chin_length_is_face_face_sets():
    r = resolve_in_catalog("Face", "Face Sets", "Chin Length")
    assert r["ok"] is True


def test_eye_size_x_keeps_axis_and_scope():
    x = resolve_in_catalog("Face", "Face Sets", "Eye Size X")
    y = resolve_in_catalog("Face", "Face Sets", "Eye Size Y")
    assert x["ok"] and y["ok"]
    assert x["row"]["label"] != y["row"]["label"]
    assert catalog_addresses("Eye Size X") == [("Face", "Face Sets")]


def test_chest_size_and_fem_height_are_body_whole_body():
    for label in ("Chest Size", "Fem Height"):
        r = resolve_in_catalog("Body", "Whole Body", label)
        assert r["ok"] is True, label
        assert r["control_set"] == "Whole Body"
        assert catalog_addresses(label) == [("Body", "Whole Body")]


def test_wrong_scope_sunken_cheeks_on_body():
    r = resolve_in_catalog("Body", "Whole Body", "Sunken Cheeks")
    assert r["ok"] is False
    assert r["reason"] == "wrong_scope"
    assert r["expected"][0]["section"] == "Face"


def test_duplicate_labels_are_disambiguated_by_scope():
    catalog = [
        {"section": "Face", "control_set": "Face Sets", "label": "Width",
         "control": "slider", "numeric_entry": True},
        {"section": "Body", "control_set": "Whole Body", "label": "Width",
         "control": "slider", "numeric_entry": True},
    ]
    addrs = catalog_addresses("Width", catalog=catalog)
    assert len(addrs) == 2
    face = resolve_in_catalog("Face", "Face Sets", "Width", catalog=catalog)
    body = resolve_in_catalog("Body", "Whole Body", "Width", catalog=catalog)
    assert face["ok"] and body["ok"]
    assert face["section"] != body["section"]


def test_control_set_of_accepts_legacy_subsection():
    assert control_set_of({"section": "Face", "subsection": "Face Sets"}) == "Face Sets"
    assert control_set_of({"section": "Body"}) == DEFAULT_CONTROL_SET["Body"]
