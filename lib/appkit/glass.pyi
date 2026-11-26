# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Glass controls: buttons that float over an app, see-through so the app shows behind them."""

from typing import Any

#: The glass behind a control, and how much of it shows (of 255).
GLASS: int
GLASS_OPA: int
#: A key on a pane of glass, and how much of its white tint shows.
KEY_OPA: int
#: A control while it's pressed.
PRESSED: int
PRESSED_OPA: int
#: The icon on a control, in pixels.
ICON: int

def side(w: int, h: int) -> int:
    """How big a control is on a `w` by `h` screen, in pixels."""
def pane(obj: Any) -> Any:
    """Make `obj` a pane of glass."""
def key(obj: Any, icon: str) -> Any:
    """Make `obj` a key on a pane, with `icon` at its middle; returns the icon."""
def button(parent: Any, icon: str, size: int, radius: int | None = None) -> Any:
    """A square glass button `size` pixels a side on `parent`, with `icon` at its middle."""
