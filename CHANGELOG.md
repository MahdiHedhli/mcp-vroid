# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [semantic versioning](https://semver.org/).

## [Unreleased]

### Added

* **macOS backend** (`src/mcp_vroid/driver/macos/`): AX + Quartz window
  discovery, `screencapture` window capture, Quartz `CGEvent` pointer/keys.
  Selected at import via `sys.platform`; Wayland modules moved to
  `src/mcp_vroid/driver/wayland/`. MCP tool names are unchanged.
* Accessibility reconnaissance of native VRoid Studio 2.14.0: Unity does not
  expose parameter widgets through AX (`docs/macos-ax.md`, `docs/macos.md`).

### Changed

* `_find_label` keeps 1-letter tokens (`X`/`Y`/`Z`) so `Eye Size X` is not
  matched as `Eye Size Y`. Linux benefits from the same fix.
* `read_param` uses a wider numeric-box crop so non-2560 layouts still OCR
  values such as `0.850`.
* `python-xlib` is Linux-only; PyObjC frameworks are Darwin-only.

### Added (inventory)

* Read-only `vroid_inventory` and `schema/vroid-2.14/body.json` (labels and
  control types only — not character values). Generic `vroid_export_params`,
  `vroid_plan_params`, `vroid_apply_params`; apply aborts before mutation if
  any label is unresolved.

## [0.1.0] — 2026-08-24

First public release.

### Added

* **MCP server** (`mcp-vroid`, stdio) exposing 18 tools over VRoid Studio:
  * lifecycle — `vroid_launch`, `vroid_status`, `vroid_release`
  * seeing — `vroid_screenshot`, `vroid_find_text`, `vroid_find_button`,
    `vroid_current_screen`
  * raw input — `vroid_click`, `vroid_drag`, `vroid_scroll`, `vroid_type`,
    `vroid_key`
  * flows — `vroid_new_character`, `vroid_open_tab`, `vroid_set_slider`,
    `vroid_set_color`, `vroid_export_vrm`, `vroid_save_project`
* **Driver engine** (`mcp_vroid.driver`): `grim` capture, tesseract OCR and
  OpenCV colour matching for locating, `hyprctl` for window management, and
  input through a `zwlr_virtual_pointer_unstable_v1` helper (pointer) plus
  X11 XTEST (keyboard and wheel).
* **`native/vpointer`** — a small C client for the Wayland virtual-pointer
  protocol, built by `native/build.sh`. Moves the real compositor cursor and
  needs no `/dev/uinput` access.
* **Session-environment recovery** so the server works when an MCP client
  launches it with a sanitised environment.
* **Focus guard** — every acting tool refuses to run unless VRoid Studio is
  the focused window; the idle screensaver is dismissed rather than typed
  into.
* **`vroid-driver` CLI** for driving the same engine from a shell.
* `scripts/smoke_test.py` — starts the server, lists tools, calls the
  read-only ones; never sends input.
* Documentation: README, [`docs/ui-map.md`](docs/ui-map.md).

### Known limitations

Calibrated against VRoid Studio 2.14.0 (English) at 2560×1440 / scale 1.25 on
Hyprland. See the README's *Limitations and brittleness* section.

[0.1.0]: https://github.com/nhodges/mcp-vroid/releases/tag/v0.1.0
