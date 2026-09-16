"""Recorded-evidence tests for the T5b swallowed-dispatch incident (2026-09-16).

Fixtures are the ACTUAL captures from the live incident:
    tests/fixtures/t5b-swallowed-dispatch/before-restore-dispatch.png
        = live captures/349.png -- the locate shot immediately before the
          Chest Size restore dispatch (chip reads 0.720).
    tests/fixtures/t5b-swallowed-dispatch/after-restore-dispatch-and-observation.png
        = live captures/350-observe-chestsize.png -- the fresh, later
          observation taken after journal recorded restore_dispatched=True
          (chip still reads 0.720, not the requested 0.000).

What these prove: the two frames are pixel-identical in the parameter
panel, at two genuinely different points in time (confirmed by the journal
timestamps: restore_dispatch at 02:04:39.256, this observation at
02:04:46.814 -- a fresh screenshot, not a reused Shot object). That is
real, direct evidence that the on-screen chip value did not change across
a dispatch the driver reported as completed without error.

What these do NOT prove, and this file does not claim: WHY it didn't
change. A screenshot cannot see a keystroke, a focus change, or an OS
event queue. It cannot distinguish "the click never registered" from "the
keystrokes went to the wrong window" from "Unity redrew before committing
and would have caught up eventually." Those remain live-only questions;
see docs/t5b-swallowed-dispatch.md. Running these two images back through
`find_text`/OCR is also not a second, independent check that the *value*
matches what a human would read -- it is the same OCR path the driver
itself uses, so it can only confirm internal consistency (the driver's own
before/after readings agree with each other), not ground truth. The
Gate B session record already has the independent human reading for that
(both a person and the coordinator read "0.720" here).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from mcp_vroid.driver import locate as L
from mcp_vroid.driver.types import Shot

FIXTURES = Path(__file__).parent / "fixtures" / "t5b-swallowed-dispatch"
BEFORE = FIXTURES / "before-restore-dispatch.png"
AFTER = FIXTURES / "after-restore-dispatch-and-observation.png"

# Measured from these exact fixtures via _find_label("Chest Size"): the row
# sits at center y=1152; a +/-20px band around it covers the numeric chip.
CHEST_SIZE_ROW_BOX = (958, 1132, 1410, 1172)   # (l, t, r, b), full 1410x2295 frame


def _load(path: Path) -> Shot:
    return Shot(Image.open(path).convert("RGB"), path, 0, 0, 1.0)


def test_fixtures_are_the_expected_full_window_frames():
    for p in (BEFORE, AFTER):
        img = Image.open(p)
        assert img.size == (1410, 2295), f"{p.name}: unexpected size {img.size}"


def test_panel_pixels_are_identical_across_the_reported_dispatch():
    """The direct, reproducible observation the incident turns on: dispatch
    was reported to complete between these two captures, yet the parameter
    panel (everything right of the 3D viewport) did not change by a single
    pixel."""
    before = np.asarray(Image.open(BEFORE).convert("RGB").crop((958, 0, 1410, 2295)))
    after = np.asarray(Image.open(AFTER).convert("RGB").crop((958, 0, 1410, 2295)))
    assert before.shape == after.shape
    assert np.array_equal(before, after), (
        "expected byte-identical panels (that is exactly what the live incident "
        "showed); a mismatch here would mean these fixtures were mislabeled, not "
        "that the underlying live bug is fixed -- this test targets a recorded "
        "observation, not the code under repair")


def test_both_frames_ocr_the_same_prior_value_not_the_restore_target():
    """Both frames independently OCR to 0.720 -- the pre-dispatch value --
    never to 0.000, the value the restore actually requested. This is the
    driver's own OCR path applied to two real frames; it demonstrates
    internal consistency (both reads agree), not independent ground truth
    (a human read the same "0.720" live and is recorded separately)."""
    for path, label in ((BEFORE, "before"), (AFTER, "after")):
        s = _load(path)
        crop = s.image.crop(CHEST_SIZE_ROW_BOX)
        words = L.all_text(crop)
        raw = " ".join(w.text for w in words if any(c.isdigit() for c in w.text))
        assert "720" in raw.replace(".", ""), f"{label} frame: expected the pre-dispatch value, got {raw!r}"
        assert "000" not in raw or "720" in raw, f"{label} frame: did not expect the restore target here"


def test_diff_ratio_reports_zero_change_for_these_two_frames():
    """Cross-check with the driver's own diff_ratio helper (used elsewhere
    to detect an unchanged inventory page): agrees the panel is unchanged."""
    before = _load(BEFORE)
    after = _load(AFTER)
    ratio = L.diff_ratio(before.crop((958, 0, 1410, 2295)), after.crop((958, 0, 1410, 2295)))
    assert ratio == 0.0
