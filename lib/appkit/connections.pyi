# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The endpointkit providers this device has, registered once for the picker and the bar."""

from typing import Any

HOSTS: tuple[str, ...]

def register(registry: Any = None) -> list[str]:
    """Register the device's providers once; returns the names registered."""
