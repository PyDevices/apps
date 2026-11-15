# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The chameleon's colour change: more colour schemes, and any blend of two.

`between` gives the scheme part of the way from one to another, so a change
of colour is a handful of redraws. Each scheme here comes with the ground it
was made for.
"""

from . import mascot_chameleon
from .mascot_chameleon import COLORS
from .vec import Doc, at, mix, rect

# More schemes, in mascot_chameleon's order: skin, shade, light, belly, spots, deep.
COLORS.update(
    {
        "blossom": (0xF59AB8, 0xD0668F, 0xFFC7D8, 0xFFF1E0, 0xFFFFFF, 0x9A3D68),
        "snow": (0xDCEBF5, 0xA9C6DC, 0xFFFFFF, 0xFFFFFF, 0x7FB2D9, 0x6E93B5),
        "night": (0x3B3F8F, 0x272A6B, 0x6A70C9, 0xC4DC4C, 0xE8FF8A, 0x171A4A),
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

_VIEW = (-262, -326, 508, 420)


def between(a, b, t):
    """Register and return the name of the scheme *t* of the way from *a* to *b*."""
    name = "%s>%s@%d" % (a, b, int(t * 100))
    COLORS[name] = tuple(mix(x, y, t) for x, y in zip(COLORS[a], COLORS[b]))
    return name


def _panels(cells, columns):
    # cells: (ground colour, scheme name, pose) laid out on a grid of studies
    def build():
        doc = Doc()
        w, h = _VIEW[2], _VIEW[3]
        for i, (ground, scheme, pose) in enumerate(cells):
            x, y = (i % columns) * w, (i // columns) * h
            doc.add(rect(x, y, w + 1, h + 1, ground))
            doc.add(at(x - _VIEW[0], y - _VIEW[1], mascot_chameleon.draw(doc, colors=scheme, **pose)))
        rows = (len(cells) + columns - 1) // columns
        return doc.svg((0, 0, w * columns, h * rows))

    return build


def _shift(a, b, steps=5):
    cells = []
    for i in range(steps):
        t = i / (steps - 1)
        pose = {"look": (0.5 - t, 0.1), "look_far": (0.6, -0.4 + 0.6 * t), "perch": "twig"}
        if i == steps - 1:
            pose["mood"] = "happy"
        cells.append((mix(GROUNDS[a], GROUNDS[b], t), between(a, b, t), pose))
    return _panels(cells, steps)


_ALL = ("leaf", "brand", "sunset", "board", "blossom", "snow", "night", "copper")
_POSES = (
    {},
    {"mood": "happy", "hand": 1, "perch": "wire"},
    {"mood": "curious", "look": (0.9, 0.5), "look_far": (-0.6, -0.7)},
    {"perch": "wire", "look": (-0.4, 0.2)},
    {"mood": "happy"},
    {"look": (0.2, -0.6), "look_far": (0.8, 0.4)},
    {"mood": "sleepy", "curl": 2},
    {"mood": "curious", "perch": "wire", "hand": 1},
)

STILLS = [
    ("chameleon_schemes", _panels([(GROUNDS[n], n, _POSES[i]) for i, n in enumerate(_ALL)], 4), 1600),
    ("chameleon_shift", _shift("leaf", "sunset"), 1600),
    ("chameleon_shift_night", _shift("blossom", "night"), 1600),
]
