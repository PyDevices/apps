# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Photos the factory's way, from whatever frame the Preview holds.

The crop for zoom N is the centre 1/N of the frame (1920x1080, 960x540,
480x270, 240x135 on the sensor). 1080P keeps that at full size; 720P and
480P take its centre 1280x960 (in sensor pixels) and scale it to 1280x720 or
640x480, which squashes it a little, exactly as the factory does.
"""

import ppa

try:
    import jpegio
except ImportError:
    jpegio = None

QUALITY = 90
SIZES = {"1080P": (1920, 1080), "720P": (1280, 720), "480P": (640, 480)}
SENSOR_W = 1920


class Photo:
    def __init__(self, preview, storage, lights, work=None):
        self.preview = preview
        self.storage = storage
        self.lights = lights
        self.work = work  # a buffer of at least 1920*1080*2 bytes to scale into, or None to allocate
        self._enc = jpegio.JpegEncoder(quality=QUALITY) if jpegio else None

    def take(self, magnify, resolution, flash):
        if self._enc is None or not self.storage.mounted():
            return None
        self.lights.backlight(False)
        self.lights.flash(bool(flash))
        try:
            src, sw, sh = self.preview.source()
            k = sw / SENSOR_W  # source pixels per sensor pixel
            cw, ch = sw // magnify, sh // magnify
            cx, cy = (sw - cw) // 2, (sh - ch) // 2
            ow, oh = SIZES[resolution]
            if resolution != "1080P":
                # The factory's 1280x960 centre crop, of the zoomed frame.
                zw, zh = int(1280 * k) // magnify, int(960 * k) // magnify
                cx, cy = cx + (cw - zw) // 2, cy + (ch - zh) // 2
                cw, ch = zw, zh
            out = memoryview(self.work)[: ow * oh * 2] if self.work is not None else bytearray(ow * oh * 2)
            ppa.srm(src, sw, sh, out, ow, oh, src_rect=(cx, cy, cw, ch), approx=True)  # 3x is not a whole sixteenth
            data = self._enc.encode(out, ow, oh)
            del out
            path = self.storage.next_photo()
            with open(path, "wb") as f:
                f.write(data)
            return path
        finally:
            self.lights.flash(False)
            self.lights.backlight(True)
