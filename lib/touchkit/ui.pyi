# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The board's look, and the few widgets its apps build from."""

from typing import Any, Callable

from appkit.scope import AppScope

HEADER: int
HOME_W: int
font: Any
small: Any
tiny: Any
big: Any
huge: Any
BG: Any
PANEL: Any
KEY: Any
ACCENT: Any
WARN: Any
BAD: Any
GOOD: Any
MUTED: Any
WHITE: Any

def apply_theme() -> None:
    """The dark theme in the board's colours, on the default display."""
def plain(obj: Any) -> Any:
    """`obj` with no style of its own and no scrolling: a bare area."""
def status(scope: AppScope) -> Any:
    """The app's status line label."""
def missing(scope: AppScope, short: str, text: str) -> Any:
    """Say an app can't run here: `short` on the status line and `text` in the middle."""
def hide_button(scope: AppScope, reason: str, below: Any) -> Any:
    """A Hide from Home button under `below`, when there's a home screen; else None."""
def label(parent: Any, text: str = "", font: Any = None, color: Any = None) -> Any: ...
def button(
    parent: Any,
    text: str,
    cb: Callable[[], Any],
    w: int | None = None,
    h: int | None = None,
    font: Any = None,
    color: Any = None,
) -> tuple[Any, Any]:
    """A button that calls `cb()` when tapped. Returns `(button, label)`."""
def box(parent: Any, x: int, y: int, w: int, h: int, color: Any = None) -> Any:
    """A plain rectangle (a card or a panel) at a fixed place."""
def frame(parent: Any, x: int, y: int, w: int, h: int) -> Any:
    """A thin border round a picture drawn straight into the framebuffer."""
def rgb565_image(img: Any, pixels: bytearray | bytes, w: int, h: int, keep: dict[int, Any]) -> None:
    """Show `pixels` (RGB565, `w` x `h`) in LVGL image `img`; `keep` holds the buffer for as long as it shows."""
def decode_jpeg(data: bytes | bytearray | memoryview, max_w: int, max_h: int | None = None) -> tuple[bytearray, int, int]:
    """`(pixels, w, h)`: JPEG `data` decoded to RGB565, scaled down by halves to fit."""
