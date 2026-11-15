# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The coast: a beach, a headland with a lighthouse and one tree, in any season.

`draw` adds the scene to a `vec.Doc`, 800 by 480 units. The season picks the
colours, what the tree carries and what lies on the sand; `night` turns the
same season to night.
"""

import math

from . import chameleon_props
from . import chameleon_shift  # noqa: F401  (its colour schemes)
from . import crab
from .vec import Doc, at, circle, ellipse, group, limb, line, mix, path, pts, rect, smooth, wash

W, H = 800, 480
HORIZON = 252

# Per season: the sky from its top to the sun, the sea far to near, the sand,
# the headland, the tree's leaves, the grass.
SEASONS = {
    "spring": {
        "sky": (0x6FBDE8, 0xBFE4F2, 0xFFF1D8),
        "sun": 0xFFF7D6,
        "sea": (0x2F8FB3, 0x48B5C4, 0x8FDCD2),
        "sand": (0xF6E3B4, 0xEBCF93, 0xD9B777),
        "land": (0x8FB7A8, 0x5E9A7E),
        "leaves": (0xFFD3E0, 0xFFA9C4, 0xE87DA3),
        "grass": (0x8CC152, 0x5E9E3E),
        "cloud": (0xFFFFFF, 0xE3F1F7),
        "sun_at": (560, 120),
    },
    "summer": {
        "sky": (0x1E8FD5, 0x6CC4EE, 0xD9F4FB),
        "sun": 0xFFFBE0,
        "sea": (0x0E6FA8, 0x1FA3C0, 0x6FDCCB),
        "sand": (0xFBE7B2, 0xF2D08A, 0xDDB066),
        "land": (0x6FA9A0, 0x3F8A66),
        "leaves": (0x9BD45A, 0x5FB045, 0x2F8544),
        "grass": (0x9CCB4A, 0x4F9A3A),
        "cloud": (0xFFFFFF, 0xDDF0F8),
        "sun_at": (600, 84),
    },
    "autumn": {
        "sky": (0x4B3F8C, 0xD7607A, 0xFFC56B),
        "sun": 0xFFF0B8,
        "sea": (0x3B3A7A, 0x8B4E86, 0xF29A6B),
        "sand": (0xF2C58E, 0xDFA56C, 0xB97F52),
        "land": (0x6B4B7E, 0x4A335F),
        "leaves": (0xFFC83D, 0xF58B2A, 0xC9482B),
        "grass": (0xD9A441, 0x9A6B2F),
        "cloud": (0xFFD9B0, 0xF79C7C),
        "sun_at": (470, 214),
    },
    "winter": {
        "sky": (0x7C9CC0, 0xBDD3E6, 0xF4F7FA),
        "sun": 0xFFFFFF,
        "sea": (0x4A6E8F, 0x6E97B2, 0xA9CAD8),
        "sand": (0xFFFFFF, 0xE6F0F8, 0xC3D7E8),
        "land": (0xC9D9E6, 0x9DB6CB),
        "leaves": None,
        "grass": (0xC9B98A, 0x9C8B62),
        "cloud": (0xFFFFFF, 0xDCE7F1),
        "sun_at": (520, 150),
    },
}

_NIGHT_SKY = (0x06122A, 0x12305C, 0x2A5A8C)
_BARK = 0x5B3B2E
_BARK_LIGHT = 0x7A5440


class _Random:
    # the same numbers on every runtime, so the tree is the same tree
    def __init__(self, seed):
        self.state = seed

    def next(self):
        self.state = (self.state * 1103515245 + 12345) & 0x7FFFFFFF
        return (self.state >> 8) / 8388608.0

    def between(self, a, b):
        return a + (b - a) * self.next()


def _dim(color, night):
    """A daytime colour as moonlight sees it."""
    if not night:
        return color
    return mix(mix(color, 0x1B3A6B, 0.55), 0x06122A, 0.25)


def _wave_edge(x0, x1, y, amp, length, phase, bottom):
    """Path data: a strip from a wavy top edge down to *bottom*."""
    points = []
    x = x0
    while x <= x1 + length / 4:
        points.append((x, y + amp * math.sin((x + phase) * 2 * math.pi / length)))
        x += length / 4
    return smooth(points) + "L%d %dL%d %dZ" % (x1 + length, bottom, x0, bottom)


def _sky(season, night):
    out = []
    top, middle, glow = _NIGHT_SKY if night else season["sky"]
    sx, sy = season["sun_at"]
    if night:
        sx, sy = 590, 96
    out.append(rect(0, 0, W, HORIZON + 4, top))
    # rings of light around the sun: the sky's steps are drawn, not left to the display
    radii = (560, 470, 390, 320, 255, 195, 140, 92)
    for i, r in enumerate(radii):
        t = (i + 1) / len(radii)
        color = mix(top, middle, t * 2) if t < 0.5 else mix(middle, glow, t * 2 - 1)
        out.append(circle(sx, sy, r, color))
    if night:
        stars = _Random(7)
        for _ in range(70):
            x, y = stars.between(0, W), stars.between(0, HORIZON - 30)
            if (x - sx) ** 2 + (y - sy) ** 2 < 70 * 70:
                continue
            out.append(circle(x, y, stars.between(0.6, 1.9), 0xFFFFFF, opacity=stars.between(0.45, 1)))
        # the moon, with the dark of it hiding one side
        out.append(circle(sx, sy, 50, 0xFFFFFF, opacity=0.10))
        out.append(circle(sx, sy, 34, 0xFFF8E1))
        out.append(circle(sx - 9, sy - 8, 6, 0xE9DFC0))
        out.append(circle(sx + 10, sy + 6, 9, 0xE9DFC0))
        out.append(circle(sx + 2, sy - 16, 3.5, 0xE9DFC0))
    else:
        out.append(circle(sx, sy, 62, 0xFFFFFF, opacity=0.35))
        out.append(circle(sx, sy, 40, season["sun"]))
    return "".join(out)


def _cloud(x, y, s, colors):
    light, shade = colors
    out = [
        circle(x - 34 * s, y + 3 * s, 18 * s, shade),
        circle(x + 36 * s, y + 5 * s, 15 * s, shade),
        circle(x + 6 * s, y - 6 * s, 26 * s, shade),
        rect(x - 52 * s, y + 3 * s, 103 * s, 18 * s, shade, r=9 * s),
        circle(x - 30 * s, y - 2 * s, 16 * s, light),
        circle(x + 4 * s, y - 13 * s, 23 * s, light),
        circle(x + 33 * s, y - 1 * s, 13 * s, light),
        rect(x - 46 * s, y - 2 * s, 92 * s, 14 * s, light, r=7 * s),
    ]
    return "".join(out)


def _headland(season, night, beam):
    far, near = season["land"]
    far, near = _dim(far, night), _dim(near, night)
    out = []
    out.append(path(smooth([(-20, HORIZON + 6), (40, 214), (120, 196), (190, 206), (262, 232), (330, HORIZON + 6)]) + "Z", far))
    out.append(path(smooth([(-20, HORIZON + 8), (20, 226), (84, 212), (150, 224), (214, 244), (250, HORIZON + 8)]) + "Z", near))
    # the lighthouse
    x, y = 96, 212
    if beam:
        out.append(path("M%d %dL%d %dL%d %dZ" % (x, y - 78, 820, y - 40, 820, y + 70), 0xFFF3B0, opacity=0.16))
        out.append(path("M%d %dL%d %dL%d %dZ" % (x, y - 78, 820, y - 10, 820, y + 42), 0xFFF3B0, opacity=0.16))
    white, red = _dim(0xFFFDF5, night), _dim(0xE4513D, night)
    out.append(path(pts([(x - 13, y), (x - 8, y - 66), (x + 8, y - 66), (x + 13, y)], True), white))
    out.append(path(pts([(x - 11.6, y - 18), (x - 10.2, y - 36), (x + 10.2, y - 36), (x + 11.6, y - 18)], True), red))
    out.append(path(pts([(x + 3, y), (x + 2, y - 66), (x + 8, y - 66), (x + 13, y)], True), 0x000000, opacity=0.12))
    out.append(rect(x - 11, y - 70, 22, 5, _dim(0x3A3F4B, night), r=1))
    out.append(rect(x - 7, y - 86, 14, 16, 0xFFF3B0 if beam else _dim(0xBFE4F2, night)))
    out.append(path(pts([(x - 10, y - 86), (x, y - 98), (x + 10, y - 86)], True), red))
    return "".join(out)


def _sea(season, night):
    deep, mid_, shallow = (_dim(c, night) for c in season["sea"])
    out = [rect(0, HORIZON, W, H - HORIZON, deep)]
    bands = ((274, mix(deep, mid_, 0.5), 3, 150, 0), (300, mid_, 4, 190, 40), (330, mix(mid_, shallow, 0.5), 5, 230, 120), (362, shallow, 6, 270, 30))
    for y, color, amp, length, phase in bands:
        out.append(path(_wave_edge(0, W, y, amp, length, phase, H), color))
    # the light on the water, in broken bars that widen toward the shore
    sx = 590 if night else season["sun_at"][0]
    glint = 0xFFF8E1 if night else season["sun"]
    bars = _Random(11)
    y = HORIZON + 5
    half = 26.0
    while y < 372:
        for _ in range(2):
            w = bars.between(half * 0.3, half)
            x = sx + bars.between(-half, half) - w / 2
            out.append(rect(x, y, w, 2.6, glint, r=1.3, opacity=bars.between(0.35, 0.8)))
        y += 9
        half += 5
    return "".join(out)


def _shore(season, night):
    light, sand, wet = (_dim(c, night) for c in season["sand"])
    out = []
    # foam, wet sand, dry sand: three curves a little apart
    edge = [(-20, 392), (120, 372), (270, 380), (430, 366), (600, 372), (820, 352)]
    out.append(path(smooth([(x, y - 12) for x, y in edge]) + "L820 480L-20 480Z", _dim(0xFFFFFF, night), opacity=0.9))
    out.append(path(smooth([(x, y - 4) for x, y in edge]) + "L820 480L-20 480Z", wet))
    out.append(path(smooth([(x, y + 14 + 6 * math.sin(x / 90)) for x, y in edge]) + "L820 480L-20 480Z", sand))
    out.append(path(smooth([(-20, 452), (160, 436), (360, 452), (560, 440), (820, 458)]) + "L820 480L-20 480Z", light))
    return "".join(out)


def _dune(season, night):
    light, sand, wet = (_dim(c, night) for c in season["sand"])
    dark, green = (_dim(c, night) for c in season["grass"])
    out = []
    out.append(path(smooth([(400, 500), (480, 420), (560, 338), (650, 288), (740, 268), (830, 262)]) + "L830 500Z", wet))
    out.append(path(smooth([(450, 500), (520, 428), (592, 348), (676, 302), (760, 282), (830, 278)]) + "L830 500Z", sand))
    out.append(path(smooth([(540, 500), (590, 440), (650, 380), (724, 340), (830, 320)]) + "L830 500Z", light))
    # dune grass, in tufts
    tufts = _Random(3)
    for cx, cy, n in ((548, 356, 7), (598, 322, 6), (742, 290, 8), (786, 300, 6), (640, 384, 7), (720, 356, 5), (772, 410, 8)):
        for _ in range(n):
            lean = tufts.between(-16, 16)
            tall = tufts.between(16, 38)
            x = cx + tufts.between(-12, 12)
            out.append(limb(x, cy, x + lean, cy - tall, lean / 60, 3.2, 0.8, green if tufts.next() > 0.45 else dark))
    return "".join(out)


def _tree(season, night, x, y):
    leaves = season["leaves"]
    out = []
    tips = []
    rng = _Random(29)
    bark, bark_light = _dim(_BARK, night), _dim(_BARK_LIGHT, night)

    def branch(x0, y0, angle, length, width, depth):
        x1 = x0 + math.cos(angle) * length
        y1 = y0 + math.sin(angle) * length
        out.append(limb(x0, y0, x1, y1, rng.between(-0.12, 0.12), width, width * 0.62, bark))
        if depth == 0 or length < 9:
            tips.append((x1, y1))
            return
        if depth < 3:
            tips.append((x1, y1))
        # the sea wind has pushed every fork a little inland
        spread = rng.between(0.36, 0.62)
        branch(x1, y1, angle - spread - 0.05, length * rng.between(0.68, 0.8), width * 0.62, depth - 1)
        branch(x1, y1, angle + spread * 0.8 - 0.05, length * rng.between(0.62, 0.76), width * 0.6, depth - 1)

    # the trunk leans, then forks
    out.append(path("M%d %dQ%d %d %d %dL%d %dQ%d %d %d %dZ" % (x - 22, y + 8, x - 8, y + 2, x - 6, y - 14, x + 8, y - 14, x + 8, y + 2, x + 20, y + 8), bark))
    out.append(limb(x - 1, y - 4, x + 8, y - 44, 0.10, 17, 13, bark))
    out.append(limb(x - 9, y + 2, x - 2, y - 30, 0.1, 5, 3, bark_light))
    branch(x + 8, y - 44, -math.pi / 2 - 0.42, 44, 12, 4)
    branch(x + 8, y - 44, -math.pi / 2 + 0.50, 40, 11, 4)
    if leaves:
        light, mid_, dark = (_dim(c, night) for c in leaves)
        blobs = []
        for tx, ty in tips:
            blobs.append((tx + rng.between(-6, 6), ty + rng.between(-6, 6), rng.between(13, 22)))
        for bx, by, r in blobs:
            out.append(circle(bx - 3, by + 5, r, dark))
        for bx, by, r in blobs:
            out.append(circle(bx, by, r * 0.86, mid_))
        for bx, by, r in blobs:
            if rng.next() > 0.35:
                out.append(circle(bx + r * 0.3, by - r * 0.34, r * 0.42, light))
    else:
        # snow lying along the branch tips
        for tx, ty in tips:
            out.append(ellipse(tx, ty - 3, 7, 3, _dim(0xFFFFFF, night)))
    return "".join(out)


def _gull(x, y, s, color):
    return path("M%.1f %.1fQ%.1f %.1f %.1f %.1fQ%.1f %.1f %.1f %.1f" % (x - 9 * s, y - 2 * s, x - 4 * s, y - 7 * s, x, y, x + 5 * s, y - 8 * s, x + 11 * s, y - 3 * s), None, color, 1.8 * s)


def _sailboat(x, y, night):
    hull, sail = _dim(0xC8452F, night), _dim(0xFFFDF5, night)
    return (
        path(pts([(x - 14, y - 5), (x + 16, y - 5), (x + 11, y + 2), (x - 9, y + 2)], True), hull)
        + path(pts([(x + 1, y - 34), (x + 1, y - 7), (x + 15, y - 7)], True), sail)
        + path(pts([(x - 2, y - 28), (x - 2, y - 7), (x - 12, y - 7)], True), mix(sail, 0x8FA9C4, 0.35))
    )


def _starfish(x, y, r, color, turn):
    points = []
    for i in range(10):
        a = math.radians(turn + i * 36)
        rr = r if i % 2 == 0 else r * 0.42
        points.append((x + math.cos(a) * rr, y + math.sin(a) * rr * 0.62))
    return path(smooth(points, True), color) + ellipse(x, y, r * 0.2, r * 0.12, mix(color, 0xFFFFFF, 0.4))


def _sandcastle(x, y, sand, shade):
    out = [
        rect(x - 30, y - 22, 60, 24, sand, r=2),
        rect(x - 30, y - 22, 14, 24, shade, opacity=0.5),
        rect(x - 13, y - 44, 26, 26, sand, r=2),
        rect(x - 13, y - 44, 7, 26, shade, opacity=0.5),
    ]
    for dx in (-30, -15, 0, 15):
        out.append(rect(x + dx + 2, y - 28, 9, 8, sand, r=1))
    for dx in (-13, -1, 9):
        out.append(rect(x + dx, y - 50, 7, 8, sand, r=1))
    out.append(path("M%d %dA6 9 0 0 1 %d %dZ" % (x - 6, y, x + 6, y), shade))
    out.append(line(x, y - 50, x, y - 72, 0x7A5440, 1.6))
    out.append(path(pts([(x, y - 72), (x + 15, y - 67), (x, y - 62)], True), 0xE4513D))
    return "".join(out)


def _snowman(x, y):
    return (
        ellipse(x, y + 1, 26, 5, 0x6E97B2, opacity=0.35)
        + circle(x, y - 14, 17, 0xFFFFFF)
        + circle(x, y - 38, 12, 0xFFFFFF)
        + circle(x - 5, y - 13, 15, 0xDCE7F1, opacity=0.6)
        + circle(x + 2, y - 15, 15, 0xFFFFFF)
        + circle(x - 4, y - 41, 1.6, 0x2B2B33)
        + circle(x + 4, y - 41, 1.6, 0x2B2B33)
        + path(pts([(x, y - 38), (x + 12, y - 35), (x, y - 34)], True), 0xF58B2A)
        + limb(x - 11, y - 28, x + 12, y - 27, 0.2, 5, 5, 0xE4513D)
        + limb(x + 8, y - 27, x + 13, y - 14, 0, 5, 4, 0xE4513D)
        + line(x - 16, y - 20, x - 32, y - 32, 0x5B3B2E, 1.8)
        + line(x + 16, y - 20, x + 31, y - 34, 0x5B3B2E, 1.8)
    )


def _scarf(color, stripe):
    # around the crab, under its face, with one end hanging: in the crab's own units
    out = [
        limb(42, -56, 30, -20, -0.12, 15, 14, mix(color, 0x000000, 0.18)),
        path("M22 -74Q70 -46 122 -72", None, color, 16),
        path("M24 -77Q70 -50 120 -75", None, stripe, 2.6),
        path("M26 -69Q70 -42 118 -67", None, stripe, 2.6),
        line(24, -24, 36, -21, stripe, 3),
    ]
    return "".join(out)


def _hat(color, stripe):
    # a knitted hat on the tip of the shell
    out = [
        group(
            path("M-30 6A30 34 0 0 1 30 6Z", color)
            + rect(-33, 0, 66, 13, stripe, r=6)
            + path("M-22 -14Q0 -24 22 -14", None, stripe, 4)
            + circle(0, -29, 10, 0xFFFFFF),
            "translate(-150 -292) rotate(-30)",
        )
    ]
    return "".join(out)


def _drift(season_name, night, rng):
    """What the air carries: petals, leaves, snow, or fireflies at night."""
    out = []
    if season_name == "winter":
        for _ in range(90):
            out.append(circle(rng.between(0, W), rng.between(0, H), rng.between(1.2, 3.4), 0xFFFFFF, opacity=rng.between(0.6, 1)))
    elif season_name in ("spring", "autumn"):
        colors = (0xFFA9C4, 0xFFD3E0, 0xFFFFFF) if season_name == "spring" else (0xFFC83D, 0xF58B2A, 0xC9482B)
        for _ in range(26):
            x, y = rng.between(380, 800), rng.between(140, 470)
            color = _dim(colors[int(rng.between(0, 2.99))], night)
            out.append(ellipse(x, y, rng.between(3, 5.5), rng.between(1.6, 2.6), color, rot=rng.between(0, 180)))
    if night and season_name != "winter":
        for _ in range(14):
            x, y = rng.between(430, 790), rng.between(250, 450)
            out.append(circle(x, y, 7, 0xE8FF8A, opacity=0.18))
            out.append(circle(x, y, 3.4, 0xE8FF8A, opacity=0.35))
            out.append(circle(x, y, 1.5, 0xFDFFE0))
    return "".join(out)


# The chameleon in each season: its colour scheme, what it holds, its pose.
_HUE = {
    "spring": ("blossom", "flower", {"mood": "happy", "look": (0.6, -0.3), "look_far": (-0.5, 0.2)}),
    "summer": ("leaf", "plane", {"mood": "calm", "look": (0.7, -0.4), "look_far": (0.2, 0.5)}),
    "autumn": ("sunset", "sparkler", {"mood": "happy", "look": (0.8, -0.6), "look_far": (-0.6, -0.5)}),
    "winter": ("snow", "mug", {"mood": "happy", "look": (0.3, 0.2)}),
    "night": ("night", "lantern", {"mood": "calm", "look": (0.8, -0.2), "look_far": (0.1, -0.8)}),
}

_WOOD = 0xCFC2AC
_WOOD_SHADE = 0x9D8D78
_WOOD_LIGHT = 0xEEE5D3


def _driftwood(x, y, s, night):
    """A sea-bleached bough propped on the sand, its top where the chameleon's perch is."""
    wood, shade, light = _dim(_WOOD, night), _dim(_WOOD_SHADE, night), _dim(_WOOD_LIGHT, night)
    top = y + 8 * s
    left, right = x - 262 * s, x + 262 * s
    out = [
        ellipse(x - 30 * s, y + 80 * s, 240 * s, 14 * s, 0x000000, opacity=0.16),
        # it stands on its root end, and its far end rests on the dune
        limb(left + 40 * s, top + 8 * s, left - 6 * s, top + 76 * s, 0.16, 40 * s, 56 * s, shade),
        limb(left + 4 * s, top + 60 * s, left - 44 * s, top + 80 * s, 0.2, 18 * s, 7 * s, shade),
        limb(left + 30 * s, top + 56 * s, left + 70 * s, top + 82 * s, -0.2, 16 * s, 6 * s, shade),
        # the bough
        limb(left, top + 8 * s, right + 40 * s, top - 2 * s, 0.014, 40 * s, 20 * s, wood),
        path("M%.1f %.1fQ%.1f %.1f %.1f %.1f" % (left + 16 * s, top + 21 * s, x, top + 22 * s, right + 10 * s, top + 7 * s), None, shade, 6 * s),
        path("M%.1f %.1fQ%.1f %.1f %.1f %.1f" % (left + 30 * s, top - 4 * s, x - 60 * s, top - 6 * s, x + 40 * s, top - 7 * s), None, light, 3.2 * s),
        path("M%.1f %.1fq%.1f %.1f %.1f 0" % (x - 150 * s, top + 8 * s, 14 * s, -5 * s, 30 * s), None, shade, 2 * s),
        path("M%.1f %.1fq%.1f %.1f %.1f 0" % (x + 60 * s, top + 4 * s, 12 * s, 4 * s, 26 * s), None, shade, 2 * s),
        # a snapped side branch, and the rings of the cut end
        limb(right - 80 * s, top - 6 * s, right - 30 * s, top - 56 * s, 0.14, 14 * s, 6 * s, wood),
        limb(left + 90 * s, top + 16 * s, left + 120 * s, top + 44 * s, -0.1, 12 * s, 5 * s, shade),
        ellipse(left - 2 * s, top + 8 * s, 11 * s, 19 * s, light),
        ellipse(left - 2 * s, top + 8 * s, 6.5 * s, 12 * s, None, shade, 1.6 * s),
        ellipse(left - 2 * s, top + 8 * s, 2 * s, 4 * s, shade),
    ]
    return "".join(out)


