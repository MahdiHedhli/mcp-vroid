"""macOS backend: AX for window chrome, ScreenCaptureKit/screencapture + Quartz CGEvent.

VRoid Studio's Unity canvas does not expose parameter widgets through
Accessibility (see docs/macos-ax.md). Window find/focus/raise use AX +
Quartz window list; locating sliders falls back to the existing OCR layer.
"""
