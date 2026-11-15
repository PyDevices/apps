# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Stills of the chameleon's colours: each a name, a function that returns SVG text, and a width."""

from perch import hue
from perch.hue_shift import GROUNDS, between, mix
from perch.vec import Doc, at, rect


_VIEW = (-262, -326, 508, 420)


def _panels(cells, columns):
    # cells: (ground colour, scheme name, pose) laid out on a grid of studies
    def build():
        doc = Doc()
        w, h = _VIEW[2], _VIEW[3]
        for i, (ground, scheme, pose) in enumerate(cells):
            x, y = (i % columns) * w, (i // columns) * h
            doc.add(rect(x, y, w + 1, h + 1, ground))
            doc.add(at(x - _VIEW[0], y - _VIEW[1], hue.draw(doc, colors=scheme, **pose)))
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
    ("hue_shift", _shift("leaf", "sunset"), 1600),
    ("hue_shift_night", _shift("blossom", "night"), 1600),
]
