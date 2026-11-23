# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Type on a USB keyboard plugged into the board's host port."""

from typing import Any

READ_MS: int

class HostKeys:
    """Sends what the keyboards in use type to `appkit.keys`."""

    registry: Any
    read_ms: int
    open: dict[str, Any]
    def __init__(self, registry: Any, read_ms: int = ..., look_ms: int | None = None) -> None: ...
    def in_use(self) -> list[Any]:
        """The `keys` endpoints on the host port to read: the chosen ones, or every one while none is chosen."""
    def update(self) -> None:
        """Open the keyboards that came into use and close the ones that left."""
    def read(self) -> None:
        """Type what each open keyboard sent since the last read."""
    def close(self) -> None:
        """Stop reading: close every keyboard and stop following `keys`."""
