# VRoid Studio 2.14 parameter schema

Capability catalog (labels + control types), **not** a character preset.
Do not treat numbers from a live session as VRoid defaults; those belong
in a per-character manifest owned by the caller (for example a Lyra
`appearance/vroid/` tree, outside this repo).

Discovered by read-only OCR of the Parameters panel on native VRoid Studio
2.14.0 (English). No `data.bin` / executable reverse engineering.

`body.json` lists Whole Body slider labels. Ranges and factory defaults are
not published in app resources (UTF-8/UTF-16 scans of `data.unity3d` found
none of these English strings).
