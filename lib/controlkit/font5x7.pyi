# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A 5x7 dot-matrix font for printable ASCII, drawn for this package."""

FIRST: int
LAST: int
DATA: bytes

def rows(char: str) -> bytes:
    """The seven row bytes of `char`."""
