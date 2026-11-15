# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Write stills of the drawings as BMP files, from MicroPython.

    micropython -X heapsize=64M tools/still.py OUT_DIR [NAME ...]

Run it from the app's folder. Each still in `stills.STILLS` (tools/stills.py) is drawn by svgio
and written as a 16-bit BMP, which any image tool opens.
"""

import sys
import time

sys.path.insert(0, "..")

from perch.tools import stills  # noqa: E402
from perch.vec import render  # noqa: E402


def write_bmp(name, pixels, w, h):
    row = w * 2
    pad = (4 - row % 4) % 4
    size = 14 + 40 + 12 + (row + pad) * h
    head = bytearray(66)
    head[0:2] = b"BM"
    head[2:6] = size.to_bytes(4, "little")
    head[10:14] = (66).to_bytes(4, "little")
    head[14:18] = (40).to_bytes(4, "little")
    head[18:22] = w.to_bytes(4, "little")
    head[22:26] = ((1 << 32) - h).to_bytes(4, "little")  # negative: rows top to bottom
    head[26:28] = (1).to_bytes(2, "little")
    head[28:30] = (16).to_bytes(2, "little")
    head[30:34] = (3).to_bytes(4, "little")  # bit fields
    head[54:58] = (0xF800).to_bytes(4, "little")
    head[58:62] = (0x07E0).to_bytes(4, "little")
    head[62:66] = (0x001F).to_bytes(4, "little")
    view = memoryview(pixels)
    with open(name, "wb") as f:
        f.write(head)
        for y in range(h):
            f.write(view[y * row : (y + 1) * row])
            if pad:
                f.write(b"\x00" * pad)


def main():
    out = sys.argv[1]
    wanted = sys.argv[2:]
    for name, build, width in stills.STILLS:
        if wanted and name not in wanted:
            continue
        t0 = time.ticks_ms()
        text = build()
        t1 = time.ticks_ms()
        pixels, _, w, h = render(text, width, 0x000000)
        t2 = time.ticks_ms()
        write_bmp("%s/%s.bmp" % (out, name), pixels, w, h)
        print("%-24s %4dx%-4d svg %6d bytes, built %d ms, drawn %d ms" % (name, w, h, len(text), time.ticks_diff(t1, t0), time.ticks_diff(t2, t1)))


if __name__ == "__main__":
    main()
