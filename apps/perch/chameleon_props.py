# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Things the chameleon holds, and the chameleon holding them.

Each prop is a function that returns shapes with its grip at the origin and
the prop pointing up, so `vec.at` stands it in a hand. `hold` draws the
chameleon with one hand raised, the prop in it and its toes closed round the
handle.
"""

import math

from . import mascot_chameleon
from .vec import at, circle, ellipse, group, line, path, pts, rect, smooth

NAVY = 0x0B2A4A
LIME = 0xC4DC4C
WHITE = 0xFFFFFF
_STEEL = 0xC9D2DC
_STEEL_DARK = 0x8A97A6
_STEEL_LIGHT = 0xF1F5F9
_INK = 0x2B2B33
_RED = 0xE4513D
_RED_DARK = 0xB23A2B
_GOLD = 0xF4B43A
_GOLD_DARK = 0xC98A1E
_WOOD = 0xD9A066
_WOOD_DARK = 0xA9743F
_CREAM = 0xFFF6E0


def _smoke(turn):
    # smoke and steam rise straight up, whichever way the prop leans
    wisps = path("M0 0C-9 -12 9 -22 0 -36C-8 -48 7 -56 1 -70", None, WHITE, 4.5, opacity=0.5) + path(
        "M9 -8C3 -18 16 -26 10 -40", None, WHITE, 3, opacity=0.32
    )
    return group(wisps, "rotate(%.1f)" % -turn)


def iron(turn=0):
    """A soldering iron, hot, with its wisp of smoke."""
    return (
        path("M-3 24Q-12 44 -4 62", None, _INK, 4)
        + rect(-8, -22, 16, 46, 0x1C6E8C, r=7)
        + rect(-8, -22, 6, 46, 0x145670, r=3)
        + rect(-9, -30, 18, 10, LIME, r=3)
        + rect(-4, -62, 8, 34, _STEEL)
        + rect(-4, -62, 3, 34, _STEEL_DARK)
        + rect(-6, -40, 12, 5, _STEEL_DARK, r=2)
        + path("M-3 -62L3 -62L1 -84L-1 -84Z", _STEEL_LIGHT)
        + circle(0, -84, 2.6, 0xFFB26B)
        + at(0, -88, _smoke(turn))
    )


def wire(turn=0):
    """A jumper wire, held by its housing, pin up."""
    return (
        path("M0 14C2 44 -34 40 -30 72C-27 94 -52 96 -58 112", None, LIME, 6.5)
        + path("M0 14C2 44 -34 40 -30 72", None, 0xE4F5A8, 1.8, opacity=0.8)
        + rect(-2, -52, 4, 30, _STEEL_LIGHT, r=1.5)
        + rect(-2, -52, 1.6, 30, _STEEL_DARK)
        + rect(-7.5, -24, 15, 40, _INK, r=3)
        + rect(2, -20, 3, 32, 0x55555F, r=1.5)
    )


def screwdriver(turn=0):
    """A small screwdriver with a fat handle."""
    return (
        rect(-3, -78, 6, 52, _STEEL, r=1)
        + rect(-3, -78, 2.4, 52, _STEEL_DARK)
        + path("M-3 -78L3 -78L5 -90L-5 -90Z", _STEEL_LIGHT)
        + rect(-10, -30, 20, 56, _RED, r=9)
        + rect(-10, -30, 7, 56, _RED_DARK, r=4)
        + rect(4, -20, 3, 34, 0xFF8A70, r=1.5)
        + rect(-10, -22, 20, 5, _INK, opacity=0.35)
    )


def magnifier(turn=0):
    """A magnifying glass: what's behind the lens shows through it."""
    return (
        rect(-6, -14, 12, 48, _INK, r=5)
        + rect(1, -8, 3, 34, 0x55555F, r=1.5)
        + rect(-5, -24, 10, 12, _GOLD_DARK, r=2)
        + circle(0, -60, 36, 0xBFE9FF, opacity=0.30)
        + circle(0, -60, 36, None, _GOLD_DARK, 9)
        + circle(0, -60, 37.5, None, _GOLD, 5)
        + path("M-22 -66A24 24 0 0 1 -6 -83", None, WHITE, 5, opacity=0.85)
        + circle(-24, -55, 2.6, WHITE, opacity=0.85)
    )


