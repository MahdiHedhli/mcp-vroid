# mcp-vroid

An **MCP server that drives VRoid Studio's GUI**. It gives any MCP client
(Claude Code, or anything else that speaks the protocol) a set of tools to
launch the app, look at it, find widgets in the picture, click and type, set
parameters, and export a `.vrm` — on **Arch + Hyprland (Wayland)**, with
VRoid Studio running under **Steam/Proton**.

There is no scripting API in VRoid Studio, so this works the only way that is
available: screenshot the window, locate things with OCR and colour matching,
and inject real pointer and keyboard events.

```
   grim ──► PNG ──► tesseract / cv2 ──► (x, y) ──► virtual pointer / XTEST
    ▲                                                        │
    └────────────────────  screenshot again  ◄───────────────┘
```

The engine under the server is the `tools/vroid-driver` spike from my
`arrakis` project, vendored here as `mcp_vroid.driver` — same code, repackaged
so it can be installed and started by an MCP client.

---

## Requirements

| thing | why |
|---|---|
| **Hyprland** (>= 0.55, Lua dispatch API) | window discovery, focus, workspaces |
| **VRoid Studio** via Steam/Proton (appid `1486350`) | the app being driven |
| `grim` | screenshots |
| `tesseract` + `eng` traineddata | OCR |
| `gcc`, `wayland-scanner`, `libwayland-client` | building the pointer helper |
| Xwayland (`DISPLAY`) | keyboard and wheel go through X11 XTEST |
| Python **3.11+**, `uv` | the server itself |

Python deps (`uv sync` installs them): `mcp`, `pillow`, `numpy`,
`opencv-python-headless`, `pytesseract`, `python-xlib`.

## Install

```bash
git clone https://github.com/nhodges/mcp-vroid
cd mcp-vroid
uv sync                 # virtualenv + dependencies
bash native/build.sh    # builds native/vpointer  <-- REQUIRED, not optional
```

`native/build.sh` compiles a ~150-line C client for
`zwlr_virtual_pointer_unstable_v1` (the protocol XML is vendored under
`native/protocols/`). Without it, every pointer tool fails with
`native/vpointer missing`. `vroid_status` reports whether it is present.

Why a C helper: `ydotool` is not installed on the reference machine and
`/dev/uinput` is `0600 root:root`, so evdev injection would need sudo or a
udev rule. The Wayland virtual-pointer protocol needs neither, moves the real
compositor cursor, and works over any window.

### Register it with a client

Claude Code:

```bash
claude mcp add vroid -- uv run --directory /path/to/mcp-vroid mcp-vroid
```

Generic `mcpServers` JSON:

```json
{
  "mcpServers": {
    "vroid": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-vroid", "mcp-vroid"]
    }
  }
}
```

Clients often launch servers with a **sanitised environment**. This server
recovers `XDG_RUNTIME_DIR`, `WAYLAND_DISPLAY`, `HYPRLAND_INSTANCE_SIGNATURE`
and `DISPLAY` from the runtime dir at startup (`src/mcp_vroid/session_env.py`)
so `hyprctl`/`grim`/XTEST work anyway; `vroid_status` shows what it had to
fill in. Anything already in the environment wins.

Optional environment variables:

| var | default | meaning |
|---|---|---|
| `MCP_VROID_CAPTURES` | `$XDG_STATE_HOME/mcp-vroid/captures` | where screenshots are written |
| `MCP_VROID_OUT` | `$XDG_STATE_HOME/mcp-vroid/out` | default dir for exports/saves |
| `MCP_VROID_VPOINTER` | `<checkout>/native/vpointer` | path to the pointer helper |
| `MCP_VROID_MAX_IMAGE_PX` | `1600` | longest edge of images sent to the client (0 = never downscale) |

## Tools

**Lifecycle**

| tool | what it does |
|---|---|
| `vroid_launch(restart=false, timeout=240)` | Start VRoid via Steam if needed, park it on Hyprland workspace 9, remember the workspace you were on, focus + fullscreen it. `restart=true` kills the running instance first — unsaved work is lost. |
| `vroid_status()` | Window present/focused/title/geometry, active workspace, capture dirs, and whether `vpointer`/`grim`/`tesseract`/`hyprctl` are available. Read-only, no OCR. |
| `vroid_release()` | Switch back to the workspace the user was on. VRoid keeps running on ws 9. |

**Seeing**

| tool | what it does |
|---|---|
| `vroid_screenshot(region?, tag?, whole_screen?, full_resolution?)` | Capture the window (or the whole output, for the Wine save dialog), save it to the captures dir, and return it as MCP image content so the client's model can look at it. Reports the native image size and the downscale factor applied for transport. |
| `vroid_find_text(query, region?, exact?, limit?)` | Fresh capture + tesseract; returns matching word boxes and centres in image px. Pass `region` — full-frame OCR takes ~10 s, a panel ~2 s. |
| `vroid_find_button(color='primary'\|'disabled', label?, region?)` | Finds VRoid's solid `#0096FA` pills by colour, because tesseract loses white-on-blue labels. A grey pill means *disabled*. |
| `vroid_current_screen()` | `start` / `editor` / `export_vrm` / `hair_editor` / `unknown`. |

