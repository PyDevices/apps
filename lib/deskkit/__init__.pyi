# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A clock and the weather on a screen that sits on a desk."""
from typing import Any

APPS: tuple[str, ...]
launcher: Any

def run(
    *,
    hostname: str | None = None,
    apps: tuple[str, ...] = ...,
    awake: tuple[int, int] | None = (7, 18),
    weekends: bool = False,
    idle_ms: int = 60000,
) -> None:
    """Join Wi-Fi, set the clock and run `apps` until the program ends."""
