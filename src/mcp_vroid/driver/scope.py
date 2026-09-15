"""VRoid parameter addresses: section + control_set + label.

A label is not a unique address. Sunken Cheeks lives at Face → Face Sets;
Chest Size lives at Body → Whole Body. Inventory, plan, and apply all
carry this scope. Catalog files under schema/vroid-2.14/ are labels and
control types only — not character values.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .locate import _norm
from .paths import REPO

SCHEMA_DIR = REPO / "schema" / "vroid-2.14"

# Top-level editor tab → default left-rail control set (VRoid 2.14 English).
DEFAULT_CONTROL_SET = {
    "Face": "Face Sets",
    "Body": "Whole Body",
    "Hairstyle": "Hairstyle Sets",
}


def control_set_of(doc: dict[str, Any], section: str | None = None) -> str | None:
    """Manifest/inventory control set. Accepts legacy `subsection`."""
    sec = section or doc.get("section")
    return (
        doc.get("control_set")
        or doc.get("subsection")
        or DEFAULT_CONTROL_SET.get(str(sec) if sec else "")
    )


def address_key(section: str, control_set: str | None, label: str) -> tuple[str, str, str]:
    return (_norm(section), _norm(control_set or ""), _norm(label))


@lru_cache(maxsize=1)
def load_catalog() -> list[dict[str, Any]]:
    """Capability rows from schema JSON. No character values."""
    rows: list[dict[str, Any]] = []
    if not SCHEMA_DIR.is_dir():
        return rows
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict) or "parameters" not in doc:
            continue
        section = doc.get("section") or path.stem.capitalize()
        cs = control_set_of(doc, section)
        for p in doc.get("parameters") or []:
            if not isinstance(p, dict) or not p.get("label"):
                continue
            rows.append({
                "section": section,
                "control_set": cs,
                "label": p["label"],
                "control": p.get("control"),
                "numeric_entry": bool(p.get("numeric_entry")),
            })
    return rows


def catalog_addresses(label: str,
                      catalog: list[dict[str, Any]] | None = None) -> list[tuple[str, str]]:
    """(section, control_set) pairs where `label` is a known capability."""
    want = _norm(label)
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in (catalog if catalog is not None else load_catalog()):
        if _norm(row["label"]) != want:
            continue
        pair = (str(row.get("section") or ""), str(row.get("control_set") or ""))
        key = (_norm(pair[0]), _norm(pair[1]))
        if key in seen:
            continue
        seen.add(key)
        out.append(pair)
    return out


def resolve_in_catalog(section: str, control_set: str | None, label: str,
                       catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Look up a scoped address in the capability catalog.

    Returns {ok, reason, row?, expected?}.
    reason: ok | not_in_catalog | wrong_scope | ambiguous
    """
    rows = catalog if catalog is not None else load_catalog()
    addrs = catalog_addresses(label, catalog=rows)
    if not addrs:
        return {"ok": False, "reason": "not_in_catalog", "label": label}
    cs = control_set or DEFAULT_CONTROL_SET.get(section)
    want = (_norm(section), _norm(cs or ""))
    hits = [a for a in addrs if (_norm(a[0]), _norm(a[1])) == want]
    if len(hits) == 1:
        for row in rows:
            if (_norm(str(row.get("section") or "")),
                    _norm(str(row.get("control_set") or "")),
                    _norm(row["label"])) == (want[0], want[1], _norm(label)):
                return {"ok": True, "reason": "ok", "label": label, "row": row,
                        "section": row.get("section"), "control_set": row.get("control_set")}
        return {"ok": True, "reason": "ok", "label": label,
                "section": section, "control_set": cs}
    if hits:
        return {"ok": False, "reason": "ambiguous", "label": label,
                "expected": addrs}
    return {
        "ok": False,
        "reason": "wrong_scope",
        "label": label,
        "section": section,
        "control_set": cs,
        "expected": [{"section": s, "control_set": c} for s, c in addrs],
    }
