# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Turn shoot.py's ARGB captures, or shoot_board.py's PNG triples, into 240x240 PNGs.

    python tools/shots_to_png.py SHOTS_DIR docs/screens
"""

import os
import sys

from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
os.makedirs(dst, exist_ok=True)
for name in sorted(os.listdir(src)):
    if name.endswith(".screen.png"):
        # shoot_board.py's three PNGs: the screen, the top layer and its alpha.
        stem = name[: -len(".screen.png")]
        img = Image.open(os.path.join(src, name)).convert("RGB")
        b, g, r = Image.open(os.path.join(src, stem + ".top.png")).convert("RGB").split()
        top = Image.merge("RGB", (r, g, b))  # the PPA writes RGB888 as B, G, R
        alpha = Image.open(os.path.join(src, stem + ".alpha.png")).convert("L")
        img.paste(top, (0, 0), alpha)
        img.save(os.path.join(dst, stem + ".png"))
        print(stem)
        continue
    if not name.endswith(".rgb"):
        continue
    layers = []
    with open(os.path.join(src, name), "rb") as f:
        for _ in range(2):  # the screen, then the top layer over it
            w, h, stride = (int(v) for v in f.readline().split())
            raw = f.read(stride * h)
            layers.append(Image.frombytes("RGBA", (w, h), raw, "raw", "BGRA", stride))
    img = layers[0].convert("RGB")
    top = layers[1]
    if top.size == img.size:
        img.paste(top, (0, 0), top)
    img.save(os.path.join(dst, name[:-4] + ".png"))
    print(name[:-4])