def pencil(turn=0):
    """A pencil, sharpened."""
    return (
        rect(-6, -62, 12, 86, _GOLD)
        + rect(-6, -62, 4.5, 86, _GOLD_DARK)
        + rect(3, -62, 3, 86, 0xFFD778)
        + path("M-6 -62L6 -62L0 -84Z", _WOOD)
        + path("M-6 -62L-1.5 -62L0 -84Z", _WOOD_DARK)
        + path("M-2.2 -76L2.2 -76L0 -84Z", _INK)
        + rect(-6, 22, 12, 7, _STEEL)
        + rect(-6, 22, 12, 2.2, _STEEL_DARK)
        + rect(-6, 28, 12, 11, 0xFF8FA3, r=4)
    )


def board(turn=0):
    """A small microcontroller board, held by its edge, its light on."""
    out = [
        rect(-34, -98, 68, 100, 0x0E3B66, r=6),
        rect(-34, -98, 68, 100, None, 6, 0x1D5C96, 2),
        # the USB socket at the top, the chip, the header pads down each side
        rect(-11, -106, 22, 18, _STEEL, r=2),
        rect(-11, -106, 22, 5, _STEEL_LIGHT, r=2),
        rect(-15, -66, 30, 30, _INK, r=2),
        circle(-9, -60, 2, 0x6A6A75),
        path("M-22 -24L-22 -14L-8 -14", None, LIME, 1.8),
        path("M22 -30L22 -78L16 -78", None, LIME, 1.8),
    ]
    for i in range(7):
        y = -86 + i * 12.5
        out.append(rect(-31, y, 6, 6, _GOLD, r=1))
        out.append(rect(25, y, 6, 6, _GOLD, r=1))
    for i in range(4):
        out.append(rect(-19, -62 + i * 7, 4, 2.4, _STEEL))
        out.append(rect(15, -62 + i * 7, 4, 2.4, _STEEL))
    out.append(circle(10, -22, 13, LIME, opacity=0.22))
    out.append(circle(10, -22, 8, LIME, opacity=0.35))
    out.append(rect(5, -25, 10, 6, 0xF6FFC4, r=1.5))
    return "".join(out)


def lantern(turn=0, color=LIME):
    """A lit LED carried by its legs, like a lantern."""
    return (
        circle(0, -74, 62, color, opacity=0.10)
        + circle(0, -74, 46, color, opacity=0.14)
        + circle(0, -74, 33, color, opacity=0.20)
        + line(-7, -44, -7, 26, _STEEL, 3.2)
        + line(7, -44, 7, 14, _STEEL, 3.2)
        + path("M-20 -72A20 20 0 0 1 20 -72L20 -50L-20 -50Z", color)
        + path("M-20 -72A20 20 0 0 1 -6 -91L-6 -50L-20 -50Z", 0x000000, opacity=0.14)
        + rect(-24, -52, 48, 8, color, r=2)
        + rect(-24, -47, 48, 3, 0x000000, opacity=0.18)
        + path(pts([(-9, -52), (-9, -72), (-2, -72), (-2, -62), (2, -66), (9, -66), (9, -52)], True), 0x000000, opacity=0.20)
        + path("M8 -84A14 14 0 0 1 14 -72", None, WHITE, 4, opacity=0.9)
        + circle(1, -76, 8, 0xFDFFE0, opacity=0.9)
    )