**Acting (raw input)**

| tool | what it does |
|---|---|
| `vroid_click(x, y, space='image', button='left', double=false)` | Glides the pointer in a few steps (so hover states fire) and clicks. |
| `vroid_drag(x1, y1, x2, y2, space='image', button='left')` | Press → 24-step glide → release. Right-drag orbits the camera, middle-drag pans. |
| `vroid_scroll(dy, dx=0, x?, y?, space='image')` | Wheel, as X11 buttons 4/5 (6/7 horizontal). Park the pointer over the panel you mean to scroll. |
| `vroid_type(text, clear_first=false)` | Types into the focused widget over XTEST. |
| `vroid_key(combo, times=1)` | `Return`, `Escape`, `ctrl+s`, `ctrl+shift+s`, … |

**Acting (flows)**

| tool | what it does |
|---|---|
| `vroid_new_character(base='Fem'\|'Masc')` | Start screen → Create New → base → editor. |
| `vroid_open_tab(name)` | Face / Hairstyle / Body / Outfit / Accessories / Look. |
| `vroid_set_slider(label, value)` | Scrolls the Parameters panel to the row and types an exact value into its numeric box. |
| `vroid_set_color(label, hex)` | Same, for a `#RRGGBB` colour box. |
| `vroid_export_vrm(path, avatar_name, creator, version='1.0')` | The whole Export-as-VRM walk, including the VRM Settings metadata modal and Wine's save dialog. `version` picks VRM1.0 or VRM0.0. |
| `vroid_save_project(name?)` | Ctrl+Shift+S to an explicit `.vroid` path, or a plain Save with no argument. |

Every acting tool focuses VRoid first and **refuses to act if the focused
window is not VRoid Studio**.

## How to drive it

Mostly: **screenshot → look → locate → act → screenshot again.**

1. `vroid_launch()`
2. `vroid_screenshot()` and *look at the image*
3. `vroid_find_text("Export")` (or `vroid_find_button()`) for coordinates
4. `vroid_click(x, y)` — coordinates from a *fresh* capture, always
5. `vroid_screenshot()` to confirm what actually happened

Rules of thumb learned the hard way in the original spike:

* **Read the whole frame, not a crop.** A "Close Hairstyle Editor" confirm
  modal sat in the middle of the screen for six failed clicks because the
  check only OCR'd the top 60 px.
* **Don't judge change by the 3D viewport.** VRoid dithers every frame, so a
  full-window diff reads ~0.98 even when nothing happened. Watch a UI strip.
* **Prefer numeric boxes to slider drags.** `vroid_set_slider` types an exact
  value; dragging is for controls that have no box.
* **Primary buttons are found by colour, not text.** A grey pill where you
  expect blue is the app telling you a required field is empty.
* OCR of a full 2560×1440 frame takes ~10 s. Pass a region.

### Coordinate spaces

Three spaces are in play, and they are all different:

| space | size on the reference machine | who uses it |
|---|---|---|
| Hyprland **layout** (logical) | 2048 × 1152 | `hyprctl`, the virtual pointer |
| **image pixels** of a capture | 2560 × 1440 | tesseract, cv2, everything you see |
| **X11** pixels (Xwayland) | 2560 × 1440 | XTEST |

Tools take and return **image px** (`space="image"`) by default and convert
internally, so hand `vroid_find_text` output straight to `vroid_click`. If
`MCP_VROID_MAX_IMAGE_PX` downscaled the picture you were shown, multiply
coordinates you read off it by the inverse of the reported `downscale` factor
first — or just ask `vroid_find_text`, which always reports native px.

## UI map (VRoid Studio 2.14.0, English)

Coordinates are **image px on a 2560×1440 capture** of the fullscreen window.
Treat them as hints — the tools locate by OCR first.

**Start screen** — `Create New` `+` card at ≈ (118, 218), caption at
(118, 328); `New` / `Open` top-right at (2439, 99) / (2495, 100); Sample
Models grid below. Create New opens a modal *"Select a base to start with"*
with captions `Fem` (1199, 862) and `Masc` (1359, 862) — click the thumbnail
~100 px above the caption.

**Editor** — tab strip at y ≈ 23: `Face` 97 · `Hairstyle` 198 · `Body` 302 ·
`Outfit` 392 · `Accessories` 509 · `Look` 622. Hamburger `☰` at (29, 23) →
Save (Ctrl+S), Save As… (Ctrl+Shift+S), import/bulk export, undo/redo, back
to model selection — **Escape does not close this menu**, click elsewhere.
Toolbar top-right: camera (2415, 23), **share/export** (2464, 23), kebab `⋮`
(2512, 23). Left icon rail (x ≈ 24, first icon y ≈ 77, then every ~48 px) =
sub-category for the current tab. Left panel = preset grid with
`Presets`/`Custom` at y ≈ 120. Right panel = Customize, then Parameters.