def draw(doc, season="summer", night=False, pose=None, shell=None, crab_at=(300, 446), crab_scale=0.62, drift=True, who="chameleon", hue_at=(322, 404), hue_scale=0.6):
    """Add the coast to *doc*.

    Args:
        doc: The `vec.Doc` to draw into.
        season (str): "spring", "summer", "autumn" or "winter".
        night (bool): The same place after dark, the lighthouse lit.
        pose (dict): Arguments for `crab.draw`, or None for the season's own.
        shell (str): The crab's shell, or None for the season's own.
        crab_at: Where the crab stands, or None for the place without it.
        crab_scale (float): The crab's size.
        drift (bool): Draw what the air carries: petals, leaves, snow, fireflies.
        who (str): "chameleon", on a driftwood bough, "stage" for the bough alone,
            "crab", or None for the place alone.
        hue_at: Where the chameleon's perch is.
        hue_scale (float): The chameleon's size.
    """
    s = SEASONS[season]
    staged = who in ("chameleon", "stage")
    rng = _Random(101)
    add = doc.add
    add(_sky(s, night))
    cloud = tuple(_dim(c, night) for c in s["cloud"])
    if not night:
        add(_cloud(170, 86, 1.0, cloud), _cloud(400, 54, 0.62, cloud), _cloud(716, 168, 0.8, cloud))
    else:
        add(group(_cloud(210, 120, 0.9, cloud), opacity=0.5))
    add(_sea(s, night))
    add(_headland(s, night, night))
    ink = _dim(0x2B3A4B, night)
    if season == "summer" and not night:
        add(_sailboat(396, HORIZON + 4, night))
    if not night:
        add(_gull(300, 130, 1.0, ink), _gull(332, 116, 0.7, ink), _gull(268, 150, 0.6, ink))
    add(_shore(s, night))
    add(_dune(s, night))
    add(_tree(s, night, 676, 306))
    light, sand, wet = (_dim(c, night) for c in s["sand"])
    # what lies on the sand
    pebble = 30 if staged else 96
    add(ellipse(pebble, 440, 26, 8, wet), ellipse(pebble - 4, 437, 24, 8, _dim(0x9AA7B4, night)), ellipse(pebble, 434, 9, 3, _dim(0xC3CCD6, night)))
    add(ellipse(470, 462, 9, 3.4, wet), ellipse(52, 468, 6, 2.4, wet), ellipse(246, 470, 5, 2, wet))
    star_x, star_y = (232, 470) if staged else (180, 456)
    if season == "summer":
        add(_sandcastle(118 if staged else 430, 456 if staged else 450, sand, wet))
        add(_starfish(star_x, star_y, 15, _dim(0xF58B2A, night), 20))
    elif season == "spring":
        add(_starfish(star_x, star_y, 15, _dim(0xF27A9B, night), 20))
        for fx, fy, color in ((610, 330, 0xFFFFFF), (628, 352, 0xFFE066), (700, 318, 0xFF8FB1), (756, 332, 0xFFFFFF), (668, 380, 0xFFE066), (736, 392, 0xFF8FB1)):
            add(line(fx, fy, fx + 1, fy - 12, _dim(0x5E9E3E, night), 1.6))
            for i in range(5):
                a = i * 1.2566
                add(circle(fx + 1 + math.cos(a) * 3.6, fy - 13 + math.sin(a) * 3.6, 2.6, _dim(color, night)))
            add(circle(fx + 1, fy - 13, 2, _dim(0xF5A623, night)))
    elif season == "autumn":
        add(_starfish(star_x, star_y, 15, _dim(0xC9482B, night), 20))
        for _ in range(16):
            add(ellipse(rng.between(520, 790), rng.between(330, 470), 5.5, 2.6, _dim((0xFFC83D, 0xF58B2A, 0xC9482B)[int(rng.between(0, 2.99))], night), rot=rng.between(0, 180)))
    else:
        add(_snowman(112 if staged else 500, 458 if staged else 452))
    if who in ("chameleon", "stage"):
        add(_driftwood(hue_at[0], hue_at[1], hue_scale, night))
    if who == "chameleon":
        scheme, prop, default = _HUE["night" if night else season]
        options = dict(default)
        options.update(pose or {})
        body = chameleon_props.hold(doc, prop, perch=None, colors=shell or scheme, **options)
        add(at(hue_at[0], hue_at[1], body, scale=hue_scale))
    elif who == "crab" and crab_at is not None:
        default = {
            "spring": ("rose", {"mood": "calm", "wave": 30, "look": (0.5, -0.3)}),
            "summer": ("sand", {"mood": "calm", "look": (0.6, 0.0)}),
            "autumn": ("moss", {"mood": "curious", "look": (0.9, -0.5), "wave": 10}),
            "winter": ("night", {"mood": "calm", "wave": 26, "look": (0.2, -0.4)}),
        }[season]
        if night:
            default = (default[0], {"mood": "calm", "look": (0.7, -0.7)})
        if night:
            wash(0x12305C, 0.42)
        body = crab.draw(doc, shell=shell or default[0], **(pose or default[1]))
        if season == "winter":
            body += _scarf(0xE4513D, 0xFFF1D6) + _hat(0xE4513D, 0xFFF1D6)
        wash()
        add(at(crab_at[0], crab_at[1], body, scale=crab_scale))
    if drift:
        add(_drift(season, night, rng))


