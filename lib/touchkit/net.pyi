# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Wi-Fi for the board's apps: when it's on is the set's call."""

from . import settings as settings

def hostname() -> str | None:
    """The board's name on the network, without `.local`, or None."""
def up() -> bool:
    """True when the station is connected; when it isn't, starts a join."""
def start_webrepl() -> None:
    """Start WebREPL, once, when `settings.json` doesn't turn it off."""
def webrepl_on() -> bool:
    """True when WebREPL is listening, whoever started it."""
def boot() -> None:
    """Join a known network quietly, then start WebREPL."""
def keep_time() -> None:
    """Set the board's clock once the station has joined, and again each day."""
def setup_job() -> None:
    """The phone setup page until a network is joined: a job for the foreground loop."""
def rssi() -> int | None:
    """The signal from the access point in dBm, or None off the network."""
def ip() -> str | None:
    """This board's IPv4 address, or None off the network."""
def ntp(timeout: int = 2) -> None:
    """Set the clock from NTP (a blocking call: run it on the worker)."""
