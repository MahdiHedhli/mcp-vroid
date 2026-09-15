# macOS Accessibility reconnaissance — VRoid Studio 2.14.0

Recorded 2026-09-15 against the live native app
`/Applications/VRoidStudio.app` with **Lyra.vroid** open. Nothing in this
document was taken from `Lyra.vroid` or `data.bin`; it is only what
Accessibility, Quartz window metadata, and the app bundle expose.

This pass was required **before** implementing screenshot/OCR automation.

## Target

| | |
|---|---|
| App | VRoid Studio 2.14.0 (native, not Proton) |
| Bundle ID | `net.pixiv.vroid.macosx` |
| Engine | Unity IL2CPP (`UnityPlayer.dylib`, `GameAssembly.dylib`, `il2cpp_data`) |
| Process | `VRoid Studio`, pid observed as 84030 |
| Window title (AX) | `VRoid Studio 2.14.0 - Lyra.vroid*` |
| Quartz bounds | `x=-1411 y=-175 w=1410 h=2295` (secondary display, left of main) |
| AX trusted for this agent | **yes** (`AXIsProcessTrusted() == true`) |
| Screen Recording for this agent | **no** (`screencapture` / `CGWindowListCreateImage` fail; macOS 15+ obsolete API) |

## Verdict

**Parameter labels, numeric fields, sliders, tabs, and scroll containers
cannot be addressed semantically through AX.**

The in-window UI is a Unity canvas. The AX tree of the document window is
window chrome only. The preferred path is therefore:

1. **AX** — find / focus / raise the VRoid window, read title, press menu-bar
   items and traffic-light buttons.
2. **Screenshot → OCR/OpenCV → Quartz `CGEvent`** — locate and operate
   Face/Hairstyle/Body widgets, including **Eye Size X**.

Unity's `AXEnhancedUserInterface` / `AXManualAccessibility` flags **cannot
be set** on this process (`AXError`); they do not grow the tree.

## AX tree (document window)

Roles present: `AXApplication`, `AXWindow` (`AXStandardWindow`),
`AXButton` (close / zoom / minimize), `AXGroup` (zoom-button internals),
`AXStaticText` (title bar), `AXMenuBar`, `AXMenuBarItem`, `AXMenu`,
`AXMenuItem`.

Roles **absent** (and needed for `vroid_set_slider`): `AXSlider`,
`AXTextField`, `AXScrollArea`, `AXTabGroup`, `AXValueIndicator`,
`AXList`, `AXCell`.

Window children:

* `AXCloseButton`, `AXZoomButton`, `AXMinimizeButton`
* `AXStaticText` value `VRoid Studio 2.14.0 - Lyra.vroid*`

`AXFocusedUIElement` is the window itself, not an inner control.

Menu bar top-level items: **Apple**, **VRoid Studio**, **Window**. There is
no File/Edit/Face menu that could drive parameters.

Node count before and after the Unity AX flags: **155** (no change).

AX `AXPosition` matched Quartz `kCGWindowBounds` (top-left origin, y down,
including negative coordinates on the left-hand display). Use Quartz
points as the `layout` space; image pixels differ by backing scale.

## Capture blocker (pause reason)

`screencapture -l<windowId>`, `screencapture -R…`, and fullscreen
`screencapture` all returned *could not create image*. Swift
`CGWindowListCreateImage` is **unavailable** on this SDK (obsoleted
macOS 15; "use ScreenCaptureKit"). `CGRequestScreenCaptureAccess()`
opened a system prompt and blocked; the user is quitting/reopening the
agent so Screen Recording can attach to `xai-grok-pager`
(Developer ID `X.AI Corporation`, team `5Y6N3AJ54S`).

After relaunch, grant **Screen Recording** to Grok (and **Accessibility**
if it dropped). Then ScreenCaptureKit / `screencapture` can feed the
existing OCR layer.

## Seiðr-Smiðja / Brúarhönd notes

Studied `hrabanazviking/Seidr-Smidja` (Apache-2.0) `brunhand/daemon/runtime.py`
and `docs/features/brunhand/ARCHITECTURE.md`.

v0.1 does **not** ship a dedicated macOS AX backend. `pyproject.toml`
declares `seidr-smidja[brunhand-mac] = pyobjc-framework-Quartz`; the
daemon actually drives the host with **MSS** (Quartz screenshots) and
**PyAutoGUI** (Quartz `CGEvent` under the hood). `platform.py` is
documented but not present. Reuse the *ideas* (platform shim, Quartz
capture + HID events, capabilities probe, focus-before-act) and write
original code. Do not copy their VRoid File-menu scripts (Windows-oriented).

## Planned split (not implemented yet — paused)

Keep `actions.py` / `locate.py` / MCP tools unchanged. Make
`window.py`, `capture.py`, `input.py` facades:

```
src/mcp_vroid/driver/
  window.py, capture.py, input.py     # re-export selected backend
  wayland/{window,capture,input}.py   # current Hyprland/grim/vpointer/XTEST
  macos/{window,capture,input}.py     # AX window + ScreenCaptureKit/screencapture + CGEvent
```

macOS `clear_field` must send **⌘A** then Delete, not Ctrl+A.

## Milestone 1 (2026-09-15)

Against the live window `VRoid Studio 2.14.0 - Lyra.vroid*` (Face tab):

* Located **Eye Size X** at image (1140, 133) via OCR of the Parameters panel.
* Read numeric box: **0.850**.
* `actions.set_param("Eye Size X", 0.850)` (same path as `vroid_set_slider`).
* Re-read: **0.850**. Character unchanged.

Screen Recording and `screencapture -l<CGWindowID>` work. `CGWindowListCreateImage` is unavailable on this SDK.
