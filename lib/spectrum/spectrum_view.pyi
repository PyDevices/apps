# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
from _typeshed import Incomplete

PALETTE: Incomplete
BG_TOP: Incomplete
BG_BASE: Incomplete
BG_FLOOR: Incomplete
GRID: Incomplete
GRID_MINOR: Incomplete
BASELINE: Incomplete
LABEL: Incomplete
LABEL_DECADE: Incomplete
LOW_HZ: float
HIGH_HZ: float
LABELS: Incomplete
ATTACK_S: float
FALL_PER_S: float
PEAK_HOLD_S: float
PEAK_GRAVITY: float
KEY: int

def rgb565(rgb): ...
def mix(a, b, t): ...
def palette_at(frac): ...
def band_count_for(plot_w): ...
def label_text(hz): ...
def band_centres(n): ...

class SpectrumView:
    width: Incomplete
    height: Incomplete
    style: Incomplete
    fb: Incomplete
    font: Incomplete
    bands: Incomplete
    pitch: Incomplete
    gap: Incomplete
    bar_w: Incomplete
    x0: Incomplete
    span_x0: Incomplete
    span_w: Incomplete
    label_y: Incomplete
    refl_h: Incomplete
    top: Incomplete
    baseline: Incomplete
    plot_h: Incomplete
    refl_y: Incomplete
    cap_h: Incomplete
    hi_h: Incomplete
    seg_pitch: Incomplete
    level: Incomplete
    peak: Incomplete
    hold: Incomplete
    pvel: Incomplete
    def __init__(self, width, height, bands=None, style: str = 'smooth') -> None: ...
    def freq_x(self, hz): ...
    def update(self, targets, dt) -> None: ...
    def render(self): ...
    def render_columns(self, blit) -> None: ...
    def compose(self): ...
    def strip(self, y, h): ...
