# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The workbench: the crab fits a part to a board under the lamp.

`draw` adds the whole scene to a `vec.Doc`, 800 units wide and 480 tall.
Every still is a view of that one drawing, from the whole bench down to the
board's parts.
"""

import math

import crab
from vec import Doc, at, circle, ellipse, group, limb, line, path, pts, rect, smooth

WALL = 0x17364A
PEG = 0xD6AD78
PEG_SHADE = 0xC39A66
PEG_HOLE = 0x9C7446
FRAME = 0x7A4E2B
WOOD = 0xB5733F
WOOD_LIGHT = 0xCF8E55
WOOD_DARK = 0x935A2E
MAT = 0x1F7D62
MAT_LIT = 0x2B9978
MAT_LINE = 0x58BC9A
MAT_EDGE = 0x155A47
PCB = 0x0B2A4A
PCB_EDGE = 0x1A4A7A
TRACE = 0x1F568C
GOLD = 0xE8B84A
GOLD_DARK = 0xB58A2C
LIME = 0xC4DC4C
STEEL = 0xC6D0D9
STEEL_LIGHT = 0xEEF3F7
STEEL_DARK = 0x8492A0
IRON = 0x39424D
IRON_LIGHT = 0x56626F
BLACK = 0x1B2028
MUSTARD = 0xF2B632
MUSTARD_DARK = 0xC98D1B
LIGHT = 0xFFE9A8
CREAM = 0xFFF6E0
RED = 0xE2483A
TEAL = 0x2BA6B8
ORANGE = 0xF29A2E
SHADOW = 0x000000

# Where the crab stands and how big it is beside the board.
CRAB_X, CRAB_Y, CRAB_SCALE = 299, 436, 0.62
# The board's top-left corner; it is 204 wide and 130 tall.
BOARD_X, BOARD_Y = 453, 262


def _dots(x0, y, x1, pitch, size, color):
    # a row of round dots: a line dashed into points with round caps
    return path("M%s %sL%s %s" % (x0, y, x1, y), None, color, size, extra='stroke-dasharray="0.01 %s"' % pitch)


# --- the wall ----------------------------------------------------------------


def _pegboard():
    out = [rect(0, 0, 800, 480, WALL), rect(22, 14, 756, 312, FRAME, r=7), rect(31, 23, 738, 303, PEG)]
    out.append(rect(31, 23, 738, 7, PEG_SHADE))
    y = 46
    while y < 318:
        out.append(_dots(48, y, 760, 22, 5.5, PEG_HOLE))
        y += 22
    return "".join(out)


def _cabinet(x, y):
    # a parts cabinet: four by three clear drawers, each with something in it
    out = [rect(x - 7, y - 3, 190, 124, SHADOW, r=5, opacity=0.14)]
    out.append(rect(x, y, 180, 112, 0x35505F, r=5))
    out.append(rect(x, y, 180, 5, 0x47677A, r=2))
    fills = (RED, MUSTARD, LIME, TEAL, ORANGE, 0xB98AD9, STEEL, GOLD, TEAL, LIME, RED, MUSTARD)
    for row in range(3):
        for col in range(4):
            dx, dy = x + 7 + col * 42, y + 10 + row * 33
            out.append(rect(dx, dy, 40, 29, 0x233845, r=3))
            out.append(rect(dx + 2, dy + 2, 36, 25, 0x9CC6D4, r=2))
            out.append(rect(dx + 4, dy + 15, 32, 10, fills[row * 4 + col], r=2))
            out.append(rect(dx + 2, dy + 2, 36, 5, 0xC9E6EF, r=2))
            out.append(rect(dx + 13, dy + 9, 14, 4, 0x35505F, r=2))
    # the shelf it stands on
    out.append(rect(x - 16, y + 112, 212, 9, WOOD_DARK, r=2))
    out.append(rect(x - 16, y + 112, 212, 3, WOOD_LIGHT, r=1))
    out.append(rect(x - 16, y + 119, 212, 2.5, FRAME, r=1))
    return "".join(out)


def _succulent(x, y):
    out = []
    for dx, tip, color in ((-15, -22, 0x3F8F5F), (15, -24, 0x3F8F5F), (-8, -32, 0x58AD72), (9, -33, 0x58AD72), (0, -38, 0x7CC98D)):
        out.append(limb(x + dx * 0.3, y - 6, x + dx, y + tip, 0.12 if dx < 0 else -0.12, 13, 3, color))
    out.append(path(pts(((x - 15, y - 8), (x + 15, y - 8), (x + 11, y + 12), (x - 11, y + 12)), True), 0xC96A45))
    out.append(rect(x - 17, y - 11, 34, 6, 0xDE8159, r=2))
    return "".join(out)


def _screwdrivers(x, y):
    # three screwdrivers standing in a rail
    out = [rect(x - 6, y + 5, 98, 4, SHADOW, r=2, opacity=0.16)]
    for i, color in enumerate((ORANGE, TEAL, 0x8E6BBF)):
        cx = x + 14 + i * 30
        out.append(rect(cx - 1.8, y, 3.6, 58, STEEL_DARK))
        out.append(rect(cx - 1.8, y, 1.4, 58, STEEL_LIGHT))
        out.append(path(pts(((cx - 3, y + 56), (cx + 3, y + 56), (cx + 1.6, y + 64), (cx - 1.6, y + 64)), True), STEEL_DARK))
        out.append(rect(cx - 8, y - 44, 16, 42, color, r=6))
        out.append(rect(cx + 2, y - 40, 3.5, 30, 0xFFFFFF, r=1.7, opacity=0.35))
        out.append(rect(cx - 8, y - 12, 16, 6, BLACK, opacity=0.35))
    out.append(rect(x - 4, y - 4, 96, 10, IRON, r=3))
    out.append(rect(x - 4, y - 4, 96, 3, IRON_LIGHT, r=1.5))
    return "".join(out)


def _pliers(x, y):
    # hung on a hook by the pivot, jaws up
    out = [limb(x - 10, y + 16, x - 27, y + 86, -0.10, 12, 10, SHADOW, opacity=0.13)]
    out.append(path(pts(((x - 8, y + 4), (x - 5, y - 40), (x - 0.8, y - 44), (x - 0.8, y + 4)), True), STEEL))
    out.append(path(pts(((x + 8, y + 4), (x + 5, y - 40), (x + 0.8, y - 44), (x + 0.8, y + 4)), True), STEEL_DARK))
    out.append(limb(x - 4, y + 8, x - 20, y + 80, -0.10, 12, 10, RED))
    out.append(limb(x + 4, y + 8, x + 20, y + 80, 0.10, 12, 10, 0xB93A2E))
    out.append(limb(x - 6, y + 26, x - 18, y + 70, -0.08, 3, 3, 0xFF8C7A))
    out.append(circle(x, y + 6, 8, STEEL_DARK))
    out.append(circle(x, y + 6, 3.2, STEEL_LIGHT))
    return "".join(out)


def _spool(x, y):
    # a reel of solder on a peg, a loose end hanging
    out = [circle(x - 5, y + 5, 27, SHADOW, opacity=0.13)]
    out.append(path("M%s %sC%s %s %s %s %s %sS%s %s %s %s" % (x + 21, y + 6, x + 30, y + 30, x + 12, y + 44, x + 22, y + 60, x + 34, y + 70, x + 26, y + 78), None, STEEL, 2.2))
    out.append(circle(x, y, 27, 0x2F6FA8))
    out.append(circle(x, y, 27, None, 0x245A8B, 3))
    out.append(circle(x, y, 20, STEEL))
    for r in (17, 14, 11):
        out.append(circle(x, y, r, None, STEEL_DARK, 1))
    out.append(circle(x, y, 8, 0x2F6FA8))
    out.append(circle(x, y, 3.5, BLACK))
    out.append(path("M%s %sA22 22 0 0 1 %s %s" % (x + 4, y - 23.5, x + 21, y - 9), None, 0x7FB4E0, 2.5))
    return "".join(out)


def _tape(x, y):
    out = [circle(x - 4, y + 5, 21, SHADOW, opacity=0.13)]
    out.append(circle(x, y, 16, None, 0xD98E2B, 10))
    out.append(circle(x, y, 20.5, None, 0xB87118, 1.2))
    out.append(path("M%s %sA16 16 0 0 1 %s %s" % (x + 2, y - 16, x + 15, y - 5), None, 0xF4B55A, 3))
    out.append(circle(x, y - 13, 2.6, IRON))
    return "".join(out)


def _postcard(x, y, rot):
    # a postcard of the shore, pinned up
    out = [rect(-3, 4, 84, 58, SHADOW, opacity=0.14), rect(0, 0, 84, 58, CREAM)]
    out.append(rect(5, 5, 74, 48, 0xFFC98A))
    out.append(rect(5, 5, 74, 12, 0xF79F79))
    out.append(circle(54, 30, 9, 0xFFF1B8))
    out.append(rect(5, 30, 74, 13, 0x2A93A8))
    out.append(rect(5, 30, 74, 3, 0x7FD0D6))
    out.append(path("M5 53L5 44Q30 36 79 43L79 53Z", 0xF3D9A8))
    out.append(path(pts(((18, 30), (20, 16), (22, 30)), True), CREAM))
    out.append(rect(19, 20, 2, 3, RED))
    out.append(circle(42, 3, 3.2, RED))
    out.append(circle(41, 2, 1.1, 0xFF9A8C))
    return at(x, y, "".join(out), rot=rot)


def _sticky(x, y, rot):
    out = [rect(-2, 3, 46, 44, SHADOW, opacity=0.14), rect(0, 0, 46, 44, 0xFFE26A)]
    out.append(path("M46 44L34 44L46 32Z", 0xE8C440))
    for i, w in enumerate((30, 34, 22)):
        out.append(line(7, 12 + i * 9, 7 + w, 12 + i * 9, 0x8A7420, 1.6))
    out.append(rect(14, -4, 18, 9, 0xBFE0EA, opacity=0.8))
    return at(x, y, "".join(out), rot=rot)


def _mug(x, y):
    # a mug of pens at the back of the bench
    out = [ellipse(x - 8, y + 1, 30, 6, SHADOW, opacity=0.2)]
    out.append(limb(x - 9, y - 30, x - 16, y - 74, 0, 5, 5, 0x2F6FA8))
    out.append(limb(x - 16, y - 74, x - 17, y - 80, 0, 5, 2, BLACK))
    out.append(limb(x + 2, y - 30, x + 4, y - 82, 0, 5, 5, MUSTARD))
    out.append(path(pts(((x + 1.5, y - 82), (x + 6.5, y - 82), (x + 4, y - 90)), True), 0xF3D9A8))
    out.append(limb(x + 10, y - 30, x + 22, y - 68, 0, 4, 4, RED))
    out.append(path("M%s %sA11 12 0 0 1 %s %s" % (x + 19, y - 34, x + 19, y - 10), None, 0xE8DCC0, 5.5))
    out.append(rect(x - 20, y - 44, 40, 44, CREAM, r=5))
    out.append(rect(x - 20, y - 44, 9, 44, 0xE8DCC0, r=4))
    out.append(rect(x - 20, y - 26, 40, 8, LIME))
    out.append(rect(x - 20, y - 26, 9, 8, 0xA8C038))
    out.append(ellipse(x, y - 44, 20, 4.5, 0x4A3A30))
    return "".join(out)


# --- the bench ---------------------------------------------------------------


def _bench():
    out = [rect(0, 322, 800, 158, WOOD), rect(0, 322, 800, 5, WOOD_LIGHT), rect(0, 327, 800, 2, WOOD_DARK, opacity=0.5)]
    for x, y, length in ((14, 342, 70), (700, 338, 84), (748, 352, 40), (6, 372, 38), (10, 420, 30), (764, 470, 30), (2, 462, 44)):
        out.append(line(x, y, x + length, y, WOOD_DARK, 1.6, opacity=0.6))
    return "".join(out)


_MAT = ((118, 350), (736, 350), (792, 478), (56, 478))


def _mat_pt(u, v):
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = _MAT
    left = ax + (dx - ax) * v
    right = bx + (cx - bx) * v
    return left + (right - left) * u, ay + (dy - ay) * v


def _mat():
    out = [path(pts(((112, 355), (742, 355), (800, 480), (46, 480)), True), SHADOW, opacity=0.18)]
    out.append(path(pts(_MAT, True), MAT_EDGE, MAT_EDGE, 6))
    out.append(path(pts([_mat_pt(u, v) for u, v in ((0.012, 0.03), (0.988, 0.03), (0.992, 1), (0.008, 1))], True), MAT))
    # where the lamp lands
    out.append(ellipse(566, 428, 196, 46, MAT_LIT))
    for i in range(1, 16):
        x0, y0 = _mat_pt(i / 16, 0.03)
        x1, y1 = _mat_pt(i / 16, 1)
        out.append(line(x0, y0, x1, y1, MAT_LINE, 1.1 if i % 4 else 1.8, opacity=0.55))
    for v in (0.16, 0.33, 0.53, 0.76):
        x0, y0 = _mat_pt(0.012, v)
        x1, y1 = _mat_pt(0.988, v)
        out.append(line(x0, y0, x1, y1, MAT_LINE, 1.1, opacity=0.55))
    return "".join(out)


def _lamp_arm():
    out = [rect(736, 310, 34, 16, IRON, r=3), rect(736, 310, 34, 4, IRON_LIGHT, r=2)]
    out.append(limb(752, 312, 782, 176, 0, 9, 9, MUSTARD_DARK))
    out.append(limb(782, 176, 704, 86, 0, 9, 9, MUSTARD))
    out.append(circle(782, 176, 9, IRON))
    out.append(circle(782, 176, 3.5, IRON_LIGHT))
    return "".join(out)


_LAMP_TURN = 120.5


def _lamp_light():
    # the cone from the shade to the mat, drawn flat and faint
    return path(pts(((644.5, 111.5), (703, 146), (756, 428), (372, 428)), True), LIGHT, opacity=0.13)


def _lamp_head():
    out = [path("M-4 -15L52 -36L52 36L-4 15Z", MUSTARD)]
    out.append(path("M-4 -15L52 -36L52 -22L-4 -7Z", 0xFFD05E))
    out.append(path("M-4 15L52 36L52 22L-4 8Z", MUSTARD_DARK))
    out.append(circle(-4, 0, 15, MUSTARD))
    out.append(path("M-4 -15A15 15 0 0 0 -17 -7L-4 -7Z", 0xFFD05E))
    out.append(ellipse(52, 0, 7, 36, 0xFFF7D6))
    out.append(ellipse(52, 0, 3.5, 22, 0xFFFFFF))
    out.append(circle(-4, 0, 6, IRON))
    out.append(circle(-4, 0, 2.4, IRON_LIGHT))
    return at(704, 86, "".join(out), rot=_LAMP_TURN)


# --- the board ---------------------------------------------------------------


def _header(x, y, pins):
    out = [rect(x, y, pins * 9.6 + 3, 13, BLACK, r=2), rect(x, y, pins * 9.6 + 3, 3, 0x343C48, r=1.5)]
    for i in range(pins):
        px = x + 3.8 + i * 9.6
        out.append(rect(px, y + 4, 5, 5, GOLD_DARK))
        out.append(rect(px + 1, y + 4, 4, 4, GOLD))
        out.append(rect(px + 2.6, y + 4.6, 1.8, 1.8, 0xFFE9A0))
    return "".join(out)


def _passive(x, y, body, upright=False):
    if upright:
        return rect(x, y, 4, 8, STEEL) + rect(x, y + 2, 4, 4, body)
    return rect(x, y, 8, 4, STEEL) + rect(x + 2, y, 4, 4, body)


def _trace(points):
    return path(pts(points), None, TRACE, 1.5)


def _board(doc):
    # drawn with its top-left corner at the origin
    out = [rect(0, 0, 204, 130, PCB_EDGE, r=8), rect(1.5, 1.5, 201, 127, PCB, r=7)]
    for x, y in ((10, 10), (194, 10), (10, 120), (194, 120)):
        out.append(circle(x, y, 5.5, GOLD_DARK))
        out.append(circle(x, y, 4.6, GOLD))
        out.append(circle(x, y, 2.6, 0x06182C))
    # copper, under everything else
    for points in (
        ((100, 44), (100, 34), (92, 26), (92, 18)),
        ((108, 44), (108, 30), (102, 24), (102, 18)),
        ((116, 44), (116, 32), (121, 27), (121, 18)),
        ((124, 44), (124, 36), (140, 24), (140, 18)),
        ((100, 78), (100, 90), (92, 98), (92, 112)),
        ((108, 78), (108, 96), (111, 99), (111, 112)),
        ((116, 78), (116, 92), (130, 104), (130, 112)),
        ((124, 78), (124, 86), (146, 106), (150, 112)),
        ((96, 52), (84, 52), (78, 46)),
        ((96, 60), (82, 60)),
        ((96, 68), (86, 68), (80, 74)),
        ((130, 52), (140, 52), (144, 46)),
        ((130, 62), (186, 62)),
        ((130, 70), (144, 70), (150, 76), (186, 76)),
        ((56, 104), (56, 112)),
        ((78, 104), (72, 108), (72, 112)),
        ((34, 104), (34, 108), (44, 112)),
        ((160, 50), (160, 18)),
        ((150, 98), (160, 106), (160, 112)),
        ((172, 98), (169, 106), (169, 112)),
    ):
        out.append(_trace(points))
    for x, y in ((82, 60), (144, 46), (78, 46), (80, 74)):
        out.append(circle(x, y, 2.2, GOLD))
        out.append(circle(x, y, 0.9, 0x06182C))
    out.append(_header(24, 5, 16))
    out.append(_header(24, 112, 16))
    # silk: a tick beside every fourth pin, and a mark at pin 1
    for i in range(0, 16, 4):
        out.append(line(30.3 + i * 9.6, 21, 30.3 + i * 9.6, 24, LIME, 1.2))
        out.append(line(30.3 + i * 9.6, 106, 30.3 + i * 9.6, 109, LIME, 1.2))
    out.append(path("M19 6L19 16L13 11Z", LIME))

    # the radio module: its own small board, an antenna, a shield can
    out.append(rect(12, 26, 64, 56, 0x162231, r=2))
    out.append(path("M16 78L16 31L21 31L21 74L26 74L26 31L31 31L31 78", None, GOLD, 2.2, extra='stroke-linecap="butt" stroke-linejoin="miter"'))
    out.append(rect(36, 30, 37, 48, STEEL_DARK, r=3))
    out.append(rect(36, 30, 36, 47, STEEL, r=3))
    out.append(path("M54 30L66 30L48 77L39 77Q36 77 36 74L36 70Z", STEEL_LIGHT, opacity=0.75))
    out.append(rect(42, 60, 11, 11, None, r=1.5, stroke=STEEL_DARK, width=1))
    out.append(path("M44 68L47.5 62L51 68Z", STEEL_DARK))
    for i in range(6):
        out.append(rect(40 + i * 5.6, 79.5, 3, 3.5, GOLD))

    # the processor
    for i in range(7):
        out.append(rect(98.5 + i * 4.3, 41, 2.4, 40, STEEL))
        out.append(rect(93, 46.5 + i * 4.3, 40, 2.4, STEEL))
    out.append(rect(96, 44, 34, 34, 0x10151C, r=2))
    out.append(rect(96, 44, 34, 34, None, r=2, stroke=0x39424D, width=1))
    out.append(circle(101, 49, 1.6, 0x56626F))
    out.append(rect(106, 57, 14, 2, 0x56626F))
    out.append(rect(106, 62, 18, 2, 0x56626F))
    out.append(rect(106, 67, 9, 2, 0x56626F))

    # crystal, regulator, passives
    out.append(rect(137, 32, 20, 9, STEEL_DARK, r=4.5))
    out.append(rect(137, 32, 20, 8, STEEL, r=4))
    out.append(rect(141, 34, 9, 1.6, STEEL_LIGHT, r=0.8))
    out.append(rect(141, 49, 4, 14, STEEL))
    out.append(rect(151, 49, 4, 14, STEEL))
    out.append(rect(138, 52, 20, 8, 0x10151C, r=1))
    out.append(_passive(82, 30, 0xC9A26B))
    out.append(_passive(82, 37, 0x10151C))
    out.append(_passive(164, 30, 0xC9A26B))
    out.append(_passive(86, 84, 0x10151C, True))
    out.append(_passive(132, 84, 0xC9A26B, True))
    out.append(_passive(166, 50, 0x10151C, True))

    # two buttons
    for bx in (143, 165):
        out.append(rect(bx, 86, 15, 15, STEEL_DARK, r=2))
        out.append(rect(bx, 86, 15, 14, STEEL, r=2))
        out.append(circle(bx + 7.5, 93, 4.6, BLACK))
        out.append(circle(bx + 6.6, 92, 1.6, 0x56626F))

    # the USB socket, overhanging the edge
    out.append(rect(183, 52, 27, 34, STEEL_DARK, r=4))
    out.append(rect(183, 52, 27, 32, STEEL, r=4))
    out.append(rect(185, 54, 20, 4, STEEL_LIGHT, r=2))
    out.append(rect(204, 59, 4, 19, 0x39424D, r=2))

    # the row of lights: an empty footprint, one lit, one for power
    out.append(rect(22, 88, 68, 19, None, r=3, stroke=LIME, width=1.1))
    out.append(rect(26.5, 94, 5, 7, GOLD))
    out.append(rect(36.5, 94, 5, 7, GOLD))
    glow = doc.radial([(0, 0xE9FF8A, 0.85), (0.45, LIME, 0.4), (1, LIME, 0)])
    out.append(circle(56, 97.5, 17, glow))
    out.append(rect(49, 94, 14, 7, STEEL))
    out.append(rect(51.5, 94, 9, 7, 0xF4FFC2))
    out.append(rect(53, 95.5, 6, 2, 0xFFFFFF))
    out.append(rect(71, 94, 14, 7, STEEL))
    out.append(rect(73.5, 94, 9, 7, 0xB93A2E))
    out.append(rect(75, 95.5, 4, 1.6, 0xFF8C7A))
    # the maker's mark in silk: a faceted square
    out.append(path("M112 90L120 94L120 102L112 106L104 102L104 94Z", None, LIME, 1.1))
    out.append(path("M104 94L112 98L120 94M112 98L112 106", None, LIME, 1.1))
    return "".join(out)


def _holder():
    # a board vise: a heavy foot, a post, a bar and two jaws
    out = [ellipse(545, 432, 76, 13, SHADOW, opacity=0.2)]
    out.append(ellipse(555, 428, 62, 12, IRON))
    out.append(ellipse(555, 424, 62, 11, IRON_LIGHT))
    out.append(ellipse(560, 423, 44, 6, 0x6B7885))
    out.append(rect(549, 402, 12, 22, IRON))
    out.append(rect(557, 402, 4, 22, IRON_LIGHT))
    out.append(rect(436, 396, 240, 9, IRON, r=4.5))
    out.append(rect(440, 396, 232, 3, IRON_LIGHT, r=1.5))
    for x in (440, 658):
        out.append(rect(x, 296, 14, 106, IRON, r=3))
        out.append(rect(x + 9, 298, 3.5, 100, IRON_LIGHT, r=1.7))
    out.append(circle(684, 400.5, 9, MUSTARD_DARK))
    out.append(circle(685, 399.5, 7, MUSTARD))
    return "".join(out)


def _cable():
    # from the USB socket off to the right, behind the meter
    d = "M664 331C700 331 706 372 742 372S792 352 806 362"
    return path(d, None, 0x10151C, 6.5) + path(d, None, 0x39424D, 2, opacity=0.9) + rect(660, 321, 18, 20, BLACK, r=3) + rect(660, 321, 18, 5, 0x343C48, r=2)


# --- things on the mat -------------------------------------------------------

_SEGS = {
    "0": "abcdef",
    "1": "bc",
    "2": "abdeg",
    "3": "abcdg",
    "4": "bcfg",
    "5": "acdfg",
    "6": "acdefg",
    "7": "abc",
    "8": "abcdefg",
    "9": "abcdfg",
}


def _digit(x, y, w, h, char, color):
    # one seven-segment digit, each lit segment a bar
    t = w * 0.2
    half = h / 2
    bars = {
        "a": (x + t, y, w - 2 * t, t),
        "g": (x + t, y + half - t / 2, w - 2 * t, t),
        "d": (x + t, y + h - t, w - 2 * t, t),
        "f": (x, y + t * 0.6, t, half - t),
        "b": (x + w - t, y + t * 0.6, t, half - t),
        "e": (x, y + half + t * 0.4, t, half - t),
        "c": (x + w - t, y + half + t * 0.4, t, half - t),
    }
    return "".join(rect(*(bars[s] + (color,))) for s in _SEGS[char])


def _meter(x, y):
    # a multimeter standing on its foot, reading the board's 3.30 volts
    out = [path(pts(((-52, 60), (-16, 66), (34, 66), (-40, 44)), True), SHADOW, opacity=0.2)]
    out.append(rect(-41, -66, 82, 132, MUSTARD_DARK, r=12))
    out.append(rect(-41, -66, 80, 130, MUSTARD, r=12))
    out.append(rect(-33, -58, 66, 114, 0x2A313B, r=7))
    out.append(rect(-27, -52, 54, 30, 0x8FA583, r=3))
    out.append(rect(-26, -51, 52, 28, 0xC6D6AE, r=3))
    ink = 0x26301F
    out.append(_digit(-19, -46, 10, 18, "3", ink))
    out.append(rect(-6.2, -30.5, 2.6, 2.6, ink))
    out.append(_digit(-1, -46, 10, 18, "3", ink))
    out.append(_digit(12, -46, 10, 18, "0", ink))
    # the dial
    out.append(circle(0, 8, 22, 0x1B2028))
    for i in range(10):
        a = math.radians(i * 36 + 18)
        out.append(line(math.cos(a) * 24.5, 8 + math.sin(a) * 24.5, math.cos(a) * 27.5, 8 + math.sin(a) * 27.5, STEEL_DARK, 1.4))
    out.append(circle(0, 8, 16, 0x3B4552))
    out.append(group(rect(-4, -16, 8, 32, MUSTARD, r=4) + rect(-1.2, -14, 2.4, 9, 0x2A313B, r=1), "translate(0 8) rotate(-54)"))
    # the jacks
    for jx, color in ((-20, RED), (0, BLACK), (20, BLACK)):
        out.append(circle(jx, 43, 6.5, 0x10151C))
        out.append(circle(jx, 43, 4.2, color))
        out.append(circle(jx, 43, 1.8, 0x10151C))
    out.append(rect(31, -52, 3.5, 100, 0xFFD05E, r=1.7))
    return at(x, y, "".join(out))


def _leads():
    # the meter's two probes, lying on the mat
    out = []
    for d, color, tip in (
        ("M682 449C676 474 640 476 606 468", RED, (606, 468, 566, 460)),
        ("M702 449C700 484 640 492 596 480", 0x10151C, (596, 480, 556, 474)),
    ):
        out.append(path(d, None, color, 3.2))
        x0, y0, x1, y1 = tip
        out.append(limb(x0, y0, x1, y1, 0, 8, 5, color))
        out.append(limb(x1, y1, x1 - 20, y1 - 4, 0, 2, 1, STEEL))
    return "".join(out)


def _iron(x, y):
    # a soldering iron in its stand, a wisp of smoke rising
    out = [ellipse(x - 6, y + 6, 66, 10, SHADOW, opacity=0.2)]
    out.append(path("M%s %sC%s %s %s %s %s %sS%s %s %s %s" % (x - 30, y - 78, x - 70, y - 60, x - 96, y - 20, x - 78, y + 4, x - 84, y + 30, x - 110, y + 30), None, 0x10151C, 4))
    out.append(rect(x - 50, y - 8, 104, 15, IRON, r=5))
    out.append(rect(x - 50, y - 8, 104, 4, IRON_LIGHT, r=2))
    out.append(rect(x - 42, y - 15, 30, 9, 0xE8C440, r=3))
    out.append(rect(x - 42, y - 15, 30, 3, 0xFFE26A, r=1.5))
    # the iron, pointing down into the spring
    turn = "translate(%s %s) rotate(-42)" % (x + 26, y - 14)
    iron = rect(-3, -44, 6, 46, STEEL_DARK) + rect(0, -44, 3, 46, STEEL)
    iron += rect(-6, -52, 12, 10, STEEL_DARK, r=2)
    iron += rect(-9, -112, 18, 62, 0x2F6FA8, r=8) + rect(1, -106, 5, 50, 0x5B9BD5, r=2.5)
    iron += rect(-9, -74, 18, 22, BLACK, r=3) + rect(-9, -68, 18, 2, 0x343C48) + rect(-9, -62, 18, 2, 0x343C48)
    out.append(group(iron, turn))
    spring = ""
    for i in range(6):
        spring += ellipse(0, -6 - i * 6.2, 9.5 - i * 0.5, 4, None, STEEL_LIGHT if i % 2 else STEEL, 2.4)
    out.append(group(spring, turn))
    out.append(limb(x + 26, y - 6, x + 26, y - 14, 0, 6, 6, IRON))
    for points, width, opacity in (
        (((x + 30, y - 22), (x + 40, y - 50), (x + 26, y - 78), (x + 40, y - 108), (x + 30, y - 136)), 3.2, 0.34),
        (((x + 34, y - 26), (x + 50, y - 62), (x + 42, y - 92), (x + 54, y - 118)), 2.2, 0.22),
    ):
        out.append(path(smooth(points), None, 0xFFFFFF, width, opacity=opacity))
    return "".join(out)


def _breadboard():
    # a small breadboard lying on the mat, with three wires up to the board
    out = [path(pts(((404, 452), (532, 452), (540, 480), (396, 480)), True), SHADOW, opacity=0.2)]
    out.append(path(pts(((408, 446), (536, 446), (544, 476), (400, 476)), True), 0xD9D2C2))
    out.append(path(pts(((408, 446), (536, 446), (543, 472), (401, 472)), True), 0xF6F1E6))
    out.append(line(409, 450, 535, 450, RED, 1.1))
    out.append(line(403, 469, 541, 469, 0x2F6FA8, 1.1))
    for y, inset in ((454.5, 5), (459, 4), (464, 3)):
        out.append(_dots(408 + 6 - inset, y, 538 + inset - 6, 7.2, 2.4, 0x8E8676))
    return "".join(out)


def _wires():
    out = []
    for x0, x1, color, dark in ((470, BOARD_X + 54.5, MUSTARD, MUSTARD_DARK), (496, BOARD_X + 93, TEAL, 0x1B7F8E), (520, BOARD_X + 131.4, 0xF6F1E6, 0xBDB6A6)):
        d = "M%s 458C%s 418 %s 430 %s %s" % (x0, x0 - 6, x1 + 12, x1, BOARD_Y + 121)
        out.append(path(d, None, dark, 4.2))
        out.append(path(d, None, color, 2.6))
        out.append(rect(x1 - 4.6, BOARD_Y + 114, 9.2, 15, 0x2A313B, r=1.5))
        out.append(rect(x1 - 4.6, BOARD_Y + 114, 3, 15, 0x475260, r=1.5))
        out.append(rect(x0 - 2.5, 455, 5, 6, BLACK, r=1))
    return "".join(out)


def _parts():
    # loose parts on the mat: two resistors, a capacitor, a red light
    out = []
    for x, y, rot, bands in ((180, 468, -14, (0xB93A2E, 0x6B3B1D, MUSTARD)), (232, 474, 8, (0x2F6FA8, BLACK, RED))):
        body = line(-17, 0, 17, 0, STEEL, 1.6) + rect(-9, -4, 18, 8, 0xE7C99A, r=4)
        for i, color in enumerate(bands):
            body += rect(-6 + i * 4.5, -4, 2.4, 8, color)
        out.append(at(x, y, body, rot=rot))
    out.append(ellipse(346, 471, 9, 3, SHADOW, opacity=0.2))
    out.append(rect(338, 452, 13, 18, 0x2A4A8C, r=2) + rect(338, 452, 4, 18, STEEL, r=1) + ellipse(344.5, 452, 6.5, 2, 0x5B7FC9))
    out.append(line(371, 466, 366, 476, STEEL, 1.4) + line(376, 466, 379, 477, STEEL, 1.4))
    out.append(path("M366 467L366 458A7.5 7.5 0 0 1 381 458L381 467Z", RED) + rect(364, 465, 19, 3.5, 0xB93A2E, r=1.5))
    out.append(path("M369 458A4.5 4.5 0 0 1 373.5 453.5", None, 0xFF9A8C, 1.8))
    return "".join(out)


# --- the crab and what it holds ----------------------------------------------


def _tweezers():
    # in the claw's frame: joined behind the palm, squeezed where the claw
    # grips, the tips meeting on a part
    out = [path(pts(((-8, 10), (57, 3), (150, 12), (150, 13.6), (57, 8.5), (-8, 13)), True), STEEL_LIGHT)]
    out.append(path(pts(((-8, 13), (57, 17.5), (150, 13.6), (150, 15.2), (57, 23), (-8, 16)), True), STEEL_DARK))
    out.append(path(pts(((57, 3), (150, 12), (150, 12.6), (57, 5)), True), 0xFFFFFF))
    # the part: a small light for the empty footprint
    out.append(rect(143, 7.5, 16, 11, STEEL))
    out.append(rect(146, 7.5, 10, 11, 0xFFF3B0))
    out.append(rect(147.5, 9.5, 6, 2.5, 0xFFFFFF))
    return "".join(out)


def draw(doc, look=(0.95, 0.42), mood="curious", blink=0, wave=4, shell="night"):
    """Add the workbench to *doc*, back to front.

    Args:
        doc: The `vec.Doc` to draw into.
        look: Where the crab's eyes point; the default is the board.
        mood (str): The crab's mood, as `crab.draw` takes it.
        blink (float): 0 with the eyes open, 1 closed.
        wave (float): The big claw's lift in degrees. The tweezers follow
            it, and at the default their tips sit on the empty footprint.
        shell (str): A name from `crab.SHELLS`.
    """
    doc.add(_pegboard(), _cabinet(58, 48), _succulent(206, 37), _screwdrivers(268, 102), _pliers(398, 78))
    doc.add(_spool(470, 76), _tape(540, 72), _postcard(500, 104, -4), _sticky(604, 44, 5))
    doc.add(_bench(), _mug(60, 344), _mat(), _lamp_arm(), _lamp_light())
    doc.add(_cable(), _holder(), at(BOARD_X, BOARD_Y, _board(doc)))
    doc.add(_meter(712, 392), _leads(), _iron(112, 452), _breadboard(), _wires(), _parts())
    hx, hy, turn = crab.claw(wave)
    held = at(hx, hy, _tweezers(), rot=turn)
    body = crab.draw(doc, look=look, blink=blink, mood=mood, wave=wave, shell=shell, wear="goggles")
    doc.add(at(CRAB_X, CRAB_Y, held + body, scale=CRAB_SCALE))
    doc.add(_lamp_head())


def _still(view):
    def build():
        doc = Doc()
        draw(doc)
        return doc.svg(view)

    return build


STILLS = [
    ("bench_wide", _still((0, 0, 800, 480)), 800),
    ("bench_mid", _still((161, 174, 510, 306)), 800),
    ("bench_close", _still((262, 240, 290, 174)), 800),
    ("bench_board", _still((434, 252, 240, 144)), 800),
]
