# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A hummingbird, drawn from a pose: a mascot study.

The bird hovers over the origin: x to the right, y down, the ground at y = 0,
its crest about 280 units up. `draw` returns its shapes for a `vec.Doc`. Its
throat patch is cut like a jewel, in flat facets.
"""

import math

from .vec import Doc, at, circle, ellipse, group, limb, path, pts, rect

NAVY = 0x0B2A4A
LIME = 0xC4DC4C
WHITE = 0xFFFFFF

TEAL = 0x17A68E
TEAL_LIGHT = 0x58D8B6
TEAL_DARK = 0x0E7C78
TEAL_DEEP = 0x0A5463
CREAM = 0xFBF6E4
CREAM_SHADE = 0xDCE5CF
GOLD = 0xFFC44D
GOLD_DARK = 0xE0902B
BLUSH = 0xFF8F8A
INK = 0x08223C

# The throat's facets, lightest where the light lands (upper right).
_GEMS = (0xF3FBA6, 0xE6F47E, 0xD3E85A, LIME, 0xA6C636, 0x7FA528, 0x93B92E, 0xB4D240, 0xDDEF6A)

_SCALE = 0.9
_CENTRE_Y = -172


def _crescent(cx, cy, rx, ry, tilt, toward, thick, fill, inset=1.0, half=95, opacity=None):
    """A crescent hugging the edge of an ellipse, for a shade, a glint or a belly.

    *toward* is the side it sits on, in degrees in the ellipse's own frame,
    *thick* its width at the middle as a fraction of the radius.
    """
    c, s = math.cos(math.radians(half)), math.sin(math.radians(half))
    k = 1 - thick - c
    big = (s * s + k * k) / (2 * k)
    d = "M%.4f %.4fA1 1 0 %d 1 %.4f %.4fA%.4f %.4f 0 0 0 %.4f %.4fZ" % (c, -s, 1 if half > 90 else 0, c, s, big, big, c, -s)
    t = "translate(%.2f %.2f) rotate(%.2f) scale(%.2f %.2f) rotate(%.2f)" % (cx, cy, tilt, rx * inset, ry * inset, toward)
    return group(path(d, fill, opacity=opacity), t)


def _feather(length, w0, w1, fill):
    # along +x from the origin, pointed
    return path(
        "M0 %.1fC%.1f %.1f %.1f %.1f %.1f 0C%.1f %.1f %.1f %.1f 0 %.1fZ"
        % (-w0 / 2, length * 0.3, -w0, length * 0.86, -w0 * 0.7 - w1, length, length * 0.9, w0 * 0.45 + w1, length * 0.3, w0 * 0.8, w0 / 2),
        fill,
    )


def _wing(angle, dark, mid_, light, tip):
    """A wing from its shoulder at the origin, turned to *angle* degrees."""
    out = []
    # the long flight feathers, the hindmost first
    fan = ((-36, 76, 26, dark), (-24, 104, 26, mid_), (-12, 128, 25, dark), (-1, 146, 22, mid_))
    for offset, length, width, fill in fan:
        out.append(group(_feather(length, width, 3, fill), "rotate(%.1f)" % offset))
    # the small feathers over the shoulder
    out.append(group(_feather(92, 20, 2, light), "rotate(-4)"))
    out.append(ellipse(26, -8, 34, 17, light, rot=-16))
    out.append(ellipse(22, -10, 20, 8, tip, rot=-16))
    return group("".join(out), "rotate(%.1f)" % angle)


def _folded_wing(dark, mid_, light, tip):
    # at rest along the back, its tip crossing the tail
    out = [
        group(_feather(118, 34, 4, dark), "rotate(112)"),
        group(_feather(104, 30, 4, mid_), "rotate(104)"),
        ellipse(-4, 30, 20, 34, light, rot=14),
        ellipse(-1, 22, 10, 20, tip, rot=14),
    ]
    return "".join(out)


def _eye(doc, x, y, r, look, lid, mood):
    if mood == "happy":
        out = []
        out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (x - r * 0.66, y + r * 0.18, x, y - r * 0.7, x + r * 0.66, y + r * 0.18), None, TEAL_DEEP, r * 0.24))
        return "".join(out)
    out = [circle(x, y, r + 3, TEAL_DEEP), circle(x, y, r, WHITE)]
    pr = r * 0.74
    px, py = x + look[0] * (r - pr) * 1.5, y + look[1] * (r - pr) * 1.5
    iris = doc.radial([(0, 0x245F94), (0.7, NAVY), (1, INK)], cx=0.5, cy=0.64)
    out.append(circle(px, py, pr, iris))
    out.append(circle(px + pr * 0.34, py - pr * 0.40, pr * 0.30, WHITE))
    out.append(circle(px - pr * 0.40, py + pr * 0.36, pr * 0.14, WHITE, opacity=0.85))
    if lid > 0:
        drop = -r + 2 * r * lid
        top = y + min(drop, 0)
        d = "M%.2f %.2fA%.2f %.2f 0 0 1 %.2f %.2fQ%.2f %.2f %.2f %.2fZ" % (x - r - 3, top, r + 3, r + 3, x + r + 3, top, x, y + drop + (r * 0.5 if lid >= 0.95 else r * 0.1), x - r - 3, top)
        out.append(path(d, TEAL))
        if lid >= 0.95:
            out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (x - r * 0.7, y + r * 0.1, x, y + r * 0.62, x + r * 0.7, y + r * 0.1), None, TEAL_DEEP, r * 0.18))
        else:
            out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (x - r * 0.98, y + drop * 0.5, x, y + drop * 0.5 + r * 0.06, x + r * 0.98, y + drop * 0.5), None, TEAL_DEEP, r * 0.14))
    return "".join(out)


def _gorget():
    # a bib of facets round one centre, puffed out a little past the throat
    rim = ((81, -35), (76, -17), (69, 2), (63, 24), (50, 46), (29, 36), (15, 13), (22, -10), (48, -24))
    cx, cy = 48, 8
    out = []
    n = len(rim)
    for i in range(n):
        a, b = rim[i], rim[(i + 1) % n]
        out.append(path(pts([a, b, (cx, cy)], True), _GEMS[i]))
    # the table of the gem: a small bright facet at the centre
    out.append(path(pts([(cx + 7, cy - 8), (cx + 9, cy + 3), (cx + 1, cy + 10), (cx - 8, cy + 3), (cx - 4, cy - 7)], True), 0xF7FDC2))
    out.append(path(pts([(cx + 7, cy - 8), (cx + 9, cy + 3), (cx + 1, cy)], True), WHITE))
    return "".join(out)


def _beak(open_):
    out = []
    if open_:
        out.append(limb(70, -40, 160, -14, 0.03, 11, 2, GOLD_DARK))
        out.append(path("M84 -41Q110 -34 128 -30Q106 -30 84 -36Z", 0xFF7F8E))
    out.append(limb(68, -46, 170, -36 - (10 if open_ else 0), -0.05, 15, 2.2, GOLD))
    if not open_:
        out.append(path("M74 -40Q118 -30 166 -34", None, GOLD_DARK, 2.4))
    return "".join(out)


def draw(doc, look=(0.4, 0.0), blink=0, mood="calm", beat=0.12, tilt=0, perched=False, blur=True, shadow=True):
    """The hummingbird's shapes, back to front.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        look: Where the eye points, each of x and y from -1 to 1.
        blink (float): 0 with the eye open, 1 closed.
        mood (str): "calm", "happy", "curious" or "sleepy".
        beat (float): Where the wings are in their beat, 0 to 1: up at 0, down at 0.5.
        tilt (float): The body's lean in degrees, positive nose-down.
        perched (bool): On a twig with its wings folded, not hovering.
        blur (bool): Draw the fan of air the wings sweep through.
        shadow (bool): Draw the shadow on the ground.
    """
    out = []
    swing = (1 - math.cos(2 * math.pi * beat)) / 2
    near = -108 - 122 * swing
    far = near + 16
    if mood == "sleepy":
        blink = max(blink, 0.5)
    if mood == "curious":
        tilt -= 9

    if not perched:
        # the far wing, and the air both wings blur
        out.append(at(2, -4, _wing(far, TEAL_DEEP, 0x0C6570, TEAL_DARK, TEAL_DARK)))
        if blur:
            a0, a1 = math.radians(-104), math.radians(-236)
            out.append(path("M-14 2L%.1f %.1fA150 150 0 0 0 %.1f %.1fZ" % (-14 + 150 * math.cos(a0), 2 + 150 * math.sin(a0), -14 + 150 * math.cos(a1), 2 + 150 * math.sin(a1)), 0xBFF3E6, opacity=0.09))
            ghost = -108 - 122 * (1 - swing)
            out.append(group(at(-14, 2, _wing(ghost, 0xBFF3E6, 0xBFF3E6, 0xBFF3E6, 0xBFF3E6)), opacity=0.16))

    # the tail: three feathers, the middle one longest, tipped white
    for angle, length, fill in ((152, 88, TEAL_DARK), (110, 86, TEAL_DARK), (131, 108, 0x119085)):
        feather = _feather(length, 19, 2, fill) + group(_feather(20, 9, 1.5, LIME), "translate(%d 0)" % (length - 23))
        out.append(at(-28, 78, feather, rot=angle))

    # feet, tucked up when it flies
    if perched:
        out.append(limb(-4, 100, 0, 116, 0, 5, 4, GOLD_DARK))
        out.append(limb(14, 98, 18, 114, 0, 5, 4, GOLD_DARK))
    else:
        out.append(limb(2, 100, 14, 110, 0.3, 5, 3, GOLD_DARK))
        out.append(limb(18, 96, 30, 105, 0.3, 5, 3, GOLD_DARK))

    # the body: green back, pale belly on the side that faces us
    out.append(ellipse(-8, 30, 62, 78, TEAL, rot=25))
    out.append(_crescent(-8, 30, 62, 78, 25, 160, 0.30, TEAL_DARK, half=95))
    out.append(_crescent(-8, 30, 62, 78, 25, 8, 0.86, CREAM, half=104))
    out.append(_crescent(-8, 30, 62, 78, 25, 62, 0.20, CREAM_SHADE, half=64))

    out.append(_beak(mood == "happy"))

    # the head
    out.append(circle(22, -50, 60, TEAL))
    out.append(_crescent(22, -50, 60, 60, 0, 150, 0.26, TEAL_DARK, half=92))
    # the crest: three short feathers, lifted when something catches its eye
    lift = -16 if mood == "curious" else 0
    for angle, length in ((-134 + lift, 38), (-112 + lift, 48), (-92 + lift, 32)):
        out.append(at(6, -98, _feather(length, 10, 1, TEAL_LIGHT if length > 40 else TEAL), rot=angle))
    # where the light lands on the crown, as two facets
    out.append(path(pts([(34, -100), (62, -88), (48, -78), (30, -86)], True), TEAL_LIGHT))
    out.append(path(pts([(62, -88), (74, -70), (58, -68), (48, -78)], True), 0x8EE8CF))
    # the cheek, and the white spot behind the eye
    out.append(ellipse(6, -52, 5, 7, CREAM, rot=-20))

    out.append(_gorget())

    if mood in ("happy", "calm"):
        out.append(ellipse(14, -30, 10, 6, BLUSH, opacity=0.9, rot=-20))
    if mood == "calm":
        out.append(path("M64 -40Q70 -35 77 -39", None, TEAL_DEEP, 2.6))
    out.append(_eye(doc, 40, -62, 22, look, blink, mood))

    if perched:
        out.append(at(-30, 6, _folded_wing(TEAL_DEEP, TEAL_DARK, TEAL, TEAL_LIGHT)))
    else:
        out.append(at(-14, 2, _wing(near, TEAL_DARK, 0x119085, TEAL, TEAL_LIGHT)))

    body = at(0, _CENTRE_Y, group("".join(out), "rotate(%.1f)" % tilt), scale=_SCALE)
    back = ""
    if perched:
        # the twig it sleeps on, with a leaf
        twig_y = _CENTRE_Y + 112 * _SCALE
        back += limb(-150, twig_y + 14, 150, twig_y - 2, 0.03, 13, 9, 0x7A5440)
        back += limb(60, twig_y + 2, 104, twig_y - 26, 0.15, 6, 3, 0x7A5440)
        back += at(104, twig_y - 26, _feather(40, 22, 3, 0x7DBE4E), rot=-30)
        back += at(104, twig_y - 26, path("M2 0L34 0", None, 0x4F9A3A, 1.6), rot=-30)
        if shadow:
            back += ellipse(0, 4, 120, 13, 0x000000, opacity=0.2)
    elif shadow:
        back += ellipse(-6, 4, 78, 11, 0x000000, opacity=0.16) + ellipse(-4, 5, 46, 7, 0x000000, opacity=0.18)
    return back + body


def _study(view, **pose):
    def build():
        doc = Doc()
        doc.add(rect(-1000, -1000, 2000, 2000, NAVY))
        doc.add(draw(doc, **pose))
        return doc.svg(view)

    return build


def _icon():
    doc = Doc()
    doc.add(rect(-300, -400, 600, 600, 0x061A30))
    doc.add(circle(0, -150, 190, NAVY))
    doc.add(circle(0, -150, 190, None, LIME, 7))
    doc.add(at(-6, 40, draw(doc, beat=0.04, blur=False, shadow=False, look=(0.5, -0.1)), scale=1.18))
    return doc.svg((-200, -350, 400, 400))


_FULL = (-230, -340, 460, 380)

STILLS = [
    ("hummingbird_full", _study(_FULL), 920),
    ("hummingbird_face", _study((-52, -334, 228, 190), look=(0.6, 0.1)), 900),
    ("hummingbird_happy", _study(_FULL, mood="happy", beat=0.42, tilt=-6), 920),
    ("hummingbird_curious", _study(_FULL, mood="curious", beat=0.25, look=(0.9, -0.5)), 920),
    ("hummingbird_sleepy", _study(_FULL, mood="sleepy", perched=True, look=(0.2, 0.7)), 920),
    ("hummingbird_icon", _icon, 400),
]
