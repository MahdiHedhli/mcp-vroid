# T5b swallowed-dispatch incident: investigation, repair, and open question

## Incident

During Gate B's T5b fault case, Chest Size's restoration reported
`restore_dispatched: True` but the very next fresh observation (a genuinely
new screenshot, ~6s later) still read the chip's pre-dispatch value
(`0.72`, not the requested `0.00`). Confirmed with the two real captures
now kept as test fixtures (`tests/fixtures/t5b-swallowed-dispatch/`): the
parameter panel is byte-identical across the reported dispatch.

The established symptom, stated precisely: **dispatch returned normally;
the requested state was not observed.**

## What the audit ruled out

- **Observation freshness/staleness.** `Coordinator._observe_until_readable`
  always calls `driver.observe(label, None)`; `LiveDriver.observe` with
  `shot=None` always takes a brand-new screenshot after a settle delay.
  Confirmed by the journal: the failing observation's timestamp is ~6s
  after `restore_dispatched`, consistent with a fresh capture + OCR pass,
  not a reused Shot object. **Not the cause.**
- **Accounting / truthiness bugs.** Read `manifest.py`, `transaction.py`,
  `attended.py` end to end for `0` / `0.0` / `"0.000"` / `None` / `""`
  mishandling. Every prior/observed/target comparison uses an explicit
  `is None` check or `values_match()` (`Decimal`-based, at UI precision),
  never Python truthiness on a possibly-zero number. `_restore_one`
  restoring to a `0.0` prior, and a `0.0`-target `verified_noop`, are both
  covered by regression tests (`test_reliability_sweep.py::ZeroValuedRestoration`)
  and pass on the unmodified accounting code. **Not the cause.**
- **Dispatched-vs-restored conflation.** Already correctly distinct before
  this sweep: a readable-but-wrong restore observation was already reported
  as `outcome: "failed"`, never `"verified"`. **Not a defect** (verified by
  re-reading `_restore_one` and by `RecoveryFailureAccounting` tests).
- **Duplicate/ambiguous targeting.** `locate_param` already raises
  `AmbiguousTarget` before any click if a page shows more than one row with
  the same caption; Chest Size is not a duplicated label. **Not the cause.**

## Leading hypothesis (code-supported, not proven live)

`_type_value` (the function both forward writes and restoration dispatch
through) used to wrap its click in `I.set_safety(False)` / `set_safety(True)`
— the *only* click anywhere in the driver that skips the standard
`_guard() -> assert_vroid_focused()` check. Every other click (scrolling to
locate a row, selecting a tab, etc.) re-confirms VRoid is the OS-level
focused/key window first, focusing it if not.

The click that opens a numeric field for editing is delivered via Quartz
directly to VRoid's pid (`CGEventPostToPid`), which can visually land
regardless of OS-level focus. But the very next step,
`type_field_value`, types through **AppleScript System Events**, which
delivers keystrokes to whatever the OS considers frontmost *at that
moment* — not pid-targeted. `type_field_value` does call
`tell application "VRoid Studio" to activate` first, but that happens
*after* the click, not before it. If VRoid was not actually key at the
moment of the click (skipped guard, nothing re-asserts it), a plausible
Unity-side outcome is: the click is visually indistinguishable from a
normal one, but the canvas does not register it as placing a text-edit
caret; the later `activate` brings the window forward but cannot
retroactively make that click a focus event; `Cmd+A` + digits + `Return`
then apply to no specific field and do nothing.

This matches the observed symptom exactly (normal return, chip unchanged)
and is a real, demonstrable divergence from this driver's own established
pattern (every other click is guarded; this one deliberately was not, with
no comment explaining why). It has **not** been confirmed live as the
actual mechanism — no live desktop access was used in this sweep.

**Live probe, if pursued in the next attended session** (not run here):
before the fix, add temporary logging of `W.is_vroid_focused()` immediately
before the chip click on a handful of forward writes and restores; compare
against which ones subsequently fail to commit. A clean correlation would
confirm the hypothesis; its absence would mean the search continues
elsewhere (Category B's "double-posted input events" and "asynchronous
calls returning before the application processes input" remain untested
alternatives).

## Repair

1. **`_type_value` now uses the ordinary guarded click**, identical to
   every other click in the driver (`src/mcp_vroid/driver/actions.py`).
   Addresses the leading hypothesis directly; does not introduce a new
   input backend, and does not add a blanket sleep.

2. **A bounded, explicitly journaled, fresh-relocate write retry**, applied
   identically to forward writes (`Coordinator.execute`) and restoration
   (`Coordinator._restore_one`), in
   `appearance/vroid/executor/transaction.py`. This is a defensive
   structural improvement independent of whether (1) is the true root
   cause: it detects the specific, unambiguous "readable, but exactly the
   pre-dispatch value" signature — never a generic wrong-value mismatch,
   never an unreadable chip (those already have their own, separate,
   correct handling) — and gives the dispatch **exactly one** more attempt
   with a genuinely fresh `locate()` (never reusing the stale shot/match),
   journaled as `write_dispatch_retry` / `restore_dispatch_retry` so it is
   never confused with the original attempt. If the retry also fails, the
   original failure is reported honestly (`mismatch` / `failed`) — never
   silently converted into success, never retried a second time.

Both changes are additive to the existing, already-correct recovery
accounting (dispatched≠restored, reverse order, primary/recovery errors
kept separate, no re-entrant rollback) — none of that required repair.

## Coverage added

`test_reliability_sweep.py` exercises the real `Coordinator` against a
stateful fake desktop (application/field focus distinct, pending-vs-
committed value, injectable stale/delayed observations) through: a
dispatch ignored once then succeeding; a dispatch ignored persistently
(never falsely verified); focus lost between locate and dispatch; a
genuine wrong-value mismatch (never retried); a stale post-write
observation that self-corrects; the restore-side equivalents of the first
two; transient vs. persistent unreadable observation (pre-existing
behavior, confirmed untouched); exact-zero restoration and zero-vs-None
prior handling; a partial cross-section mutation followed by an exception;
an exception immediately after dispatch; recovery dispatch failure and
recovery verification failure with primary/recovery errors kept separate;
no re-entrant rollback; and journal-failure-before-dispatch (fails closed,
zero input attempted).

`test_t5b_swallowed_dispatch_fixtures.py` replays the two actual incident
screenshots: confirms they are byte-identical in the parameter panel and
both OCR to the pre-dispatch value, never the target — real evidence for
*what* happened. It explicitly does not claim this proves *why* (a
screenshot cannot see OS event delivery), and notes that OCR-ing both
frames again is internal-consistency evidence, not an independent ground
truth check (the live session's recorded human reading is that check).

## Remaining gap

The leading hypothesis is unconfirmed live. If the guard restoration in
(1) does not fully resolve recurrence, the bounded retry in (2) provides a
safety net but the underlying cause would still need the live probe above,
or investigation of the alternative Category B mechanisms not yet tested
(double-posted events, async completion races).
