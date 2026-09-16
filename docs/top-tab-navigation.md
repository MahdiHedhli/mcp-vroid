# Top-level tab navigation: root cause and fix (Project Lyra T4 incident)

## Incident

During Project Lyra's Gate B attended acceptance test, `open_tab("Body")`
failed twice in a row, identically, with `RuntimeError: tab 'Body' not
found in the tab strip`, even though the operator and the reviewer could
both plainly read "Body" in the screenshot taken at the moment of failure.
Both failures occurred before any dispatch — zero mutation risk — but the
repeated, identical failure ruled out ordinary OCR flakiness and required
root-causing before further live testing.

Incident captures (preserved as test fixtures, not reproduced from
description): `tests/fixtures/top-tab-navigation/incident-136-*.png`,
`incident-137-*.png`.

## Old mechanism

```python
def open_tab(name: str) -> Shot:
    s = shot()
    m = L.find_text(s, name, region=(0, 0, int(s.image.width * 0.4),
                                     int(s.image.height * 0.04)))
    if m is None:
        raise RuntimeError(f"tab {name!r} not found in the tab strip")
    I.click(*m.center, space="image", shot=s)
    ...
```

OCR (Tesseract via `find_text`) on a crop of the window's top-left corner —
which necessarily includes the macOS title bar, since the tab strip sits
immediately below it.

## Root cause, established by direct evidence (not inferred)

1. **Reproduced offline**, feeding the two incident captures through the
   exact production pipeline (`_prep` → `ocr_words` → `find_text`), all
   four (invert × psm) combinations `find_text` tries. Every inactive tab
   label ("Hairstyle", "Body", "Outfit", "Accessories") is **completely
   absent from Tesseract's output — not merely low-confidence, absent at
   any confidence, including 0**. Only the active tab ("Face", bold +
   underlined) is detected, at ~96% confidence, in every pass.

2. **Ruled out our own preprocessing.** `_prep()`'s output pixels (post
   grayscale/upscale/autocontrast) in the "Body" glyph region are
   **byte-identical** (min/max/mean/std) between a capture where OCR
   succeeded and one where it failed. Whatever changes, it isn't anything
   this codebase does to the image.

3. **Isolated the actual variable**: a pixel diff of the full OCR crop
   between a working capture (`019.png`/`043.png`/`107.png`) and the two
   failing captures shows differences **only in y=[0,28]** — the macOS
   title bar — never in the tab-strip row itself (y=44-60, where "Body"
   lives), which is pixel-identical. The working captures have a **light
   gray title bar** (VRoid not the frontmost/key window); the failing
   captures have a **dark title bar** (VRoid frontmost/key).

4. **Confirmed causally with a controlled swap.** Pasting the dark
   (focused) title bar onto an otherwise-working image reproduces the
   failure (`find_text` → `None`). Pasting the light (unfocused) title bar
   onto an otherwise-failing image fixes it (`find_text` → `Body` at 97%
   confidence). This is a clean, reversible A/B result, not correlation.

**Conclusion**: this is not a flaw in this driver's cropping, region math,
or normalisation — the mechanism is internal to Tesseract's page
segmentation. A large solid near-black block (the focused title bar)
sharing a page/crop with fainter medium-gray text (inactive tab labels)
causes Tesseract to drop the fainter tokens; heavier-weight ink (the
bold+underlined active tab) survives. Critically, **this fails exactly
when VRoid is correctly focused** — the state automation wants — and
earlier navigations in the same session only "worked" because window
focus had incidentally drifted to the host process between actions.

A parallel, unpatched risk: `current_screen()` classifies the top-level
app screen by requiring `{"face","hairstyle","body"} <= words` from OCR of
the same region, and would misclassify a focused editor as "unknown" under
the identical condition. It was not touched here — different call shape
(passive classifier vs. active navigator), not exercised by the reproduced
incident, and fixing it needs its own verification design. Flagged for
separate follow-up.

## Why not just patch `find_text`

