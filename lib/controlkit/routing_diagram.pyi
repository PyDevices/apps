# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Boxes and arrows for a small modulation graph: who shapes whom, and who is heard."""
from collections.abc import Callable, Collection, Hashable, Iterable
from typing import Any

from .theme import _Theme

def arrange(
    nodes: Iterable[Hashable], edges: Iterable[tuple[Hashable, Hashable]], carriers: Collection[Hashable]
) -> dict[Hashable, tuple[float, int]]:
    """Where each node goes: `{name: (column, row)}`, row 0 at the bottom."""

class RoutingDiagram:
    """A diagram of a modulation graph at (`x`, `y`) in `parent`, `width` x `height`."""

    theme: _Theme
    on_press: Callable[[RoutingDiagram, Hashable], None] | None
    width: int
    height: int
    obj: Any
    nodes: list[Hashable]
    edges: list[tuple[Hashable, Hashable]]
    carriers: list[Hashable]
    feedback: tuple[Hashable, Hashable] | None
    places: dict[Hashable, tuple[float, int]]
    selected: Hashable | None
    colors: dict[Hashable, int | None]
    def __init__(
        self,
        parent: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        theme: _Theme,
        nodes: Iterable[Hashable] = (),
        edges: Iterable[tuple[Hashable, Hashable]] = (),
        carriers: Iterable[Hashable] = (),
        feedback: tuple[Hashable, Hashable] | None = None,
        on_press: Callable[[RoutingDiagram, Hashable], None] | None = None,
    ) -> None: ...
    def set_graph(
        self,
        nodes: Iterable[Hashable],
        edges: Iterable[tuple[Hashable, Hashable]],
        carriers: Iterable[Hashable],
        feedback: tuple[Hashable, Hashable] | None = None,
    ) -> None:
        """Draw this graph in place of the one shown. The selection and the colours start again."""
    def set_selected(self, name: Hashable | None) -> None:
        """Light node `name` as the one being edited, or none with None."""
    def set_color(self, name: Hashable, rgb: int | None) -> None:
        """Light node `name` in `rgb`, or put it out with None."""
    def node(self, name: Hashable) -> Any:
        """Node `name`'s LVGL object."""
