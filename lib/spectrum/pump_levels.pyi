# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from .spectrum_view import HIGH_HZ as HIGH_HZ, LOW_HZ as LOW_HZ, band_centres as band_centres
from _typeshed import Incomplete

FLOOR_DB: float
TOP_DB: float
TILT_DB: float
TILT_FROM_HZ: float
STALE_MS: int

class PumpLevels:
    bands: Incomplete
    meter: Incomplete
    peak_db: float
    rms_db: float
    track: Incomplete
    def __init__(self, bands, low_hz=..., high_hz=..., source=None, rate: int = 48000) -> None: ...
    def raw(self): ...
    def levels(self, t=None): ...
    def track_start(self): ...
    def close(self) -> None: ...

class TapLevels(PumpLevels):
    tap: Incomplete
    def __init__(self, bands, rate: int = 48000, low_hz=..., high_hz=..., tap=None, channels: int = 2) -> None: ...