`find_text`/`ocr_words` are the shared locator used for dynamic content
(parameter labels, buttons, dialog text) throughout the driver. The top
tab strip is not dynamic — six labels, fixed text, fixed relative
position, unaffected by character/candidate/session state. Patching
Tesseract's internal segmentation behaviour generically (e.g. forcing a
tile size, disabling adaptive thresholding) is out of this codebase's
control, risks unpredictable side effects on the genuinely dynamic content
`find_text` still has to handle correctly, and isn't the smallest fix for
a control that never needs OCR in the first place.

## Fix: deterministic tab map + colour-based state verification

```python
TOP_TAB_FRAC = {  # window-relative centre, VRoid 2.14.0 native macOS
    "Face": (0.0688, 0.0222), "Hairstyle": (0.1404, 0.0227),
    "Body": (0.2142, 0.0227), "Outfit": (0.2780, 0.0218),
    "Accessories": (0.3610, 0.0218), "Look": (0.4404, 0.0218),
}
```

Calibrated from three independent successful captures at different points
in the same live session — **identical to 5 decimal places**, confirming a
static layout, not a per-frame measurement. Every calibrated click point
was verified to land inside the tab's real (OCR-measured) bounding box,
for all six tabs, with no cross-tab confusion (no tab's click point falls
inside a neighbour's bbox — tabs sit close enough at this pitch that this
was worth checking explicitly).

`open_tab` now clicks the calibrated fraction and verifies success by
looking for VRoid's own accent-blue (`#0096fa`) active-tab underline at
that same x-fraction — a colour-blob check, not text OCR. This lives at
y-fraction 0.0318, well below the title bar (y<0.013), so it is
**structurally immune** to the failure mode above. Verified directly: the
underline check correctly reports Face active / Body inactive on the
*exact two incident captures* that broke OCR, and correctly discriminates
all six tabs pairwise on three independent real post-click screenshots.

Fails closed: an unknown tab name raises before any screenshot or click;
a click that doesn't produce the expected underline raises
`RuntimeError` with no retry and no second click.

## What this does not change

- `find_text`, `ocr_words`, `_prep` — untouched. No risk to other OCR call
  sites; nothing about confidence thresholds or normalisation changed.
- No new automation framework, no retries added to paper over the old
  failure, no change to transaction/recovery semantics or Gate B
  acceptance criteria.
- `current_screen()`'s parallel latent risk (see above) is unresolved.
- Calibration is specific to VRoid Studio 2.14.0's native macOS window at
  the 1410×2295 geometry exercised throughout this session. The mechanism
  (fractions of window width/height, verified against the window actually
  found by `window.find_window()`) generalises across window
  size/position since every downstream calculation is already
  fraction-based, but a materially different aspect ratio or a future
  VRoid layout change would need re-calibration and is not covered by the
  regression tests.


## Deferred work (explicitly out of scope for this repair)

Recorded during Project Lyra Gate B B2 review, not implemented now:

- **Left-hand category mapping.** `TOP_TAB_FRAC` covers only the six
  top-level tabs (Face/Hairstyle/Body/Outfit/Accessories/Look). The
  left-rail sub-categories within a tab (e.g. Face's "Face Sets"/"Eyes
  Sets"/"Irises"/...) still resolve by `_panel_title` OCR verification
  after a coordinate-guess click (`face_category`/`body_category`/
  `hair_category` in `actions.py`), unaffected by this incident and
  untouched here. Map additional categories the same way -- calibrated
  fractions plus a state check -- only when a specific character task
  actually needs one that isn't already covered, not preemptively.
- **Keyboard-shortcut navigation.** VRoid Studio may expose documented
  keyboard shortcuts for tab/category switching as an alternative to
  clicking. Not evaluated here. If considered later, treat it as a new
  mechanism needing its own calibration and regression tests (same bar as
  this repair), not a drop-in replacement.
- **Camera/orientation fixes.** Out of scope for this repair and for Gate
  B generally (see the executor's `capture_views`, which already labels
  captures `current-camera`/`orientation: not_established` rather than
  claiming front/three-quarter/side). Evaluate separately.
- **Category navigation vs. preset application stay distinct.** Selecting
  a left-rail category (read-only navigation, like `open_tab`/
  `face_category`) must not be conflated with clicking a preset tile in
  that category, which *changes the model*. Any future left-menu mapping
  work must preserve this distinction -- a calibrated click that lands on
  a category header is not interchangeable with one that lands on a
  preset thumbnail.
