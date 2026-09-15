"""Shared geometry types used by every platform backend."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass
class Window:
    address: str
    cls: str
    title: str
    x: int
    y: int
    w: int
    h: int
    workspace: int
    focused: bool
    fullscreen: bool = False
    pid: int = 0

    @property
    def geometry(self) -> tuple[int, int, int, int]:
        """(x, y, w, h) in the backend's layout / point coordinate space."""
        return (self.x, self.y, self.w, self.h)

    def to_layout(self, x: float, y: float) -> tuple[float, float]:
        """Window-relative point -> global layout point."""
        return (self.x + x, self.y + y)


@dataclass
class Shot:
    image: Image.Image
    path: Path
    ox: int          # region origin x, layout coords
    oy: int
    scale: float     # image px per layout unit

    @property
    def size(self):
        return self.image.size

    def to_window(self, px: float, py: float) -> tuple[float, float]:
        """Image pixel -> window-relative layout coords."""
        return (px / self.scale, py / self.scale)

    def to_layout(self, px: float, py: float) -> tuple[float, float]:
        return (self.ox + px / self.scale, self.oy + py / self.scale)

    def crop(self, box) -> "Shot":
        l, t, r, b = box
        return Shot(self.image.crop(box), self.path,
                    int(self.ox + l / self.scale), int(self.oy + t / self.scale),
                    self.scale)
