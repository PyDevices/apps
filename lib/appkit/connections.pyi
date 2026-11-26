# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The endpointkit providers this device has, registered once for the picker and the bar."""

from collections.abc import Callable
from typing import Any

HOSTS: tuple[str, ...]
BROWSERS: tuple[str, ...]
BOARD_PROVIDERS: tuple[tuple[str, Callable[[Any], bool]], ...]
HOST_PROVIDERS: tuple[tuple[str, Callable[[Any], None]], ...]
WEB_PROVIDERS: tuple[tuple[str, Callable[[Any], None]], ...]
USB_HOST_APART: dict[str, bool]

def register(registry: Any = None) -> list[str]:
    """Register the device's providers once; returns the names registered."""

def usb_host(registry: Any = None) -> bool:
    """Register what's plugged into the board's USB host port once; True when it's registered."""

def device(endpoints: list[Any]) -> str | None:
    """The device name a computer's backend opens for the first of `endpoints`, or None for the default."""
