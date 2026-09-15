"""Declarative parameter manifests on top of inventory + set_param.

Schema (capability) is labels/control types. A manifest instance carries
values for one character and must not be treated as VRoid defaults.

export: read-only inventory → manifest
plan:   navigate scope, compare current UI to a manifest, no mutations
apply:  resolve every label first; abort before any set_param if any miss;
        stop candidate writes at the first mismatch or unreadable readback
"""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

from . import actions as A
from . import inventory as INV
from .locate import _norm
from .scope import control_set_of, resolve_in_catalog

# VRoid 2.14 numeric chips display three decimals and echo a typed value
# exactly ("0.120" -> 0.120). Compare at that precision, not with a blanket
# tolerance: 0.02 hid twenty display steps and did nothing for the failure
# that actually happens (a blank OCR).
UI_DECIMALS = 3
OBSERVE_RETRIES = 2   # additional fresh observations after an unreadable chip


def quantize(value: float | int | str | Decimal, places: int = UI_DECIMALS) -> Decimal:
    q = Decimal(1).scaleb(-places)
    return Decimal(str(value)).quantize(q)


def is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def values_match(observed: Any, target: Any, places: int = UI_DECIMALS) -> bool:
    """Decimal-aware equality at the UI's displayed precision."""
    if observed is None or target is None:
        return False
    if not (is_finite_number(observed) and is_finite_number(target)):
        return False
    try:
        return quantize(observed, places) == quantize(target, places)
    except InvalidOperation:
        return False


def parse_value(raw: Any) -> float | None:
    """'0.120' / '136.8 cm' → float; anything else → None."""
    if raw is None:
        return None
    try:
        f = float(str(raw).replace("cm", "").replace(" ", "").strip())
    except ValueError:
        return None
    return f if math.isfinite(f) else None


def manifest_from_inventory(inv: dict[str, Any]) -> dict[str, Any]:
    params = {}
    for row in inv.get("parameters") or []:
        if not row.get("numeric_entry") or row.get("duplicate"):
            continue
        val = parse_value(row.get("value"))
        if val is None:
            continue
        params[row["label"]] = val
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
    """Read current slider values in `section` without changing them.

    Duplicate, unreadable and unmapped observations are exported explicitly
    so the manifest cannot be mistaken for a complete restore target.
    """
    inv = INV.inventory_section(section, control_set=control_set)
    man = manifest_from_inventory(inv)
    man["inventory"] = {
        "stop_reason": inv.get("stop_reason"),
        "pages_scanned": inv.get("pages_scanned"),
        "count": inv.get("count"),
        "coverage": inv.get("coverage"),
    }
    man["duplicates"] = inv.get("duplicates") or []
    man["unreadable"] = inv.get("unreadable") or []
    man["unmapped"] = inv.get("unmapped") or []
    return man