def _still(view, **options):
    def build():
        doc = Doc()
        draw(doc, **options)
        return doc.svg(view)

    return build


_WIDE = (0, 0, 800, 480)
_MID = (150, 190, 480, 288)
_CLOSE = (262, 270, 250, 150)

STILLS = [
    ("coast_hue_spring", _still(_WIDE, season="spring"), 800),
    ("coast_hue_summer", _still(_WIDE, season="summer"), 800),
    ("coast_hue_autumn", _still(_WIDE, season="autumn"), 800),
    ("coast_hue_winter", _still(_WIDE, season="winter"), 800),
    ("coast_hue_night", _still(_WIDE, season="summer", night=True), 800),
    ("coast_hue_autumn_mid", _still((120, 170, 500, 300), season="autumn"), 800),
    ("coast_hue_winter_close", _still((300, 250, 270, 162), season="winter"), 800),
    ("coast_spring", _still(_WIDE, season="spring", who="crab"), 800),
    ("coast_summer", _still(_WIDE, season="summer", who="crab"), 800),
    ("coast_autumn", _still(_WIDE, season="autumn", who="crab"), 800),
    ("coast_winter", _still(_WIDE, season="winter", who="crab"), 800),
    ("coast_summer_night", _still(_WIDE, season="summer", night=True, who="crab"), 800),
    ("coast_autumn_mid", _still(_MID, season="autumn", who="crab"), 800),
    ("coast_winter_close", _still(_CLOSE, season="winter", who="crab", pose={"mood": "happy", "wave": 26}), 800),
    ("coast_spring_night", _still(_WIDE, season="spring", night=True, who="crab"), 800),
]
