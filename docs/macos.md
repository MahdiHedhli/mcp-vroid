# macOS backend

Native VRoid Studio 2.14.0 on macOS is a Unity IL2CPP app
(`net.pixiv.vroid.macosx`). This tree adds a separable driver backend under
`src/mcp_vroid/driver/macos/` so the existing MCP tools and
`actions.py` VRoid flows run without Hyprland, grim, or `vpointer`.

Linux/Wayland remains the default: `window.py` / `capture.py` / `input.py`
import `driver.wayland.*` unless `sys.platform == "darwin"`.

## Permissions

Grant both of these to **the process that launches the MCP server** (Terminal,
Grok, Claude Desktop, … — not VRoid Studio itself):

| Permission | Settings | Used for |
|---|---|---|
| **Accessibility** | Privacy & Security → Accessibility | Find / focus / raise the VRoid window (`AXRaise`, `NSRunningApplication`). Safety checks. |
| **Screen Recording** | Privacy & Security → Screen Recording | Window screenshots via `/usr/sbin/screencapture -l<CGWindowID>` (ScreenCaptureKit on macOS 15+). |

`vroid_status` reports `helpers.ax_trusted` and `helpers.screen_recording`.
A new grant often requires quitting and relaunching the host process.

`native/build.sh` is **not** required on macOS.

## Architecture

```
MCP tools (server.py)  ──unchanged──►  actions.py / locate.py
                                          │
                    window / capture / input   (facades)
                       │                │
              driver/wayland/    driver/macos/
              hyprctl, grim,     AX + Quartz window list,
              vpointer, XTEST    screencapture, CGEvent
```

Settled split:

* **AX / Quartz window list** — process discovery, window geometry, focus,
  raise, title (`VRoid Studio 2.14.0 - …`). Menu bar chrome only.
* **OCR + Quartz `CGEvent`** — every in-canvas widget (parameter labels,
  numeric boxes, sliders, tabs, scroll). Unity does **not** expose these
  through Accessibility. `AXEnhancedUserInterface` /
  `AXManualAccessibility` cannot be set. Do not spend more time trying to
  make sliders AX-addressable unless new evidence appears.

Evidence for the AX gap: [`macos-ax.md`](macos-ax.md).

Coordinate spaces match the Linux driver: tools speak **image pixels** of a
window capture; `Shot.scale` maps to Quartz global points (origin = top-left
of the main display, y down).

Keyboard select-all is **⌘A** (`clear_field`), not Ctrl+A. App shortcuts
that the Linux driver spells `ctrl+…` are mapped to Command.

Events are posted both to the HID tap (real cursor) and to VRoid's pid
(`CGEventPostToPid`) because a CLI MCP host often steals frontmost status
immediately after `activate`.

## Known limitations

* Coupled to **English UI**, VRoid Studio **2.14.0**, as on Linux.
* OCR is the locating story. `_find_label` keeps 1-letter tokens (`X`/`Y`/`Z`)
  so `Eye Size X` is not collapsed into `Eye Size Y`. That is an upstream-
  worthy behaviour change vs mcp-vroid 0.1.0, which skipped tokens shorter
  than 3 characters.
* `read_param` crops a wider numeric box (`0.90–0.995` of window width) so a
  1410-px editor still captures `0.850`; the old `0.963–0.993` crop clipped
  to `50` on that layout.
* `vroid_export_vrm` / Wine save-dialog helpers are still Hyprland/Proton-
  shaped (`hyprctl_json`). Native macOS Save panels are not walked yet.
* `vroid_launch(restart=true)` quits the Mac app via `terminate()`, not
  `pkill VRoidStudio.exe`.
* Hyprland workspace parking is a no-op; `vroid_release` does not hide VRoid.
* Capture uses `screencapture`, not the obsolete `CGWindowListCreateImage`.

## Upstream notes

Safe to propose as an additive PR:

* `driver/wayland/` — move of the current Linux modules
* `driver/macos/` — new
* facades that default to Wayland off Darwin
* `_find_label` 1-letter token fix (Linux benefits too)
* optional `python-xlib` on Linux; PyObjC extras on Darwin

Keep Project Lyra names out of generic source. Do not vendor Seiðr-Smiðja
code; see `NOTICE` for the Quartz-approach attribution.
