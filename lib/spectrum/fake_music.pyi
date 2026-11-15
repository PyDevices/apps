# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Band levels that move like a band playing, with no audio."""

from .spectrum_view import band_centres as band_centres

BEAT: float
LOOP: float
FLOOR_DB: float
CHORDS: tuple[tuple[float, tuple[float, float, float]], ...]
PENTA: tuple[float, ...]

class XorShift:
    """A seeded xorshift random number generator."""

    s: int
    def __init__(self, seed: int) -> None: ...
    def next(self) -> int: ...
    def uniform(self) -> float: ...

class FakeMusic:
    """Band levels for time `t` seconds, over log-spaced bands."""

    n: int
    seed: int
    oct: list[float]
    bw_oct: float
    sigma: float
    tilt: list[float]
    snare_w: list[float]
    hat_w: list[float]
    room_w: list[float]
    kick_click_w: list[float]
    def __init__(self, bands: int, seed: int = 2026) -> None: ...
    def levels(self, t: float) -> list[float]: ...
