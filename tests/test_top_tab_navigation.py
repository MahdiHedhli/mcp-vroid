"""Regression coverage for the T4-incident Body-navigation defect.

Root cause (reproduced from live captures, see docs/top-tab-navigation.md):
`open_tab` located a top-level tab by OCR'ing a crop that included the macOS
title bar. When VRoid Studio is the focused/key window the title bar renders
near-black; that large dark block skews Tesseract's internal page
segmentation for the whole crop and it silently drops every inactive-tab
token ("Hairstyle"/"Body"/"Outfit"/"Accessories"/"Look") while the bold,
underlined *active* tab survives. Confirmed by a controlled pixel swap
(pasting the title bar between a working and a failing capture flips the
result) and by byte-identical `_prep()` output in the tab-label region
across both cases -- the defect is entirely inside Tesseract's layout
analysis, not this driver's cropping or normalisation.

The fix removes OCR from top-level tab discovery entirely: the six tabs
occupy a static, window-relative layout (identical to 5 decimal places
across three independent captures at different points in a live session),
so `open_tab` clicks a calibrated fraction and verifies success with VRoid's
own accent-blue active-tab underline -- a colour check, immune to the
title-bar-darkness artifact because it lives well below the title bar.

Fixtures under tests/fixtures/top-tab-navigation/ are the *actual* captures
from the reproduced incident and from real successful navigations earlier in
the same Gate B run -- not synthesised images.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from mcp_vroid.driver import actions as A
from mcp_vroid.driver import locate as L
from mcp_vroid.driver.types import Shot

FIXTURES = Path(__file__).parent / "fixtures" / "top-tab-navigation"

INCIDENT_CAPTURES = [
    "incident-136-body-navigation-failed.png",
    "incident-137-body-navigation-failed-retry.png",
]


def _shot(name: str) -> Shot:
    p = FIXTURES / name
    return Shot(Image.open(p).convert("RGB"), p, 0, 0, 1.0)


# --- pin the original bug: prove it was real, not imagined -----------------

class TestReproducedIncident:
    """The exact failure the old find_text-based open_tab hit, pinned so a
    future change to the shared OCR locator can't silently reintroduce it
    for this code path without a test noticing."""

    @pytest.mark.parametrize("capture", INCIDENT_CAPTURES)
    def test_old_ocr_approach_genuinely_failed_on_these_captures(self, capture):
        s = _shot(capture)
        region = (0, 0, int(s.image.width * 0.4), int(s.image.height * 0.04))
        assert L.find_text(s, "Body", region=region) is None
        assert L.find_text(s, "Body", region=region, all_matches=True) == []

    @pytest.mark.parametrize("capture", INCIDENT_CAPTURES)
    def test_old_ocr_approach_still_found_the_active_tab(self, capture):
        """Confirms the failure was selective (inactive tabs only), matching
        the diagnosed mechanism -- not a wholesale OCR outage on the frame."""
        s = _shot(capture)
        region = (0, 0, int(s.image.width * 0.4), int(s.image.height * 0.04))
        assert L.find_text(s, "Face", region=region) is not None


# --- the fix works on the exact incident pixels -----------------------------

class TestFixOnIncidentCaptures:
    """Both incident captures must demonstrate the new mechanism resolves
    Body navigation correctly where the old one failed."""

    @pytest.mark.parametrize("capture", INCIDENT_CAPTURES)
    def test_calibrated_body_click_lands_on_real_body_pixels(self, capture):
        s = _shot(capture)
        # independently measured, not from TOP_TAB_FRAC itself
        body_bbox = (283, 44, 283 + 39, 44 + 16)
        fx, fy = A.TOP_TAB_FRAC["Body"]
        cx, cy = int(s.image.width * fx), int(s.image.height * fy)
        assert body_bbox[0] <= cx <= body_bbox[2]
        assert body_bbox[1] <= cy <= body_bbox[3]

    @pytest.mark.parametrize("capture", INCIDENT_CAPTURES)
    def test_underline_check_is_unaffected_by_the_corrupting_titlebar(self, capture):
        """On the exact frames that broke OCR, the colour-based check still
        correctly reports which tab is active (Face) and which is not
        (Body) -- proving the verification signal survives the failure mode
        that killed text-OCR discovery."""
        s = _shot(capture)
        assert A._tab_is_active(s, "Face") is True
        assert A._tab_is_active(s, "Body") is False


# --- all six tabs, real pixels ----------------------------------------------

ALL_TABS = ("Face", "Hairstyle", "Body", "Outfit", "Accessories", "Look")


class TestAllTopLevelTabs:
    def test_every_calibrated_click_lands_inside_its_own_real_bbox(self):
        """Correct target chosen for every tab, measured against real OCR
        bounding boxes from an independent calibration frame (not the
        frames TOP_TAB_FRAC itself was authored from -- 019.png is used
        here purely as ground truth for where the text actually is)."""
        s = _shot("calibration-019-all-tabs-unfocused.png")
        w, h = s.image.width, s.image.height
        region = (0, 0, w, 100)
        words = L.ocr_words(s.image.crop(region), upscale=2.0, invert=False,
                            psm=11, min_conf=40.0)
        bboxes = {}
        for m in words:
            n = L._norm(m.text)
            for name in ALL_TABS:
                if n == L._norm(name):
                    bboxes[name] = (m.left, m.top, m.left + m.width, m.top + m.height)
        assert set(bboxes) == set(ALL_TABS), f"calibration frame missing labels: {set(ALL_TABS) - set(bboxes)}"
        for name in ALL_TABS:
            fx, fy = A.TOP_TAB_FRAC[name]
            cx, cy = int(w * fx), int(h * fy)
            bx0, by0, bx1, by1 = bboxes[name]
            assert bx0 <= cx <= bx1, f"{name}: click x={cx} outside bbox x=[{bx0},{bx1}]"
            assert by0 <= cy <= by1, f"{name}: click y={cy} outside bbox y=[{by0},{by1}]"

    def test_no_neighbouring_tab_is_confused_with_the_target(self):
        """Pairwise: every tab's calibrated x must not fall inside any
        *other* tab's bbox (rules out Hairstyle-vs-Body, Outfit-vs-
        Accessories mix-ups at these tight tab pitches)."""
        s = _shot("calibration-019-all-tabs-unfocused.png")
        w, h = s.image.width, s.image.height
        words = L.ocr_words(s.image.crop((0, 0, w, 100)), upscale=2.0,
                            invert=False, psm=11, min_conf=40.0)
        bboxes = {}
        for m in words:
            n = L._norm(m.text)
            for name in ALL_TABS:
                if n == L._norm(name):
                    bboxes[name] = (m.left, m.left + m.width)
        for name, (fx, _) in A.TOP_TAB_FRAC.items():
            cx = int(w * fx)
            for other, (ox0, ox1) in bboxes.items():
                if other == name:
                    continue
                assert not (ox0 <= cx <= ox1), f"{name}'s click x={cx} falls inside {other}'s bbox"

    @pytest.mark.parametrize("active,inactive_pairs", [
        ("post-click-002-face-active.png", [("Face", True)] + [(t, False) for t in ALL_TABS if t != "Face"]),
        ("post-click-020-body-active.png", [("Body", True)] + [(t, False) for t in ALL_TABS if t != "Body"]),
        ("post-click-132-face-active.png", [("Face", True)] + [(t, False) for t in ALL_TABS if t != "Face"]),
    ])
    def test_underline_check_discriminates_every_tab_on_real_screenshots(self, active, inactive_pairs):
        s = _shot(active)
        for tab, expected in inactive_pairs:
            assert A._tab_is_active(s, tab) is expected, f"{active}: is_active({tab}) expected {expected}"


# --- window-relative scaling -------------------------------------------------

class TestWindowRelativeScaling:
    def test_click_coordinates_scale_linearly_with_window_size(self):
        """Fraction-based positions, not absolute pixels: doubling the
        window dimensions must double the target pixel (within rounding)."""
        base_w, base_h = 1410, 2295
        scale = 2.0
        for name, (fx, fy) in A.TOP_TAB_FRAC.items():
            x1, y1 = int(base_w * fx), int(base_h * fy)
            x2, y2 = int(base_w * scale * fx), int(base_h * scale * fy)
            assert abs(x2 - x1 * scale) <= 1
            assert abs(y2 - y1 * scale) <= 1


# --- control flow: fail closed, no follow-on input --------------------------

class TestOpenTabControlFlow:
    """open_tab's own sequencing, with the desktop boundary mocked -- no
    real click or screenshot is ever made in this test class."""

    def test_unknown_tab_fails_closed_before_any_click_or_screenshot(self):
        with patch.object(A, "shot") as shot_mock, \
                patch.object(A.I, "click") as click_mock:
            with pytest.raises(ValueError, match="unknown top-level tab"):
                A.open_tab("Nonexistent")
        shot_mock.assert_not_called()
        click_mock.assert_not_called()

    def test_verification_failure_raises_and_attempts_no_second_click(self):
        pre = _shot("post-click-002-face-active.png")     # arbitrary pre-click frame
        # simulate a click that lands but the tab never actually activates
        post_no_underline = Shot(Image.new("RGB", pre.image.size, "white"),
                                 Path("/fake/no-underline.png"), 0, 0, 1.0)
        with patch.object(A, "shot", side_effect=[pre, post_no_underline]) as shot_mock, \
                patch.object(A.I, "click") as click_mock:
            with pytest.raises(RuntimeError, match="accent underline was not confirmed"):
                A.open_tab("Body")
        assert click_mock.call_count == 1          # no retry
        assert shot_mock.call_count == 2           # pre-click locate + post-click verify only

    def test_successful_click_returns_the_post_click_shot(self):
        pre = _shot("post-click-002-face-active.png")
        post = _shot("post-click-020-body-active.png")    # has Body's real underline
        with patch.object(A, "shot", side_effect=[pre, post]), \
                patch.object(A.I, "click") as click_mock, \
                patch("time.sleep"):
            result = A.open_tab("Body")
        assert result is post
        assert click_mock.call_count == 1
        (cx, cy), kw = click_mock.call_args
        fx, fy = A.TOP_TAB_FRAC["Body"]
        assert cx == int(pre.image.width * fx)
        assert cy == int(pre.image.height * fy)
        assert kw["space"] == "image"

    def test_face_navigation_still_works_end_to_end(self):
        """Existing Face navigation (used throughout Gate B T2-T4) is
        unaffected by removing OCR from this function."""
        pre = _shot("post-click-020-body-active.png")
        post = _shot("post-click-132-face-active.png")
        with patch.object(A, "shot", side_effect=[pre, post]), \
                patch.object(A.I, "click"), patch("time.sleep"):
            result = A.open_tab("Face")
        assert result is post
