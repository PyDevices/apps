# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The song as an hmilink model: any screen as the groovebox's front panel."""

from typing import Any, Callable, Protocol

from .model import _Op, _Project

class Model:
    """The hmilink model base class, as this module uses it."""

    doc: Any
    def __init__(self, doc: Any = None) -> None: ...
    def describe(self) -> dict[str, Any]: ...
    def apply(self, op: dict[str, Any]) -> dict[str, Any]: ...
    def telemetry(self) -> dict[str, Any] | None: ...
    def command(self, name: str, args: Any) -> dict[str, Any] | None: ...

class Host(Protocol):
    """What answers for the transport, the engines, the playhead and meters."""

    def command(self, name: str, args: Any) -> dict[str, Any] | None: ...
    def telemetry(self) -> dict[str, Any] | None: ...

RANGES: dict[str, list[int]]

def to_pointer(project: _Project, op: _Op) -> tuple[str, str, Any]:
    """An op as `(kind, pointer, value)` for `Panel.send`."""
def from_pointer(op: dict[str, Any]) -> _Op:
    """A JSON Patch op as the op `model.apply` takes."""

class SongModel(Model):
    """The song a device holds."""

    forward: Callable[[_Op], Any] | None
    host: Host | None
    samples: dict[int, dict[str, int]]
    loaded: Any
    def __init__(
        self,
        project: _Project | None = None,
        forward: Callable[[_Op], Any] | None = None,
        host: Host | None = None,
    ) -> None: ...
    def describe(self) -> dict[str, Any]: ...
    def sample_cost(self) -> dict[str, Any]:
        """The preloaded samples, per SoundFont track and in all, against the arena."""
    def apply(self, op: dict[str, Any]) -> dict[str, Any]: ...
    def load(self, project: _Project, by: Any = None) -> None:
        """Replace the whole song and tell every panel."""
    def telemetry(self) -> dict[str, Any] | None: ...
    def command(self, name: str, args: Any) -> dict[str, Any] | None: ...
