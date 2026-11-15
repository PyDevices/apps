# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The desk: a place to write code, with the chameleon keeping you company.

`draw` adds the whole scene to a `vec.Doc`, 800 by 480 units, at one of three
times of day. The window, the lamp and the light on the desk follow the time,
and the chameleon takes a pose, a place and the colours of where it stands, so
one drawing gives a wide shot, a close-up and everything between. The crab can
stand in for it.
"""

import math

from . import chameleon_props
from . import chameleon_shift
from . import chameleon_views
from . import crab
from . import mascot_chameleon
from .vec import Doc, at, circle, ellipse, line, mix, path, pts, rect, smooth

W, H = 800, 480
DESK_Y = 322  # the back edge of the desk top
FRONT_Y = 458  # where the top meets the front face
# where the crab stands, and how large
CRAB_X, CRAB_Y, CRAB_SCALE = 164, 436, 0.6
# where the chameleon perches: the middle of its feet, and how large
SPOTS = {"books": (160, 391, 0.58), "monitor": (338, 75, 0.4)}

NAVY = 0x0B2A4A
LIME = 0xC4DC4C
CORAL = 0xF46A45
WHITE = 0xFFFFFF

WALL = 0xA5CBC3
WOOD = 0xDDA56C
WOOD_LIGHT = 0xE9BB86
WOOD_DARK = 0xB97F4B
WOOD_FRONT = 0x9A6638
FRAME = 0xF7F1E3
FRAME_SHADE = 0xD9CDB6
CASE = 0x2A2F3A
CASE_LIGHT = 0x444B5A
SCREEN = 0x0E1B2E
KEYS = 0xECEAE4
KEYS_SHADE = 0xBDB9B0

TIMES = ("day", "evening", "night")
# How far the room's colours sink toward the evening and the night.
_AMBIENT = {"day": (0x000000, 0.0), "evening": (0x9A4B3C, 0.26), "night": (0x071A33, 0.62)}

# The view through the window: sky bands from the top, sea bands, sun or moon.
_VIEW = {
    "day": ((0x6FBDEB, 0x8CCDF0, 0xAEDDF3, 0xD3EEF6), (0x2F9DB5, 0x2488A6, 0x1B7394), 0xFFF6C9),
    "evening": ((0x5C4B8A, 0xB0608F, 0xF08A62, 0xFFC56B), (0xE8846A, 0x8E5A88, 0x4C4479), 0xFFF0B0),
    "night": ((0x081B38, 0x0D274B, 0x14345E, 0x1D4470), (0x163A63, 0x0F2C50, 0x0A2140), 0xF6F2D8),
}

# The code on the monitor: each row an indent and its (length, colour) words.
_CODE_COLORS = (0xC4DC4C, 0xFF8A66, 0x6EC6FF, 0xD7DEE8, 0xB79CFF, 0x5B6B82)
_CODE = (
    (0, ((30, 4), (44, 3))),
    (0, ((30, 4), (26, 3), (18, 5))),
    (0, ()),
    (0, ((22, 4), (40, 0), (16, 3))),
    (1, ((34, 3), (10, 5), (30, 2))),
    (1, ((20, 4), (46, 3))),
    (2, ((40, 0), (22, 1), (14, 3))),
    (2, ((28, 3), (10, 5), (36, 1))),
    (1, ((26, 4), (30, 2))),
    (0, ()),
    (0, ((40, 0), (24, 3))),
)


def _toner(time):
    color, amount = _AMBIENT[time]

    def tone(c):
        return mix(c, color, amount)

    return tone


def _room(tone, time):
    # the wall goes on above the picture, for a view that follows something up the monitor
    out = [rect(0, -200, W, DESK_Y + 202, tone(WALL))]
    if time != "night":
        # the window's light, thrown down the wall to the left
        glow = 0xFFF4C8 if time == "day" else 0xFFB37A
        out.append(path(pts(((538, 60), (538, 256), (300, 322), (120, 322)), True), glow, opacity=0.13))
    # a line of shade where the wall meets the desk
    out.append(rect(0, DESK_Y - 8, W, 10, tone(mix(WALL, NAVY, 0.18))))
    out.append(rect(0, DESK_Y, W, FRONT_Y - DESK_Y, tone(WOOD)))
    out.append(rect(0, DESK_Y, W, 5, tone(WOOD_LIGHT)))
    grain = tone(WOOD_DARK)
    for x0, y, length in ((30, 352, 150), (250, 344, 90), (520, 340, 170), (90, 396, 110), (430, 442, 190), (660, 404, 110), (20, 446, 80), (300, 428, 70)):
        out.append(line(x0, y, x0 + length, y, grain, 2, opacity=0.35))
    out.append(rect(0, FRONT_Y, W, H - FRONT_Y, tone(WOOD_FRONT)))
    out.append(rect(0, FRONT_Y, W, 4, tone(WOOD_DARK)))
    return "".join(out)


def _sunlight(time):
    # the window's two halves, laid across the desk by the sun
    if time == "night":
        return ""
    color = 0xFFF4C8 if time == "day" else 0xFFB37A
    out = [path(pts(((452, DESK_Y), (566, DESK_Y), (470, FRONT_Y), (320, FRONT_Y)), True), color, opacity=0.26)]
    out.append(path(pts(((578, DESK_Y), (690, DESK_Y), (630, FRONT_Y), (486, FRONT_Y)), True), color, opacity=0.26))
    return "".join(out)


def _window(tone, time):
    x0, y0, w, h = 552, 44, 208, 200
    sky, sea, disc = _VIEW[time]
    out = []
    horizon = y0 + 132
    band = (horizon - y0) / 4
    for i in range(4):
        out.append(rect(x0, y0 + i * band, w, band + 1, sky[i]))
    if time == "night":
        for sx, sy, r in ((572, 62, 1.6), (606, 92, 1.2), (640, 58, 1.8), (700, 60, 1.4), (744, 122, 1.2), (590, 128, 1.3), (696, 150, 1.5), (676, 104, 1.1)):
            out.append(circle(sx, sy, r, 0xEAF2FF))
        # the moon sits inside one band of sky, so the bite out of it is that band's colour
        out.append(circle(712, 93, 14, disc))
        out.append(circle(719, 89, 11, sky[1]))
        # the lighthouse's beam, sweeping out to sea
        out.append(path(pts(((x0 + 34, horizon - 51), (x0 + 150, horizon - 70), (x0 + 150, horizon - 38)), True), 0xFFF3B0, opacity=0.22))
    else:
        sun_y = y0 + 52 if time == "day" else horizon - 8
        sun_x = 700 if time == "day" else 680
        out.append(circle(sun_x, sun_y, 34, disc, opacity=0.28))
        out.append(circle(sun_x, sun_y, 25, disc, opacity=0.4))
        out.append(circle(sun_x, sun_y, 17, disc))
        cloud = WHITE if time == "day" else 0xFFD9B8
        for cx, cy, s in ((606, 84, 1.0), (724, 134, 0.7)):
            out.append(rect(cx - 26 * s, cy, 56 * s, 12 * s, cloud, r=6 * s, opacity=0.92))
            out.append(circle(cx - 8 * s, cy, 12 * s, cloud, opacity=0.92))
            out.append(circle(cx + 10 * s, cy - 3 * s, 15 * s, cloud, opacity=0.92))
    # the sea, and the light lying on it
    step = (y0 + h - horizon) / 3
    for i in range(3):
        out.append(rect(x0, horizon + i * step, w, step + 1, sea[i]))
    if time != "night":
        glint = 0xFFFFFF if time == "day" else 0xFFE3A0
        gx = 700 if time == "day" else 680
        for i, half in enumerate((30, 20, 26, 14)):
            out.append(rect(gx - half, horizon + 5 + i * 11, half * 2, 3, glint, r=1.5, opacity=0.7))
    # a headland and its lighthouse
    land = (0x4F8F6A, 0x3E5E73, 0x0B1E33)[TIMES.index(time)]
    out.append(path("M%d %dL%d %dC%d %d %d %d %d %dZ" % (x0, horizon + 6, x0, horizon - 20, x0 + 34, horizon - 30, x0 + 66, horizon - 2, x0 + 100, horizon + 6), land))
    lx = x0 + 28
    out.append(path(pts(((lx, horizon - 20), (lx + 12, horizon - 20), (lx + 10, horizon - 48), (lx + 2, horizon - 48)), True), 0xF4F1EA if time != "night" else 0x8FA3BD))
    out.append(rect(lx + 1.4, horizon - 38, 9.2, 6, CORAL if time != "night" else 0x8B4A4A))
    out.append(rect(lx, horizon - 54, 12, 6, CASE))
    out.append(rect(lx + 2.5, horizon - 53, 7, 4, 0xFFF3B0))

    # the frame over the view's edges, its bars, and the sill
    frame, shade = tone(FRAME), tone(FRAME_SHADE)
    out.append(rect(x0 - 7, y0 - 7, w + 14, h + 14, None, stroke=frame, width=14))
    out.append(rect(x0 + w / 2 - 4, y0, 8, h, frame))
    out.append(rect(x0, y0 + 62, w, 7, frame))
    out.append(rect(x0 + w / 2 - 4, y0, 2.5, h, shade))
    out.append(rect(x0, y0 + 67, w, 2, shade))
    out.append(rect(x0 - 26, y0 + h + 12, w + 52, 13, frame, r=3))
    out.append(rect(x0 - 20, y0 + h + 25, w + 40, 5, tone(mix(WALL, NAVY, 0.22))))
    return "".join(out)


def _picture(tone):
    # a framed print of a shell: one line winding in to the middle
    out = [rect(36, 26, 100, 84, tone(0x8A5A36), r=3)]
    out.append(rect(42, 32, 88, 72, tone(FRAME)))
    out.append(rect(49, 39, 74, 58, tone(0x1C6E8C)))
    cx, cy = 86, 69
    spiral = []
    for i in range(22):
        a = i * 0.62
        r = 23 * (1 - i / 24)
        spiral.append((cx + math.cos(a) * r, cy + math.sin(a) * r * 0.92))
    out.append(path(smooth(spiral), None, tone(0xFFF6E0), 4.2))
    out.append(circle(spiral[0][0], spiral[0][1], 3.6, tone(LIME)))
    return "".join(out)


def _monitor(tone, time):
    x0, y0, w, h = 226, 74, 300, 204
    mid = x0 + w / 2
    out = []
    # stand
    out.append(ellipse(mid + 6, DESK_Y + 14, 92, 9, 0x000000, opacity=0.14))
    out.append(path(pts(((mid - 16, y0 + h - 6), (mid + 16, y0 + h - 6), (mid + 22, DESK_Y + 8), (mid - 22, DESK_Y + 8)), True), tone(CASE_LIGHT)))
    out.append(path(pts(((mid - 16, y0 + h - 6), (mid - 4, y0 + h - 6), (mid - 6, DESK_Y + 8), (mid - 22, DESK_Y + 8)), True), tone(CASE)))
    out.append(ellipse(mid, DESK_Y + 10, 62, 8, tone(CASE)))
    out.append(ellipse(mid, DESK_Y + 8, 62, 7, tone(CASE_LIGHT)))
    # case and screen
    out.append(rect(x0, y0, w, h, tone(CASE), r=11))
    out.append(rect(x0 + 8, y0 + 2, w - 16, 3, tone(CASE_LIGHT), r=1.5))
    sx, sy, sw, sh = x0 + 10, y0 + 10, w - 20, h - 24
    out.append(rect(sx, sy, sw, sh, SCREEN, r=3))
    # the editor's title strip and its three lights
    out.append(rect(sx, sy, sw, 14, 0x16263D, r=3))
    for i, c in enumerate((0xFF6B5E, 0xFFC24A, LIME)):
        out.append(circle(sx + 10 + i * 10, sy + 7, 2.8, c))
    out.append(rect(sx + 56, sy + 3, 60, 11, SCREEN, r=3))
    out.append(rect(sx + 64, sy + 7, 34, 3, 0x8FA3BD, r=1.5))
    # the file tree down the left
    out.append(rect(sx, sy + 14, 46, sh - 14, 0x122036))
    for i, (ind, length) in enumerate(((0, 26), (6, 24), (6, 30), (6, 18), (0, 22), (6, 28), (6, 20))):
        c = LIME if i == 2 else 0x4E6079
        out.append(rect(sx + 7 + ind, sy + 24 + i * 11, length, 3.4, c, r=1.7))
    # code
    left = sx + 56
    y = sy + 25
    for n, (indent, words) in enumerate(_CODE):
        out.append(rect(left, y, 5, 3, 0x33455F, r=1.5))
        x = left + 13 + indent * 14
        for length, color in words:
            out.append(rect(x, y - 0.5, length, 4.4, _CODE_COLORS[color], r=2.2))
            x += length + 6
        if n == 7:
            out.append(rect(x + 1, y - 3, 3, 9, WHITE))
        y += 11.4
    # the pane at the right: what the code draws
    px, py, pw, ph = sx + sw - 92, sy + 22, 84, sh - 30
    out.append(rect(px, py, pw, ph, 0x16263D, r=5))
    wave = []
    for i in range(13):
        wave.append((px + 8 + i * 5.6, py + 34 + math.sin(i * 0.82) * 15))
    out.append(path(smooth(wave), None, LIME, 2.4))
    out.append(circle(wave[4][0], wave[4][1], 3.4, WHITE))
    for i, height in enumerate((18, 30, 24, 40, 34, 22)):
        out.append(rect(px + 9 + i * 11.6, py + ph - 12 - height, 8, height, (0x6EC6FF, 0xFF8A66)[i == 3], r=2))
    out.append(rect(px + 8, py + ph - 11, pw - 16, 2, 0x4E6079, r=1))
    # the glass catches the window
    out.append(path(pts(((sx + sw - 54, sy), (sx + sw - 22, sy), (sx + sw - 96, sy + sh), (sx + sw - 128, sy + sh)), True), WHITE, opacity=0.035))
    # the maker's light
    out.append(circle(mid, y0 + h - 7, 2.2, LIME))
    if time == "night":
        out.append(ellipse(mid, DESK_Y + 44, 170, 30, 0x6EC6FF, opacity=0.10))
    return "".join(out)


def _notes(tone):
    out = []
    for x, y, rot, c, dark in ((192, 92, -6, 0xFFE27A, 0xE3BF47), (196, 136, 5, 0xFF9FB2, 0xE07A90)):
        body = rect(-17, 0, 34, 34, tone(c)) + path("M17 34L5 34L17 22Z", tone(dark))
        body += rect(-11, 8, 22, 2.6, tone(dark), r=1.3) + rect(-11, 15, 15, 2.6, tone(dark), r=1.3)
        out.append(at(x, y, body, rot=rot))
    return "".join(out)


def _keyboard(tone):
    top, bottom = 366, 418
    xl0, xr0, xl1, xr1 = 306, 512, 292, 526
    out = [ellipse(412, bottom + 6, 128, 8, 0x000000, opacity=0.15)]
    out.append(path(pts(((xl1, bottom), (xr1, bottom), (xr1, bottom + 6), (xl1, bottom + 6)), True), tone(0x8E8A82)))
    out.append(path(pts(((xl0, top), (xr0, top), (xr1, bottom), (xl1, bottom)), True), tone(0xCFCBC2)))
    rows = 5
    for r in range(rows):
        t0, t1 = (r + 0.16) / rows, (r + 0.86) / rows
        y0, y1 = top + 3 + (bottom - top - 6) * t0, top + 3 + (bottom - top - 6) * t1
        left = xl0 + (xl1 - xl0) * t0 + 6
        right = xr0 + (xr1 - xr0) * t0 - 6
        if r == rows - 1:
            cells = ((0, 2), (2, 3.6), (3.6, 9.6), (9.6, 11.2), (11.2, 13))
        else:
            cells = [(i, i + 1) for i in range(13)]
        for a, b in cells:
            kx0 = left + (right - left) * a / 13 + 1.2
            kx1 = left + (right - left) * b / 13 - 1.2
            c = KEYS
            if r == 0 and a == 0:
                c = CORAL
            elif r == 2 and a == 12:
                c = LIME
            out.append(rect(kx0, y0 + 1.4, kx1 - kx0, y1 - y0, tone(KEYS_SHADE), r=1.8))
            out.append(rect(kx0, y0, kx1 - kx0, y1 - y0 - 0.6, tone(c), r=1.8))
    return "".join(out)


def _mug(tone):
    x, y = 606, 386  # the middle of its foot
    out = [ellipse(x - 6, y + 1, 30, 6, 0x000000, opacity=0.16)]
    out.append(circle(x - 21, y - 21, 10, None, tone(0x123A5E), 5.5))
    out.append(path("M%d %dL%d %dQ%d %d %d %dL%d %dQ%d %d %d %dL%d %dZ" % (x - 19, y - 40, x - 19, y - 6, x - 19, y + 2, x - 11, y + 2, x + 11, y + 2, x + 19, y + 2, x + 19, y - 6, x + 19, y - 40), tone(NAVY)))
    out.append(path("M%d %dL%d %dQ%d %d %d %dL%d %dZ" % (x - 19, y - 40, x - 19, y - 6, x - 19, y + 2, x - 11, y + 2, x - 9, y - 40), tone(0x061A30)))
    out.append(rect(x - 19, y - 22, 38, 6, tone(LIME)))
    out.append(ellipse(x, y - 40, 19, 5.5, tone(0x1D4470)))
    out.append(ellipse(x, y - 39.4, 15.5, 3.8, tone(0x5B3524)))
    out.append(rect(x + 10, y - 34, 3.4, 9, tone(0x4A6FA5), r=1.7))
    for dx, lift in ((-5, 0), (6, 8)):
        x1, y1 = x + dx, y - 46 - lift
        d = "M%d %dC%d %d %d %d %d %dC%d %d %d %d %d %d" % (x1, y1, x1 - 8, y1 - 10, x1 + 8, y1 - 18, x1, y1 - 28, x1 - 7, y1 - 36, x1 + 5, y1 - 42, x1 + 1, y1 - 50)
        out.append(path(d, None, WHITE, 3.4, opacity=0.42))
    return "".join(out)


def _leaf(x, y, length, width, rot, light, dark):
    body = path("M0 0C%.1f %.1f %.1f %.1f 0 %.1fC%.1f %.1f %.1f %.1f 0 0Z" % (width, -length * 0.25, width, -length * 0.8, -length, -width, -length * 0.8, -width, -length * 0.25), light)
    body += path("M0 0C%.1f %.1f %.1f %.1f 0 %.1fZ" % (-width, -length * 0.25, -width, -length * 0.8, -length), dark)
    return at(x, y, body, rot=rot)


def _plant(tone):
    out = []
    # two books, lying flat
    out.append(ellipse(718, 349, 76, 7, 0x000000, opacity=0.15))
    out.append(rect(658, 334, 128, 14, tone(0x2F6F7E), r=2))
    out.append(rect(664, 337, 116, 3, tone(0xF2EAD8)))
    out.append(rect(666, 344, 22, 2, tone(0x7FB6C2)))
    out.append(rect(670, 320, 108, 14, tone(0xE0A83A), r=2))
    out.append(rect(676, 323, 96, 3, tone(0xF2EAD8)))
    out.append(rect(752, 329, 18, 2, tone(0xF7D58A)))
    # stems and leaves, the back ones first
    green, deep, pale = tone(0x4E9A63), tone(0x2F6E4A), tone(0x7CC27F)
    px, py = 726, 268
    for tx, ty in ((690, 214), (756, 196), (722, 176), (776, 236), (676, 250)):
        out.append(path("M%d %dQ%d %d %d %d" % (px, py, (px + tx) // 2, ty + 20, tx, ty), None, deep, 3))
    out.append(_leaf(676, 252, 44, 15, -74, green, deep))
    out.append(_leaf(776, 238, 46, 16, 62, pale, green))
    out.append(_leaf(690, 216, 54, 18, -38, pale, green))
    out.append(_leaf(756, 198, 56, 19, 30, green, deep))
    out.append(_leaf(722, 178, 58, 19, -4, pale, green))
    # pot
    out.append(path(pts(((698, 272), (758, 272), (750, 320), (706, 320)), True), tone(0xF4EFE6)))
    out.append(path(pts(((698, 272), (716, 272), (720, 320), (706, 320)), True), tone(0xD6CDBD)))
    out.append(rect(693, 264, 70, 11, tone(0xFFFBF2), r=3))
    out.append(rect(693, 264, 20, 11, tone(0xE4DCCD), r=3))
    out.append(rect(706, 296, 44, 5, tone(CORAL)))
    return "".join(out)


def _lamp(tone, on):
    body, dark = tone(LIME), tone(0x93AA2E)
    arm = tone(0x3A4150)
    out = [ellipse(40, 352, 44, 8, 0x000000, opacity=0.15)]
    out.append(ellipse(44, 346, 38, 9, dark))
    out.append(ellipse(44, 343, 38, 8, body))
    out.append(line(44, 340, 24, 250, arm, 6))
    out.append(line(24, 250, 78, 178, arm, 6))
    out.append(circle(24, 250, 7, tone(CASE)))
    # the shade, pointing down and to the right
    head = path("M-12 -8L12 -8L34 32L-34 32Z", body) + path("M-12 -8L-2 -8L-10 32L-34 32Z", dark)
    head += rect(-9, -17, 18, 10, tone(CASE), r=3)
    head += ellipse(0, 32, 34, 6, 0xFFF6D2 if on else dark)
    out.append(at(78, 178, head, rot=-24))
    return "".join(out)


def _lamp_light(time):
    # the cone through the air, and the pool it leaves on the desk
    cone = path(pts(((62, 196), (120, 222), (330, 440), (0, 452), (0, 330)), True), 0xFFE9A8, opacity=0.10 if time == "evening" else 0.13)
    pool = ellipse(166, 426, 178, 28, 0xFFDFA0, opacity=0.22 if time == "evening" else 0.30)
    return cone + pool


def _board(doc, tone):
    # drawn about its own middle, so it can sit at an angle
    out = [ellipse(2, 16, 62, 9, 0x000000, opacity=0.16)]
    out.append(rect(-54, -18, 108, 34, tone(0x061A30), r=5))
    out.append(rect(-54, -20, 108, 34, tone(NAVY), r=5))
    for x, y in ((-48, -14), (48, -14), (-48, 8), (48, 8)):
        out.append(circle(x, y, 2.6, tone(0xD9B45A)))
    # the processor, its radio can and the traces between them
    out.append(path("M-6 -3L8 -3L14 -9L30 -9M-6 3L10 3L16 9L36 9M-20 -10L-20 -15L-34 -15", None, tone(0x1F5E8F), 1.6))
    out.append(rect(-24, -11, 18, 18, tone(0x15171C), r=2))
    out.append(rect(-20, -7, 10, 10, tone(0x2F343F), r=1))
    out.append(rect(14, -15, 24, 14, tone(0xC9CED6), r=2))
    out.append(rect(17, -12, 18, 3, tone(0xEEF1F5), r=1))
    for i in range(10):
        out.append(rect(-38 + i * 7.6, 8, 4, 4, tone(0xD9B45A), r=1))
    out.append(rect(-62, -9, 14, 14, tone(0xC9CED6), r=2))
    # its light is on
    halo = doc.radial([(0, LIME, 0.75), (1, LIME, 0)])
    out.append(circle(43, -3, 11, halo))
    out.append(circle(43, -3, 3, 0xF4FFB0))
    return "".join(out)


def _cable(tone):
    points = ((598, 433), (572, 430), (552, 416), (548, 388), (532, 352), (480, 338), (424, 336))
    return path(smooth(points), None, tone(0x1D2430), 4.4)


def _bubble(x, y):
    out = []
    for cx, cy, r in ((x + 62, y + 62, 5), (x + 50, y + 46, 8)):
        out.append(circle(cx + 1.5, cy + 2, r, NAVY, opacity=0.14))
        out.append(circle(cx, cy, r, WHITE))
    out.append(ellipse(x + 2, y + 4, 52, 35, NAVY, opacity=0.14))
    for cx, cy, r in ((x - 24, y + 6, 26), (x + 24, y + 8, 25), (x - 6, y - 12, 26), (x + 22, y - 8, 22), (x, y + 12, 26)):
        out.append(circle(cx, cy, r, WHITE))
    for i, c in enumerate((NAVY, NAVY, CORAL)):
        out.append(circle(x - 20 + i * 20, y + 2, 5.6, c))
    return "".join(out)


def _stack(tone):
    # two books by the keyboard: somewhere to stand
    out = [ellipse(160, 441, 150, 9, 0x000000, opacity=0.16)]
    out.append(rect(26, 414, 250, 25, tone(0x23466B), r=3))
    out.append(rect(26, 414, 250, 4, tone(0x3A6491), r=2))
    out.append(rect(44, 421, 8, 18, tone(LIME)))
    out.append(rect(58, 421, 3, 18, tone(LIME)))
    out.append(rect(186, 424, 62, 4, tone(0x7FA3C9), r=2))
    out.append(rect(44, 391, 218, 23, tone(0xEFE6D2), r=3))
    out.append(rect(44, 410, 218, 4, tone(0xCDBFA3), r=2))
    out.append(rect(224, 391, 9, 23, tone(CORAL)))
    out.append(rect(70, 399, 74, 4, tone(0xB9AB90), r=2))
    out.append(rect(70, 406, 44, 3, tone(0xB9AB90), r=1.5))
    return "".join(out)


def _scheme(time, spot):
    # it takes its colours from where it stands
    if time == "night":
        return "night"
    if spot == "monitor":
        return "brand" if time == "day" else chameleon_shift.between("brand", "sunset", 0.35)
    return "leaf" if time == "day" else "sunset"


def _chameleon(doc, time, spot, pose, colors, look, look_far, blink, mood, wave, nod, prop):
    x, y, scale = SPOTS[spot]
    if colors is None:
        colors = _scheme(time, spot)
    if pose == "front":
        body = chameleon_views.front(doc, look=look, look_other=look_far, blink=blink, mood=mood, colors=colors, hand=wave, perch=None)
    elif pose == "three_quarter":
        body = chameleon_views.three_quarter(doc, look=look, look_far=look_far, blink=blink, mood=mood, colors=colors, perch=None)
    elif pose == "sit":
        body = mascot_chameleon.draw_sit(doc, look=look, look_far=look_far, blink=blink, mood=mood, colors=colors, perch=None, wave=wave)
    elif pose == "sleep":
        body = mascot_chameleon.draw_sleep(doc, colors=colors, perch=None)
    elif pose == "hold":
        body = chameleon_props.hold(doc, prop, look=look, look_far=look_far, blink=blink, mood=mood, colors=colors, perch=None)
    else:
        body = mascot_chameleon.draw(doc, look=look, look_far=look_far, blink=blink, mood=mood, colors=colors, hand=wave, perch=None, nod=nod)
    # its shadow lies on what it stands on
    shadow = ellipse(x - 4, y + 2, 170 * scale, 5, 0x000000, opacity=0.16) if spot == "books" else ""
    return shadow + at(x, y, body, scale=scale)


def draw(doc, who="chameleon", time="day", mood="calm", look=None, look_far=None, wave=0, blink=0, shell="sand", bubble=False, pose="three_quarter", spot="books", colors=None, nod=0, prop=None):
    """Add the desk and its company to *doc*.

    Args:
        doc: The `vec.Doc` to draw into.
        who (str): "chameleon", or "crab" for the hermit crab beside the keyboard.
        time (str): "day", "evening" or "night". The lamp is on after day.
        mood (str): "calm", "happy", "curious" or "sleepy".
        look: Where the near eye points, each of x and y from -1 to 1.
        look_far: Where the chameleon's other eye points, or None for the same way.
        wave (float): The crab's claw lift in degrees, or the chameleon's raised hand, 0 to 1.
        blink (float): 0 with the eyes open, 1 closed.
        shell (str): The crab's shell, a name from `crab.SHELLS`.
        bubble (bool): Draw a thought bubble.
        pose (str): The chameleon's: "three_quarter", "side", "front", "sit", "sleep" or "hold".
        spot (str): Where the chameleon perches, a name from `SPOTS`.
        colors (str): A scheme from `mascot_chameleon.COLORS`, or None for the one that suits the time and the spot.
        nod (float): The chameleon's head tilt in the "side" pose, in degrees, positive chin down.
        prop (str): What it holds in the "hold" pose, a name from `chameleon_props.PROPS`.
    """
    tone = _toner(time)
    lit = time != "day"
    hue = who in ("chameleon", "stage")
    if look is None:
        look = (0.3, 0.1)
    doc.add(_room(tone, time))
    doc.add(_picture(tone))
    doc.add(_window(tone, time))
    doc.add(_sunlight(time))
    doc.add(_lamp(tone, lit))
    doc.add(_plant(tone))
    doc.add(_monitor(tone, time))
    doc.add(_notes(tone))
    if who == "chameleon" and spot == "monitor":
        doc.add(_chameleon(doc, time, spot, pose, colors, look, look_far, blink, mood, wave, nod, prop))
    doc.add(_cable(tone))
    if not (hue and prop == "mug"):
        doc.add(_mug(tone))
    doc.add(_keyboard(tone))
    doc.add(at(664, 436, _board(doc, tone), rot=-7))
    if lit:
        doc.add(_lamp_light(time))
    if hue:
        # the books stand in the lamp's light, so they keep more of their colour
        doc.add(_stack((lambda c: mix(tone(c), c, 0.5)) if lit else tone))
    if not hue:
        doc.add(at(CRAB_X, CRAB_Y, crab.draw(doc, look=look, blink=blink, mood=mood, wave=wave, shell=shell), scale=CRAB_SCALE))
        if bubble:
            doc.add(_bubble(150, 196))
        return
    if who == "stage":
        x, y, scale = SPOTS["books"]
        doc.add(ellipse(x - 4, y + 2, 170 * scale, 5, 0x000000, opacity=0.16))
        return
    if spot != "monitor":
        doc.add(_chameleon(doc, time, spot, pose, colors, look, look_far, blink, mood, wave, nod, prop))
    if bubble:
        x, y, scale = SPOTS[spot]
        doc.add(_bubble(x - 76, y - 330 * scale))


def _still(view, **options):
    def build():
        doc = Doc()
        draw(doc, **options)
        return doc.svg(view)

    return build


STILLS = [
    ("desk_wide", _still((0, 0, 800, 480), who="crab", wave=20, look=(0.5, 0.2)), 800),
    ("desk_mid", _still((0, 180, 490, 294), who="crab", look=(0.8, -0.7)), 980),
    ("desk_close", _still((126, 286, 210, 126), who="crab", mood="happy", wave=20), 900),
    ("desk_hello", _still((126, 286, 210, 126), who="crab", wave=20, look=(0.1, 0.15)), 900),
    ("desk_thinking", _still((0, 130, 540, 324), who="crab", time="evening", mood="curious", look=(0.7, -0.8), bubble=True), 960),
    ("desk_evening", _still((0, 0, 800, 480), who="crab", time="evening", wave=20, look=(0.6, 0.0)), 800),
    ("desk_night", _still((0, 0, 800, 480), who="crab", time="night", mood="sleepy", look=(0.2, 0.6)), 800),
    ("desk_hue_wide", _still((0, 0, 800, 480), look=(0.0, 0.1), look_far=(0.9, -0.5)), 800),
    ("desk_hue_mid", _still((0, 180, 490, 294), look=(0.0, 0.1), look_far=(0.9, -0.5)), 980),
    ("desk_hue_hello", _still((5, 222, 310, 186), pose="front", wave=1, look=(0.0, 0.1)), 900),
    ("desk_hue_thinking", _still((150, -112, 480, 288), spot="monitor", pose="side", mood="curious", nod=10, look=(0.5, 0.8), look_far=(0.0, 0.0), bubble=True), 960),
    ("desk_hue_evening", _still((0, 0, 800, 480), time="evening", pose="sit", wave=1, look=(0.0, 0.1), look_far=(0.8, -0.4)), 800),
    ("desk_hue_night", _still((0, 0, 800, 480), time="night", pose="sleep"), 800),
    ("desk_hue_coffee", _still((0, 180, 490, 294), time="evening", pose="hold", prop="mug", mood="happy", look=(0.2, 0.0)), 980),
]
