# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A log-frequency spectrum analyzer drawn with pygraphics."""

from typing import Any, Callable, Literal

_Color = tuple[int, int, int]

PALETTE: tuple[tuple[float, _Color], ...]
BG_TOP: _Color
BG_BASE: _Color
BG_FLOOR: _Color
GRID: _Color
GRID_MINOR: _Color
BASELINE: _Color
LABEL: _Color
LABEL_DECADE: _Color
LOW_HZ: float
HIGH_HZ: float
LABELS: tuple[int, ...]
ATTACK_S: float
FALL_PER_S: float
PEAK_HOLD_S: float
PEAK_GRAVITY: float
KEY: int

def rgb565(rgb: tuple[int | float, int | float, int | float]) -> int:
    """An RGB colour as an RGB565 value that is never the colour key."""
def mix(a: tuple[float, float, float], b: tuple[float, float, float], t: float) -> tuple[float, float, float]: ...
def palette_at(frac: float) -> _Color:
    """The bar colour at `frac` of full height."""
def band_count_for(plot_w: int) -> int:
    """About one band per 12-16 px, clamped to 16..48."""
def label_text(hz: int) -> str: ...
def band_centres(n: int) -> list[float]:
    """Centre frequency of each of `n` log-spaced bands between `LOW_HZ` and `HIGH_HZ`."""

class SpectrumView:
    """The analyzer's frame: a painted background and the bars drawn over it."""

    width: int
    height: int
    style: Literal["smooth", "segmented"]
    fb: Any
    font: Any
    bands: int
    pitch: int
    gap: int
    bar_w: int
    x0: int
    span_x0: int
    span_w: int
    label_y: int
    refl_h: int
    top: int
    baseline: int
    plot_h: int
    refl_y: int
    cap_h: int
    hi_h: int
    seg_pitch: int
    level: list[float]
    peak: list[float]
    hold: list[float]
    pvel: list[float]
    def __init__(
        self, width: int, height: int, bands: int | None = None, style: Literal["smooth", "segmented"] = "smooth"
    ) -> None: ...
    def freq_x(self, hz: float) -> int: ...
    def update(self, targets: list[float], dt: float) -> None:
        """Move the bars toward `targets` (0..1 per band) over `dt` seconds."""
    def render(self) -> tuple[int, int]:
        """Draw this frame; return `(y, h)`, the row strip that changed."""
    def render_columns(self, blit: Callable[[Any, int, int, int, int], Any]) -> None:
        """Draw this frame bar by bar, calling `blit(buf, x, y, w, h)` for each run of rows that changed."""
    def compose(self) -> bytearray:
        """The whole frame as the panel shows it, rebuilt from the background and the shown state."""
    def strip(self, y: int, h: int) -> memoryview:
        """The bytes of rows `y..y+h` of the frame, for `blit_rect`."""
