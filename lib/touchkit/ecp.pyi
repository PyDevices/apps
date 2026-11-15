# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Roku's External Control Protocol, for the remote and Cast."""

from typing import TypedDict

class _TV(TypedDict):
    """A Roku found on the network."""

    host: str
    name: str
    model: str
    power: str

PORT: int
KEY_TIMEOUT: int

def request(host: str, method: str, path: str, timeout: float = 3) -> tuple[int, bytes]:
    """`(status, body)` of one HTTP request to the Roku at `host`."""
def keypress(host: str, key: str) -> int:
    """Press `key` on the Roku at `host`; returns the status code."""
def device_info(host: str) -> _TV | None:
    """The TV at `host`, or None."""
def discover(seconds: float = 2.5) -> list[_TV]:
    """Every Roku that answers SSDP."""
def pick(tvs: list[_TV], prefer: str | None = None, last: str | None = None) -> int | None:
    """The index in `tvs` to choose, or None when `prefer` matches none."""