def probe(turn=0):
    """A multimeter probe on its lead."""
    return (
        path("M0 26C-4 56 28 54 22 82C18 100 36 106 40 118", None, _RED_DARK, 5)
        + rect(-1.6, -86, 3.2, 34, _STEEL_LIGHT)
        + path("M-1.6 -86L1.6 -86L0 -94Z", _STEEL_LIGHT)
        + path("M-5 -54L5 -54L8 -32L-8 -32Z", _RED)
        + rect(-11, -34, 22, 6, _RED_DARK, r=3)
        + rect(-8, -30, 16, 58, _RED, r=7)
        + rect(-8, -30, 5.5, 58, _RED_DARK, r=3)
        + rect(3, -22, 2.6, 40, 0xFF8A70, r=1.3)
    )


def mug(turn=0):
    """A mug of something hot, held by its handle."""
    return (
        path("M8 -18A17 17 0 1 0 8 14", None, _CREAM, 8)
        + path("M8 -18A17 17 0 1 0 8 14", None, 0xD9CDB4, 2.5)
        + rect(4, -34, 52, 60, _CREAM, r=8)
        + rect(4, -34, 15, 60, 0xD9CDB4, r=7)
        + rect(4, -12, 52, 9, 0x1C6E8C)
        + rect(4, -1, 52, 4, LIME)
        + ellipse(30, -33, 23, 5.5, 0x6B4226)
        + ellipse(34, -33, 12, 2.4, 0x94603A)
        + at(30, -42, _smoke(turn))
    )


def umbrella(turn=0):
    """An umbrella, open."""
    out = [
        line(0, -96, 0, 22, _INK, 4),
        path("M0 22Q0 34 -9 34Q-17 34 -17 25", None, _INK, 4),
        path("M-70 -92Q0 -168 70 -92Q52 -104 35 -92Q17 -104 0 -92Q-17 -104 -35 -92Q-52 -104 -70 -92Z", _RED),
        path("M-35 -92Q-30 -140 0 -129Q-17 -104 -35 -92Z", 0xFFF1D6),
        path("M35 -92Q30 -140 0 -129Q17 -104 35 -92Z", 0xFFF1D6),
        path("M-70 -92Q-52 -122 0 -129Q-30 -140 -35 -92Q-52 -104 -70 -92Z", _RED_DARK),
        path("M22 -122Q44 -112 54 -98", None, 0xFF8A70, 3.5),
        line(0, -129, 0, -140, _INK, 4),
    ]
    return "".join(out)


def leaf(turn=0):
    """A broad leaf on its stalk, as good as a parasol."""
    return (
        path("M0 26Q-4 0 2 -30", None, 0x3F7D32, 5)
        + path("M2 -30C-52 -44 -58 -104 2 -132C62 -104 56 -44 2 -30Z", 0x6FC24B)
        + path("M2 -30C-52 -44 -58 -104 2 -132C-18 -96 -14 -58 2 -30Z", 0x4A9E3F)
        + path("M2 -34L2 -122M2 -56L-24 -76M2 -56L30 -74M2 -84L-18 -100M2 -84L24 -100", None, 0x2F7A36, 2.4)
        + path("M26 -52Q44 -74 30 -104", None, 0xB8EB7A, 3.5)
    )


def flower(turn=0):
    """A daisy."""
    out = [path("M0 26Q6 -8 0 -48", None, 0x3F7D32, 4.5), path("M2 -6C16 -20 34 -16 38 -4C24 4 10 4 2 -6Z", 0x5E9E3E)]
    for i in range(9):
        out.append(group(ellipse(0, -21, 8.5, 15, WHITE if i % 2 else 0xF1E9F7), "translate(0 -62) rotate(%d)" % (i * 40)))
    out.append(circle(0, -62, 12, _GOLD))
    out.append(circle(3, -65, 5.5, 0xFFD778))
    return "".join(out)


def plane(turn=0):
    """A paper aeroplane, pinched by its keel, ready to throw."""
    return (
        path(pts([(-4, 6), (4, -96), (10, 2)], True), 0xC9D6E4)
        + path(pts([(4, -96), (-44, 14), (-4, 6)], True), WHITE)
        + path(pts([(4, -96), (46, 4), (10, 2)], True), 0xE6EDF5)
        + path(pts([(4, -96), (-4, 6), (2, 26), (10, 2)], True), 0xA9BACD)
        + line(4, -96, 2, 26, 0x8A9BB0, 1.2)
    )


