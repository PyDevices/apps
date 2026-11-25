# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Shell: what's around an app, and what it hands each app's scope."""

from typing import Any

from . import data as data
from .bar import Bar
from .hostkeys import HostKeys
from .launcher import Launcher
from .picker import Picker
from .scope import AppScope

ROUND_MARGIN: int

def is_round() -> bool:
    """Whether the default display is a round panel."""
def round_corner(size: int, d: int, margin: int = ...) -> tuple[int, int]:
    """`(x, y)` of the top left of a `d`-pixel circle at the top right of a round screen `size` pixels across."""

class Shell:
    """The plainest shell: apps get the whole screen, with a Home button in the corner."""

    launcher: Launcher
    home_button: Any
    picker: Picker | None
    bar: Bar | None
    host_keys: HostKeys | None
    def __init__(self, launcher: Launcher, *, data_root: str | None = None, bar: bool = False) -> None: ...
    def make_bar(self) -> Bar:
        """The status bar, made once, with Home on it when there's a home screen."""
    def make_host_keys(self) -> HostKeys | None:
        """What reads a keyboard on the board's USB host port, made once, or None without one."""
    def bar_mode(self, scope: AppScope) -> str:
        """What the app's `app.json` asks for: "shell", "own" or "none"."""
    def home_title(self) -> str:
        """What the bar says on the home screen: "Home"."""
    def make_home_button(self) -> Any:
        """The Home button, made once: an LVGL object, or None for no button."""
    def open_picker(self, kind: str | None = None) -> Picker:
        """Open the picker over the running app, at `kind`'s page or the list of kinds."""
    def prepare(self, scope: AppScope) -> None:
        """Fill `scope` before the app's `main` runs: its `root`, `size` and `rect`."""
    def make_root(self, scope: AppScope) -> Any:
        """The LVGL object the app builds on: a screen, or with the bar showing, the area below it."""
    def bar_area(self, screen: Any) -> Any:
        """A plain area of `screen` below the bar, which grows to the whole screen while the bar hides."""
    def measure(self, scope: AppScope) -> None:
        """Set `scope.size` and `scope.rect` from `scope.root`."""