**Right-panel controls**

| control | drive it by |
|---|---|
| slider | the numeric box at x ≈ 2505 (`vroid_set_slider`); the track spans x ≈ 2278 → 2516 with 0.0 centred |
| colour | the `#RRGGBB` box at x ≈ 2450 (`vroid_set_color`) |
| checkbox / radio | click the square/circle |
| accordion | click the caption (e.g. `> Reduce Polygons`) |
| dropdown | only in the native Wine dialogs; click, then arrow keys |

`Body` parameters start `Model's Height : 161.2 cm`, then `Fem Height`,
`Masc Height`, `Body Size`, `Head Size`, `Head Width`, `Head Tip (Y)`,
`Neck Length/Thickness/Width`, `Soften Collarbone`, … `Face` parameters:
`Eye Size X/Y`, `Eyes Position (X/Y)`, `Rotate Eye Socket`, `Inner/Outer Eye
Slant`, `Iris Size X/Y`, `Gaze (Y)`, … (~40 rows; the tools scroll for you).

**Hair editor** — Hairstyle tab → left-rail part icon → `Custom` sub-tab →
`+ Create New` → right panel `Edit Hairstyle`. Inside: `Add Freehand Hair
Guides` / `Add Procedural Hair Guides`, a `Hair Groups` list, a tool palette
at (330 / 365 / 398 / 432, 83), undo/redo at (76, 23) / (133, 23). **Leaving
asks first**: the `✕` at (23, 23) pops a *Close Hairstyle Editor* modal with
`Save as new item` / `Overwrite` / `Close without saving`.

**Export as VRM** — share icon (2464, 23) → `Export as VRM` → full-screen
export page with the blue `Export` pill at ≈ (2412, 197) → **VRM Settings**
modal (centred, ~x 1000–1560, scrollable): `Export Format` radios
`VRM1.0`/`VRM0.0`, `Avatar Name` **required**, `Version`, `Creators`
**required**, copyright/contact/references, usage checkboxes; the Export pill
stays **grey and dead** until both required fields are filled → **Wine save
dialog** (its own window, title `Export`): the `File name:` field opens
focused and selected, so typing a Windows path replaces it and Return fires
the default button. The Proton prefix maps `Z:\` to `/`, so `/home/nuri/x` is
`Z:\home\nuri\x`. Do *not* click a `Save` located by OCR: the `Save in:`
label matches the same needle.

## What is brittle

* **OCR is the whole locating story.** Small, letter-spaced or light-on-dark
  labels get split or dropped (`Export` → `E` + `xport`). Icons have no text
  at all — those anchors are hard-coded fractions of the window and will move
  if pixiv reflows the UI.
* **Fixed anchors are fractions calibrated on 2560×1440 at scale 1.25.** A
  different monitor may need them re-measured.
* **Modals appear outside your search region** and swallow clicks silently.
* **Timing.** The 3D viewport takes ~5 s to appear after a base is chosen;
  export takes 5–30 s (longer for heavy models).
* **The Wine dialog is a separate window** with its own class and geometry —
  use `vroid_screenshot(whole_screen=true)` there.
* **Language.** These needles assume the English UI. If VRoid comes up
  Japanese, switch it in kebab `⋮` → Settings → Language.
* **The idle screensaver** can grab the session mid-run. The guard refuses to
  type into it and closes that one window (and only that one) before acting.

## Security note

**This server injects real mouse and keyboard events into your live desktop
session and takes screenshots of it.** That is the entire point, and it is
also the risk:

* Screenshots may capture anything on the output — `whole_screen=true`
  captures everything, and captures are written to disk unencrypted.
* Keystrokes go to whatever holds focus. The driver refuses to act unless
  VRoid Studio is the focused window, but a compromised or careless prompt
  can still click anywhere *inside* VRoid.
* `vroid_launch(restart=true)` kills VRoid Studio and loses unsaved work.
* Nothing here is sandboxed and there is no confirmation step.

**Run it attended**, on a session you are watching, and don't leave an agent
driving it unsupervised. `vroid_release()` gives the desktop back when you're
done.

## Development

```bash
uv run python scripts/smoke_test.py             # start the server, list tools, call vroid_status
uv run python scripts/smoke_test.py --screenshot # + one passive capture if VRoid is open
uv run vroid-driver shot                        # the original driver CLI, still here
```

`vroid-driver` (`mcp_vroid.driver.cli`) is the spike's shell interface —
`launch`, `shot`, `find`, `click`, `tab`, `slider`, `export`, `cam`,
`apply-params`, … — handy for debugging without an MCP client in the loop.

## Credits and licence

The driver (`src/mcp_vroid/driver/`, `native/`) started life as the
`tools/vroid-driver` spike in my own `arrakis` project and is included here
with the MCP server wrapped around it.

MIT — see [LICENSE](LICENSE).
