"""Declarative parameter manifests on top of inventory + set_param.

Schema (capability) is labels/control types. A manifest instance carries
values for one character and must not be treated as VRoid defaults.

export: read-only inventory → manifest
plan:   compare current UI to a manifest, no mutations
apply:  resolve every label first; abort before any set_param if any miss
"""
from __future__ import annotations

from typing import Any

from . import actions as A
from . import inventory as INV
from .locate import _norm


def manifest_from_inventory(inv: dict[str, Any]) -> dict[str, Any]:
    params = {}
    for row in inv.get("parameters") or []:
        if not row.get("numeric_entry"):
            continue
        val = row.get("value")
        if val is None:
            continue
        try:
            params[row["label"]] = float(str(val).replace("cm", "").strip())
        except ValueError:
            continue
    return {
        "schema_version": 1,
        "vroid_version": inv.get("vroid_version") or "2.14.0",
        "section": inv["section"],
        "parameters": params,
    }


def export_params(section: str) -> dict[str, Any]:
    """Read current slider values in `section` without changing them."""
    inv = INV.inventory_section(section)
    man = manifest_from_inventory(inv)
    man["inventory"] = {
        "stop_reason": inv.get("stop_reason"),
        "pages_scanned": inv.get("pages_scanned"),
        "count": inv.get("count"),
    }
    return man


def _index_current(inv: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for row in inv.get("parameters") or []:
        out[_norm(row["label"])] = row
        out[row["label"]] = row
    return out


def plan_params(manifest: dict[str, Any],
                current: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare current UI to `manifest`. Makes no changes.

    Rejects unresolved or ambiguous labels before returning a plan.
    """
    section = manifest["section"]
    wanted = manifest.get("parameters") or {}
    inv = current or INV.inventory_section(section)
    index = _index_current(inv)
    changes = []
    unresolved = []
    for label, target in wanted.items():
        row = index.get(label) or index.get(_norm(label))
        if row is None:
            unresolved.append({"label": label, "reason": "not_found"})
            continue
        if not row.get("numeric_entry"):
            unresolved.append({"label": label, "reason": "not_numeric",
                               "observed": row.get("label")})
            continue
        old = row.get("value")
        try:
            old_f = float(str(old).replace("cm", "").strip()) if old is not None else None
        except ValueError:
            old_f = None
        new_f = float(target)
        changes.append({
            "label": row["label"],
            "requested_as": label,
            "old": old_f,
            "requested": new_f,
        })
    return {
        "section": section,
        "ok": not unresolved,
        "unresolved": unresolved,
        "changes": changes,
        "would_mutate": bool(changes) and not unresolved,
    }


def apply_params(manifest: dict[str, Any]) -> dict[str, Any]:
    """Apply a manifest through set_param. Abort before mutation if unresolved."""
    plan = plan_params(manifest)
    if not plan["ok"]:
        return {
            "applied": False,
            "aborted": True,
            "reason": "unresolved_labels",
            "plan": plan,
        }
    originals = {c["label"]: c["old"] for c in plan["changes"]}
    verified = []
    failures = []
    for change in plan["changes"]:
        label = change["label"]
        target = change["requested"]
        A.set_param(label, target)
        after = A.read_param(label)
        try:
            after_f = float(str(after).replace("cm", "").strip())
        except ValueError:
            after_f = None
        ok = after_f is not None and abs(after_f - float(target)) < 0.02
        rec = {"label": label, "requested": target, "after": after_f, "ok": ok}
        verified.append(rec)
        if not ok:
            failures.append(rec)
    return {
        "applied": True,
        "aborted": False,
        "originals": originals,
        "verified": verified,
        "failures": failures,
        "ok": not failures,
    }
