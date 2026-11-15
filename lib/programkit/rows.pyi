# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Lines of text on a board's display, sent one row at a time."""
from collections.abc import Sequence
from typing import Any

WHITE: int
BLACK: int

def clean(text: str) -> str:
    """Printable ASCII only: the fonts have nothing else."""
def wrap(text: str, width: int) -> tuple[str, str]:
    """Split text at the last space that fits in width, or at width if none does."""

class Rows:
    """Rows of text, each redrawn only when it changes."""

    display: Any
    width: int
    height: int
    count: int
    cols: int
    def __init__(self, display: Any) -> None: ...
    def line(self, row: int, text: str, width: int | None = None) -> None:
        """Put text on a row, replacing what was there; nothing happens if it's unchanged."""
    def lines(self, first_row: int, texts: Sequence[str]) -> None:
        """Put each of `texts` on its own row, starting at `first_row`."""
    def send(self) -> bool:
        """Put one changed row on the panel. Returns False when none was waiting."""
    def send_all(self) -> None:
        """Put every changed row on the panel."""
    def rect(self, x: int, y: int, w: int, h: int, on: bool = True) -> None:
        """Fill a rectangle in white, or black when `on` is False, straight to the panel."""
