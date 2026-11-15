# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Band levels from audiodsp's audiometer, fed in C."""

from typing import Any

from .spectrum_view import HIGH_HZ as HIGH_HZ, LOW_HZ as LOW_HZ, band_centres as band_centres

FLOOR_DB: float
TOP_DB: float
TILT_DB: float
TILT_FROM_HZ: float
STALE_MS: int

class PumpLevels:
    """A meter on `source`, an `audiopump.Tap` at `rate`."""

    bands: int
    meter: Any
    peak_db: float
    rms_db: float
    track: list[Any] | None
    def __init__(
        self, bands: int, low_hz: float = ..., high_hz: float = ..., source: Any = None, rate: int = 48000
    ) -> None: ...
    def raw(self) -> tuple[int, bytearray, int, int]:
        """`(seq, levels bytes, peak, rms)` straight from C."""
    def levels(self, t: float | None = None) -> list[float]: ...
    def track_start(self) -> list[Any]:
        """Record each band's loudest, quietest and summed raw level from now on."""
    def close(self) -> None: ...

class TapLevels(PumpLevels):
    """Any audiopump stream, through the pump's tap."""

    tap: Any
    def __init__(
        self,
        bands: int,
        rate: int = 48000,
        low_hz: float = ...,
        high_hz: float = ...,
        tap: Any = None,
        channels: int = 2,
    ) -> None: ...
