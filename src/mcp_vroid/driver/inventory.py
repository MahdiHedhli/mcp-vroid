"""Read-only crawl of a VRoid Parameters panel.

Never clicks a numeric box, never types a value. Tab switches and wheel
scrolls are the only input, and scrolling is skipped when the last row is
already above the bottom of the window.

Overlapping scroll pages are merged by normalised label, keeping 1-letter
axis tokens (X/Y/Z).
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass

from . import actions as A
from . import capture as C
from . import locate as L
from .types import Shot

VALUE_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:cm)?$", re.I)
COLOR_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")
SKIP_LABELS = {
    "parameters", "customize", "presets", "custom", "searchmoreitems",
    "search", "more", "items", "edittexture", "oo",
}
Y_TOL = 16
# Numeric chips sit near the right edge; the shared PANEL_REGION x1=0.97
# clips them on a 1410-px window, so inventory uses the full width.
INVENTORY_PANEL = (0.68, 0.03, 1.0, 1.0)
VALUE_X_FRAC = 0.90


@dataclass
class ObservedRow:
    label: str
    value: str | None
    y: int
    control: str
    numeric_entry: bool

    def key(self) -> str:
        return L._norm(self.label)


def _is_value_token(text: str) -> bool:
    t = text.strip().replace(" ", "")
    if not t:
        return False
    if COLOR_RE.match(t) or VALUE_RE.match(t) or t.lower() == "cm":
        return True
    return False


def _control_for(label: str, value: str | None) -> tuple[str, bool]:
    if L._norm(label) == "showheightpanel":
        return "checkbox", False
    if value is None:
        return "unknown", False
    raw = value.strip()
    compact = raw.replace(" ", "")
    if COLOR_RE.match(raw) or COLOR_RE.match(compact):
        return "color", True
    if compact.lower().endswith("cm"):
        return "readout", False
    if VALUE_RE.match(compact):
        return "slider", True
    return "unknown", False


def _join_numeric(parts: list[str]) -> str:
    if len(parts) >= 2 and parts[-1].lower() == "cm":
        return "".join(parts[:-1]) + " cm"
    if all(_is_value_token(p) and p.lower() != "cm" for p in parts):
        return "".join(parts)
    return " ".join(parts)


def cluster_by_row(matches: list[L.Match], y_tol: int = Y_TOL) -> list[list[L.Match]]:
    if not matches:
        return []
    ordered = sorted(matches, key=lambda m: (m.top, m.left))
    rows: list[list[L.Match]] = []
    cur = [ordered[0]]
    y0 = ordered[0].center[1]
    for m in ordered[1:]:
        if abs(m.center[1] - y0) <= y_tol:
            cur.append(m)
        else:
            rows.append(sorted(cur, key=lambda x: x.left))
            cur = [m]
            y0 = m.center[1]
    rows.append(sorted(cur, key=lambda x: x.left))
    return rows


def row_from_cluster(cluster: list[L.Match],
                     value_x_min: float | None = None) -> ObservedRow | None:
    if not cluster:
        return None
    if value_x_min is None:
        label_ms, value_ms = list(cluster), []
        tokens = [m.text.strip() for m in cluster if m.text.strip()]
        value_parts: list[str] = []
        while tokens and _is_value_token(tokens[-1]):
            value_parts.insert(0, tokens.pop())
        label_tokens = tokens
        value = _join_numeric(value_parts) if value_parts else None
    else:
        # Use left edge so a wide word like "Texture" is not classified as
        # a numeric chip (chips start near 0.94 of the window).
        label_ms = [m for m in cluster if m.left < value_x_min]
        value_ms = [m for m in cluster if m.left >= value_x_min]
        label_tokens = [m.text.strip() for m in label_ms if m.text.strip()]
        value_parts = [m.text.strip() for m in value_ms if m.text.strip()]
        value = _join_numeric(value_parts) if value_parts else None
        if value is None:
            tokens = [m.text.strip() for m in cluster if m.text.strip()]
            value_parts = []
            while tokens and _is_value_token(tokens[-1]):
                value_parts.insert(0, tokens.pop())
            label_tokens = tokens
            value = _join_numeric(value_parts) if value_parts else None
    if label_tokens and label_tokens[-1] in {":", "-"}:
        label_tokens.pop()
    if not label_tokens:
        return None
    label = " ".join(label_tokens).rstrip(":")
    if L._norm(label) in SKIP_LABELS or len(L._norm(label)) < 3:
        return None
    control, numeric = _control_for(label, value)
    y = int(sum(m.center[1] for m in cluster) / len(cluster))
    return ObservedRow(label=label, value=value, y=y, control=control,
                       numeric_entry=numeric)


def parse_panel(matches: list[L.Match],
                value_x_min: float | None = None) -> list[ObservedRow]:
    rows = []
    for cluster in cluster_by_row(matches):
        row = row_from_cluster(cluster, value_x_min=value_x_min)
        if row:
            rows.append(row)
    return rows


def merge_pages(pages: list[list[ObservedRow]]) -> list[ObservedRow]:
    """First-seen order. A later page may fill in a missing value, not replace."""
    by_key: dict[str, ObservedRow] = {}
    order: list[str] = []
    for page in pages:
        for row in page:
            k = row.key()
            if not k:
                continue
            if k not in by_key:
                by_key[k] = row
                order.append(k)
            elif by_key[k].value in (None, "") and row.value:
                by_key[k] = row
    return [by_key[k] for k in order]


def _inventory_box(s: Shot) -> tuple[int, int, int, int]:
    w, h = s.image.width, s.image.height
    x0, y0, x1, y1 = INVENTORY_PANEL
    return (int(w * x0), int(h * y0), int(w * x1), int(h * y1))


def panel_words(s: Shot) -> list[L.Match]:
    box = _inventory_box(s)
    cropped = s.crop(box)
    words = L.all_text(cropped, min_conf=25)
    dx, dy = box[0], box[1]
    return [L.Match(m.text, m.conf, m.left + dx, m.top + dy, m.width, m.height)
            for m in words]


def inventory_from_shot(s: Shot) -> list[ObservedRow]:
    """Parse one capture. No input."""
    value_x = int(s.image.width * VALUE_X_FRAC)
    return parse_panel(panel_words(s), value_x_min=value_x)


def inventory_section(section: str, max_pages: int = 24,
                      stagnant_limit: int = 2) -> dict:
    """Open `section`, OCR the Parameters panel, scroll only if needed.

    Does not click numeric boxes or type values.
    """
    A.open_tab(section)
    time.sleep(0.4)
    subsection = None
    try:
        subsection = A._panel_title(C.grab_window(tag=f"inv-{section}-title")) or None
    except Exception:
        subsection = None

    s = C.grab_window(tag=f"inv-{section}-top")
    # Jump to top once; skip if the first page already shows the list end.
    A.scroll_panel(-80, s)
    time.sleep(0.4)

    pages: list[list[ObservedRow]] = []
    last_fp = None
    stagnant = 0
    stop_reason = "max_pages"
    prev_crop = None

    for i in range(max_pages):
        s = C.grab_window(tag=f"inv-{section}-{i}")
        rows = inventory_from_shot(s)
        pages.append(rows)
        fp = tuple((r.key(), r.value) for r in rows)
        crop = s.crop(_inventory_box(s))
        unchanged_img = False
        if prev_crop is not None:
            try:
                unchanged_img = L.diff_ratio(prev_crop, crop) < 0.02
            except Exception:
                unchanged_img = False
        prev_crop = crop

        last_y = max((r.y for r in rows), default=0)
        end_visible = bool(rows) and last_y < s.image.height * 0.88
        unchanged = (fp == last_fp) or unchanged_img
        if end_visible and i == 0:
            stop_reason = "panel_end_visible"
            break
        if unchanged:
            stagnant += 1
            if stagnant >= stagnant_limit:
                stop_reason = "unchanged_panel"
                break
        else:
            stagnant = 0
        last_fp = fp
        A.scroll_panel(8, s)
        time.sleep(0.4)
    else:
        stop_reason = "max_pages"

    merged = merge_pages(pages)
    return {
        "schema_version": 1,
        "vroid_version": "2.14.0",
        "section": section,
        "subsection": subsection,
        "stop_reason": stop_reason,
        "pages_scanned": len(pages),
        "count": len(merged),
        "parameters": [asdict(r) for r in merged],
    }
