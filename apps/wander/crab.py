# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The hermit crab, drawn from a pose.

The crab stands on the origin: x to the right, y down, the ground at y = 0,
about 330 units wide and 300 tall. `draw` returns its shapes for a `vec.Doc`.
"""

import math

from .vec import at, circle, ellipse, group, limb, mix, path, smooth

CORAL_LIGHT = 0xFF9A76
CORAL = 0xF46A45
CORAL_DARK = 0xC2432D
CORAL_DEEP = 0x8E2B22
NAVY = 0x0B2A4A
LIME = 0xC4DC4C
WHITE = 0xFFFFFF

# The shells it can wear: (light, mid, shade, band, band highlight).
SHELLS = {
    "sand": (0xFFF6E0, 0xF6DDB0, 0xC79A6A, 0x1C6E8C, LIME),
    "night": (0x4A6FA5, 0x1D4470, 0x0B2A4A, LIME, 0xF4FFB0),
    "rose": (0xFFE9E4, 0xF7B9B0, 0xC0707A, 0x7A3B69, 0xFFD27A),
    "moss": (0xF1F5D0, 0xBFD08A, 0x6E8B4E, 0x2F5D50, 0xFFE9A8),
}


def _crescent(cx, cy, rx, ry, tilt, toward, thick, fill, inset=1.0, half=95, opacity=None):
    """A crescent hugging the edge of an ellipse, for a shade, a glint or a band.

    *toward* is the side it sits on, in degrees in the ellipse's own frame
    (0 along its x radius, 90 down), *thick* its width at the middle as a
    fraction of the radius, and *inset* shrinks it toward the centre.
    """
    c, s = math.cos(math.radians(half)), math.sin(math.radians(half))
    k = 1 - thick - c
    big = (s * s + k * k) / (2 * k)
    d = "M%.4f %.4fA1 1 0 %d 1 %.4f %.4fA%.4f %.4f 0 0 0 %.4f %.4fZ" % (c, -s, 1 if half > 90 else 0, c, s, big, big, c, -s)
    t = "translate(%.2f %.2f) rotate(%.2f) scale(%.2f %.2f) rotate(%.2f)" % (cx, cy, tilt, rx * inset, ry * inset, toward)
    return group(path(d, fill, opacity=opacity), t)


def _shell(doc, colors, whorls=4):
    light, mid, shade, band, glint = colors
    out = []
    # The axis runs from the body whorl up and back to the apex.
    ax, ay = -0.50, -0.866
    tilt = math.degrees(math.atan2(ay, ax)) + 90
    cx, cy, r = -52.0, -118.0, 108.0
    rings = []
    for i in range(whorls):
        rings.append((cx, cy, r))
        nr = r * 0.66
        cx += ax * (r * 0.52 + nr * 0.46)
        cy += ay * (r * 0.52 + nr * 0.46)
        r = nr
    dark = mix(shade, 0x000000, 0.25)
    # apex first, so each larger whorl overlaps the one above it
    for i in range(whorls - 1, -1, -1):
        cx, cy, r = rings[i]
        rx, ry = r, r * 0.84
        # the dark seam where this whorl meets the smaller one behind it
        out.append(ellipse(cx + ax * r * 0.07, cy + ay * r * 0.07, rx * 1.03, ry * 1.03, dark, rot=tilt))
        out.append(ellipse(cx, cy, rx, ry, mid, rot=tilt))
        # shade away from the light, which comes from the upper right
        out.append(_crescent(cx, cy, rx, ry, tilt, 150 - tilt, 0.34, shade, half=100))
        # the band and its fine line, toward the apex
        out.append(_crescent(cx, cy, rx, ry, tilt, -90, 0.17, band, inset=0.80, half=70))
        out.append(_crescent(cx, cy, rx, ry, tilt, -90, 0.045, glint, inset=0.56, half=60))
        # where the light lands
        out.append(ellipse(cx + r * 0.42, cy - r * 0.30, r * 0.30, r * 0.15, light, rot=tilt - 55))
        out.append(circle(cx + r * 0.62, cy + r * 0.02, r * 0.06, light))
    return "".join(out)


def _eye(doc, x, y, r, look, lid, happy):
    out = []
    white = doc.radial([(0, WHITE), (0.8, 0xF4F7FB), (1, 0xD3DCE8)])
    out.append(circle(x, y, r + 2.5, CORAL_DARK))
    out.append(circle(x, y, r, white))
    if happy:
        # a closed, smiling eye: one upward arc
        out.append(circle(x, y, r, CORAL))
        out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (x - r * 0.62, y + r * 0.12, x, y - r * 0.62, x + r * 0.62, y + r * 0.12), None, CORAL_DEEP, r * 0.2))
        return "".join(out)
    px, py = x + look[0] * r * 0.34, y + look[1] * r * 0.30
    pr = r * 0.60
    iris = doc.radial([(0, 0x1F5E8F), (0.75, NAVY), (1, 0x061A30)], cx=0.5, cy=0.62)
    out.append(circle(px, py, pr, iris))
    out.append(circle(px - pr * 0.36, py - pr * 0.40, pr * 0.30, WHITE))
    out.append(circle(px + pr * 0.38, py + pr * 0.36, pr * 0.13, WHITE, opacity=0.8))
    if lid > 0:
        # the lid comes down as a coral cap over the top of the eye
        drop = -r + 2 * r * lid
        d = "M%.2f %.2fA%.2f %.2f 0 0 1 %.2f %.2fQ%.2f %.2f %.2f %.2fZ" % (
            x - r - 2.5,
            y + min(drop, 0),
            r + 2.5,
            r + 2.5,
            x + r + 2.5,
            y + min(drop, 0),
            x,
            y + drop + r * 0.5,
            x - r - 2.5,
            y + min(drop, 0),
        )
        out.append(path(d, CORAL))
        if lid >= 0.95:
            # closed: the lashes' line, curving down
            out.append(path("M%.2f %.2fQ%.2f %.2f %.2f %.2f" % (x - r * 0.7, y + r * 0.1, x, y + r * 0.62, x + r * 0.7, y + r * 0.1), None, CORAL_DEEP, r * 0.16))
    return "".join(out)


def _claw(doc, size, open_, fill):
    # drawn pointing right from its wrist at the origin
    s = size
    out = []
    paint = CORAL if fill is None else fill
    # the thumb, behind
    out.append(
        group(
            path("M0 0C%.1f %.1f %.1f %.1f %.1f %.1fC%.1f %.1f %.1f %.1f 0 0Z" % (s * 0.2, s * 0.42, s * 0.95, s * 0.46, s * 1.08, s * 0.12, s * 0.8, s * 0.2, s * 0.3, s * 0.08), CORAL_DARK),
            "translate(%.1f %.1f) rotate(%.1f)" % (s * 0.34, s * 0.06, open_),
        )
    )
    # the palm and the upper finger, one rounded shape with a pointed tip
    out.append(
        path(
            "M%.1f %.1fC%.1f %.1f %.1f %.1f %.1f %.1fC%.1f %.1f %.1f %.1f %.1f %.1fC%.1f %.1f %.1f %.1f %.1f %.1fC%.1f %.1f %.1f %.1f %.1f %.1fZ"
            % (
                -s * 0.10, 0,
                -s * 0.12, -s * 0.52, s * 0.42, -s * 0.72, s * 0.86, -s * 0.50,
                s * 1.10, -s * 0.38, s * 1.26, -s * 0.16, s * 1.30, s * 0.04,
                s * 1.04, -s * 0.10, s * 0.70, -s * 0.04, s * 0.50, s * 0.16,
                s * 0.34, s * 0.34, -s * 0.06, s * 0.36, -s * 0.10, 0,
            ),
            paint,
        )
    )
    if fill is None:
        out.append(ellipse(s * 0.36, -s * 0.36, s * 0.26, s * 0.10, CORAL_LIGHT, rot=-18))
    return "".join(out)


def eyes(look=(0.3, 0.1), mood="calm"):
    """The centres of the two eyes, ``(x0, y0, x1, y1)``, for a pose."""
    lean = look[0] * 5
    ey1 = -184 + look[1] * 3
    if mood == "curious":
        ey1 -= 12
    return 46 + lean, -186 + look[1] * 3, 104 + lean, ey1


def claw(wave=0):
    """The big claw's wrist and its turn in degrees, ``(x, y, turn)``.

    Something it holds goes at the wrist, turned the same way, with the grip
    about 40 units along.
    """
    reach = math.radians(-18 - wave)
    return 104 + math.cos(reach) * 46, -70 + math.sin(reach) * 46, -12 - wave * 1.1


def _goggles(ex0, ey0, ex1, ey1):
    out = [path("M%.1f %.1fL%.1f %.1f" % (ex0 + 30, ey0, ex1 - 28, ey1), None, 0x2B2B33, 9)]
    for x, y, r in ((ex0, ey0, 31), (ex1, ey1, 29)):
        out.append(circle(x, y, r, None, 0x2B2B33, 7))
        out.append(circle(x, y, r, None, 0xF2B632, 3))
        out.append(circle(x, y, r - 3, 0x9FE3FF, opacity=0.22))
        out.append(path("M%.1f %.1fA%.1f %.1f 0 0 1 %.1f %.1f" % (x - r * 0.55, y - r * 0.35, r * 0.7, r * 0.7, x - r * 0.1, y - r * 0.66), None, WHITE, 3, opacity=0.8))
    return "".join(out)


def draw(doc, look=(0.3, 0.1), blink=0, mood="calm", wave=0, shell="sand", shadow=True, wear=None):
    """The crab's shapes, back to front.

    Args:
        doc: The `vec.Doc` that holds the gradients.
        look: Where the eyes point, each of x and y from -1 to 1.
        blink (float): 0 with the eyes open, 1 closed.
        mood (str): "calm", "happy", "curious" or "sleepy".
        wave (float): The big claw's lift in degrees.
        shell (str): A name from `SHELLS`.
        shadow (bool): Draw the soft shadow on the ground.
        wear (str): "goggles", or None.
    """
    out = []
    if shadow:
        out.append(ellipse(-14, 4, 178, 22, 0x000000, opacity=0.16))
        out.append(ellipse(-4, 5, 128, 14, 0x000000, opacity=0.18))

    leg = CORAL
    # the legs on the far side, darker
    out.append(limb(4, -52, -34, -3, -0.22, 20, 8, CORAL_DEEP))
    out.append(limb(34, -46, 20, -3, -0.18, 20, 8, CORAL_DEEP))
    # the small claw, tucked on the far side
    out.append(limb(96, -84, 128, -58, 0.2, 22, 16, CORAL_DARK))
    out.append(at(126, -58, _claw(doc, 26, 16, CORAL_DARK), rot=28))

    out.append(_shell(doc, SHELLS[shell]))

    # the mouth of the shell, and the dark inside it
    inside = 0x4A2A22
    lip = SHELLS[shell][0]
    out.append(ellipse(30, -88, 70, 80, mix(SHELLS[shell][2], 0x000000, 0.15), rot=18))
    out.append(ellipse(33, -89, 64, 74, lip, rot=18))
    out.append(ellipse(38, -88, 54, 64, inside, rot=18))

    # near legs, their tops under the body
    out.append(limb(60, -62, 58, -4, 0.30, 26, 10, leg))
    out.append(limb(92, -64, 120, -4, 0.34, 26, 10, leg))
    out.append(limb(58, -4, 70, -1, 0, 10, 7, leg))
    out.append(limb(120, -4, 133, -1, 0, 10, 7, leg))

    # eye stalks, their feet under the body
    ex0, ey0, ex1, ey1 = eyes(look, mood)
    out.append(limb(52, -126, ex0, ey0 + 14, -0.10, 18, 13, CORAL))
    out.append(limb(92, -128, ex1, ey1 + 14, 0.10, 18, 13, CORAL))

    # the body
    out.append(ellipse(70, -98, 56, 50, CORAL, rot=-8))
    out.append(_crescent(70, -98, 56, 50, -8, 128, 0.30, CORAL_DARK, half=92))
    out.append(ellipse(110, -112, 7, 13, CORAL_LIGHT, rot=-28))
    # antennae
    out.append(path("M72 -142C86 -168 112 -176 138 -166", None, CORAL_DARK, 3.2))
    out.append(path("M78 -140C100 -154 128 -152 150 -136", None, CORAL_DARK, 3.2))
    out.append(circle(138, -166, 3.4, CORAL_DARK))
    out.append(circle(150, -136, 3.4, CORAL_DARK))
    happy = mood == "happy"
    if mood == "sleepy":
        blink = max(blink, 0.55)
    out.append(_eye(doc, ex0, ey0, 25, look, blink, happy))
    out.append(_eye(doc, ex1, ey1, 23, look, blink, happy))
    if wear == "goggles":
        out.append(_goggles(ex0, ey0, ex1, ey1))
    # cheeks and smile
    blush = 0xFF7F6E
    out.append(ellipse(44, -92, 15, 9, blush))
    out.append(ellipse(108, -90, 14, 9, blush))
    if happy:
        out.append(path("M62 -96Q77 -72 94 -95Z", CORAL_DEEP))
        out.append(path("M70 -84Q78 -78 86 -84Q78 -88 70 -84Z", 0xFF8F8F))
    elif mood == "curious":
        out.append(ellipse(79, -86, 6, 7, CORAL_DEEP))
    else:
        out.append(path("M64 -92Q77 -79 92 -91", None, CORAL_DEEP, 3.6))

    # the big claw, on its arm
    hx, hy, turn = claw(wave)
    out.append(limb(104, -70, hx, hy, -0.25, 26, 20, leg))
    out.append(at(hx, hy, _claw(doc, 44, 20 + wave * 0.2, None), rot=turn))
    return "".join(out)