def flag(turn=0):
    """A pennant on a stick, with a spiral for its mark."""
    spiral = []
    for i in range(26):
        a = i * 0.42
        r = 2 + i * 0.52
        spiral.append((27 + math.cos(a) * r, -98 + math.sin(a) * r))
    return (
        rect(-3, -128, 6, 156, _WOOD, r=3)
        + rect(-3, -128, 2.4, 156, _WOOD_DARK, r=1.2)
        + circle(0, -130, 5.5, _GOLD)
        + path("M3 -124Q32 -132 62 -120Q44 -100 64 -78Q32 -66 3 -74Z", LIME)
        + path("M3 -84Q32 -76 62 -88L64 -78Q32 -66 3 -74Z", 0x9DB93A)
        + path(smooth(spiral), None, NAVY, 3.6)
    )


def wrench(turn=0):
    """An open-ended spanner."""
    return (
        rect(-7, -64, 14, 92, _STEEL, r=6)
        + rect(-7, -64, 5, 92, _STEEL_DARK, r=2.5)
        + rect(3, -54, 2.6, 70, _STEEL_LIGHT, r=1.3)
        + circle(0, 20, 3.4, NAVY)
        + path("M-9 -58A20 20 0 1 1 9 -58Z", _STEEL)
        + path("M-9 -58A20 20 0 0 1 -18 -84L-8 -78Z", _STEEL_DARK)
        + path(pts([(-8, -100), (-8, -78), (8, -78), (8, -100)], True), NAVY)
    )


def sparkler(turn=0):
    """A sparkler, lit."""
    out = [line(0, 26, 0, -70, _STEEL_DARK, 2.6), line(0, -40, 0, -70, 0x6A6A75, 4.5)]
    out.append(circle(0, -78, 44, _GOLD, opacity=0.12))
    out.append(circle(0, -78, 28, 0xFFE9A8, opacity=0.2))
    for i in range(12):
        a = math.radians(i * 30 + 8)
        r1 = 40 if i % 2 else 27
        out.append(line(math.cos(a) * 9, -78 + math.sin(a) * 9, math.cos(a) * r1, -78 + math.sin(a) * r1, 0xFFE9A8 if i % 2 else _GOLD, 2.6))
        if i % 2:
            out.append(circle(math.cos(a) * (r1 + 8), -78 + math.sin(a) * (r1 + 8), 2.4, WHITE))
        else:
            out.append(circle(math.cos(a + 0.3) * (r1 + 12), -78 + math.sin(a + 0.3) * (r1 + 12), 1.8, _GOLD))
    out.append(circle(0, -78, 8, WHITE))
    return "".join(out)


def balloon(turn=0):
    """A balloon on its string."""
    return (
        path("M0 26C-6 -4 8 -30 0 -62", None, _STEEL_LIGHT, 1.8)
        + path("M-6 -60L6 -60L0 -70Z", _RED_DARK)
        + ellipse(0, -112, 38, 46, _RED)
        + path("M0 -66C-30 -70 -44 -110 -30 -140C-24 -106 -16 -84 0 -66Z", _RED_DARK)
        + ellipse(14, -130, 9, 15, 0xFF9C88, rot=24)
        + circle(22, -106, 3.4, 0xFF9C88)
    )


# name -> (the prop, how far it leans from upright in degrees, or None to lie along the hand)
PROPS = {
    "iron": (iron, None),
    "wire": (wire, None),
    "screwdriver": (screwdriver, None),
    "magnifier": (magnifier, None),
    "pencil": (pencil, None),
    "board": (board, None),
    "lantern": (lantern, 30),
    "probe": (probe, None),
    "mug": (mug, 0),
    "umbrella": (umbrella, 12),
    "leaf": (leaf, 22),
    "flower": (flower, None),
    "plane": (plane, None),
    "flag": (flag, 30),
    "wrench": (wrench, None),
    "sparkler": (sparkler, None),
    "balloon": (balloon, 28),
}
ORDER = ("iron", "screwdriver", "wrench", "probe", "wire", "board", "magnifier", "pencil", "lantern", "sparkler", "mug", "flag", "umbrella", "leaf", "flower", "balloon", "plane")

