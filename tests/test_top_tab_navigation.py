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
from mcp_vroid.driver import window as W
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


# --- bounded retry (CANARY-0001 postmortem repair) --------------------------
#
# CANARY-0001 (2026-09-16 production canary) established: the calibrated
# Body click target was geometrically correct, the click was dispatched,
# Body did not activate, and the existing verifier correctly detected Face
# remained active -- a genuine click/input miss, not a verifier defect (see
# ~/VRoid-scratch/canary-0001-postmortem/). Native F1/F2/F3 shortcuts were
# then evaluated as an alternative and found not to work on this VRoid
# build via four independent delivery-method variants (deferred finding,
# see ~/VRoid-scratch/nav-shortcut-qualification-20260916/). This class
# covers the bounded (<=2 click), evidenced retry adopted instead.

def _fake_window(w, h):
    return W.Window(address="x", cls="net.pixiv.vroid.macosx", title="t",
                     x=0, y=0, w=w, h=h, workspace=0, focused=True)


class TestBoundedRetryNavigation:

    def test_1_already_active_zero_clicks(self):
        already = _shot("post-click-020-body-active.png")   # Body active
        with patch.object(A, "shot", return_value=already) as shot_mock, \
                patch.object(A.I, "click") as click_mock:
            result, ev = A.open_tab_with_evidence("Body")
        assert result is already
        click_mock.assert_not_called()
        assert shot_mock.call_count == 1
        assert ev["outcome"] == A.NAV_ALREADY_ACTIVE
        assert ev["clicks"] == 0

    def test_2_first_attempt_succeeds_one_click(self):
        pre = _shot("post-click-002-face-active.png")        # Face active
        post = _shot("post-click-020-body-active.png")       # Body active
        with patch.object(A, "shot", side_effect=[pre, post]), \
                patch.object(A.I, "click") as click_mock, patch("time.sleep"):
            result, ev = A.open_tab_with_evidence("Body")
        assert result is post
        assert click_mock.call_count == 1
        assert ev["outcome"] == A.NAV_FIRST_ATTEMPT_VERIFIED
        assert ev["clicks"] == 1
        assert len(ev["attempts"]) == 1

    def test_3_first_fails_second_succeeds_exactly_two_clicks(self):
        pre = _shot("post-click-002-face-active.png")         # Face active
        post1 = _shot("canary-0001-449-body-failed-face-still-active.png")  # still Face
        reval = _shot("canary-0001-449-body-failed-face-still-active.png")  # still Face
        post2 = _shot("post-click-020-body-active.png")       # now Body active
        with patch.object(A, "shot", side_effect=[pre, post1, reval, post2]), \
                patch.object(A.I, "click") as click_mock, patch("time.sleep"), \
                patch.object(A.W, "find_window",
                            return_value=_fake_window(*pre.image.size)):
            result, ev = A.open_tab_with_evidence("Body")
        assert result is post2
        assert click_mock.call_count == 2
        assert ev["outcome"] == A.NAV_SECOND_ATTEMPT_VERIFIED
        assert ev["clicks"] == 2
        assert len(ev["attempts"]) == 2

    def test_4_late_verified_before_retry_only_one_click(self):
        pre = _shot("post-click-002-face-active.png")         # Face active
        post1 = _shot("canary-0001-449-body-failed-face-still-active.png")  # still Face
        reval = _shot("post-click-020-body-active.png")       # a delayed redraw: now Body
        with patch.object(A, "shot", side_effect=[pre, post1, reval]), \
                patch.object(A.I, "click") as click_mock, patch("time.sleep"), \
                patch.object(A.W, "find_window",
                            return_value=_fake_window(*pre.image.size)):
            result, ev = A.open_tab_with_evidence("Body")
        assert result is reval
        assert click_mock.call_count == 1              # no second click sent
        assert ev["outcome"] == A.NAV_LATE_VERIFIED_BEFORE_RETRY
        assert ev["clicks"] == 1

    def test_5_both_attempts_fail_exactly_two_clicks_then_exception(self):
        pre = _shot("post-click-002-face-active.png")
        post1 = _shot("canary-0001-449-body-failed-face-still-active.png")
        reval = _shot("canary-0001-449-body-failed-face-still-active.png")
        post2 = _shot("canary-0001-449-body-failed-face-still-active.png")
        with patch.object(A, "shot", side_effect=[pre, post1, reval, post2]), \
                patch.object(A.I, "click") as click_mock, patch("time.sleep"), \
                patch.object(A.W, "find_window",
                            return_value=_fake_window(*pre.image.size)):
            with pytest.raises(RuntimeError, match="accent underline was not confirmed"):
                A.open_tab_with_evidence("Body")
        assert click_mock.call_count == 2               # exactly two, no third

    def test_6_geometry_change_before_retry_no_second_click(self):
        pre = _shot("post-click-002-face-active.png")
        post1 = _shot("canary-0001-449-body-failed-face-still-active.png")
        reval = _shot("canary-0001-449-body-failed-face-still-active.png")
        changed = _fake_window(pre.image.width + 200, pre.image.height)
        with patch.object(A, "shot", side_effect=[pre, post1, reval]), \
                patch.object(A.I, "click") as click_mock, patch("time.sleep"), \
                patch.object(A.W, "find_window", return_value=changed):
            with pytest.raises(RuntimeError, match="geometry changed"):
                A.open_tab_with_evidence("Body")
        assert click_mock.call_count == 1                # no second click

    def test_7_window_identity_lost_no_second_click(self):
        pre = _shot("post-click-002-face-active.png")
        post1 = _shot("canary-0001-449-body-failed-face-still-active.png")
        with patch.object(A, "shot", side_effect=[pre, post1]), \
                patch.object(A.I, "click") as click_mock, patch("time.sleep"), \
                patch.object(A.W, "find_window", return_value=None):
            with pytest.raises(RuntimeError, match="could not be reacquired"):
                A.open_tab_with_evidence("Body")
        assert click_mock.call_count == 1                # no second click

    def test_8_neighbouring_active_tab_cannot_satisfy_verification(self):
        """A frame where Face (not Body) is active must never verify Body,
        even though *some* tab's underline is genuinely present."""
        face_active = _shot("canary-0001-449-body-failed-face-still-active.png")
        assert A._tab_is_active(face_active, "Body") is False
        assert A._tab_is_active(face_active, "Face") is True

    def test_9_canary_0001_fixture_first_attempt_leaves_face_active_retry_eligible(self):
        """The real CANARY-0001 failure frame: attempt 1 must be classified
        as unverified (not raise immediately -- the postmortem's whole
        point is that this needs a bounded retry, not an instant failure),
        making the retry path eligible rather than failing outright."""
        pre = _shot("post-click-002-face-active.png")
        incident = _shot("canary-0001-449-body-failed-face-still-active.png")
        reval = _shot("canary-0001-449-body-failed-face-still-active.png")
        recovered = _shot("post-click-020-body-active.png")
        with patch.object(A, "shot", side_effect=[pre, incident, reval, recovered]), \
                patch.object(A.I, "click") as click_mock, patch("time.sleep"), \
                patch.object(A.W, "find_window",
                            return_value=_fake_window(*pre.image.size)):
            result, ev = A.open_tab_with_evidence("Body")
        assert ev["attempts"][0]["verified"] is False
        assert ev["attempts"][0]["capture"] == str(incident.path)
        assert ev["outcome"] == A.NAV_SECOND_ATTEMPT_VERIFIED   # retry recovered it
        assert click_mock.call_count == 2

    def test_10_known_good_body_fixture_first_attempt_succeeds(self):
        """The real, earlier-in-the-same-run successful Body click from the
        CANARY-0001 planning phase: must verify on the first attempt,
        with no retry needed."""
        pre = _shot("post-click-002-face-active.png")
        known_good = _shot("canary-0001-429-body-known-good.png")
        with patch.object(A, "shot", side_effect=[pre, known_good]), \
                patch.object(A.I, "click") as click_mock, patch("time.sleep"):
            result, ev = A.open_tab_with_evidence("Body")
        assert A._tab_is_active(known_good, "Body") is True
        assert ev["outcome"] == A.NAV_FIRST_ATTEMPT_VERIFIED
        assert ev["clicks"] == 1
        assert click_mock.call_count == 1

    def test_11_no_parameter_input_during_navigation(self):
        """Navigation must never touch a numeric field, in either the
        happy path or the full bounded-retry path."""
        pre = _shot("post-click-002-face-active.png")
        post1 = _shot("canary-0001-449-body-failed-face-still-active.png")
        reval = _shot("canary-0001-449-body-failed-face-still-active.png")
        post2 = _shot("post-click-020-body-active.png")
        with patch.object(A, "shot", side_effect=[pre, post1, reval, post2]), \
                patch.object(A.I, "click"), patch("time.sleep"), \
                patch.object(A.I, "type_field_value") as type_mock, \
                patch.object(A.W, "find_window",
                            return_value=_fake_window(*pre.image.size)):
            A.open_tab_with_evidence("Body")
        type_mock.assert_not_called()

    def test_canary_0001_evidence_remains_classified_as_click_failure_not_verifier_failure(self):
        """Permanent regression pin for the postmortem's conclusion: on the
        actual incident pixels, the verifier's read is correct (Face is
        genuinely active, Body genuinely is not) -- the defect was the
        click/input, never this check."""
        incident = _shot("canary-0001-449-body-failed-face-still-active.png")
        assert A._tab_is_active(incident, "Face") is True
        assert A._tab_is_active(incident, "Body") is False
