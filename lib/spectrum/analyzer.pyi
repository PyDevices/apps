# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The spectrum analyzer as a widget any app can put on its screen."""

from typing import Any, Callable, Literal, Protocol

from .spectrum_view import SpectrumView as SpectrumView, band_count_for as band_count_for

class _LevelSource(Protocol):
    """A source of band levels: `levels(t)` gives one 0..1 level per band."""

    def levels(self, t: float) -> list[float]: ...

class _Display(Protocol):
    """A display driver."""

    width: int
    height: int
    def blit_rect(self, buf: Any, x: int, y: int, w: int, h: int) -> Any: ...

class _Timer(Protocol):
    def deinit(self) -> Any: ...

FRAME_MS: int
REPORT_S: int

def levels_for(audio_out: Any) -> Callable[[int], _LevelSource]:
    """Levels of whatever an audiodev `AudioOut` is playing, for `Spectrum`."""

class Spectrum:
    """A spectrum analyzer drawn on `display_drv`, fed by `source`."""

    display_drv: _Display
    x: int
    y: int
    view: SpectrumView
    source: _LevelSource
    report: bool
    last_report: str
    timer: _Timer | None
    present_rows: bool
    present_all: bool
    def __init__(
        self,
        display_drv: _Display,
        source: _LevelSource | Callable[[int], _LevelSource],
        *,
        bands: int | None = None,
        height: int | None = None,
        y: int | None = None,
        x: int = 0,
        width: int | None = None,
        style: Literal["smooth", "segmented"] = "smooth",
        report: bool = False,
    ) -> None: ...
    def start(self, app: Any, period_ms: int = ...) -> Spectrum:
        """Paint the meter's background and start drawing from `app`'s timer.

        `app` is anything with an `every(callback, period=ms)` that returns a timer.
        """
    def stop(self) -> None:
        """Stop drawing; the last frame stays on the panel."""
    def tick(self, _: Any = None) -> None:
        """Draw one frame."""
    def capture(self, path: str) -> tuple[int, int]:
        """Write the meter's rows to `path` as raw little-endian RGB565; returns its width and height."""
