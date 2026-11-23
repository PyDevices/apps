# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The board's chrome and launcher."""

from typing import Any, Callable, Literal

from appkit import Launcher, Shell
from appkit.scope import AppScope

from . import ui as ui

TOUCH_MS: int
launcher: Launcher | None
boot_presses: int

class TouchLauncher(Launcher):
    """appkit's launcher, keeping the last switches."""

    history: list[tuple[str, str, int | None, int | None]]
    def __init__(self, *args: Any, **kw: Any) -> None: ...
    def switch(self, name: str) -> Literal["start", "switch", "restart"]: ...

class TouchShell(Shell):
    """The board's look: the status bar, a header with the app's title and a status line, and BOOT going home."""

    boot_pin: Any
    def __init__(self, launcher: Launcher, *, data_root: str | None = None, bar: bool = True) -> None: ...
    def make_home_button(self) -> Any: ...
    def lend_boot(self) -> Callable[[], None]:
        """Hand the BOOT button to the running app until the returned function is called."""
    def make_root(self, scope: AppScope) -> Any: ...

def go(name: str) -> None:
    """Switch to app `name` after the current callback."""
def redraw_home_button() -> None:
    """Have LVGL redraw the Home button."""
def quiet_app_timers(app: Any) -> None:
    """Stop the App's own service and refresh timers."""
def touch_period(scope: AppScope, ms: int) -> None:
    """Have LVGL read the touch panel every `ms` while app `scope` is open."""
def heap_text() -> str: ...
def audit() -> dict[str, Any]:
    """What the apps share and must leave as they found it."""
