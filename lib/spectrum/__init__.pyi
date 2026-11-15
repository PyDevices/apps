# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The spectrum analyzer in an app's area, sharing the panel with LVGL."""

from typing import Any, Callable, Iterable, Protocol

from appkit.scope import AppScope

from .analyzer import _LevelSource, Spectrum

class _Redrawable(Protocol):
    def invalidate(self) -> Any: ...

def meter(
    scope: AppScope,
    source: _LevelSource | Callable[[int], _LevelSource],
    top: int,
    x: int = 0,
    width: int | None = None,
    height: int | None = None,
    bands: int | None = None,
    report: bool = False,
) -> Spectrum:
    """A `Spectrum` (not started) in `scope`'s area, from its row `top` to the bottom, or the given rectangle there."""
def pump_tap(rate: int, channels: int) -> Callable[[int], _LevelSource]:
    """A level source for whatever the audio pump plays, push streams too."""
def start(m: Spectrum, scope: AppScope, above: Iterable[_Redrawable] = ()) -> None:
    """Start `m` on `scope`'s timer without clearing the rest of the panel."""
def stop(m: Spectrum | None) -> None: ...
