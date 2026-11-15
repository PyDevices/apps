# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Write the frames of a short loop, drawn the way a board would draw it.

    micropython -X heapsize=128M tools/motion.py OUT_DIR [SEASON]

The coast is drawn once into a buffer. Each frame copies it, then svgio blends
the crab in its pose for that frame, and the petals where the wind has
carried them, straight over the copy. Frames are 16-bit BMP files.
"""

import math
import sys
import time

sys.path.insert(0, "..")
sys.path.insert(0, "tools")

from wander import crab  # noqa: E402
from wander import scene_coast  # noqa: E402
import svgio  # noqa: E402
from still import write_bmp  # noqa: E402
from wander.vec import Doc, ellipse, render  # noqa: E402

FRAMES = 48
SCALE = 0.62
VIEW = (-230, -340, 460, 380)
AT = (300, 446)


def crab_text(i):
    t = i / FRAMES
    doc = Doc()
    blink = 1 if i in (9, 10, 33) else 0.5 if i in (8, 11) else 0
    wave = 22 + 22 * math.sin(t * 4 * math.pi)
    look = (0.5 + 0.4 * math.sin(t * 2 * math.pi), -0.2 + 0.3 * math.cos(t * 2 * math.pi))
    doc.add(crab.draw(doc, look=look, blink=blink, wave=wave, shell="rose"))
    return doc.svg(VIEW)


def petals_text(i):
    doc = Doc()
    for k in range(22):
        x = (k * 173 + i * (5 + k % 4) * 800 // (FRAMES * 5)) % 800
        fall = (k * 97 + i * 480 * (1 + k % 2) // FRAMES) % 480
        y = fall + 10 * math.sin((i / FRAMES) * 2 * math.pi + k)
        doc.add(ellipse(x, y, 5, 2.4, (0xFFA9C4, 0xFFD3E0, 0xFFFFFF)[k % 3], rot=(k * 40 + i * 15) % 180))
    return doc.svg((0, 0, 800, 480))


def main():
    out = sys.argv[1]
    season = sys.argv[2] if len(sys.argv) > 2 else "spring"
    doc = Doc()
    scene_coast.draw(doc, season=season, who=None, drift=False)
    t0 = time.ticks_us()
    background, _, w, h = render(doc.svg((0, 0, 800, 480)), 800, 0)
    print("background %d ms" % (time.ticks_diff(time.ticks_us(), t0) // 1000))
    x0 = int(AT[0] + VIEW[0] * SCALE)
    y0 = int(AT[1] + VIEW[1] * SCALE)
    decoder = svgio.SvgDecoder()
    spent_crab = spent_petals = 0
    for i in range(FRAMES):
        frame = bytearray(background)
        bob = int(round(1.5 * math.sin(i / FRAMES * 4 * math.pi)))
        t0 = time.ticks_us()
        decoder.open(crab_text(i).encode(), width=int(VIEW[2] * SCALE))
        decoder.decode(frame, x=x0, y=y0 + bob, stride=w)
        t1 = time.ticks_us()
        decoder.open(petals_text(i).encode(), width=800)
        decoder.decode(frame, stride=w)
        spent_crab += time.ticks_diff(t1, t0)
        spent_petals += time.ticks_diff(time.ticks_us(), t1)
        write_bmp("%s/f%03d.bmp" % (out, i), frame, w, h)
    print("a frame: crab built and blended %d us, petals %d us" % (spent_crab // FRAMES, spent_petals // FRAMES))


main()
