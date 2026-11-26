# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The status bar: Home and the title at the left; the connections button, the clock, the network and the rest from the right."""

from collections.abc import Callable
from typing import Any

from .scope import AppScope

HEIGHT: int
ICON: int
TICK_MS: int
BACKGROUND: int
FOREGROUND: int
FULL_MIN: tuple[int, int]
SHORT: int
TALL: int
TALL_FROM: int
FULL_ICON: int
TITLE_MIN: int
STATUS_ROW_UNDER: int
TITLE: int
MUTED: int

def height_for(w: int, h: int) -> int:
    """The full bar's height on a `w` x `h` screen."""

_Read = Callable[[], tuple[str | None, str | None] | None]

class Item:
    """One thing the bar shows."""

    name: str
    read: _Read
    every: int
    on_click: Callable[[], object] | None
    def __init__(self, name: str, read: _Read, every: int = 1, on_click: Callable[[], object] | None = None) -> None: ...

def clock_item() -> Item:
    """The time, `14:05`."""
def net_item(registry: Any) -> Item:
    """The network carrying traffic, by its icon."""
def bluetooth_item(registry: Any) -> Item:
    """Bluetooth, while something on the radio is connected or chosen."""
def audio_item(registry: Any, on_click: Callable[[], object] | None = None) -> Item:
    """Where sound goes."""
def cast_item(registry: Any, on_click: Callable[[], object] | None = None) -> Item:
    """The cast icon while the screen goes somewhere, with "viewing" while someone watches."""
def battery_item(source: Any) -> Item:
    """The battery from the board's `battery()`."""
def board_battery() -> Any:
    """The battery the imported board config gives, or None."""

class Bar:
    """The bar, on `lv.layer_top()`."""

    registry: Any
    on_picker: Callable[[str | None], object] | None
    compact: bool
    height: int
    icon: int
    status_below: bool
    header: Any
    title: Any
    title_icon: Any
    status_line: Any
    under: Any
    group: Any
    root: Any
    home: Any
    left: Any | None
    right: Any
    connections: Any
    items: list[Item]
    def __init__(
        self,
        registry: Any = None,
        on_home: Callable[[], object] | None = None,
        on_picker: Callable[[str | None], object] | None = None,
        compact: bool | None = None,
        items: list[Item] | None = None,
        tick_ms: int = ...,
    ) -> None: ...
    def open(self, title: str, status: bool = True, icon: str | None = None) -> tuple[Any, Any]:
        """Set the bar up for the app being opened: its title after `icon`, and a fresh status line."""
    def status_row(self) -> Any:
        """The status line in its row under the bar, made when the app first asks; the area makes room at once."""
    def chrome_height(self) -> int:
        """How much of the screen's top the bar takes while it shows."""
    def default_items(self) -> list[Item]:
        """The built-in items this device has."""
    def add(self, item: Item, owner: AppScope | None = None) -> Item:
        """Show `item`; with `owner` it goes when that app closes."""
    def remove(self, name: str) -> None:
        """Take the item called `name` off the bar."""
    def status(self) -> list[tuple[str, str | None, str | None]]:
        """`(name, icon, text)` for each item showing something, in the order added."""
    def tick(self) -> None:
        """Poll endpointkit and redraw what changed."""
    def is_shown(self) -> bool: ...
    def hide(self) -> None:
        """Hide the bar until `show`."""
    def show(self) -> None:
        """Show the bar again."""
    def set_home(self, visible: bool) -> None:
        """Show the Home button or not."""
    def close(self) -> None:
        """Stop the timer and delete the bar."""
