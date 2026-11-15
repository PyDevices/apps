# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Hover styles for LVGL apps: a control lights up under the mouse."""

from typing import Any

#: How wide the outline is, in pixels, and how strongly it shows.
WIDTH: int
OPACITY: int

def apply(disp: Any = None) -> None:
    """Add hover styles to `disp`'s theme (the default display's if omitted)."""
