# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The firefly, drawn from a pose: a small hovering creature whose lantern is an LED.

It hovers over the origin: x to the right, y down, the ground at y = 0, about
290 units tall with the gap under it. `draw` returns its shapes for a
`vec.Doc`. The lantern's glow is an argument, so it can blink, pulse or dim.
"""

import math

from vec import Doc, at, circle, ellipse, group, limb, mix, path, rect

NAVY = 0x0B2A4A
LIME = 0xC4DC4C
WHITE = 0xFFFFFF

BODY_LIGHT = 0xA795E0
BODY = 0x7C68C4
BODY_DARK = 0x54439A
BODY_DEEP = 0x362A6E
FACE = 0xF3EEFF
BLUSH = 0xF58FB0
WING = 0xD8F1FF
LAMP_OFF = 0x5F6B3A


def _crescent(cx, cy, rx, ry, tilt, toward, thick, fill, inset=1.0, half=95, opacity=None):
    # a crescent hugging the edge of an ellipse, on the side *toward* (degrees)
    c, s = math.cos(math.radians(half)), math.sin(math.radians(half))
    k = 1 - thick - c
    big = (s * s + k * k) / (2 * k)
    d = "M%.4f %.4fA1 1 0 %d 1 %.4f %.4fA%.4f %.4f 0 0 0 %.4f %.4fZ" % (c, -s, 1 if half > 90 else 0, c, s, big, big, c, -s)
    t = "translate(%.2f %.2f) rotate(%.2f) scale(%.2f %.2f) rotate(%.2f)" % (cx, cy, tilt, rx * inset, ry * inset, toward)
    return group(path(d, fill, opacity=opacity), t)


def _eye(doc, x, y, r, look, lid, happy, glint):
    if happy:
        # a closed, smiling eye: one upward arc on the face
        out = []
        out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (x - r * 0.62, y + r * 0.18, x, y - r * 0.66, x + r * 0.62, y + r * 0.18), None, BODY_DEEP, r * 0.22))
        return "".join(out)
    out = [circle(x, y, r + 2.5, BODY_DEEP)]
    white = doc.radial([(0, WHITE), (0.8, 0xF6F8FC), (1, 0xD6DCEA)])
    out.append(circle(x, y, r, white))
    px, py = x + look[0] * r * 0.32, y + look[1] * r * 0.28
    pr = r * 0.64
    iris = doc.radial([(0, 0x2A5E96), (0.75, NAVY), (1, 0x061A30)], cx=0.5, cy=0.62)
    out.append(circle(px, py, pr, iris))
    out.append(circle(px - pr * 0.36, py - pr * 0.40, pr * 0.30, WHITE))
    # the lantern's light, caught low in the eye
    out.append(circle(px + pr * 0.36, py + pr * 0.38, pr * 0.16, glint))
    if lid > 0:
        drop = -r + 2 * r * lid
        top = y + min(drop, 0)
        d = "M%.2f %.2fA%.2f %.2f 0 0 1 %.2f %.2fQ%.2f %.2f %.2f %.2fZ" % (x - r - 2.5, top, r + 2.5, r + 2.5, x + r + 2.5, top, x, y + drop + r * 0.5, x - r - 2.5, top)
        out.append(path(d, BODY_LIGHT))
        out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (x - r * 0.9, y + drop * 0.55 + r * 0.1, x, y + drop + r * 0.42, x + r * 0.9, y + drop * 0.55 + r * 0.1), None, BODY_DEEP, r * 0.13))
    return "".join(out)


def _wing(length, fill, opacity):
    # a teardrop pointing up from its root at the origin
    w = length * 0.36
    d = "M0 0C%.1f %.1f %.1f %.1f 0 %.1fC%.1f %.1f %.1f %.1f 0 0Z" % (w * 1.5, -length * 0.35, w * 1.25, -length * 1.02, -length, -w * 1.25, -length * 1.02, -w * 0.9, -length * 0.3)
    vein = "M0 %.1fQ%.1f %.1f 0 %.1f" % (-length * 0.12, w * 0.5, -length * 0.5, -length * 0.86)
    return group(path(d, fill) + path(vein, None, WHITE, 2.2, opacity=0.7), opacity=opacity)


def _lantern(glow, color):
    # an LED: collar at the origin, dome hanging down the +y axis
    lit = mix(LAMP_OFF, color, min(1, 0.25 + glow))
    core = mix(lit, 0xFBFFE0, glow * 0.85)
    edge = mix(lit, 0x3F4A1E, 0.35)
    out = []
    out.append(path("M-31 0L-31 44A31 31 0 0 0 31 44L31 0Z", edge))
    out.append(path("M-27 0L-27 44A27 27 0 0 0 27 44L27 0Z", lit))
    # the bright heart of it
    out.append(path("M-12 4L-12 46A14 14 0 0 0 16 46L16 4Z", core))
    # what's inside any LED: the post and the anvil
    out.append(path("M-9 2L-9 34L-3 34L-3 2Z", edge, opacity=0.45))
    out.append(path("M2 2L2 22L16 22L16 28L8 34L2 34Z", edge, opacity=0.45))
    # shade on the left, a glint on the right
    out.append(path("M-27 0L-27 44A27 27 0 0 0 -8 69A30 34 0 0 1 -18 44L-18 0Z", edge, opacity=0.55))
    out.append(rect(15, 8, 6, 30, WHITE, r=3, opacity=0.85))
    out.append(circle(17, 48, 3.4, WHITE, opacity=0.85))
    # the collar, the rim every LED has
    out.append(ellipse(0, 1, 37, 11, BODY_DEEP))
    out.append(ellipse(0, -2, 36, 10, BODY_DARK))
    out.append(ellipse(3, -4, 26, 5, BODY, opacity=0.9))
    return "".join(out)


def draw(doc, look=(0.3, 0.1), blink=0, mood="calm", glow=1.0, beat=0.0, wave=0, tilt=0, lift=0, color=LIME, shadow=True):
    """The firefly's shapes, back to front.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        look: Where the eyes point, each of x and y from -1 to 1.
        blink (float): 0 with the eyes open, 1 closed.
        mood (str): "calm", "happy", "curious" or "sleepy".
        glow (float): The lantern, 0 dark to 1 bright.
        beat (float): Where the wings are in their beat, -1 down to 1 up.
        wave (float): The near arm's lift in degrees.
        tilt (float): The head's tilt in degrees.
        lift (float): How far above its resting height it hovers.
        color: The lantern's colour, 0xRRGGBB.
        shadow (bool): Draw the shadow and the pool of light on the ground.
    """
    happy = mood == "happy"
    if mood == "sleepy":
        blink = max(blink, 0.58)
        beat = min(beat, -0.6)
    if mood == "curious" and tilt == 0:
        tilt = 9
    out = []
    lx, ly = -42, -82 - lift  # the lantern's middle
    if shadow:
        out.append(ellipse(-18, 4, 92 - lift * 0.2, 13, 0x000000, opacity=0.20))
        if glow > 0.05:
            out.append(ellipse(-34, 4, 124, 17, color, opacity=0.10 * glow))
            out.append(ellipse(-38, 4, 70, 10, color, opacity=0.16 * glow))
    # the light it throws: flat rings, so nothing is left to band
    if glow > 0.05:
        for r, a in ((112, 0.06), (92, 0.08), (74, 0.10), (58, 0.14)):
            out.append(circle(lx, ly, r, color, opacity=a * glow))

    body = []
    # wings, from the back of the shoulders
    swing = beat * 20
    body.append(at(-34, -178, _wing(118, WING, 0.42), rot=-58 - swing))
    body.append(at(-30, -182, _wing(128, WING, 0.62), rot=-26 - swing * 0.7))

    # the lantern, hanging back and down from the body
    body.append(at(-10, -130, _lantern(glow, color), rot=30, scale=1.3))

    # legs, short and tucked up in front
    body.append(limb(18, -120, 22, -103, 0.2, 11, 8, BODY_DEEP))
    body.append(limb(34, -126, 43, -110, 0.2, 11, 8, BODY_DEEP))
    body.append(ellipse(25, -100, 9, 6, BODY_DEEP, rot=-8))
    body.append(ellipse(47, -107, 9, 6, BODY_DEEP, rot=-14))

    # the far arm
    body.append(limb(-22, -156, -44, -138, 0.25, 13, 10, BODY_DARK))
    # the body: a small round belly
    body.append(ellipse(2, -150, 38, 36, BODY))
    body.append(_crescent(2, -150, 38, 36, 0, 140, 0.34, BODY_DARK, half=95))
    body.append(ellipse(8, -146, 22, 23, FACE))
    body.append(ellipse(8, -146, 22, 23, color, opacity=0.10 * glow))
    # the near arm
    reach = math.radians(38 - wave)
    hx, hy = 30 + math.cos(reach) * 30, -160 + math.sin(reach) * 30
    body.append(limb(30, -160, hx, hy, -0.25, 14, 11, BODY))
    body.append(circle(hx, hy, 7.5, BODY_LIGHT))
    out.append(at(0, -lift, "".join(body)))

    # the head
    head = []
    cock = 16 if mood == "curious" else 0
    droop = 22 if mood == "sleepy" else 0
    tip = mix(LAMP_OFF, color, min(1, 0.3 + glow))
    for x0, x1, y1, bend in ((-20, -52 + droop * 0.5, -86 + droop, -0.32), (22, 58 + cock * 0.4 + droop * 0.4, -90 - cock + droop, 0.32)):
        head.append(path("M%d -52Q%.1f %.1f %.1f %.1f" % (x0, x0 + bend * 30, -88 + droop * 0.4, x1, y1), None, BODY_DEEP, 5))
        if glow > 0.05:
            head.append(circle(x1, y1, 13, color, opacity=0.22 * glow))
        head.append(circle(x1, y1, 8, tip))
        head.append(circle(x1 + 2.4, y1 - 2.6, 2.6, WHITE, opacity=0.9))
    head.append(ellipse(0, 0, 70, 64, BODY_DEEP))
    head.append(ellipse(0, 0, 67, 61, BODY))
    head.append(_crescent(0, 0, 67, 61, 0, 140, 0.26, BODY_DARK, half=100))
    # the face: a pale mask the eyes sit in
    head.append(path("M-50 6C-54 -30 -22 -40 6 -32C34 -42 62 -26 58 8C56 40 30 50 6 48C-22 52 -48 38 -50 6Z", FACE))
    head.append(ellipse(34, -44, 17, 7, BODY_LIGHT, rot=24))
    ex0, ey0, ex1, ey1 = -20 + look[0] * 3, -2 + look[1] * 2, 30 + look[0] * 3, -2 + look[1] * 2
    glint = mix(WHITE, color, 0.3 + 0.7 * glow)
    head.append(_eye(doc, ex0, ey0, 23, look, blink, happy, glint))
    head.append(_eye(doc, ex1, ey1, 21, look, blink, happy, glint))
    head.append(ellipse(-38, 22, 10, 6, BLUSH, opacity=0.85))
    head.append(ellipse(46, 22, 9, 6, BLUSH, opacity=0.85))
    if happy:
        head.append(path("M-6 24Q6 44 20 24Z", BODY_DEEP))
        head.append(path("M0 34Q7 39 14 34Q7 30 0 34Z", 0xFF8FA8))
    elif mood == "curious":
        head.append(ellipse(8, 30, 5, 6, BODY_DEEP))
    elif mood == "sleepy":
        head.append(path("M0 30Q7 34 14 30", None, BODY_DEEP, 3.4))
    else:
        head.append(path("M-4 27Q7 38 18 27", None, BODY_DEEP, 3.6))
    out.append(at(4, -228 - lift, "".join(head), rot=tilt))
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
    doc.add(rect(-300, -400, 600, 600, NAVY))
    doc.add(circle(0, -150, 190, 0x123E6B))
    doc.add(circle(0, -150, 176, 0x17507F))
    doc.add(at(18, 6, draw(doc, look=(0.4, 0.0), shadow=False, beat=0.4), scale=1.02))
    return doc.svg((-200, -350, 400, 400))


_FULL = (-240, -350, 460, 380)

STILLS = [
    ("firefly_full", _study(_FULL), 920),
    ("firefly_face", _study((-116, -336, 246, 164)), 900),
    ("firefly_happy", _study(_FULL, mood="happy", wave=70, beat=1, lift=12, look=(0, 0)), 920),
    ("firefly_curious", _study(_FULL, mood="curious", look=(0.9, -0.5), glow=0.7, beat=0.3), 920),
    ("firefly_sleepy", _study(_FULL, mood="sleepy", glow=0.18, look=(0.1, 0.8), lift=-14), 920),
    ("firefly_icon", _icon, 400),
]
