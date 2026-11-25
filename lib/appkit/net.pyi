# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit.net: sockets, HTTP and the clock, with the same calls on every Python."""

from typing import Any, Callable

CIRCUITPYTHON: bool
NTP_HOST: str

def sockets() -> Any:
    """The `socket` module, or on CircuitPython a `socketpool.SocketPool` on `wifi.radio`."""
def recv(sock: Any, size: int) -> bytes:
    """Up to `size` bytes from `sock`, `b""` when the other end has closed."""
def requests() -> Any:
    """An HTTP client with the calls of `requests`.

    Raises:
        ImportError: The client isn't installed.
    """
def sets_clock() -> bool:
    """True where this program keeps the clock (a board), False on a desktop."""
def local_time() -> tuple[int, ...]:
    """The local time as a `time.localtime`-style tuple, from the source set with `set_local_time`."""
def set_local_time(source: Callable[[], tuple[int, ...]]) -> None:
    """Have `local_time` read from `source`, a function returning a `time.localtime`-style tuple."""
def set_clock(year: int, month: int, day: int, hour: int, minute: int, second: int) -> None:
    """Set the board's clock to a UTC time.

    Raises:
        OSError: This is a desktop.
    """
def ntp(timeout: int = 3) -> None:
    """Set the board's clock from NTP. It blocks: call it from a worker.

    Raises:
        OSError: No answer within `timeout` seconds, or this is a desktop.
    """
