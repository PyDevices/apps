# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A chameleon on its perch, drawn from a pose and a set of colours.

It sits above the origin: x to the right, y down, the top of the perch at
y = 0, about 450 units wide and 260 tall. `draw` returns its shapes for a
`vec.Doc`. Its two eyes look where they like, each on its own.
"""

import math

from .vec import Doc, at, circle, ellipse, group, limb, line, path, rect, smooth

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
    if blink >= 0.88:
        out.append(circle(ox, oy, open_r, skin))
        out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (ox - open_r * 0.8, oy, ox, oy + open_r * 0.34, ox + open_r * 0.8, oy), None, deep, r * 0.11))
        return "".join(out)
    out.append(circle(ox, oy, open_r + r * 0.07, deep))
    white = doc.radial([(0, WHITE), (0.8, 0xF4F7FB), (1, 0xD3DCE8)])
    out.append(circle(ox, oy, open_r, white))
    pr = open_r * 0.62
    # a heavy lid pushes the gaze down
    px, py = ox + look[0] * open_r * 0.30, oy + look[1] * open_r * 0.28 + blink * open_r * 0.42
    iris = doc.radial([(0, 0x1F5E8F), (0.75, NAVY), (1, 0x061A30)], cx=0.5, cy=0.62)
    out.append(circle(px, py, pr, iris))
    out.append(circle(px - pr * 0.36, py - pr * 0.40, pr * 0.30, WHITE))
    out.append(circle(px + pr * 0.38, py + pr * 0.36, pr * 0.13, WHITE, opacity=0.8))
    if blink > 0:
        # the lid: a cap of skin drawn down over the top of the eye
        lr = open_r + r * 0.07
        drop = -lr + 2 * lr * blink
        half = math.sqrt(max(lr * lr - drop * drop, 0))
        out.append(
            path(
                "M%.2f %.2fA%.2f %.2f 0 %d 1 %.2f %.2fQ%.2f %.2f %.2f %.2fZ" % (ox - half, oy + drop, lr, lr, 1 if drop > 0 else 0, ox + half, oy + drop, ox, oy + drop + lr * 0.16, ox - half, oy + drop),
                skin,
            )
        )
        out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (ox - half, oy + drop, ox, oy + drop + lr * 0.16, ox + half, oy + drop), None, deep, r * 0.09))
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
    if kind == "stem":
        # a green stem, long enough to climb
        out.append(limb(-360, 9, 360, 7, 0.004, 16, 12, 0x4F9A3A))
        out.append(path("M-350 4Q0 6 350 2", None, 0x8CC152, 3))
        for x, turn, flip in ((-250, -150, False), (-236, 150, True), (236, -40, False), (286, 36, True)):
            leaf = path("M0 0C14 -22 44 -26 58 -8C40 6 14 8 0 0Z", 0x3F8F3A) + path("M0 0C14 -22 44 -26 58 -8C36 -12 16 -8 0 0Z", 0x6FC24B)
            out.append(at(x, 8, leaf, rot=turn, flip=flip))
        return "".join(out)
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


_HIP = (-78, -70)
_NECK = (62, -128)


def _upper(doc, colors, look, look_far, blink, mood, curl=1.0, nod=0, tongue=0, target=None, tail=True):
    """Tail, body and head, in the units they were drawn in, before the crouch."""
    skin, shade, light, belly, spots, deep = COLORS[colors]
    happy = mood == "happy"
    out = []
    if tail:
        # the tail, wound like a watch spring behind it
        turns = 1.25 + 0.3 * curl
        tx, ty = -160, -96
        out.append(limb(-86, -110, tx + 43, ty - 36, 0.10, 46, 32, skin))
        out.append(_spiral(tx, ty, 56, 8, 32, 8, -40, turns, skin))
        out.append(path(smooth(_spiral_points(tx, ty, 56, 8, -40, turns, -10, -2, 0.04, 0.9, 36)), None, shade, 4.5))
        out.append(path(smooth(_spiral_points(tx, ty, 56, 8, -40, turns, 8, 2, 0.02, 0.42, 20)), None, light, 3))

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

    head = []
    # the far eye, half hidden behind the brow
    head.append(_eye(doc, 150, -190, 28, look_far, blink, happy, skin, shade, light, deep))
    # the head: a helmet with its casque at the back
    head.append(path(smooth([(52, -112), (42, -160), (58, -214), (86, -240), (118, -222), (156, -178), (184, -144), (178, -116), (128, -92), (76, -94)], True), skin))
    head.append(path(smooth([(50, -124), (42, -162), (58, -214), (86, -240), (74, -206), (64, -160), (62, -122)], True), shade))
    head.append(limb(90, -232, 112, -204, -0.08, 7, 2.5, light))
    # the lower jaw, pale like the belly
    head.append(path(smooth([(90, -116), (134, -111), (180, -128), (182, -118), (170, -104), (128, -91), (82, -95)], True), belly))
    if tongue > 0:
        # the mouth open, and the tongue on its way to the target
        gx, gy = target if target else (360, -128)
        ex, ey = 176 + (gx - 176) * tongue, -122 + (gy + 122) * tongue
        head.append(path("M92 -120Q138 -108 182 -132Q180 -108 152 -100Q112 -97 92 -120Z", deep))
        head.append(limb(150, -112, ex, ey, 0.03, 13, 8, 0xFF8F8F))
        head.append(circle(ex, ey, 13, 0xFF8F8F))
        head.append(circle(ex + 3, ey - 5, 4, 0xFFC0C0))
        head.append(path("M92 -120Q84 -123 84 -131", None, deep, 4))
    elif happy:
        # a wide open grin
        head.append(path("M90 -121Q138 -104 182 -131Q176 -104 150 -99Q112 -96 90 -121Z", deep))
        head.append(path("M118 -104Q140 -110 162 -104Q140 -98 118 -104Z", 0xFF8F8F))
        head.append(path("M90 -121Q84 -124 84 -132", None, deep, 4))
    else:
        head.append(path("M181 -130Q138 -106 92 -119Q84 -122 84 -131", None, deep, 4))
    if mood == "curious" and tongue <= 0:
        # the tip of its tongue, tasting the air
        head.append(limb(178, -127, 214, -124, 0.10, 7, 6, 0xFF8F8F))
        head.append(circle(217, -124, 8.5, 0xFF8F8F))
        head.append(circle(219, -127, 2.6, 0xFFC0C0))
        head.append(path("M181 -130Q170 -124 160 -119", None, deep, 4))
    head.append(circle(170, -148, 2.4, deep))
    # the near eye
    head.append(_eye(doc, 110, -164, 39, look, blink, happy, skin, shade, light, deep))
    head = "".join(head)
    if nod:
        head = group(head, "rotate(%.2f %d %d)" % (nod, _NECK[0], _NECK[1]))
    out.append(head)
    return "".join(out)


def _gait(phase):
    """A foot's place in its stride: ``(forward, lift)`` for a phase from 0 to 1."""
    phase = phase % 1.0
    if phase < 0.6:
        # on the perch, carried back as the body moves on
        return 19 * (1 - 2 * phase / 0.6), 0.0
    q = (phase - 0.6) / 0.4
    return -19 + 38 * q, math.sin(q * math.pi) * 18


