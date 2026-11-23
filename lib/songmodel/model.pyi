# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The song: plain data, shared by every panel and the engine that plays it."""

from typing import Any

_Project = dict[str, Any]
_Track = dict[str, Any]
_Pattern = dict[str, Any]
_Op = dict[str, Any]

VERSION: int
PPQ: int
STEP: int
BEATS_PER_BAR: int
BAR: int

def new_id() -> int: ...
def pattern(bars: int = 1) -> _Pattern: ...
def track(kind: str, instrument: str, name: str | None = None, patch: int = 0) -> _Track: ...
def new_project() -> _Project: ...
def swung(tick: int | float, swing: int | float) -> int | float:
    """Where a note at `tick` plays with `swing` percent applied."""
def migrate(project: _Project) -> _Project:
    """Bring an older project up to date in place."""
def ramp_to(project: _Project, part: str) -> float | None:
    """The tempo the song's `tempo_map` takes `part` to by its end, or None."""
def pattern_at(track: _Track, tick: int | float) -> tuple[int, int]:
    """The pattern a track plays at `tick` in pattern mode, and the tick its start falls on."""
def segments(
    project: _Project, t0: int | float, t1: int | float
) -> list[tuple[int | float, int | float, int | float, dict[int, Any]]]:
    """What plays between ticks `t0` and `t1`, as (from, to, base, patterns)."""
def shown_pattern(track: _Track) -> int:
    """The pattern to show and edit for a track."""
def find_track(project: _Project, track_id: int) -> _Track | None: ...
def resolve(project: _Project, path: list[Any]) -> tuple[Any, Any]:
    """The container and key a path ends in."""
def apply(project: _Project, op: _Op) -> _Project:
    """Apply one op to `project` and return it."""
def track_path(track_id: int, *rest: Any) -> list[Any]: ...
