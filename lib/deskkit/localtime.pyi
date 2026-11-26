# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""deskkit.localtime: keep the board's clock right, and read it in local time."""
from collections.abc import Callable
from typing import Any

gmtime: Callable[..., tuple[int, ...]]
offset_s: int | None
zone: str | None

def is_set() -> bool:
    """Return True once the clock holds a real date."""
def parse_http_date(text: str) -> tuple[int, int, int, int, int, int]:
    """Return `(year, month, day, hour, minute, second)` from a `Date` header."""
def sync() -> bool:
    """Set the clock from the network. It blocks: call it from a worker."""
def due() -> bool:
    """Return True when the clock is unset, or this program hasn't set it in a day."""
def finds_place() -> bool:
    """Return True where the program looks up its place from its public IP address: on a board, and in a browser page."""
def parse_ip_zone(reply: dict[str, Any]) -> tuple[str, int | None]:
    """Return `(zone, offset_s)` from an ipwho.is reply."""
def from_geojs(reply: dict[str, Any]) -> dict[str, Any]:
    """Return a GeoJS reply in the shape of an ipwho.is one."""
def parse_ip_place(reply: dict[str, Any]) -> dict[str, Any] | None:
    """Return the place an ipwho.is reply points at, for Weather to start on."""
def follow_ip_zone() -> bool:
    """Take the timezone, and Weather's place until one is chosen, from the public IP address of the board or the browser."""
def keep_board_clock() -> None:
    """Copy the clock to the board's own clock chip (its `rtc` role), where it has one."""
def resync_if_due() -> None:
    """Set the clock, the timezone and the place from the IP when the clock is unset or a day has passed."""
def network_moved() -> None:
    """Another network carries traffic now: the next `resync_if_due` sets the clock and finds the place again."""
def finding() -> bool:
    """Return True while a board or a browser page hasn't yet tried to find where it is."""
def now() -> tuple[int, ...]:
    """Return the local time as a `time.gmtime`-style tuple."""
def clock_time() -> tuple[int, int, int]:
    """Return the local `(hour, minute, second)`."""