# each prop's own box, (left, top, right, bottom), for laying out the sheet
_BOX = {
    "iron": (-12, -160, 18, 62),
    "screwdriver": (-10, -90, 10, 26),
    "wrench": (-20, -100, 20, 28),
    "probe": (-11, -94, 42, 118),
    "wire": (-60, -52, 8, 114),
    "board": (-37, -106, 37, 5),
    "magnifier": (-42, -100, 42, 34),
    "pencil": (-6, -84, 6, 39),
    "lantern": (-62, -136, 62, 26),
    "sparkler": (-54, -132, 54, 26),
    "mug": (-13, -112, 56, 26),
    "flag": (-6, -136, 64, 28),
    "umbrella": (-70, -140, 70, 34),
    "leaf": (-44, -132, 48, 26),
    "flower": (-24, -98, 38, 26),
    "balloon": (-38, -158, 38, 26),
    "plane": (-44, -96, 46, 26),
}


def party_hat():
    """A party hat, its point up and its brim at the origin."""
    return (
        path(pts([(-22, 0), (0, -58), (22, 0)], True), LIME)
        + path(pts([(-22, 0), (0, -58), (-4, 0)], True), 0x9DB93A)
        + path("M-13 -24L14 -20L16 -14L-16 -17Z", 0x1C6E8C)
        + path("M-6 -42L7 -40L9 -34L-9 -36Z", _RED)
        + path("M-22 0Q0 8 22 0", None, WHITE, 6)
        + circle(0, -60, 8, WHITE)
        + circle(2, -62, 3.4, 0xF1F5F9)
    )


def _fist(skin, shade, deep):
    # the two bundles of toes closed round a handle, over the open hand beneath
    return (
        ellipse(0, -10, 19, 18, skin)
        + ellipse(0, -17, 18, 9.5, skin)
        + path("M-17 -9Q0 -3 17 -9", None, deep, 2.2)
        + path("M-15 -20Q0 -26 13 -21", None, shade, 2.4, opacity=0.9)
        + ellipse(-11, 0, 7, 5, shade, opacity=0.55)
    )


def hold(doc, prop, wear=None, lean=None, size=1.25, **pose):
    """The chameleon with one hand raised and *prop* in it.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        prop (str): A name from `PROPS`, or None for an empty hand.
        wear (str): "party_hat", or None.
        lean (float): The prop's turn in degrees, or None for its usual one.
        size (float): The prop's size.
        pose: Arguments for `mascot_chameleon.draw`: look, mood, colors, perch.
    """
    pose.setdefault("hand", 1)
    colors = mascot_chameleon.COLORS[pose.get("colors", "leaf")]
    skin, shade, deep = colors[0], colors[1], colors[5]
    out = [mascot_chameleon.draw(doc, **pose)]
    if wear == "party_hat":
        out.append(at(84, -214, party_hat(), rot=-14))
    if prop:
        x, y, turn = mascot_chameleon.grip(pose["hand"])
        shape, own = PROPS[prop]
        if lean is None:
            lean = turn if own is None else own
        # the toes close a little up the hand, round the low end of the handle
        gx = x + math.sin(math.radians(turn)) * 9 + math.sin(math.radians(lean)) * 10 * size
        gy = y - math.cos(math.radians(turn)) * 9 - math.cos(math.radians(lean)) * 10 * size
        out.append(at(gx, gy, shape(lean), rot=lean, scale=size))
        out.append(at(x, y, _fist(skin, shade, deep), rot=turn))
    return "".join(out)