def _index_current(inv: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in inv.get("parameters") or []:
        out.setdefault(_norm(row["label"]), []).append(row)
        if row["label"] != _norm(row["label"]):
            out.setdefault(row["label"], []).append(row)
    return out


def plan_params(manifest: dict[str, Any],
                current: dict[str, Any] | None = None,
                catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compare current UI to `manifest`. Makes no changes.

    Navigates to section + control_set (unless `current` is supplied).
    Rejects unresolved, wrong-scope, ambiguous, duplicated, non-finite and
    unreadable-prior labels before returning.
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
        base = {"label": label, "section": section, "control_set": cs}
        if not is_finite_number(target):
            unresolved.append({**base, "reason": "non_finite", "requested": target})
            continue
        cat = resolve_in_catalog(section, cs, label, catalog=catalog)
        if cat.get("reason") == "wrong_scope":
            unresolved.append({**base, "reason": "wrong_scope",
                               "expected": cat.get("expected")})
            continue
        if cat.get("reason") == "ambiguous":
            unresolved.append({**base, "reason": "ambiguous"})
            continue

        rows = index.get(label) or index.get(_norm(label)) or []
        # de-dupe identical row objects reached by both keys
        uniq: list[dict[str, Any]] = []
        for r in rows:
            if all(r is not u for u in uniq):
                uniq.append(r)
        rows = uniq
        if not rows:
            unresolved.append({**base, "reason": "not_found"})
            continue
        if len(rows) > 1 or any(r.get("duplicate") for r in rows):
            unresolved.append({
                **base, "reason": "ambiguous_duplicate",
                "observed": [{"label": r.get("label"), "value": r.get("value"),
                              "y": r.get("y"), "page": r.get("page"),
                              "shot": r.get("shot")} for r in rows],
            })
            continue
        row = rows[0]
        if not row.get("numeric_entry"):
            unresolved.append({**base, "reason": "not_numeric",
                               "observed": row.get("label")})
            continue
        old_f = parse_value(row.get("value"))
        if old_f is None or row.get("value_conflict"):
            unresolved.append({**base, "reason": "prior_unreadable",
                               "observed": row.get("value"),
                               "shot": row.get("shot")})
            continue
        changes.append({
            "label": row["label"],
            "requested_as": label,
            "old": old_f,
            "requested": float(target),
            "section": section,
            "control_set": cs,
            "prior_shot": row.get("shot"),
        })
    return {
        "section": section,
        "control_set": cs,
        "ok": not unresolved,
        "unresolved": unresolved,
        "changes": changes,
        "would_mutate": bool(changes) and not unresolved,
        "coverage": current.get("coverage"),
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


def observe_value(label: str, shot=None, retries: int = OBSERVE_RETRIES,
                  settle: float = 0.8) -> dict[str, Any]:
    """Observe a chip with a bounded retry budget for *unreadable* results.

    Returns {"status": readable|unreadable|not_visible, "value", "raw",
             "attempts": [observation, ...]}. A readable observation ends the
    loop immediately; the budget only covers blank/garbled OCR. Never types.
    """
    attempts = []
    obs = A.observe_param(label, shot, settle=settle if shot is None else 0.0)
    attempts.append(obs)
    while obs["status"] != "readable" and len(attempts) <= retries:
        obs = A.observe_param(label, None, settle=settle)
        attempts.append(obs)
    return {"status": obs["status"], "value": obs["value"], "raw": obs["raw"],
            "shot": obs["shot"], "attempts": attempts}


def apply_params(manifest: dict[str, Any],
                 plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply a manifest through the transactional primitives.

    Abort before mutation if unresolved. Stop candidate writes at the first
    mismatch or at an unreadable readback whose retry budget is exhausted.
    Does not roll back: the caller (or the Lyra executor's coordinator)
    owns recovery and the journal.
    """
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
    outcome = "ok"
    reason = None
    try:
        for change in plan["changes"]:
            label = change["label"]
            target = change["requested"]
            if values_match(change["old"], target):
                verified.append({"label": label, "requested": target,
                                 "after": change["old"], "ok": True,
                                 "outcome": "verified_noop"})
                continue
            s, m = A.locate_param(label)
            A.dispatch_value(s, m, target)
            obs = observe_value(label)
            after_f = obs["value"]
            rec = {"label": label, "requested": target, "after": after_f,
                   "raw": obs["raw"], "shot": obs["shot"],
                   "attempts": len(obs["attempts"])}
            if obs["status"] != "readable":
                rec.update(ok=False, outcome="uncertain")
                verified.append(rec)
                failures.append(rec)
                outcome = "unreadable"
                reason = f"{label}: chip unreadable after {len(obs['attempts'])} observations"
                break
            ok = values_match(after_f, target)
            rec.update(ok=ok, outcome="verified_change" if ok else "mismatch")
            verified.append(rec)
            if not ok:
                failures.append(rec)
                outcome = "mismatch"
                reason = f"{label}: observed {after_f} != requested {target}"
                break
    except Exception as exc:
        return {
            "applied": any(r.get("outcome") != "verified_noop" for r in verified),
            "aborted": True,
            "reason": str(exc),
            "originals": originals,
            "verified": verified,
            "failures": failures,
            "ok": False,
        }
    return {
        "applied": True,
        "aborted": outcome != "ok",
        "reason": reason,
        "outcome": outcome,
        "originals": originals,
        "verified": verified,
        "failures": failures,
        "ok": not failures,
    }
