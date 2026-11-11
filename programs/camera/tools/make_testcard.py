# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Draw the desktop preview's test picture: a 960x540 scene (half the
camera's 1920x1080, so each zoom step crops the same share of it).

Run with a CPython that has Pillow:  python tools/make_testcard.py
"""

import math
import os

from PIL import Image, ImageDraw

W, H = 960, 540
OUT = os.path.join(os.path.dirname(__file__), "..", "apps", "eyecam", "hw", "testcard.jpg")

img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
for y in range(H):  # sky to horizon
    t = y / (H * 0.62)
    d.line([(0, y), (W, y)], fill=(int(90 + 120 * t), int(150 + 80 * t), int(235 - 20 * t)))
ground = int(H * 0.62)
d.rectangle([0, ground, W, H], fill=(86, 140, 70))
for i in range(0, W, 48):  # a path in perspective
    d.line([(W // 2, ground), (i * 2 - W // 2, H)], fill=(110, 160, 90), width=1)
d.ellipse([760, 50, 860, 150], fill=(255, 214, 90))  # sun
d.polygon([(330, 330), (430, 250), (530, 330)], fill=(170, 60, 50))  # house
d.rectangle([350, 330, 510, 420], fill=(235, 220, 190))
d.rectangle([410, 360, 450, 420], fill=(110, 70, 40))
d.rectangle([365, 345, 395, 375], fill=(120, 180, 230))
d.rectangle([465, 345, 495, 375], fill=(120, 180, 230))
for x in (120, 650, 860):  # trees
    d.rectangle([x - 8, ground - 60, x + 8, ground + 20], fill=(100, 70, 40))
    d.ellipse([x - 50, ground - 150, x + 50, ground - 40], fill=(40, 110, 50))
bars = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0), (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0)]
bw = 30
for i, c in enumerate(bars):  # colour bars in the centre, so 4X shows them
    d.rectangle([W // 2 - 4 * bw + i * bw, H // 2 - 22, W // 2 - 3 * bw + i * bw - 1, H // 2 + 22], fill=c)
d.rectangle([W // 2 - 4 * bw - 2, H // 2 - 24, W // 2 + 4 * bw + 1, H // 2 + 24], outline=(0, 0, 0), width=2)
for r in (60, 120, 240):  # zoom rings: the crop edge at 4X, 3X, 2X
    d.rectangle([W // 2 - r // 2 * 1, H // 2 - r // 2, W // 2 + r // 2, H // 2 + r // 2], outline=(255, 255, 255), width=1)
for k in range(12):  # a clock face of dots round the centre
    a = k * math.pi / 6
    x, y = W // 2 + 200 * math.cos(a), H // 2 + 200 * math.sin(a)
    d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(255, 255, 255))
img.save(OUT, quality=90)
print(OUT, os.path.getsize(OUT))
