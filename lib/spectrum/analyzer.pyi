# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from .spectrum_view import SpectrumView as SpectrumView, band_count_for as band_count_for
from _typeshed import Incomplete

FRAME_MS: int
REPORT_S: int

def levels_for(audio_out): ...

class Spectrum:
    display_drv: Incomplete
    x: Incomplete
    y: Incomplete
    view: Incomplete
    source: Incomplete
    report: Incomplete
    last_report: str
    timer: Incomplete
    present_rows: Incomplete
    present_all: Incomplete
    def __init__(self, display_drv, source, *, bands=None, height=None, y=None, x: int = 0, width=None, style: str = 'smooth', report: bool = False) -> None: ...
    def start(self, app, period_ms=...): ...
    def stop(self) -> None: ...
    def tick(self, _=None) -> None: ...
    def capture(self, path): ...
