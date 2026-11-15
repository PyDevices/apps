# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""deskkit.shell: swipe between apps, drift back to the first, and sleep at night."""
from typing import Any

from appkit.shell import Shell
from appkit.launcher import Launcher

from . import localtime as localtime

def is_awake(hour: int, weekday: int, awake: tuple[int, int] | None, weekends: bool) -> bool:
    """Return True when the screen belongs on at this time."""
def tune_touch(indev: Any) -> None:
    """Make a one-finger swipe easy on `indev`."""

class DeskShell(Shell):
    """Give each app the whole screen, with no buttons around it."""

    apps: tuple[str, ...]
    awake: tuple[int, int] | None
    weekends: bool
    idle_ms: int
    def __init__(
        self,
        launcher: Launcher,
        apps: tuple[str, ...],
        *,
        awake: tuple[int, int] | None,
        weekends: bool,
        idle_ms: int,
    ) -> None: ...
    def make_root(self, scope: Any) -> Any: ...
