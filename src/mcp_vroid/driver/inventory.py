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
from dataclasses import asdict, dataclass, field

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
    # Provenance. A row without these came from a caller that built it by
    # hand (tests, legacy fixtures); merge treats missing context as unknown.
    page: int = 0
    shot: str | None = None
    prev_label: str | None = None
    next_label: str | None = None
    # Set by merge_pages. `duplicate`: another distinct control shares this
    # caption. `value_conflict`: the same control was read with different
    # values on overlapping pages, so its prior value is unreadable.
    duplicate: bool = False
    value_conflict: bool = False
    seen_on_pages: list[int] = field(default_factory=list)

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


def _caption_similar(a: str | None, b: str | None) -> bool | None:
    """Fuzzy caption equality tolerant of OCR noise at a page edge.

    "ar} Eyebrows Length" (scrollbar glyph glued to the caption) and
    "Eyebrows Length" are the same neighbour. Returns None when either side
    is absent (clipped at the page edge).
    """
    if not a or not b:
        return None
    na, nb = L._norm(a), L._norm(b)
    if na == nb:
        return True
    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(short) >= 4 and short in long_


def _same_context(a: ObservedRow, b: ObservedRow) -> bool | None:
    """True when at least one shared neighbour caption agrees, False when
    every comparable neighbour disagrees, None when nothing is comparable."""
    if a.prev_label is None and a.next_label is None:
        return None
    if b.prev_label is None and b.next_label is None:
        return None
    votes = [v for v in (_caption_similar(a.prev_label, b.prev_label),
                         _caption_similar(a.next_label, b.next_label)) if v is not None]
    if not votes:
        return None
    return any(votes)


def merge_pages(pages: list[list[ObservedRow]]) -> list[ObservedRow]:
    """Merge overlapping scroll pages without hiding distinct controls.

    Rules, in order:
    * Same key on the *same* page → two distinct controls. Both are kept and
      flagged `duplicate` (Face Sets really has two "Nose Size" rows).
    * Same key on a later page with the same value (or one side blank) and
      no contradicting neighbour context → the same row reappearing after a
      scroll; merged, pages recorded.
    * Same key on a later page with a different readable value → same row
      if the neighbour context agrees (flag `value_conflict`, keep both
      readings), otherwise a distinct control (flag `duplicate`).
    First-seen order is preserved.
    """
    merged: list[ObservedRow] = []
    by_key: dict[str, list[ObservedRow]] = {}
    for page_idx, page in enumerate(pages):
        for row in page:
            k = row.key()
            if not k:
                continue
            # Rows built by hand (no shot) get their page from list position.
            pg = row.page if row.shot is not None else page_idx
            row.page = pg
            row.seen_on_pages = [pg]
            candidates = by_key.get(k) or []
            target = None
            for cand in candidates:
                if pg in cand.seen_on_pages:
                    # Already saw this caption on this very page: a second
                    # occurrence is a distinct control, never a re-read.
                    continue
                ctx = _same_context(cand, row)
                values_agree = (
                    cand.value in (None, "") or row.value in (None, "")
                    or cand.value == row.value
                )
                if ctx is False:
                    continue
                if values_agree or ctx is True:
                    target = cand
                    break
            if target is None:
                if candidates:
                    row.duplicate = True
                    for cand in candidates:
                        cand.duplicate = True
                by_key.setdefault(k, []).append(row)
                merged.append(row)
                continue
            # merge into target
            if target.value in (None, "") and row.value:
                target.value = row.value
                target.control, target.numeric_entry = _control_for(target.label, row.value)
            elif row.value and target.value and row.value != target.value:
                target.value_conflict = True
                target.numeric_entry = False
            for pg in row.seen_on_pages:
                if pg not in target.seen_on_pages:
                    target.seen_on_pages.append(pg)
    return merged


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


def inventory_from_shot(s: Shot, page: int = 0) -> list[ObservedRow]:
    """Parse one capture. No input. Rows carry page, shot and neighbour captions."""
    value_x = int(s.image.width * VALUE_X_FRAC)
    rows = parse_panel(panel_words(s), value_x_min=value_x)
    for i, r in enumerate(rows):
        r.page = page
        r.shot = str(s.path)
        r.prev_label = rows[i - 1].label if i > 0 else None
        r.next_label = rows[i + 1].label if i + 1 < len(rows) else None
        r.seen_on_pages = [page]
    return rows


