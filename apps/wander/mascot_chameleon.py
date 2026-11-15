# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A chameleon on its perch, drawn from a pose and a set of colours.

It sits above the origin: x to the right, y down, the top of the perch at
y = 0, about 450 units wide and 260 tall. `draw` returns its shapes for a
`vec.Doc`. Its two eyes look where they like, each on its own.
"""

import math

from vec import Doc, at, circle, ellipse, limb, line, path, rect, smooth

NAVY = 0x0B2A4A
LIME = 0xC4DC4C
WHITE = 0xFFFFFF

# The colours it can take: (skin, shade, light, belly, spots, deep).
COLORS = {
    "leaf": (0x6FC24B, 0x3E9440, 0xA9E36B, 0xE4F5A8, 0xFFE25A, 0x25663A),
    "brand": (0x3F8FD6, 0x2767AC, 0x7DBBF0, 0xC4DC4C, 0xC4DC4C, 0x1A4A80),
    "sunset": (0xF47C4C, 0xCC4A33, 0xFFB26B, 0xFFE3A6, 0x8A3F78, 0x8E2B2B),
    "board": (0x239468, 0x146B4B, 0x56C492, 0xF4CD52, 0xF4CD52, 0x0C4A35),
}

_CROUCH = 22
_BARK = 0x7A5440
_BARK_DARK = 0x5B3B2E
_BARK_LIGHT = 0x9C7257


def _spiral_points(cx, cy, r0, r1, start, turns, offset0, offset1, t0, t1, steps):
    points = []
    for i in range(steps + 1):
        t = t0 + (t1 - t0) * i / steps
        a = math.radians(start) - t * turns * 2 * math.pi
        # the radius shrinks faster at first, so the coils sit apart
        r = r1 + (r0 - r1) * (1 - t) ** 1.25 + offset0 + (offset1 - offset0) * t
        points.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return points


def _spiral(cx, cy, r0, r1, w0, w1, start, turns, fill, steps=40):
    """A tapering tail wound round (cx, cy), from radius r0 in to r1."""
    outer = _spiral_points(cx, cy, r0, r1, start, turns, w0 / 2, w1 / 2, 0, 1, steps)
    inner = _spiral_points(cx, cy, r0, r1, start, turns, -w0 / 2, -w1 / 2, 0, 1, steps)
    inner.reverse()
    tip = ((outer[-1][0] + inner[0][0]) / 2, (outer[-1][1] + inner[0][1]) / 2)
    d = smooth(outer) + "L" + smooth(inner)[1:] + "Z"
    return path(d, fill) + circle(tip[0], tip[1], w1 / 2, fill)


def _eye(doc, x, y, r, look, blink, happy, skin, shade, light, deep):
    """A turret eye: a cone of skin with the eye at its tip, turned by *look*."""
    out = [
        circle(x, y, r, shade),
        circle(x + look[0] * r * 0.06, y + look[1] * r * 0.06, r * 0.86, skin),
        # the turret turns: its rings slide toward where it looks
        circle(x + look[0] * r * 0.14, y + look[1] * r * 0.12, r * 0.70, light),
    ]
    ox, oy = x + look[0] * r * 0.20, y + look[1] * r * 0.17
    open_r = r * 0.56
    if happy:
        out.append(circle(ox, oy, open_r, skin))
        out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (ox - open_r * 0.72, oy + open_r * 0.22, ox, oy - open_r * 0.74, ox + open_r * 0.72, oy + open_r * 0.22), None, deep, r * 0.13))
        return "".join(out)
    ry = open_r * (1 - blink)
    if ry < open_r * 0.12:
        out.append(circle(ox, oy, open_r, skin))
        out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (ox - open_r * 0.8, oy, ox, oy + open_r * 0.34, ox + open_r * 0.8, oy), None, deep, r * 0.11))
        return "".join(out)
    out.append(ellipse(ox, oy, open_r + r * 0.07, ry + r * 0.07, deep))
    white = doc.radial([(0, WHITE), (0.8, 0xF4F7FB), (1, 0xD3DCE8)])
    out.append(ellipse(ox, oy, open_r, ry, white))
    pr = min(open_r * 0.62, ry * 0.94)
    px, py = ox + look[0] * open_r * 0.30, oy + look[1] * max(min(open_r * 0.28, ry - pr), 0)
    iris = doc.radial([(0, 0x1F5E8F), (0.75, NAVY), (1, 0x061A30)], cx=0.5, cy=0.62)
    out.append(circle(px, py, pr, iris))
    if ry > open_r * 0.4:
        out.append(circle(px - pr * 0.36, py - pr * 0.40, pr * 0.30, WHITE))
        out.append(circle(px + pr * 0.38, py + pr * 0.36, pr * 0.13, WHITE, opacity=0.8))
    return "".join(out)


def _foot(x, y, skin, deep, turn=0):
    # two bundles of toes that close round the perch like tongs; we see the near one
    return at(
        x,
        y,
        ellipse(-7, 3, 9, 12, skin, rot=14) + ellipse(8, 3, 9, 12, skin, rot=-14) + ellipse(0, -4, 13, 9, skin) + line(0.5, 2, 0.5, 12, deep, 2.2),
        rot=turn,
    )


def _hand(x, y, skin, deep, turn):
    # the raised hand, its two bundles of toes spread in a wave
    return at(
        x,
        y,
        limb(0, 0, -11, -20, 0.2, 15, 11, skin) + limb(0, 0, 13, -19, -0.2, 15, 11, skin) + circle(0, 0, 10, skin) + line(0, -5, 0.5, -12, deep, 2),
        rot=turn,
    )


def _perch(kind):
    out = []
    if kind == "wire":
        # a jumper wire, pulled tight between two pins
        out.append(path("M-232 8Q0 16 232 6", None, 0xC8452F, 11))
        out.append(path("M-200 4Q0 12 200 2", None, 0xF07A5C, 2.5))
        for x, y, turn in ((-232, 8, 2), (232, 6, -2)):
            out.append(at(x, y, rect(-22, -8, 44, 16, 0x2B2B33, r=3) + rect(-18, -5, 30, 3, 0x4A4A55, r=1.5), rot=turn))
        out.append(rect(-270, 5.5, 20, 5, 0xD9DEE6, r=2))
        out.append(rect(250, 3.5, 20, 5, 0xD9DEE6, r=2))
        return "".join(out)
    out.append(limb(120, 6, 204, -36, 0.12, 9, 5, _BARK_DARK))
    out.append(limb(-236, 12, 240, 5, 0.012, 19, 13, _BARK))
    out.append(path("M-226 15Q0 22 236 9", None, _BARK_DARK, 4, opacity=0.8))
    out.append(path("M-190 5Q-60 7 60 3", None, _BARK_LIGHT, 2.6))
    out.append(path("M110 2Q160 0 214 1", None, _BARK_LIGHT, 2.2))
    # a leaf or two at the tip of the side shoot
    out.append(at(204, -37, path("M0 0C14 -22 44 -26 58 -8C40 6 14 8 0 0Z", 0x5E9E3E) + path("M0 0C14 -22 44 -26 58 -8C36 -12 16 -8 0 0Z", 0x8CC152) + path("M2 -1Q28 -12 54 -8", None, 0x3F7D32, 1.6), rot=-28))
    out.append(at(170, -19, path("M0 0C8 -14 26 -16 34 -5C22 4 8 5 0 0Z", 0x5E9E3E) + path("M0 0C8 -14 26 -16 34 -5C20 -7 9 -5 0 0Z", 0x8CC152), rot=-96))
    return "".join(out)


def draw(doc, look=(0.5, 0.1), look_far=None, blink=0, mood="calm", colors="leaf", hand=0, curl=1.0, perch="twig"):
    """The chameleon's shapes, back to front.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        look: Where the near eye points, each of x and y from -1 to 1.
        look_far: Where the far eye points, or None for the same way.
        blink (float): 0 with the eyes open, 1 closed.
        mood (str): "calm", "happy", "curious" or "sleepy".
        colors (str): A name from `COLORS`.
        hand (float): 0 with both hands on the perch, 1 with one raised in a wave.
        curl (float): How tightly the tail is wound: 0 loose, 1 at rest, 2 tight.
        perch (str): "twig", "wire", or None for no perch.
    """
    skin, shade, light, belly, spots, deep = COLORS[colors]
    happy = mood == "happy"
    if look_far is None:
        look_far = look
    if mood == "sleepy":
        blink = max(blink, 0.6)
    legs = []
    # far legs
    legs.append(limb(92, -58, 116, -8, -0.22, 24, 17, shade))
    legs.append(limb(-92, -48, -92, -8, 0.28, 26, 17, shade))
    # everything it carries above its legs, drawn _CROUCH higher than it sits
    out = []

    # the tail, wound like a watch spring behind it
    turns = 1.25 + 0.3 * curl
    tx, ty = -160, -96
    out.append(limb(-86, -110, tx + 43, ty - 36, 0.10, 46, 32, skin))
    out.append(_spiral(tx, ty, 56, 8, 32, 8, -40, turns, skin))
    out.append(path(smooth(_spiral_points(tx, ty, 56, 8, -40, turns, -10, -2, 0.04, 0.9, 36)), None, shade, 4.5))
    out.append(path(smooth(_spiral_points(tx, ty, 56, 8, -40, turns, 8, 2, 0.02, 0.42, 20)), None, light, 3))

    # the far eye, half hidden behind the brow
    out.append(_eye(doc, 150, -190, 28, look_far, blink, happy, shade, deep, skin, deep))

    # the crest along the back: a row of soft scallops
    back = ((-104, -126, 8), (-86, -144, 9), (-64, -158, 9.5), (-40, -168, 10), (-15, -174, 10), (10, -175, 10), (34, -171, 9.5))
    for bx, by, r in back:
        out.append(circle(bx, by, r, deep))

    # the body
    out.append(path(smooth([(-118, -104), (-74, -154), (-6, -172), (56, -158), (92, -116), (84, -64), (30, -42), (-42, -42), (-100, -58)], True), skin))
    # shade under the back's curve, and the pale belly
    out.append(path(smooth([(-116, -98), (-106, -66), (-50, -52), (30, -52), (84, -72), (84, -62), (30, -42), (-42, -42), (-102, -58)], True), shade))
    out.append(path(smooth([(-92, -62), (-44, -51), (28, -50), (74, -64), (62, -50), (26, -43), (-42, -43), (-88, -54)], True), belly))
    # bands down its sides, and a line of spots
    for sx, sy, lean in ((-70, -146, -10), (-30, -160, -4), (12, -162, 4)):
        out.append(limb(sx, sy, sx + lean, sy + 62, 0.16, 15, 5, shade))
    for sx, sy, r in ((-88, -98, 5), (-50, -92, 6.5), (-9, -90, 7), (32, -94, 6), (-70, -76, 3.5), (-30, -72, 4), (12, -72, 4)):
        out.append(circle(sx, sy, r, spots))
    out.append(path(smooth([(-52, -160), (-10, -169), (36, -164), (58, -152), (30, -158), (-10, -162)], True), light))

    # the head: a helmet with its casque at the back
    out.append(path(smooth([(52, -112), (42, -160), (58, -214), (86, -240), (118, -222), (156, -178), (184, -144), (178, -116), (128, -92), (76, -94)], True), skin))
    out.append(path(smooth([(50, -124), (42, -162), (58, -214), (86, -240), (74, -206), (64, -160), (62, -122)], True), shade))
    out.append(limb(90, -232, 112, -204, -0.08, 7, 2.5, light))
    # the lower jaw, pale like the belly
    out.append(path(smooth([(90, -116), (134, -111), (180, -128), (182, -118), (170, -104), (128, -91), (82, -95)], True), belly))
    if happy:
        # a wide open grin
        out.append(path("M90 -121Q138 -104 182 -131Q176 -104 150 -99Q112 -96 90 -121Z", deep))
        out.append(path("M118 -104Q140 -110 162 -104Q140 -98 118 -104Z", 0xFF8F8F))
        out.append(path("M90 -121Q84 -124 84 -132", None, deep, 4))
    else:
        out.append(path("M181 -130Q138 -106 92 -119Q84 -122 84 -131", None, deep, 4))
    if mood == "curious":
        # the tip of its tongue, tasting the air
        out.append(limb(178, -127, 214, -124, 0.10, 7, 6, 0xFF8F8F))
        out.append(circle(217, -124, 8.5, 0xFF8F8F))
        out.append(circle(219, -127, 2.6, 0xFFC0C0))
        out.append(path("M181 -130Q170 -124 160 -119", None, deep, 4))
    out.append(circle(170, -148, 2.4, deep))
    # the near eye
    out.append(_eye(doc, 110, -164, 39, look, blink, happy, skin, shade, light, deep))

    out = legs + [at(0, _CROUCH, "".join(out))]
    # near hind leg, folded
    out.append(limb(-70, -46, -42, -24, 0.34, 34, 23, skin))
    out.append(limb(-42, -26, -56, -6, 0.22, 21, 17, skin))
    if perch:
        out.append(_perch(perch))

    # feet over the perch
    out.append(_foot(118, 2, shade, deep))
    out.append(_foot(-92, 4, shade, deep))
    out.append(_foot(-58, 4, skin, deep))
    # the near arm: on the perch, or raised in a wave
    sx, sy = 60, -56
    if hand > 0:
        hx, hy = 78 + 76 * hand, -8 - 40 * hand
        out.append(limb(sx, sy, hx, hy, -0.26 + 0.1 * hand, 28, 16, skin))
        if hand > 0.5:
            out.append(_hand(hx, hy, skin, deep, 38))
        else:
            out.append(_foot(hx, hy + 8, skin, deep))
    else:
        out.append(limb(sx, sy, 78, -10, -0.26, 28, 17, skin))
        out.append(_foot(80, 3, skin, deep))
    out.append(circle(sx, sy - 2, 15, skin))
    out.append(path("M48 -46Q58 -37 72 -43", None, shade, 3.5))
    return "".join(out)


def _study(view, ground=None, scale=1, lift=0, **pose):
    def build():
        doc = Doc()
        doc.add(rect(-1000, -1000, 2000, 2000, NAVY))
        if ground:
            doc.add(ground)
        doc.add(at(0, -lift, draw(doc, **pose), scale=scale))
        return doc.svg(view)

    return build


_FULL = (-262, -326, 508, 420)

STILLS = [
    ("chameleon_full", _study(_FULL), 920),
    ("chameleon_face", _study((18, -238, 222, 185), look=(-0.5, 0.3), look_far=(0.7, -0.4), perch=None), 900),
    ("chameleon_happy", _study(_FULL, mood="happy", colors="brand", hand=1, perch="wire"), 920),
    ("chameleon_curious", _study(_FULL, mood="curious", colors="sunset", look=(0.9, 0.5), look_far=(-0.6, -0.7), curl=0), 920),
    ("chameleon_sleepy", _study(_FULL, mood="sleepy", colors="board", look=(0.2, 0.8), curl=2, perch="wire"), 920),
    ("chameleon_icon", _study((-262, -350, 500, 500), circle(-12, -100, 244, 0x123F68) + circle(-12, -100, 244, None, LIME, 6), 0.88, 26, colors="leaf", look=(-0.3, 0.2), look_far=(0.6, -0.5)), 400),
]
