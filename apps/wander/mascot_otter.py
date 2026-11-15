# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The otter, drawn from a pose: a tool user that keeps its favourite pebble close.

The otter stands on the origin: x to the right, y down, the ground at y = 0,
about 300 units tall. `draw` returns its shapes for a `vec.Doc`, and `head`
the head alone, for an icon.
"""

import math

from vec import Doc, at, circle, ellipse, group, lerp, limb, line, path, rect, smooth

FUR = 0x7A4C33
FUR_LIGHT = 0x99694A
FUR_DARK = 0x5C3724
FUR_DEEP = 0x402418
# a sea otter's head is paler than its body
HEAD = 0xB48A66
HEAD_LIGHT = 0xCFA883
HEAD_DARK = 0x8E6646
CREAM = 0xF7E6C6
CREAM_SHADE = 0xE0C197
NOSE = 0x35211C
NAVY = 0x0B2A4A
LIME = 0xC4DC4C
WHITE = 0xFFFFFF
BLUSH = 0xF0A07C
STONE = 0x9FB2C2
STONE_DARK = 0x71879A
STONE_LIGHT = 0xCBD8E2

HEAD_Y = -240


def _crescent(cx, cy, rx, ry, tilt, toward, thick, fill, inset=1.0, half=95, opacity=None):
    """A crescent hugging the edge of an ellipse: a shade or a glint."""
    c, s = math.cos(math.radians(half)), math.sin(math.radians(half))
    k = 1 - thick - c
    big = (s * s + k * k) / (2 * k)
    d = "M%.4f %.4fA1 1 0 %d 1 %.4f %.4fA%.4f %.4f 0 0 0 %.4f %.4fZ" % (c, -s, 1 if half > 90 else 0, c, s, big, big, c, -s)
    t = "translate(%.2f %.2f) rotate(%.2f) scale(%.2f %.2f) rotate(%.2f)" % (cx, cy, tilt, rx * inset, ry * inset, toward)
    return group(path(d, fill, opacity=opacity), t)


def _mirror(points):
    # a closed outline from its right half, top to bottom
    return points + [(-x, y) for x, y in reversed(points) if x != 0]


def _eye(doc, x, y, r, look, lid, happy):
    out = []
    if happy:
        # a closed, smiling eye: one upward arc on the fur
        out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (x - r * 0.8, y + r * 0.25, x, y - r * 0.85, x + r * 0.8, y + r * 0.25), None, FUR_DEEP, r * 0.3))
        return "".join(out)
    white = doc.radial([(0, WHITE), (0.8, 0xF6F4EE), (1, 0xDAD3C6)])
    out.append(circle(x, y, r + 2.5, FUR_DEEP))
    out.append(circle(x, y, r, white))
    px, py = x + look[0] * r * 0.30, y + look[1] * r * 0.28
    pr = r * 0.68
    iris = doc.radial([(0, 0x6B4A2E), (0.7, 0x2E1C14), (1, 0x1A0F0B)], cx=0.5, cy=0.62)
    out.append(circle(px, py, pr, iris))
    out.append(circle(px - pr * 0.34, py - pr * 0.40, pr * 0.32, WHITE))
    out.append(circle(px + pr * 0.40, py + pr * 0.36, pr * 0.14, WHITE, opacity=0.8))
    if lid > 0:
        # the lid comes down as a cap of fur
        drop = -r + 2 * r * lid
        top = y + min(drop, 0)
        d = "M%.2f %.2fA%.2f %.2f 0 0 1 %.2f %.2fQ%.2f %.2f %.2f %.2fZ" % (x - r - 3.6, top, r + 3.6, r + 3.6, x + r + 3.6, top, x, y + drop + (r * 0.45 if lid >= 0.95 else 0) + (drop - min(drop, 0)), x - r - 3.6, top)
        out.append(path(d, HEAD))
        if lid >= 0.95:
            out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (x - r * 0.75, y + r * 0.1, x, y + r * 0.6, x + r * 0.75, y + r * 0.1), None, FUR_DEEP, r * 0.2))
        else:
            out.append(line(x - r * 0.99, y + drop, x + r * 0.99, y + drop, FUR_DEEP, r * 0.13))
    return "".join(out)


def head(doc, look=(0.0, 0.1), blink=0, mood="calm"):
    """The head alone, centred on the origin, about 180 wide and 150 tall."""
    out = []
    # ears: small, low on the sides, as a swimmer's are
    for side in (-1, 1):
        out.append(circle(side * 84, -26, 14, HEAD_DARK))
        out.append(circle(side * 84, -26, 10, HEAD))
        out.append(circle(side * 82, -25, 6, FUR_DEEP))
    # the skull: broad, with full cheeks
    skull = _mirror([(0, -66), (48, -62), (82, -30), (92, 10), (76, 44), (38, 62), (0, 66)])
    out.append(path(smooth([(x - 3, y + 3) for x, y in skull], True), HEAD_DARK))
    out.append(path(smooth(skull, True), HEAD))
    # light on the brow, shade under the left cheek
    out.append(ellipse(42, -48, 26, 8, HEAD_LIGHT, rot=24))
    # the pale muzzle: two cheeks and a chin
    out.append(ellipse(-29, 27, 41, 31, CREAM_SHADE))
    out.append(ellipse(29, 27, 41, 31, CREAM))
    out.append(ellipse(-25, 25, 39, 29, CREAM))
    out.append(ellipse(0, 40, 34, 24, CREAM))
    # a pale blaze between the eyes ties the muzzle to the brow
    out.append(ellipse(0, -6, 15, 22, CREAM))
    # eyes
    happy = mood == "happy"
    if mood == "sleepy":
        blink = max(blink, 0.58)
    ey = -18
    lift = -5 if mood == "curious" else 0
    out.append(_eye(doc, -37, ey, 19, look, blink, happy))
    out.append(_eye(doc, 37, ey + lift, 21 if mood == "curious" else 19, look, blink, happy))
    # brows: two soft dabs that carry the mood
    if mood == "curious":
        out.append(ellipse(-38, -47, 10, 4, HEAD_DARK, rot=-8))
        out.append(ellipse(40, -57, 10, 4, HEAD_DARK, rot=12))
    elif mood == "sleepy":
        out.append(ellipse(-38, -43, 10, 3.5, HEAD_DARK, rot=-14))
        out.append(ellipse(38, -43, 10, 3.5, HEAD_DARK, rot=14))
    else:
        out.append(ellipse(-38, -46, 9, 3.5, HEAD_DARK, rot=-10))
        out.append(ellipse(38, -46, 9, 3.5, HEAD_DARK, rot=10))
    # cheeks
    out.append(ellipse(-58, 20, 13, 8, BLUSH))
    out.append(ellipse(58, 20, 13, 8, BLUSH))
    # the nose: broad and soft, with a glint
    out.append(path("M-24 4Q0 -8 24 4Q22 20 0 28Q-22 20 -24 4Z", NOSE))
    out.append(ellipse(8, 6, 8, 3, 0x7A5A50, rot=-8))
    # mouth
    if happy:
        out.append(path("M-20 38Q0 44 20 38Q16 62 0 62Q-16 62 -20 38Z", NOSE))
        out.append(path("M-10 54Q0 46 10 54Q6 61 0 61Q-6 61 -10 54Z", 0xF08A8A))
        out.append(line(0, 27, 0, 38, NOSE, 3))
    elif mood == "curious":
        out.append(line(0, 27, 0, 36, NOSE, 3))
        out.append(ellipse(0, 43, 6, 7, NOSE))
    elif mood == "sleepy":
        out.append(line(0, 27, 0, 35, NOSE, 3))
        out.append(path("M-12 37Q-6 42 0 35Q6 42 12 37", None, NOSE, 3))
    else:
        out.append(line(0, 27, 0, 35, NOSE, 3))
        out.append(path("M-17 34Q-9 46 0 35Q9 46 17 34", None, NOSE, 3.2))
    # whiskers and the dots they grow from
    for side in (-1, 1):
        for dx, dy in ((30, 26), (37, 34), (29, 40)):
            out.append(circle(side * dx, dy, 1.8, 0xD9B98E))
        out.append(path("M%d 28Q%d 22 %d 18" % (side * 44, side * 70, side * 97), None, WHITE, 2, opacity=0.9))
        out.append(path("M%d 34Q%d 34 %d 36" % (side * 46, side * 74, side * 101), None, WHITE, 2, opacity=0.9))
        out.append(path("M%d 40Q%d 46 %d 54" % (side * 44, side * 68, side * 92), None, WHITE, 2, opacity=0.9))
    return "".join(out)


def _pebble():
    # its favourite: smooth, grey-blue, with one bright vein
    return (
        ellipse(0, 2, 27, 20, STONE_DARK)
        + ellipse(1, 0, 26, 19, STONE)
        + path("M-22 6Q-2 -6 24 -4", None, LIME, 3.4)
        + ellipse(9, -9, 10, 4, STONE_LIGHT, rot=-14)
    )


def _driver():
    # a small screwdriver, pointing up from the grip at the origin
    return (
        rect(-2.2, -64, 4.4, 36, 0xC9D3DC, r=1)
        + path("M-3.4 -70L3.4 -70L2.2 -62L-2.2 -62Z", 0x8E9BA8)
        + rect(-8, -32, 16, 44, LIME, r=7)
        + rect(-8, -32, 6, 44, 0x9DB334, r=3)
        + rect(-8, -24, 16, 4, NAVY)
        + rect(-8, 0, 16, 4, NAVY)
    )


def _paw(x, y, turn):
    return group(
        ellipse(0, 0, 13.5, 12, FUR_DEEP) + circle(-8.5, -7.5, 4.6, FUR_DEEP) + circle(0, -11, 5, FUR_DEEP) + circle(8.5, -7.5, 4.6, FUR_DEEP),
        "translate(%.1f %.1f) rotate(%.1f)" % (x, y, turn),
    )


def draw(doc, look=(0.0, 0.1), blink=0, mood="calm", wave=0, tilt=None, shadow=True, tail=True):
    """The otter's shapes, back to front.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        look: Where the eyes point, each of x and y from -1 to 1.
        blink (float): 0 with the eyes open, 1 closed.
        mood (str): "calm", "happy", "curious" or "sleepy".
        wave (float): How far the paw with the screwdriver is raised, 0 to 100.
        tilt (float): The head's lean in degrees, or None for the mood's own.
        shadow (bool): Draw the soft shadow on the ground.
        tail (bool): Draw the tail lying on the ground behind.
    """
    out = []
    if shadow:
        out.append(ellipse(-24, 4, 190, 20, 0x000000, opacity=0.16))
        out.append(ellipse(-6, 5, 112, 13, 0x000000, opacity=0.18))
    # the tail: thick at the root, lying along the ground behind
    if tail:
        out.append(limb(-40, -36, -196, -20, 0.15, 60, 20, FUR_DARK))
        out.append(limb(-48, -46, -190, -26, 0.15, 30, 9, FUR))
    # feet, wide and webbed
    for side in (-1, 1):
        out.append(ellipse(side * 42, -9, 34, 14, FUR_DEEP))
        out.append(line(side * 34, -14, side * 30, -2, FUR_DARK, 2.4))
        out.append(line(side * 50, -14, side * 54, -2, FUR_DARK, 2.4))
    # the body: a long pear
    body = _mirror([(0, -200), (38, -194), (58, -140), (72, -70), (60, -18), (0, -6)])
    out.append(path(smooth([(x - 4, y + 2) for x, y in body], True), FUR_DARK))
    out.append(path(smooth(body, True), FUR))
    # the side away from the light
    out.append(path(smooth([(-34, -190), (-56, -140), (-70, -70), (-58, -20), (-28, -9), (-42, -44), (-48, -100), (-40, -160)], True), FUR_DARK))
    belly = _mirror([(0, -184), (26, -174), (40, -112), (43, -56), (28, -22), (0, -16)])
    out.append(path(smooth(belly, True), CREAM))
    out.append(path(smooth([(-24, -172), (-39, -112), (-42, -56), (-28, -23), (-12, -18), (-26, -46), (-29, -100), (-18, -156)], True), CREAM_SHADE))
    # the head's shadow on the chest
    out.append(ellipse(0, -182, 34, 12, CREAM_SHADE))

    # the arm that holds the pebble against its chest
    out.append(at(2, -118, _pebble(), rot=-8))
    out.append(limb(-42, -166, -26, -116, 0.30, 28, 23, FUR_DARK))
    out.append(_paw(-22, -114, 62))
    # the arm with the screwdriver
    a = math.radians(104 - wave * 1.35)
    hx, hy = 42 + math.cos(a) * 78, -166 + math.sin(a) * 78
    if wave < 12:
        # at rest the hand comes in to steady the pebble
        hx, hy = lerp(26, hx, wave / 12), lerp(-112, hy, wave / 12)
        out.append(limb(42, -166, hx, hy, -0.30, 28, 23, FUR))
        out.append(_paw(hx - 2, hy + 2, -62))
    else:
        turn = 14 - (wave - 12) * 0.5
        out.append(limb(42, -166, hx, hy, -0.14, 28, 23, FUR))
        out.append(at(hx, hy, _driver(), rot=turn))
        out.append(_paw(hx, hy, turn))

    if tilt is None:
        tilt = {"curious": 9, "sleepy": -6, "happy": -4}.get(mood, 0)
    out.append(at(0, HEAD_Y, head(doc, look, blink, mood), rot=tilt))
    return "".join(out)


def _study(view, **pose):
    def build():
        doc = Doc()
        doc.add(rect(-1000, -1000, 2000, 2000, NAVY))
        doc.add(draw(doc, **pose))
        return doc.svg(view)

    return build


def _icon():
    doc = Doc()
    doc.add(rect(-200, -200, 400, 400, NAVY))
    doc.add(circle(0, 0, 184, 0x1C6E8C))
    doc.add(at(0, 6, head(doc, (0.25, 0.1), 0, "calm"), scale=1.72))
    return doc.svg((-200, -200, 400, 400))


def _float():
    # on its back in the water, the pebble on its chest: seen from above
    doc = Doc()
    water, light, deep = 0x1C6E8C, 0x3C93AD, 0x175C76
    doc.add(rect(-400, -300, 800, 600, water))
    for cx, cy, rx, ry in ((-10, 10, 300, 170), (-10, 10, 236, 128)):
        doc.add(ellipse(cx, cy, rx, ry, None, deep, 5))
    for x, y, w in ((-250, -150, 90), (150, -170, 120), (190, 150, 80), (-290, 120, 110), (-60, 196, 70), (40, -214, 60)):
        doc.add(line(x, y, x + w, y, light, 5))
    doc.add(ellipse(4, 14, 190, 84, deep))
    # the tail trails behind, under the water's surface
    doc.add(limb(130, 24, 228, 60, -0.2, 44, 14, 0x3E5F5E))
    doc.add(at(126, 10, draw(doc, look=(-0.2, -0.6), mood="happy", shadow=False, tilt=66, tail=False), rot=-90, scale=0.92))
    return doc.svg((-230, -190, 460, 380))


_FULL = (-260, -344, 470, 388)

STILLS = [
    ("otter_full", _study(_FULL), 920),
    ("otter_face", _study((-135, -322, 270, 180), look=(0.4, 0.0)), 900),
    ("otter_happy", _study(_FULL, mood="happy", wave=84), 920),
    ("otter_curious", _study(_FULL, mood="curious", wave=40, look=(0.8, -0.3)), 920),
    ("otter_sleepy", _study(_FULL, mood="sleepy", look=(0.0, 0.7)), 920),
    ("otter_icon", _icon, 400),
    ("otter_float", _float, 920),
]