def inventory_section(section: str, max_pages: int = 24,
                      stagnant_limit: int = 2,
                      control_set: str | None = None) -> dict:
    """Open `section` + control set, OCR the Parameters panel, scroll only if needed.

    Does not click numeric boxes or type values.
    """
    from .scope import control_set_of, DEFAULT_CONTROL_SET
    cs = control_set or DEFAULT_CONTROL_SET.get(section)
    A.navigate_scope(section, cs)
    time.sleep(0.4)
    subsection = None
    try:
        subsection = A._panel_title(C.grab_window(tag=f"inv-{section}-title")) or None
    except Exception:
        subsection = None
    if cs and subsection and L._norm(cs) not in L._norm(subsection):
        raise RuntimeError(
            f"expected control set {cs!r} in {section!r}, panel title {subsection!r}")

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
        rows = inventory_from_shot(s, page=i)
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
    return build_inventory(section, cs, subsection, pages, merged, stop_reason, max_pages)


def coverage_report(section: str, control_set: str | None,
                    merged: list[ObservedRow], stop_reason: str,
                    pages_scanned: int, max_pages: int) -> dict:
    """Separate *why the scan stopped* from *what supports coverage*.

    termination            the loop's stop reason, nothing more
    end_evidence           what, if anything, independently supports having
                           seen the whole list. An unchanged frame after a
                           wheel event is a UI response, not proof; it is
                           listed as "weak". max_pages is no evidence at all.
    catalog                corroboration against the capability catalog for
                           this scope: which catalogued numeric labels were
                           observed, which were not. The catalog itself was
                           derived from earlier OCR crawls, so agreement is
                           corroboration, not ground truth.
    problematic            counts of observations a caller must not treat as
                           clean values (all rows are also kept in full).
    verified               True only when termination was not max_pages AND
                           every catalogued numeric label was observed AND no
                           row is problematic. Anything else is "within
                           demonstrated coverage" only.
    """
    from .scope import load_catalog
    want = _norm_pair(section, control_set)
    cat_labels = []
    for row in load_catalog():
        if _norm_pair(row.get("section"), row.get("control_set")) == want \
                and row.get("numeric_entry"):
            cat_labels.append(row["label"])
    observed_keys = {r.key() for r in merged}
    missing = [l for l in cat_labels if L._norm(l) not in observed_keys]
    cat_keys = {L._norm(l) for l in cat_labels}
    extra = [r.label for r in merged if r.numeric_entry and r.key() not in cat_keys]

    if stop_reason == "max_pages":
        end_evidence = []
    elif stop_reason == "panel_end_visible":
        end_evidence = [{"kind": "last_row_above_bottom_on_first_page", "strength": "weak"}]
    elif stop_reason == "unchanged_panel":
        end_evidence = [{"kind": "frame_unchanged_after_wheel", "strength": "weak"}]
    else:
        end_evidence = []
    if cat_labels and not missing:
        end_evidence.append({"kind": "all_catalogued_labels_observed",
                             "strength": "corroborating", "count": len(cat_labels)})

    problematic = {
        "duplicate": sum(1 for r in merged if r.duplicate),
        "value_conflict": sum(1 for r in merged if r.value_conflict),
        "unreadable_value": sum(1 for r in merged
                                if r.value is not None and r.control == "unknown"),
        "no_value": sum(1 for r in merged if r.value is None),
    }
    verified = (stop_reason != "max_pages" and bool(cat_labels) and not missing
                and not any(problematic.values()))
    return {
        "termination": stop_reason,
        "pages_scanned": pages_scanned,
        "max_pages": max_pages,
        "end_evidence": end_evidence,
        "catalog": {"expected_numeric": len(cat_labels), "observed": len(cat_labels) - len(missing),
                    "missing": missing, "extra_observed": extra},
        "problematic": problematic,
        "verified": verified,
        "claim": ("verified within catalogue" if verified
                  else "partial: compare only within demonstrated coverage"),
    }


def _norm_pair(section, control_set) -> tuple[str, str]:
    return (L._norm(str(section or "")), L._norm(str(control_set or "")))


def build_inventory(section: str, cs: str | None, subsection: str | None,
                    pages: list[list[ObservedRow]], merged: list[ObservedRow],
                    stop_reason: str, max_pages: int) -> dict:
    duplicates = [asdict(r) for r in merged if r.duplicate]
    unreadable = [asdict(r) for r in merged
                  if r.value_conflict or (r.control == "unknown" and r.value is not None)]
    unmapped = [asdict(r) for r in merged if r.value is None]
    coverage = coverage_report(section, cs, merged, stop_reason, len(pages), max_pages)
    coverage["shots"] = [pg[0].shot for pg in pages if pg]
    return {
        "schema_version": 1,
        "vroid_version": "2.14.0",
        "section": section,
        "control_set": cs or subsection,
        "subsection": subsection or cs,
        "stop_reason": stop_reason,
        "pages_scanned": len(pages),
        "count": len(merged),
        "coverage": coverage,
        "duplicates": duplicates,
        "unreadable": unreadable,
        "unmapped": unmapped,
        "parameters": [asdict(r) for r in merged],
    }
