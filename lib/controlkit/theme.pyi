# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The panel's finishes: every colour it draws, in one table per theme."""
from collections.abc import Mapping
from typing import TypeAlias

_Theme: TypeAlias = Mapping[str, int | str | None]

BLACK: dict[str, int | str | None]
SILVER: dict[str, int | str | None]
THEMES: dict[str, dict[str, int | str | None]]

def resolve(theme: str | Mapping[str, int | str | None] | None) -> Mapping[str, int | str | None]:
    """A complete theme from a name, a dict, or None (`black`)."""
