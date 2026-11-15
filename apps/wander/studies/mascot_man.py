# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A bench mentor, drawn from a pose: a mascot study beside the crab.

He stands on the origin: x to the right, y down, the ground at y = 0, about
335 units tall. `draw` returns his shapes for a `vec.Doc`.
"""

import math

from ..vec import Doc, at, circle, ellipse, group, lerp, limb, line, mix, path, rect, smooth

SKIN = 0xE2A57B
SKIN_LIGHT = 0xF3C6A2
SKIN_SHADE = 0xC4855C
NOSE = 0xD4906A
HAIR = 0x4A3F3A
HAIR_LIGHT = 0x6A5C54
GREY = 0xB5ABA2
SHIRT = 0xF4EBD6
SHIRT_SHADE = 0xD3C4A6
APRON = 0x2E6C96
APRON_SHADE = 0x1F5378
APRON_LIGHT = 0x4A8CB8
TROUSERS = 0x4B4A5A
TROUSERS_SHADE = 0x36354A
SHOE = 0x6B3F2A
SHOE_LIGHT = 0x8F5A3C
INK = 0x24212B
NAVY = 0x0B2A4A
LIME = 0xC4DC4C
WHITE = 0xFFFFFF
HEAD_Y = -256


def _eye(doc, x, y, look, lid, squint):
    out = []
    out.append(ellipse(x, y, 12, 13, WHITE))
    px, py = x + look[0] * 4.2, y + look[1] * 4.0
    iris = doc.radial([(0, 0x8A5A32), (0.7, 0x5A3418), (1, 0x3A1F0E)], cx=0.5, cy=0.6)
    out.append(circle(px, py, 7.6, iris))
    out.append(circle(px, py, 3.6, INK))
    out.append(circle(px - 2.8, py - 3.2, 2.5, WHITE))
    out.append(circle(px + 2.6, py + 2.6, 1.1, WHITE, opacity=0.8))
    if lid > 0:
        # the upper lid comes down as a cap of skin, with a lash line under it
        drop = y - 14 + 27 * lid
        out.append(path("M%.1f %.1fL%.1f %.1fQ%.1f %.1f %.1f %.1fL%.1f %.1fZ" % (x - 14, y - 15, x - 14, drop - 2, x, drop + 4, x + 14, drop - 2, x + 14, y - 15), SKIN))
        out.append(path("M%.1f %.1fQ%.1f %.1f %.1f %.1f" % (x - 12, drop - 2, x, drop + 4.5, x + 12, drop - 2), None, INK, 2.6))
    else:
        out.append(path("M%.1f %.1fQ%.1f %.1f %.1f %.1f" % (x - 12, y - 6, x, y - 16.5, x + 12, y - 6), None, 0x4A2F25, 2))
    if squint > 0:
        # a smile pushes the cheek up under the eye
        rise = y + 14 - 11 * squint
        out.append(path("M%.1f %.1fL%.1f %.1fQ%.1f %.1f %.1f %.1fL%.1f %.1fZ" % (x - 14, y + 15, x - 14, rise + 3, x, rise - 5, x + 14, rise + 3, x + 14, y + 15), SKIN))
        out.append(path("M%.1f %.1fQ%.1f %.1f %.1f %.1f" % (x - 11, rise + 3, x, rise - 4.5, x + 11, rise + 3), None, SKIN_SHADE, 2.2))
    return "".join(out)


def _head(doc, look, blink, mood):
    # drawn about the middle of the face; the neck joins at (0, 60)
    out = []
    # hair behind the ears, then the ears
    out.append(path(smooth([(-58, 0), (-62, -30), (-52, -62), (-22, -82), (16, -86), (48, -74), (62, -44), (60, 0), (40, 10), (-40, 10)], True), HAIR))
    for side in (-1, 1):
        out.append(ellipse(side * 56, 4, 10, 14, SKIN if side > 0 else SKIN_SHADE))
        out.append(ellipse(side * 57, 5, 5, 8, SKIN_SHADE if side > 0 else mix(SKIN_SHADE, 0x000000, 0.15)))
    # the face
    face = [(0, -60), (38, -50), (53, -14), (50, 24), (34, 52), (0, 63), (-34, 52), (-50, 24), (-53, -14), (-38, -50)]
    out.append(path(smooth(face, True), SKIN))
    out.append(path(smooth([(-38, -50), (-53, -14), (-50, 24), (-40, 30), (-42, -8), (-30, -44)], True), SKIN_SHADE))
    out.append(ellipse(32, -50, 9, 4, SKIN_LIGHT, rot=24))
    # the beard: jaw to jaw, with the cheeks' line as its top edge
    beard = [(-55, -6), (-53, 26), (-38, 56), (-14, 70), (14, 70), (38, 56), (53, 26), (55, -6), (47, 2), (42, 20), (26, 27), (0, 22), (-26, 27), (-42, 20), (-47, 2)]
    out.append(path(smooth(beard, True), HAIR))
    out.append(path(smooth([(-53, 26), (-38, 56), (-14, 70), (-6, 62), (-30, 48), (-44, 24)], True), mix(HAIR, 0x000000, 0.22)))
    # the grey coming in at the chin
    out.append(path(smooth([(-17, 55), (0, 51), (17, 55), (15, 65), (0, 70), (-15, 65)], True), mix(HAIR, GREY, 0.5)))
    out.append(path(smooth([(1, 52), (17, 55), (15, 65), (2, 69)], True), mix(HAIR, GREY, 0.72)))
    # the lower lip's clearing
    if mood in ("happy", "curious"):
        out.append(ellipse(0, 42, 17, 9, mix(SKIN_SHADE, 0x9A4A3A, 0.22)))
    else:
        out.append(ellipse(1, 45, 12, 5.5, mix(SKIN_SHADE, 0x9A4A3A, 0.22)))
    # the mouth, in a clearing of the beard
    if mood == "happy":
        out.append(path("M-21 34Q0 30 21 34Q16 56 0 57Q-16 56 -21 34Z", 0x5A1F1C))
        out.append(path("M-18 35Q0 31.5 18 35Q16 42 0 42Q-16 42 -18 35Z", WHITE))
        out.append(path("M-10 52Q0 46 10 52Q4 57 0 57Q-4 57 -10 52Z", 0xE8756B))
    elif mood == "curious":
        out.append(ellipse(3, 42, 6.5, 7.5, 0x5A1F1C))
    elif mood == "sleepy":
        out.append(path("M-10 42Q0 45 11 41", None, 0x5A1F1C, 3.4))
    else:
        out.append(path("M-13 38Q0 47 15 37", None, 0x5A1F1C, 3.4))
    # the moustache over it
    out.append(path("M0 20C-10 16 -26 22 -31 35C-22 36 -8 33 0 28C8 33 22 36 31 35C26 22 10 16 0 20Z", HAIR_LIGHT))
    out.append(path("M2 21C10 17 24 22 29 33C21 30 10 26 2 25Z", mix(HAIR_LIGHT, GREY, 0.45)))

    # eyes
    ex, ey = 23, -9
    lid = blink
    squint = 0
    brow_l, brow_r = (0, 0), (0, 0)  # (lift, slant) for each brow
    if mood == "sleepy":
        lid = max(lid, 0.55)
        brow_l, brow_r = (3, -2), (3, 2)
    elif mood == "happy":
        squint = 0.75
        brow_l, brow_r = (-5, 1), (-5, -1)
    elif mood == "curious":
        brow_l, brow_r = (1, 2), (-9, -3)
    out.append(_eye(doc, -ex, ey, look, lid, squint))
    out.append(_eye(doc, ex, ey, look, lid, squint))
    # the nose, over the inner corners
    out.append(limb(1, -10, 2, 10, 0.06, 10, 16, NOSE))
    out.append(ellipse(5, 8, 3.4, 4.4, SKIN_LIGHT, rot=20))
    # glasses: round, dark, a glint on each lens
    for side in (-1, 1):
        gx = side * ex
        out.append(circle(gx, ey, 20.5, WHITE, opacity=0.10))
        out.append(circle(gx, ey, 20.5, None, INK, 4.4))
        out.append(path("M%.1f %.1fA16 16 0 0 1 %.1f %.1f" % (gx + 8, ey - 14, gx + 14, ey - 8), None, WHITE, 2.6, opacity=0.8))
        out.append(line(gx + side * 20, ey - 3, side * 55, -4, INK, 3.6))
    out.append(path("M-4 -12Q0 -17 4 -12", None, INK, 4))
    # brows, heavy and ready to move
    lift, slant = brow_l
    out.append(limb(-39, -40 + lift + slant, -11, -43 + lift - slant, 0.10, 6.5, 8.5, HAIR))
    lift, slant = brow_r
    out.append(limb(11, -43 + lift + slant, 39, -40 + lift - slant, 0.10, 8.5, 6.5, HAIR))

    # the hair in front: swept up and back from a parting on his right
    front = [(-55, -8), (-60, -36), (-50, -68), (-22, -90), (18, -97), (52, -82), (64, -48), (57, -8), (51, -30), (42, -52), (20, -63), (-8, -60), (-26, -51), (-40, -53), (-49, -32)]
    out.append(path(smooth(front, True), HAIR))
    out.append(path(smooth([(-26, -54), (-8, -76), (22, -88), (48, -80), (30, -78), (8, -69), (-8, -60)], True), HAIR_LIGHT))
    # grey at the temples
    out.append(path(smooth([(51, -46), (59, -30), (57, -9), (52, -14), (52, -30)], True), mix(HAIR, GREY, 0.6)))
    out.append(path(smooth([(-50, -46), (-58, -30), (-55, -9), (-51, -14), (-51, -30)], True), mix(HAIR, GREY, 0.3)))
    # a pencil behind his ear
    out.append(group(rect(-3.2, -34, 6.4, 40, 0xF2B632, r=1) + rect(-3.2, 2, 6.4, 6, 0xE98B7E, r=2) + rect(-3.2, -1, 6.4, 4, GREY) + path("M-3.2 -34L0 -45L3.2 -34Z", 0xF0D9B5) + path("M-1.1 -41L0 -45L1.1 -41Z", INK), "translate(59 -26) rotate(18)"))
    out.append(ellipse(57, 3, 8, 11, SKIN))
    out.append(ellipse(58, 4, 3.6, 6, SKIN_SHADE))
    return "".join(out)


def _iron():
    # a soldering iron held upright: drawn pointing up from the grip at the origin
    return (
        rect(-6.5, -16, 13, 44, APRON, r=6)
        + rect(-6.5, -16, 5, 44, APRON_LIGHT, r=3)
        + rect(-7.5, -22, 15, 9, LIME, r=3)
        + rect(-3, -50, 6, 30, 0xC9D0D8)
        + rect(-3, -50, 2.2, 30, WHITE)
        + path("M-3 -50L0 -66L3 -50Z", 0x9AA3AD)
        + path("M-1.6 30Q-10 52 2 70", None, INK, 3.4)
    )


def _smoke():
    return path("M0 0C-10 -12 9 -20 0 -32C-8 -42 6 -48 2 -58", None, WHITE, 3.2, opacity=0.5) + path("M8 -8C2 -16 14 -22 9 -32", None, WHITE, 2.4, opacity=0.32)


def _open_hand():
    # an open palm, drawn pointing up from the wrist at the origin
    out = [limb(-13, -18, -25, -30, 0.2, 10, 8.5, SKIN_SHADE)]
    for dx, tip, lean, w in ((-10, -47, -5, 9), (-3, -52, -1.5, 9.5), (4.5, -50, 2.5, 9.5), (11, -43, 6, 8.5)):
        out.append(limb(dx, -24, dx + lean, tip, 0, w + 1, w, SKIN))
    out.append(path(smooth([(-15, -30), (15, -30), (17, -12), (12, 2), (-11, 2), (-16, -12)], True), SKIN))
    out.append(path("M-9 -14Q0 -8 9 -15", None, SKIN_SHADE, 2))
    return "".join(out)


def _fist():
    # a hand closed round something upright
    return (
        ellipse(0, 0, 16, 15, SKIN)
        + ellipse(-4, 3, 11, 10, SKIN_SHADE)
        + ellipse(1, 0, 13.5, 12.5, SKIN)
        + line(-8, -6, 9, -6, SKIN_SHADE, 1.8)
        + line(-9, 0, 10, 0, SKIN_SHADE, 1.8)
        + line(-8, 6, 9, 6, SKIN_SHADE, 1.8)
        + ellipse(10, -9, 6, 8, SKIN_LIGHT, rot=30)
    )


def draw(doc, look=(0.2, 0.0), blink=0, mood="calm", wave=0, shadow=True):
    """The man's shapes, back to front.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        look: Where the eyes point, each of x and y from -1 to 1.
        blink (float): 0 with the eyes open, 1 closed.
        mood (str): "calm", "happy", "curious" or "sleepy".
        wave (float): How far his free hand is raised, 0 at his side to 40 in a wave.
        shadow (bool): Draw the shadow on the ground.
    """
    out = []
    if shadow:
        out.append(ellipse(0, 3, 120, 15, 0x000000, opacity=0.16))
        out.append(ellipse(2, 4, 82, 9, 0x000000, opacity=0.18))

    # where the free arm is: at his side, or up in a wave
    t = min(max(wave / 40.0, 0), 1)
    sx, sy = 58, -190
    elx, ely = lerp(70, 92, t), lerp(-140, -168, t)
    reach = math.radians(lerp(84, -68, t))
    hx, hy = elx + math.cos(reach) * 46, ely + math.sin(reach) * 46

    # legs and shoes
    for side in (-1, 1):
        out.append(limb(side * 24, -104, side * 27, -22, 0, 40, 32, TROUSERS if side > 0 else TROUSERS_SHADE))
        out.append(ellipse(side * 30 + 5, -9, 27, 11, SHOE))
        out.append(ellipse(side * 30 + 12, -12, 14, 5.5, SHOE_LIGHT))
        out.append(rect(side * 30 - 22, -4, 54, 5, INK, r=2.5))

    # the shirt
    torso = [(-60, -196), (-30, -208), (30, -208), (60, -196), (62, -140), (52, -96), (-52, -96), (-62, -140)]
    out.append(path(smooth(torso, True), SHIRT))
    out.append(path(smooth([(-60, -196), (-62, -140), (-52, -96), (-36, -96), (-46, -140), (-44, -194)], True), SHIRT_SHADE))

    # the far arm: sleeve rolled to the elbow, forearm up, holding the iron
    out.append(limb(-58, -190, -84, -146, 0.12, 30, 26, SHIRT_SHADE))
    out.append(limb(-84, -146, -104, -178, 0.10, 22, 18, SKIN_SHADE))
    out.append(ellipse(-85, -147, 15, 12, SHIRT, rot=-40))
    out.append(at(-104, -238, _smoke()))
    out.append(at(-104, -184, _iron(), rot=-4))
    out.append(at(-104, -184, _fist()))

    # the apron over it all
    out.append(line(-22, -204, -28, -178, APRON_SHADE, 7))
    out.append(line(22, -204, 28, -178, APRON, 7))
    out.append(path("M-30 -182L30 -182L34 -146Q52 -142 56 -128L60 -64Q0 -56 -60 -64L-56 -128Q-52 -142 -34 -146Z", APRON))
    out.append(path("M-30 -182L-16 -182L-20 -146Q-40 -142 -42 -128L-44 -62Q-54 -63 -60 -64L-56 -128Q-52 -142 -34 -146Z", APRON_SHADE))
    out.append(path("M-26 -176L26 -176", None, APRON_LIGHT, 2.4))
    # a pocket, with what a bench hand keeps in it
    out.append(line(8, -128, 4, -152, 0xC9D0D8, 4))
    out.append(line(20, -126, 22, -156, 0xE4513D, 5))
    out.append(rect(17.5, -160, 9, 8, INK, r=2))
    out.append(rect(-16, -128, 48, 36, APRON_LIGHT, r=5))
    out.append(rect(-16, -128, 48, 7, APRON_SHADE, r=3, opacity=0.45))
    out.append(path("M-11 -98Q8 -94 27 -98", None, LIME, 2.2))

    # the near arm
    out.append(limb(sx, sy, elx, ely, -0.10, 31, 27, SHIRT))
    out.append(limb(elx, ely, hx, hy, 0, 23, 19, SKIN))
    out.append(ellipse(elx, ely, 16, 13, SHIRT, rot=lerp(20, 50, t)))
    out.append(ellipse(elx + 2, ely - 1, 12, 9, mix(SHIRT, WHITE, 0.5), rot=lerp(20, 50, t)))
    if t > 0.3:
        out.append(at(hx, hy, _open_hand(), rot=math.degrees(reach) + 90 + 8))
    else:
        out.append(ellipse(hx + 1, hy + 8, 14, 17, SKIN, rot=math.degrees(reach) - 90))
        out.append(limb(hx - 9, hy + 2, hx - 12, hy + 16, 0.2, 9, 7.5, SKIN_SHADE))
        out.append(path("M%.1f %.1fQ%.1f %.1f %.1f %.1f" % (hx - 4, hy + 18, hx + 3, hy + 21, hx + 9, hy + 17), None, SKIN_SHADE, 2))

    # neck, collar, head
    out.append(rect(-17, -222, 34, 24, SKIN_SHADE, r=6))
    out.append(path("M-30 -208Q0 -190 30 -208L22 -214Q0 -200 -22 -214Z", mix(SHIRT, WHITE, 0.5)))
    tilt = {"curious": 7, "sleepy": -5, "happy": -3}.get(mood, 0)
    out.append(at(0, HEAD_Y, _head(doc, look, blink, mood), rot=tilt))
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
    doc.add(rect(-1000, -1000, 2000, 2000, NAVY))
    doc.add(circle(0, -250, 118, 0x1C6E8C))
    doc.add(draw(doc, look=(0.3, 0), mood="calm", shadow=False))
    # a wide ring of the ground hides what falls outside the circle
    doc.add(circle(0, -250, 178, None, NAVY, 120))
    doc.add(circle(0, -250, 118, None, LIME, 5))
    return doc.svg((-125, -375, 250, 250))


_FULL = (-230, -356, 460, 380)

STILLS = [
    ("man_full", _study(_FULL), 920),
    ("man_face", _study((-105, -350, 210, 175), look=(0.5, -0.1)), 900),
    ("man_happy", _study(_FULL, mood="happy", wave=40, look=(0.1, 0.1)), 920),
    ("man_curious", _study(_FULL, mood="curious", look=(-0.9, -0.3), wave=0), 920),
    ("man_sleepy", _study(_FULL, mood="sleepy", look=(0.0, 0.7)), 920),
    ("man_icon", _icon, 400),
]
