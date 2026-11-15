# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Stills of the chameleon from the side: each a name, a function that returns SVG text, and a width."""

from perch.mascot_chameleon import LIME, NAVY, WHITE, _bug, _sparkle, at, circle, draw, draw_hang, draw_sit, draw_sleep, rect
from perch.vec import Doc


def _study(view, ground=None, scale=1, lift=0, **pose):
    def build():
        doc = Doc()
        doc.add(rect(-1000, -1000, 2000, 2000, NAVY))
        if ground:
            doc.add(ground)
        doc.add(at(0, -lift, draw(doc, **pose), scale=scale))
        return doc.svg(view)

    return build


def _strip(view, frames, spacing):
    """Several poses side by side: *frames* is a list of functions of a Doc."""

    def build():
        doc = Doc()
        doc.add(rect(-3000, -3000, 9000, 6000, NAVY))
        for i, frame in enumerate(frames):
            doc.add(at(i * spacing, 0, frame(doc)))
        return doc.svg(view)

    return build


def _pose(view, pose, turn=0, **options):
    def build():
        doc = Doc()
        doc.add(rect(-3000, -3000, 6000, 6000, NAVY))
        doc.add(at(0, 0, pose(doc, **options), rot=turn))
        return doc.svg(view)

    return build


def _icon():
    # the sitting pose in a round badge; a wide ring of the ground's colour trims what spills over
    doc = Doc()
    doc.add(rect(-1000, -1000, 2000, 2000, NAVY))
    doc.add(circle(-40, -150, 244, 0x123F68))
    doc.add(at(-18, 46, draw_sit(doc, look=(-0.2, 0.1), look_far=(0.5, -0.4), wave=1), scale=1.12))
    doc.add(circle(-40, -150, 444, None, NAVY, 400))
    doc.add(circle(-40, -150, 244, None, LIME, 7))
    return doc.svg((-290, -400, 500, 500))


_FULL = (-262, -326, 508, 420)
_BUG = (360, -128)

STILLS = [
    ("chameleon_full", _study(_FULL), 920),
    ("chameleon_face", _study((18, -238, 222, 185), look=(-0.5, 0.3), look_far=(0.7, -0.4), perch=None), 900),
    ("chameleon_happy", _study(_FULL, mood="happy", colors="brand", hand=1, perch="wire"), 920),
    ("chameleon_curious", _study(_FULL, mood="curious", colors="sunset", look=(0.9, 0.5), look_far=(-0.6, -0.7), curl=0), 920),
    ("chameleon_sleepy", _study(_FULL, mood="sleepy", colors="board", look=(0.2, 0.6), curl=2, perch="wire"), 920),
    ("chameleon_icon", _icon, 400),
    (
        "chameleon_walk",
        _strip((-262, -300, 2080, 384), [lambda doc, s=s: draw(doc, step=s, look=(0.6, 0.2), look_far=(0.2 - s, -0.5)) for s in (0, 0.25, 0.5, 0.75)], 520),
        1840,
    ),
    ("chameleon_climb", _pose((-389, -272, 640, 530), draw, -80, step=0.3, nod=38, perch="stem", look=(0.2, -0.6), look_far=(0.8, 0.2), colors="leaf"), 920),
    ("chameleon_hang", _pose((-180, -76, 508, 420), draw_hang, colors="sunset"), 920),
    ("chameleon_sleep", _pose(_FULL, draw_sleep, colors="board"), 920),
    (
        "chameleon_tongue",
        _strip(
            (-262, -330, 2010, 430),
            [
                lambda doc: draw(doc, look=(1, 0.0), look_far=(1, 0.3), nod=-4, colors="brand", perch="wire") + _bug(_BUG[0] + 4, _BUG[1] + 4, 1.4),
                lambda doc: draw(doc, look=(1, 0.0), look_far=(1, 0.3), nod=-4, tongue=1, target=_BUG, colors="brand", perch="wire") + _bug(_BUG[0] + 4, _BUG[1] + 4, 1.4),
                lambda doc: draw(doc, mood="happy", nod=-8, colors="brand", perch="wire") + _sparkle(250, -150, 15, LIME) + _sparkle(284, -112, 9, WHITE) + _sparkle(232, -98, 7, LIME),
            ],
            670,
        ),
        1840,
    ),
    ("chameleon_sit", _pose((-262, -366, 508, 420), draw_sit, colors="leaf", look=(-0.3, 0.1), look_far=(0.4, -0.3)), 920),
    ("chameleon_sit_wave", _pose((-262, -366, 508, 420), draw_sit, colors="brand", mood="happy", wave=1, perch="wire"), 920),
]
