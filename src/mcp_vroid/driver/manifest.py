"""Declarative parameter manifests on top of inventory + set_param.

Schema (capability) is labels/control types. A manifest instance carries
values for one character and must not be treated as VRoid defaults.

export: read-only inventory → manifest
plan:   navigate scope, compare current UI to a manifest, no mutations
apply:  resolve every label first; abort before any set_param if any miss
"""
from __future__ import annotations

from typing import Any

from . import actions as A
from . import inventory as INV
from .locate import _norm
from .scope import control_set_of, resolve_in_catalog


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
    cs = control_set_of(inv)
    return {
        "schema_version": 1,
        "vroid_version": inv.get("vroid_version") or "2.14.0",
        "section": inv["section"],
        "control_set": cs,
        "subsection": cs,
        "parameters": params,
    }


def export_params(section: str, control_set: str | None = None) -> dict[str, Any]:
    """Read current slider values in `section` without changing them."""
    inv = INV.inventory_section(section, control_set=control_set)
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
                current: dict[str, Any] | None = None,
                catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compare current UI to `manifest`. Makes no changes.

    Navigates to section + control_set (unless `current` is supplied).
    Rejects unresolved, wrong-scope, or ambiguous labels before returning.
    """
    section = manifest["section"]
    cs = control_set_of(manifest, section)
    wanted = manifest.get("parameters") or {}
    if current is None:
        current = INV.inventory_section(section, control_set=cs)
    index = _index_current(current)
    changes = []
    unresolved = []
    for label, target in wanted.items():
        cat = resolve_in_catalog(section, cs, label, catalog=catalog)
        if cat.get("reason") == "wrong_scope":
            unresolved.append({
                "label": label, "reason": "wrong_scope",
                "section": section, "control_set": cs,
                "expected": cat.get("expected"),
            })
            continue
        if cat.get("reason") == "ambiguous":
            unresolved.append({"label": label, "reason": "ambiguous",
                               "section": section, "control_set": cs})
            continue

        row = index.get(label) or index.get(_norm(label))
        if row is None:
            unresolved.append({"label": label, "reason": "not_found",
                               "section": section, "control_set": cs})
            continue
        if not row.get("numeric_entry"):
            unresolved.append({"label": label, "reason": "not_numeric",
                               "observed": row.get("label"),
                               "section": section, "control_set": cs})
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
            "section": section,
            "control_set": cs,
        })
    return {
        "section": section,
        "control_set": cs,
        "ok": not unresolved,
        "unresolved": unresolved,
        "changes": changes,
        "would_mutate": bool(changes) and not unresolved,
    }


def plan_many(manifests: list[dict[str, Any]],
              currents: list[dict[str, Any] | None] | None = None,
              catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Plan every manifest before any mutation. Fail closed on the first miss."""
    plans = []
    unresolved = []
    for i, man in enumerate(manifests):
        cur = None
        if currents is not None and i < len(currents):
            cur = currents[i]
        plan = plan_params(man, current=cur, catalog=catalog)
        plans.append(plan)
        unresolved.extend(plan.get("unresolved") or [])
    ok = not unresolved
    return {
        "ok": ok,
        "plans": plans,
        "unresolved": unresolved,
        "would_mutate": ok and any(p.get("would_mutate") for p in plans),
    }


def apply_params(manifest: dict[str, Any],
                 plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply a manifest through set_param. Abort before mutation if unresolved."""
    plan = plan or plan_params(manifest)
    if not plan["ok"]:
        return {
            "applied": False,
            "aborted": True,
            "reason": "unresolved_labels",
            "plan": plan,
        }
    A.navigate_scope(plan["section"], plan.get("control_set"))
    originals = {c["label"]: c["old"] for c in plan["changes"]}
    verified = []
    failures = []
    try:
        for change in plan["changes"]:
            label = change["label"]
            target = change["requested"]
            shot = A.set_param(label, target)
            after = A.read_param(label, shot)
            try:
                after_f = float(str(after).replace("cm", "").strip())
            except ValueError:
                after_f = None
            ok = after_f is not None and abs(after_f - float(target)) < 0.02
            rec = {"label": label, "requested": target, "after": after_f, "ok": ok}
            verified.append(rec)
            if not ok:
                failures.append(rec)
    except Exception as exc:
        return {
            "applied": bool(verified),
            "aborted": True,
            "reason": str(exc),
            "originals": originals,
            "verified": verified,
            "failures": failures,
            "ok": False,
        }
    return {
        "applied": True,
        "aborted": False,
        "originals": originals,
        "verified": verified,
        "failures": failures,
        "ok": not failures,
    }
