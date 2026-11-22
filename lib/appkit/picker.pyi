# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The picker: one screen to choose every connection the device has."""

from typing import Any

import endpointkit

TITLES: tuple[tuple[str, str, str], ...]
OTHER_ICON: str
POLL_MS: int

def title(kind: str) -> str:
    """What the picker calls `kind`: "Audio out" for `audio.out`."""
def icon(kind: str) -> str:
    """The iconkit name of `kind`'s icon."""
def kinds(registry: endpointkit.Registry) -> list[str]:
    """The kinds `registry` has providers for, in `TITLES` order, then the rest by name."""
def summary(registry: endpointkit.Registry, kind: str) -> str:
    """One line on what `kind` uses now, and whose pin it is."""
def rows(registry: endpointkit.Registry, kind: str) -> list[tuple[endpointkit.Endpoint, bool, str]]:
    """The endpoints of `kind`, as `(endpoint, chosen, detail)`."""
def toggle(registry: endpointkit.Registry, kind: str, endpoint_id: str, confirm: bool = False) -> list[str]:
    """What tapping `endpoint_id` does: the new choice for `kind`, made; returns the ids now chosen."""

class Picker:
    """The picker overlay: made hidden, shown by `open`."""

    registry: endpointkit.Registry
    kind: str | None
    group: Any
    asking: Any
    root: Any
    list: Any
    def __init__(self, registry: endpointkit.Registry | None = None, parent: Any = None, poll_ms: int = ...) -> None: ...
    def is_open(self) -> bool: ...
    def open(self, kind: str | None = None) -> None:
        """Show the picker over everything, at `kind`'s page or the list of kinds."""
    def close(self) -> None:
        """Hide it; the choices made stay made."""
    def tick(self) -> None:
        """Poll the registry and redraw what changed."""
    def show(self, kind: str | None) -> None:
        """Draw the list of kinds (`kind` None) or one kind's endpoints."""
    def choose(self, endpoint_id: str, confirm: bool = False) -> None:
        """Tap `endpoint_id` on the kind on show; a conflict opens a question first."""
