# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from .spectrum_view import band_centres as band_centres
from _typeshed import Incomplete

BEAT: float
LOOP: float
FLOOR_DB: float
CHORDS: Incomplete
PENTA: Incomplete

class XorShift:
    s: Incomplete
    def __init__(self, seed) -> None: ...
    def next(self): ...
    def uniform(self): ...

class FakeMusic:
    n: Incomplete
    seed: Incomplete
    oct: Incomplete
    bw_oct: Incomplete
    sigma: Incomplete
    tilt: Incomplete
    snare_w: Incomplete
    hat_w: Incomplete
    room_w: Incomplete
    kick_click_w: Incomplete
    def __init__(self, bands, seed: int = 2026) -> None: ...
    def levels(self, t): ...
