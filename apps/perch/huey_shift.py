# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The chameleon's colour change: more colour schemes, and any blend of two.

`between` gives the scheme part of the way from one to another, so a change
of colour is a handful of redraws. Each scheme here comes with the ground it
was made for.
"""

from .huey import COLORS
from .vec import mix

# More schemes, in huey's order: skin, shade, light, belly, spots, deep.
COLORS.update(
    {
        "blossom": (0xF59AB8, 0xD0668F, 0xFFC7D8, 0xFFF1E0, 0xFFFFFE, 0x9A3D68),
        "snow": (0xDCEBF5, 0xA9C6DC, 0xFFFFFE, 0xFEFFFF, 0x7FB2D9, 0x6E93B5),
        "night": (0x3B3F8F, 0x272A6B, 0x6A70C9, 0xC4DC4D, 0xE8FF8A, 0x171A4A),
        "copper": (0xD98A4E, 0xA8602F, 0xF4B77E, 0xFBE3B5, 0x2F7F7A, 0x6E3B1C),
    }
)

# The ground each scheme sits on in the stills.
GROUNDS = {
    "leaf": 0x1F4D3A,
    "brand": 0x0B2A4A,
    "sunset": 0x5A2A5E,
    "board": 0x0E3B3A,
    "blossom": 0x6FBDE8,
    "snow": 0x7C9CC0,
    "night": 0x06122A,
    "copper": 0x3A2A22,
}



def between(a, b, t):
    """Register and return the name of the scheme *t* of the way from *a* to *b*."""
    name = "%s>%s@%d" % (a, b, int(t * 100))
    COLORS[name] = tuple(mix(x, y, t) for x, y in zip(COLORS[a], COLORS[b]))
    return name
