# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The chameleon from other sides: head-on, turned toward you, from behind, from above.

Each view sits above the origin like the side view in `huey`:
x to the right, y down, the top of the perch at y = 0. Each returns its
shapes for a `vec.Doc` and takes the same colours, moods and eyes.
"""

from .huey import COLORS, _eye, _foot, _hand, _perch, _spiral, _spiral_points
from .vec import at, circle, ellipse, limb, path, smooth

_PINK = 0xFF8F8F


def _tail(cx, cy, r0, w0, start, turns, skin, shade, light):
    """The wound tail with its inner shade line and outer glint."""
    return (
        _spiral(cx, cy, r0, r0 / 7, w0, w0 / 4, start, turns, skin)
        + path(smooth(_spiral_points(cx, cy, r0, r0 / 7, start, turns, -w0 * 0.31, -w0 / 16, 0.04, 0.9, 36)), None, shade, w0 * 0.14)
        + path(smooth(_spiral_points(cx, cy, r0, r0 / 7, start, turns, w0 / 4, w0 / 16, 0.02, 0.42, 20)), None, light, w0 * 0.09)
    )


def _pose(mood, blink, look, look_other):
    if look_other is None:
        look_other = look
    if mood == "sleepy":
        blink = max(blink, 0.6)
    return blink, look_other, mood == "happy"


def front(doc, look=(0.0, 0.15), look_other=None, blink=0, mood="calm", colors="leaf", hand=0, curl=1.0, perch="twig"):
    """The chameleon facing you.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        look: Where the eye on the left points, each of x and y from -1 to 1.
        look_other: Where the eye on the right points, or None for the same way.
        blink (float): 0 with the eyes open, 1 closed.
        mood (str): "calm", "happy", "curious" or "sleepy".
        colors (str): A name from `huey.COLORS`.
        hand (float): 0 with both hands on the perch, 1 with one raised in a wave.
        curl (float): How tightly the tail is wound: 0 loose, 1 at rest, 2 tight.
        perch (str): "twig", "wire", or None for no perch.
    """
    skin, shade, light, belly, spots, deep = COLORS[colors]
    blink, look_other, happy = _pose(mood, blink, look, look_other)
    out = []
    # the tail, hanging out to one side behind him
    tx, ty = -134, -70
    out.append(limb(-30, -66, tx + 35, ty - 30, 0.14, 38, 27, skin))
    out.append(_tail(tx, ty, 46, 27, -40, 1.25 + 0.3 * curl, skin, shade, light))
    # hind legs, knees out to the sides
    for s in (-1, 1):
        out.append(limb(s * 56, -62, s * 104, -44, -s * 0.2, 30, 24, shade))
        out.append(limb(s * 104, -46, s * 96, -6, -s * 0.2, 22, 16, shade))
    # the crest, seen end on above the shoulders
    out.append(circle(-30, -170, 11, deep) + circle(30, -170, 11, deep) + circle(0, -176, 12, deep))
    # the body, with the pale belly down his front
    out.append(path(smooth([(0, -176), (58, -156), (84, -98), (70, -44), (0, -28), (-70, -44), (-84, -98), (-58, -156)], True), skin))
    out.append(path(smooth([(-58, -156), (-84, -98), (-70, -44), (-30, -31), (-52, -56), (-62, -98), (-46, -146)], True), shade))
    out.append(path(smooth([(0, -128), (38, -112), (48, -66), (30, -36), (0, -30), (-30, -36), (-48, -66), (-38, -112)], True), belly))
    for s in (-1, 1):
        out.append(limb(s * 56, -138, s * 72, -84, s * 0.14, 12, 5, shade))
        out.append(circle(s * 62, -72, 5.5, spots))
        out.append(circle(s * 66, -54, 3.6, spots))
    # the shadow the head throws on his chest
    out.append(ellipse(0, -114, 48, 13, shade, opacity=0.4))
    if perch:
        out.append(_perch(perch))
    out.append(_foot(-96, 3, shade, deep))
    out.append(_foot(96, 3, shade, deep))
    # the arms
    out.append(limb(-50, -84, -44, -10, 0.24, 28, 17, skin))
    out.append(_foot(-44, 3, skin, deep))
    if hand > 0:
        hx, hy = 44 + 82 * hand, -10 - 112 * hand
        out.append(limb(58, -92, hx, hy, -0.24 + 0.36 * hand, 28, 16, skin))
        if hand > 0.5:
            out.append(_hand(hx, hy, skin, deep, 24))
        else:
            out.append(_foot(hx, hy + 8, skin, deep))
    else:
        out.append(limb(50, -84, 44, -10, -0.24, 28, 17, skin))
        out.append(_foot(44, 3, skin, deep))

    # the head: a tall helmet, the casque its peak, the snout toward you
    out.append(path(smooth([(0, -292), (34, -262), (64, -214), (74, -166), (56, -128), (0, -112), (-56, -128), (-74, -166), (-64, -214), (-34, -262)], True), skin))
    out.append(path(smooth([(0, -292), (-34, -262), (-64, -214), (-74, -166), (-58, -132), (-50, -168), (-40, -214), (-16, -262)], True), shade))
    # the casque's ridges, running down to each brow
    out.append(limb(4, -280, 10, -236, 0.06, 7, 2.5, light))
    out.append(path("M-4 -284Q-30 -252 -44 -214", None, deep, 2.6, opacity=0.5))
    out.append(path("M6 -284Q32 -252 46 -214", None, shade, 2.6))
    # the snout: a soft ridge down the middle, nostrils either side
    out.append(ellipse(3, -172, 8, 16, light))
    out.append(circle(-11, -150, 2.6, deep) + circle(11, -150, 2.6, deep))
    # the lower jaw, pale like the belly
    out.append(path("M-60 -144Q0 -112 60 -144Q62 -126 44 -118Q0 -104 -44 -118Q-62 -126 -60 -144Z", belly))
    if happy:
        out.append(path("M-58 -146Q0 -124 58 -146Q44 -110 0 -108Q-44 -110 -58 -146Z", deep))
        out.append(path("M-22 -116Q0 -126 22 -116Q0 -108 -22 -116Z", _PINK))
    else:
        out.append(path("M-64 -152Q-62 -143 -54 -140Q0 -116 54 -140Q62 -143 64 -152", None, deep, 4))
    if mood == "curious":
        out.append(circle(0, -122, 9, _PINK) + circle(2, -125, 2.8, 0xFFC0C0))
    # the turret eyes, standing out past the sides of the head
    out.append(_eye(doc, -70, -192, 39, look, blink, happy, skin, shade, light, deep))
    out.append(_eye(doc, 70, -192, 39, look_other, blink, happy, skin, shade, light, deep))
    return b"".join(out)


def three_quarter(doc, look=(0.4, 0.1), look_far=None, blink=0, mood="calm", colors="leaf", curl=1.0, perch="twig"):
    """The chameleon turned halfway toward you, his body running back along the perch.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        look: Where the near eye points, each of x and y from -1 to 1.
        look_far: Where the far eye points, or None for the same way.
        blink (float): 0 with the eyes open, 1 closed.
        mood (str): "calm", "happy", "curious" or "sleepy".
        colors (str): A name from `huey.COLORS`.
        curl (float): How tightly the tail is wound: 0 loose, 1 at rest, 2 tight.
        perch (str): "twig", "wire", or None for no perch.
    """
    skin, shade, light, belly, spots, deep = COLORS[colors]
    blink, look_far, happy = _pose(mood, blink, look, look_far)
    out = []
    # the tail, smaller for being farther away
    tx, ty = -112, -84
    out.append(limb(-50, -82, tx + 32, ty - 27, 0.10, 36, 26, skin))
    out.append(_tail(tx, ty, 42, 25, -40, 1.25 + 0.3 * curl, skin, shade, light))
    # far legs
    out.append(limb(96, -56, 122, -8, -0.2, 24, 17, shade))
    out.append(limb(-58, -44, -66, -8, 0.24, 24, 16, shade))
    for bx, by, r in ((-70, -112, 8), (-56, -130, 9), (-38, -144, 10), (-18, -152, 10)):
        out.append(circle(bx, by, r, deep))
    # the body, shortened as he turns away
    out.append(path(smooth([(-84, -84), (-56, -130), (-6, -152), (52, -140), (86, -96), (76, -46), (24, -24), (-36, -26), (-76, -46)], True), skin))
    out.append(path(smooth([(-84, -84), (-76, -46), (-36, -26), (24, -24), (76, -46), (78, -58), (24, -38), (-34, -40), (-70, -56)], True), shade))
    out.append(path(smooth([(-6, -70), (34, -84), (70, -64), (62, -42), (24, -26), (-20, -28), (-30, -48)], True), belly))
    for sx, sy, lean in ((-50, -126, -8), (-20, -140, -3)):
        out.append(limb(sx, sy, sx + lean, sy + 54, 0.16, 14, 5, shade))
    for sx, sy, r in ((-62, -78, 4.5), (-36, -74, 6), (-8, -84, 6.5), (-48, -58, 3.5)):
        out.append(circle(sx, sy, r, spots))
    if perch:
        out.append(_perch(perch))
    out.append(_foot(124, 3, shade, deep))
    out.append(_foot(-66, 4, shade, deep))
    # near hind leg, folded, and the near arm
    out.append(limb(-40, -40, -20, -22, 0.34, 32, 22, skin))
    out.append(limb(-20, -24, -30, -6, 0.22, 20, 16, skin))
    out.append(_foot(-32, 4, skin, deep))
    out.append(limb(44, -50, 56, -10, -0.26, 28, 17, skin))
    out.append(_foot(58, 3, skin, deep))

    # the far eye first: it peeks round the snout
    out.append(_eye(doc, 150, -196, 27, look_far, blink, happy, shade, deep, skin, deep))
    # the head: wider than in profile, the snout coming toward you
    out.append(path(smooth([(30, -112), (16, -160), (26, -216), (58, -256), (96, -236), (140, -196), (170, -152), (166, -118), (120, -96), (64, -94)], True), skin))
    out.append(path(smooth([(30, -112), (16, -160), (26, -216), (58, -256), (50, -214), (42, -160), (46, -116)], True), shade))
    out.append(limb(64, -246, 92, -214, -0.08, 7, 2.5, light))
    out.append(path("M70 -248Q118 -216 150 -166", None, shade, 2.6))
    out.append(ellipse(142, -150, 12, 7, light, rot=38))
    out.append(circle(154, -138, 2.5, deep) + circle(134, -130, 2.5, deep))
    out.append(path("M54 -124Q110 -98 166 -128Q170 -112 154 -102Q110 -86 64 -98Q52 -108 54 -124Z", belly))
    if happy:
        out.append(path("M52 -126Q110 -104 168 -130Q158 -98 112 -92Q70 -92 52 -126Z", deep))
        out.append(path("M88 -100Q112 -108 136 -100Q112 -93 88 -100Z", _PINK))
    else:
        out.append(path("M46 -134Q46 -124 56 -120Q112 -100 166 -126Q170 -130 170 -136", None, deep, 4))
    if mood == "curious":
        out.append(limb(150, -112, 172, -98, 0.1, 7, 6, _PINK))
        out.append(circle(175, -96, 8.5, _PINK) + circle(177, -99, 2.6, 0xFFC0C0))
    out.append(_eye(doc, 78, -176, 41, look, blink, happy, skin, shade, light, deep))
    return b"".join(out)


def back(doc, look=(-0.7, 0.3), blink=0, mood="calm", colors="leaf", curl=1.0, perch="twig"):
    """The chameleon from behind, looking back at you over his shoulder.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        look: Where his one visible eye points, each of x and y from -1 to 1.
        blink (float): 0 with the eye open, 1 closed.
        mood (str): "calm", "happy", "curious" or "sleepy".
        colors (str): A name from `huey.COLORS`.
        curl (float): How tightly the tail is wound: 0 loose, 1 at rest, 2 tight.
        perch (str): "twig", "wire", or None for no perch.
    """
    skin, shade, light, belly, spots, deep = COLORS[colors]
    blink, _, happy = _pose(mood, blink, look, None)
    out = []
    # the arms, reaching forward past the body
    for s in (-1, 1):
        out.append(limb(s * 60, -108, s * 86, -8, -s * 0.2, 24, 15, shade))
    # the head, turned to look back: its profile over the shoulder
    head = []
    head.append(path(smooth([(52, -112), (42, -160), (58, -214), (86, -240), (118, -222), (156, -178), (184, -144), (178, -116), (128, -92), (76, -94)], True), skin))
    head.append(path(smooth([(50, -124), (42, -162), (58, -214), (86, -240), (74, -206), (64, -160), (62, -122)], True), shade))
    head.append(limb(90, -232, 112, -204, -0.08, 7, 2.5, light))
    head.append(path(smooth([(90, -116), (134, -111), (180, -128), (182, -118), (170, -104), (128, -91), (82, -95)], True), belly))
    if happy:
        head.append(path("M90 -121Q138 -104 182 -131Q176 -104 150 -99Q112 -96 90 -121Z", deep))
        head.append(path("M118 -104Q140 -110 162 -104Q140 -98 118 -104Z", _PINK))
    else:
        head.append(path("M181 -130Q138 -106 92 -119Q84 -122 84 -131", None, deep, 4))
    if mood == "curious":
        head.append(limb(178, -127, 214, -124, 0.10, 7, 6, _PINK) + circle(217, -124, 8.5, _PINK))
    head.append(circle(170, -148, 2.4, deep))
    head.append(_eye(doc, 110, -164, 39, look, blink, happy, skin, shade, light, deep))
    out.append(at(-52, -66, b"".join(head), scale=0.86))
    # the body from behind: a wide pear, the spine down his middle
    out.append(path(smooth([(0, -196), (50, -178), (86, -116), (78, -52), (0, -30), (-78, -52), (-86, -116), (-50, -178)], True), skin))
    out.append(path(smooth([(-50, -178), (-86, -116), (-78, -52), (-34, -35), (-58, -62), (-64, -116), (-40, -166)], True), shade))
    # bands running out from the spine, and the spots
    for s in (-1, 1):
        for sy, reach in ((-160, 40), (-128, 52), (-94, 54)):
            out.append(limb(s * 10, sy, s * reach, sy + 34, s * 0.16, 13, 5, shade))
        out.append(circle(s * 62, -84, 6, spots) + circle(s * 50, -62, 4, spots) + circle(s * 68, -108, 4, spots))
    for by, r in ((-190, 9), (-170, 10), (-148, 10.5), (-124, 11), (-100, 11), (-76, 10.5)):
        out.append(circle(0, by, r, deep))
    # hind legs, knees out
    for s in (-1, 1):
        out.append(limb(s * 60, -62, s * 104, -46, -s * 0.2, 32, 24, skin))
        out.append(limb(s * 104, -48, s * 96, -6, -s * 0.2, 22, 16, skin))
    if perch:
        out.append(_perch(perch))
    for s in (-1, 1):
        out.append(_foot(s * 96, 3, skin, deep))
        out.append(_foot(s * 86, 3, shade, deep))
    # the tail comes toward you and winds up in front
    out.append(limb(0, -66, 32, -36, -0.2, 40, 27, skin))
    out.append(_tail(-2, -4, 50, 30, -40, 1.25 + 0.3 * curl, skin, shade, light))
    return b"".join(out)


def above(doc, look=(0.6, 0.0), look_other=None, blink=0, mood="calm", colors="leaf", curl=1.0, leaf=True):
    """The chameleon from above, on a leaf, his head to the right.

    Unlike the other views it is centred on the origin, about 440 units long.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        look: Where the upper eye points, each of x and y from -1 to 1.
        look_other: Where the lower eye points, or None for the same way.
        blink (float): 0 with the eyes open, 1 closed.
        mood (str): "calm", "happy", "curious" or "sleepy".
        colors (str): A name from `huey.COLORS`.
        curl (float): How tightly the tail is wound: 0 loose, 1 at rest, 2 tight.
        leaf (bool): Draw the leaf he lies on.
    """
    skin, shade, light, belly, spots, deep = COLORS[colors]
    blink, look_other, happy = _pose(mood, blink, look, look_other)
    out = []
    if leaf:
        # an autumn leaf, so any of its colours stands clear of it
        out.append(path("M-250 60C-200 -120 60 -190 262 -70C230 110 -40 190 -250 60Z", 0xD98A2B))
        out.append(path("M-250 60C-200 -120 60 -190 262 -70C60 -90 -120 -30 -250 60Z", 0xF0AE45))
        out.append(path("M-244 58Q0 -70 256 -70", None, 0xB36A1E, 4))
        for x0, y0, x1, y1 in ((-150, 8, -110, -84), (-60, -32, -10, -124), (40, -58, 100, -132), (-120, -6, -60, 92), (-20, -44, 50, 96), (80, -64, 160, 44)):
            out.append(path("M%d %dQ%d %d %d %d" % (x0, y0, (x0 + x1) // 2 + 6, (y0 + y1) // 2, x1, y1), None, 0xB36A1E, 2.4, opacity=0.7))
    # the limbs, splayed, each ending in his two bundles of toes
    for x0, y0, x1, y1, bend, turn in ((70, -34, 122, -96, 0.3, 20), (70, 34, 126, 92, -0.3, 160), (-56, -36, -92, -100, -0.3, -30), (-56, 36, -86, 104, 0.3, 200)):
        out.append(limb(x0 + 5, y0 + 9, x1 + 5, y1 + 9, bend, 28, 16, 0x000000, opacity=0.16))
        out.append(limb(x0, y0, x1, y1, bend, 28, 16, shade))
        out.append(_foot(x1, y1, skin, deep, turn))
    out.append(ellipse(6, 12, 118, 52, 0x000000, opacity=0.16) + ellipse(146, 12, 74, 42, 0x000000, opacity=0.16))
    # the tail: out behind, then wound up
    tx, ty = -176, 18
    out.append(limb(-96, 0, tx + 33, ty - 28, 0.18, 44, 28, skin))
    out.append(_tail(tx, ty, 44, 27, -40, 1.25 + 0.3 * curl, skin, shade, light))
    # the body, a long drop with a slight bend
    out.append(path(smooth([(-108, 2), (-74, -40), (-10, -52), (60, -42), (96, -10), (92, 22), (56, 44), (-12, 50), (-76, 38)], True), skin))
    out.append(path(smooth([(-108, 2), (-76, 38), (-12, 50), (56, 44), (92, 22), (62, 30), (-10, 36), (-70, 26)], True), shade))
    # bands across the back, spots along the flank, the crest down the spine
    for bx, lean in ((-62, -6), (-22, -2), (20, 2), (58, 6)):
        out.append(limb(bx, -6, bx + lean, -42, -0.12, 13, 5, shade))
        out.append(limb(bx, 2, bx + lean, 36, 0.12, 13, 5, shade))
    for sx, sy, r in ((-46, -32, 5), (-2, -38, 5.5), (40, -34, 5), (-44, 28, 4), (0, 32, 4.5), (40, 28, 4)):
        out.append(circle(sx, sy, r, spots))
    for bx, r in ((-84, 7), (-64, 8), (-42, 9), (-20, 9.5), (2, 9.5), (24, 9), (46, 8.5), (66, 8)):
        out.append(circle(bx, -2 + bx * 0.02, r, deep))
    # the head: the casque points back over the neck, the snout forward
    out.append(path(smooth([(46, -3), (88, -36), (140, -42), (192, -24), (222, -2), (192, 22), (140, 38), (88, 32)], True), skin))
    out.append(path(smooth([(46, -3), (88, 32), (140, 38), (192, 22), (222, -2), (192, 10), (140, 22), (94, 16)], True), shade))
    out.append(path("M56 -3Q130 -14 204 -2", None, light, 5))
    out.append(path("M58 -5Q100 -26 136 -30", None, shade, 2.6))
    out.append(path("M58 0Q100 22 136 28", None, deep, 2.6, opacity=0.5))
    out.append(circle(210, -9, 2.4, deep) + circle(210, 5, 2.4, deep))
    if mood == "curious":
        out.append(limb(220, -2, 252, -4, 0.1, 7, 6, _PINK) + circle(255, -4, 8.5, _PINK))
    out.append(_eye(doc, 140, -38, 24, look, blink, happy, skin, shade, light, deep))
    out.append(_eye(doc, 140, 36, 24, look_other, blink, happy, skin, shade, light, deep))
    return b"".join(out)