def grip(hand=1.0):
    """Where the raised hand holds something, ``(x, y, turn)``.

    The point is the palm between its two bundles of toes, in the units
    `draw` uses, and the turn is the hand's in degrees: a prop drawn pointing
    up from its own origin, placed there and turned so, stands in the hand.
    """
    return 78 + 76 * hand, -8 - 40 * hand, 38


def draw(doc, look=(0.5, 0.1), look_far=None, blink=0, mood="calm", colors="leaf", hand=0, curl=1.0, perch="twig", step=None, nod=0, tongue=0, target=None):
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
        perch (str): "twig", "wire", "stem", or None for no perch.
        step (float): Where it is in its walk, 0 to 1 and round again, or None standing.
        nod (float): The head's tilt in degrees, positive chin down.
        tongue (float): 0 with the tongue in, 1 with it shot out to *target*.
        target: Where the tongue strikes, ``(x, y)`` in the head's own units.
    """
    skin, shade, light, belly, spots, deep = COLORS[colors]
    if look_far is None:
        look_far = look
    if mood == "sleepy":
        blink = max(blink, 0.5)
    # the four feet: near front, far front, near hind, far hind, each (forward, lift)
    if step is None:
        nf = ff = nh = fh = (0, 0)
        sway, bob = 0, 0
    else:
        # diagonal pairs move together, and the body rocks twice a stride
        nf, fh = _gait(step), _gait(step + 0.04)
        ff, nh = _gait(step + 0.5), _gait(step + 0.54)
        sway = 4 * math.sin(step * 4 * math.pi)
        bob = 2 * math.cos(step * 4 * math.pi)
    out = []
    # far legs
    out.append(limb(92 + sway, -58 + bob, 116 + ff[0], -8 - ff[1], -0.22, 24, 17, shade))
    out.append(limb(-92 + sway, -48 + bob, -92 + fh[0], -8 - fh[1], 0.28, 26, 17, shade))
    out.append(at(sway, _CROUCH + bob, _upper(doc, colors, look, look_far, blink, mood, curl, nod, tongue, target)))
    # near hind leg, folded
    kx, ky = -42 + nh[0] * 0.6 + sway * 0.4, -24 - nh[1] * 0.5
    out.append(limb(-70 + sway, -46 + bob, kx, ky, 0.34, 34, 23, skin))
    out.append(limb(kx, ky - 2, -56 + nh[0], -6 - nh[1], 0.22, 21, 17, skin))
    if perch:
        out.append(_perch(perch))

    # feet over the perch
    out.append(_foot(118 + ff[0], 2 - ff[1], shade, deep, -ff[1]))
    out.append(_foot(-92 + fh[0], 4 - fh[1], shade, deep, -fh[1]))
    out.append(_foot(-58 + nh[0], 4 - nh[1], skin, deep, -nh[1]))
    # the near arm: on the perch, or raised in a wave
    sx, sy = 60 + sway, -56 + bob
    if hand > 0:
        hx, hy, turn = grip(hand)
        out.append(limb(sx, sy, hx, hy, -0.26 + 0.1 * hand, 28, 16, skin))
        if hand > 0.5:
            out.append(_hand(hx, hy, skin, deep, turn))
        else:
            out.append(_foot(hx, hy + 8, skin, deep))
    else:
        out.append(limb(sx, sy, 78 + nf[0], -10 - nf[1], -0.26, 28, 17, skin))
        out.append(_foot(80 + nf[0], 3 - nf[1], skin, deep, -nf[1]))
    out.append(circle(sx, sy - 2, 15, skin))
    out.append(path("M%.1f %.1fq10 9 24 3" % (sx - 12, sy + 10), None, shade, 3.5))
    return "".join(out)


def _turned(point, turn, hip):
    """Where a point of the body lands when the body turns about its hip to stand at *hip*."""
    a = math.radians(turn)
    x, y = point[0] - _HIP[0], point[1] - _HIP[1]
    return hip[0] + x * math.cos(a) - y * math.sin(a), hip[1] + x * math.sin(a) + y * math.cos(a)


def _body_at(body, turn, hip):
    return group(body, "translate(%.2f %.2f) rotate(%.2f) translate(%d %d)" % (hip[0], hip[1], turn, -_HIP[0], -_HIP[1]))


def draw_sit(doc, look=(0.0, 0.0), look_far=None, blink=0, mood="calm", colors="leaf", perch="twig", wave=0.0):
    """Sitting up on its haunches, both hands free: how it idles on a desktop.

    Args:
        wave (float): 0 with the near hand held out, 1 with it lifted in a wave.
        The others are as in `draw`.
    """
    skin, shade, light, belly, spots, deep = COLORS[colors]
    if look_far is None:
        look_far = look
    if mood == "sleepy":
        blink = max(blink, 0.5)
    turn, hip = -52, (-36, -44)
    out = []
    # the tail, wound up on the perch behind it
    tx, ty = -150, -58
    out.append(limb(-62, -52, tx + 46, ty + 2, -0.12, 46, 32, skin))
    out.append(_spiral(tx, ty, 46, 7, 30, 8, 0, 1.55, skin))
    out.append(path(smooth(_spiral_points(tx, ty, 46, 7, 0, 1.55, -9, -2, 0.04, 0.9, 36)), None, shade, 4.5))
    out.append(path(smooth(_spiral_points(tx, ty, 46, 7, 0, 1.55, 8, 2, 0.1, 0.5, 20)), None, light, 3))
    # far limbs
    fx, fy = _turned((84, -80), turn, hip)
    out.append(limb(fx, fy, fx + 52, fy + 34, 0.22, 24, 15, shade))
    out.append(_hand(fx + 52, fy + 34, shade, deep, 100))
    out.append(limb(-16, -30, 44, -8, -0.2, 26, 18, shade))
    out.append(_body_at(_upper(doc, colors, look, look_far, blink, mood, nod=46, tail=False), turn, hip))
    # the near haunch, folded under it
    out.append(ellipse(-26, -40, 38, 29, skin, rot=-24))
    out.append(path("M-56 -30Q-30 -6 4 -22", None, shade, 3.5))
    out.append(limb(-6, -24, 16, -8, -0.2, 22, 17, skin))
    if perch:
        out.append(_perch(perch))
    out.append(_foot(46, 3, shade, deep))
    out.append(_foot(18, 4, skin, deep))
    # the near arm, held out or waving
    sx, sy = _turned((60, -78), turn, hip)
    hx, hy = sx + 58 + 40 * wave, sy + 30 - 22 * wave
    out.append(limb(sx, sy, hx, hy, 0.26 - 0.06 * wave, 27, 16, skin))
    out.append(_hand(hx, hy, skin, deep, 70 - 34 * wave))
    out.append(circle(sx, sy, 14, skin))
    return "".join(out)


def draw_sleep(doc, colors="leaf", perch="twig"):
    """Asleep on the perch: belly down, chin on its hand, tail wound tight."""
    skin, shade, light, belly, spots, deep = COLORS[colors]
    out = []
    out.append(limb(96, -30, 112, -8, -0.2, 22, 17, shade))
    out.append(at(0, 40, _upper(doc, colors, (0, 0), (0, 0), 1, "calm", curl=2, nod=14)))
    # legs folded away: a haunch and an elbow
    out.append(ellipse(-64, -22, 34, 22, skin, rot=-10))
    out.append(path("M-94 -18Q-66 2 -34 -14", None, shade, 3.5))
    out.append(limb(52, -34, 84, -10, -0.3, 26, 17, skin))
    if perch:
        out.append(_perch(perch))
    out.append(_foot(116, 2, shade, deep))
    out.append(_foot(-36, 4, skin, deep))
    out.append(_foot(88, 3, skin, deep))
    # sleep, rising off it
    for zx, zy, zs, opa in ((206, -128, 1.0, 0.9), (226, -168, 1.35, 0.75), (252, -218, 1.75, 0.6)):
        out.append(path("M%.1f %.1fh%.1fl%.1f %.1fh%.1f" % (zx, zy, 14 * zs, -14 * zs, 16 * zs, 14 * zs), None, LIME, 4.2 * zs ** 0.5, opacity=opa))
    return "".join(out)


def draw_hang(doc, look=(-0.2, 0.2), look_far=None, mood="happy", colors="leaf", perch="twig", wave=1.0):
    """Hanging head down by its tail and hind feet, hands free.

    The perch is still at y = 0; the body hangs about 330 units below it.
    """
    skin, shade, light, belly, spots, deep = COLORS[colors]
    if look_far is None:
        look_far = look
    turn, hip = 82, (22, 62)
    out = []
    # the far hind leg, and the tail going up behind the perch
    out.append(limb(hip[0] + 14, hip[1] + 6, -52, 6, 0.2, 26, 17, shade))
    rx, ry = _turned((-108, -106), turn, hip)
    out.append(limb(rx - 8, ry + 14, 96, -14, 0.24, 44, 26, skin))
    # the far arm, dangling
    fx, fy = _turned((84, -80), turn, hip)
    out.append(limb(fx, fy, fx - 62, fy + 30, 0.2, 24, 15, shade))
    out.append(_hand(fx - 62, fy + 30, shade, deep, -150))
    out.append(_body_at(_upper(doc, colors, look, look_far, 0, mood, nod=-34, tail=False), turn, hip))
    # the near hind leg, reaching up to hold on
    out.append(limb(hip[0], hip[1], -18, 6, 0.24, 32, 18, skin))
    if perch:
        out.append(_perch(perch))
    # three turns of tail round the perch, and its tip
    for i in range(3):
        cx = 96 + i * 21
        out.append(limb(cx - 5, -9, cx + 6, 20, 0, 20 - i * 3, 18 - i * 3, skin))
        out.append(limb(cx - 6, -8, cx - 1, 6, 0, 4, 3, light))
    out.append(path("M162 22q16 6 20 -8q2 -12 -9 -12q-8 1 -7 8", None, skin, 9))
    out.append(_foot(-52, 3, shade, deep, 180))
    out.append(_foot(-18, 2, skin, deep, 180))
    # the near arm, thrown wide
    sx, sy = _turned((60, -78), turn, hip)
    hx, hy = sx - 66, sy + 6 - 34 * wave
    out.append(limb(sx, sy, hx, hy, -0.24, 27, 16, skin))
    out.append(_hand(hx, hy, skin, deep, -70 + 30 * wave))
    out.append(circle(sx, sy, 14, skin))
    return "".join(out)


def _bug(x, y, s=1.0):
    """A small beetle, the kind a chameleon and a programmer both go after."""
    return at(
        x,
        y,
        ellipse(-9, -11, 12, 6, 0xCFE8FF, opacity=0.75, rot=-30)
        + ellipse(9, -11, 12, 6, 0xCFE8FF, opacity=0.75, rot=30)
        + line(-6, 6, -13, 11, 0x2B2B33, 2)
        + line(6, 6, 13, 11, 0x2B2B33, 2)
        + line(0, 8, 0, 14, 0x2B2B33, 2)
        + ellipse(0, 0, 11, 9, 0xE4513D)
        + path("M-11 0A11 9 0 0 1 11 0Z", 0x2B2B33)
        + circle(-4, 3.5, 2, 0x2B2B33)
        + circle(4, 3.5, 2, 0x2B2B33)
        + circle(-4, -4, 1.6, WHITE)
        + circle(4, -4, 1.6, WHITE),
        scale=s,
    )


def _sparkle(x, y, r, color):
    return path("M%.1f %.1fQ%.1f %.1f %.1f %.1fQ%.1f %.1f %.1f %.1fQ%.1f %.1f %.1f %.1fQ%.1f %.1f %.1f %.1fZ" % (x, y - r, x, y, x + r, y, x, y, x, y + r, x, y, x - r, y, x, y, x, y - r), color)


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
