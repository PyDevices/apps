# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The endpointkit providers this device has, registered once for the picker and the bar."""

from collections.abc import Callable
from typing import Any

HOSTS: tuple[str, ...]
BOARD_PROVIDERS: tuple[tuple[str, Callable[[Any], bool]], ...]
HOST_PROVIDERS: tuple[tuple[str, Callable[[Any], None]], ...]

def register(registry: Any = None) -> list[str]:
    """Register the device's providers once; returns the names registered."""

def device(endpoints: list[Any]) -> str | None:
    """The device name a computer's backend opens for the first of `endpoints`, or None for the default."""
