# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Send an HTTP POST in pieces and read the answer as it arrives."""

from typing import Any

class Reply:
    """An HTTP response: `status`, `headers` (names in lower case), and the body through `read`."""

    status: int
    headers: dict[str, str]
    keep: bool
    def __init__(self, sock: Any, stream: Any, session: Session | None = None) -> None: ...
    def read(self, size: int) -> bytes:
        """Up to `size` bytes of the body, and an empty bytes once it has all been read."""
    def read_all(self, most: int) -> bytes:
        """The whole body, which must be `most` bytes or fewer."""
    def close(self) -> None:
        """Let the reply go."""

def split(url: str) -> tuple[bool, str, int, str]:
    """`(secure, host, port, path)` of an http or https `url`."""
def post(url: str, headers: dict[str, str], pieces: list[Any], timeout: float = 30) -> Reply:
    """POST `pieces` to `url`, on a connection of its own."""

class Session:
    """Requests to one server over a connection kept open between them."""

    idle: float
    opened: int
    resent: int
    def __init__(self, idle: float = 60) -> None: ...
    def warm(self, url: str, timeout: float = 30) -> None:
        """Open a connection to `url`'s server now, if no good one is open."""
    def post(self, url: str, headers: dict[str, str], pieces: list[Any], timeout: float = 30) -> Reply:
        """As `post`, on the kept connection."""
    def close(self) -> None:
        """Close the connection, if one is open."""
