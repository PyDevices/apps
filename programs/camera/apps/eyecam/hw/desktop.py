# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Desktop stand-ins for the camera's hardware.

The preview is a test picture (``testcard.jpg``, 960x540, half the sensor's
1920x1080) with a figure walking across it; zoom crops its centre as the
board crops the sensor's. The SD card is a folder, ``sd/`` in the app's data
folder. Keys stand in for what a desktop has no way to do: S takes the card
out and puts it back, F fills it (too little space), U plugs a USB host in
and out, R turns the board a quarter. Interval sleep blanks the window; any
key wakes it, and each interval passes in ``MINUTE_MS`` per minute.
"""

import framebuf
import math
import os
import time

import jpegio
import lvgl as lv
import ppa

from . import Hardware
from .photo import Photo

SRC_W, SRC_H = 960, 540
OUT = 240
CROPS = (480, 240, 120, 60)  # the crop side at zoom 1..4, in test-picture pixels
MINUTE_MS = 1000  # one interval minute on the desktop

_here = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."


def rgb(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


SKIN, SHIRT, LEGS = rgb(240, 200, 160), rgb(200, 40, 40), rgb(40, 40, 90)


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _mkdirs(path):
    part = ""
    for p in path.split("/"):
        part = part + "/" + p if part or path.startswith("/") else p
        if p and not _exists(part):
            os.mkdir(part)


class Preview:
    def __init__(self):
        dec = jpegio.JpegDecoder()
        w, h = dec.open(_here + "/testcard.jpg")
        self.src = bytearray(w * h * 2)
        dec.decode(self.src)
        self.buf = bytearray(OUT * OUT * 2)
        self.fb = framebuf.FrameBuffer(self.buf, OUT, OUT, framebuf.RGB565)
        self._shot = None
        self._t0 = time.ticks_ms()
        self.rotation = 0
        self.figure = (0, 0, 0, 0)  # on screen: x0, y0, x1, y1
        self.head = (0, 0, 0)  # on screen: x, y, r

    def _figure_src(self):
        """The walking figure's feet (x, y) and height, in test-picture pixels."""
        t = time.ticks_diff(time.ticks_ms(), self._t0) / 1000
        return int(SRC_W // 2 + 170 * math.sin(t * 0.5)), 380, 110

    def _draw_figure(self, fb, x0, y0, scale):
        fx, fy, fh = self._figure_src()

        def sx(v):
            return int((v - x0) * scale)

        def sy(v):
            return int((v - y0) * scale)

        u = fh / 11
        hr = max(1, int(1.4 * u * scale))
        hx, hy = sx(fx), sy(fy - fh + 1.4 * u)
        fb.fill_rect(sx(fx - 2 * u), sy(fy - fh + 3 * u), max(1, int(4 * u * scale)), max(1, int(4 * u * scale)), SHIRT)
        fb.fill_rect(sx(fx - 1.6 * u), sy(fy - fh + 7 * u), max(1, int(1.4 * u * scale)), max(1, int(4 * u * scale)), LEGS)
        fb.fill_rect(sx(fx + 0.2 * u), sy(fy - fh + 7 * u), max(1, int(1.4 * u * scale)), max(1, int(4 * u * scale)), LEGS)
        fb.ellipse(hx, hy, hr, hr, SKIN, True)
        return (sx(fx - 2.4 * u), sy(fy - fh), sx(fx + 2.4 * u), sy(fy)), (hx, hy, hr)

    def frame(self, magnify):
        side = CROPS[max(1, min(4, magnify)) - 1]
        x0, y0 = (SRC_W - side) // 2, (SRC_H - side) // 2
        ppa.srm(self.src, SRC_W, SRC_H, self.buf, OUT, OUT, src_rect=(x0, y0, side, side))
        self.figure, self.head = self._draw_figure(self.fb, x0, y0, OUT / side)
        if self.rotation:
            tmp = bytearray(self.buf)
            ppa.srm(tmp, OUT, OUT, self.buf, OUT, OUT, rotate=self.rotation)
        return self.buf

    def source(self):
        """The test picture with the figure in it, for a photo."""
        if self._shot is None:
            self._shot = bytearray(len(self.src))
        self._shot[:] = self.src
        fb = framebuf.FrameBuffer(self._shot, SRC_W, SRC_H, framebuf.RGB565)
        self._draw_figure(fb, 0, 0, 1)
        return self._shot, SRC_W, SRC_H

    def rotate(self, degrees):
        self.rotation = degrees % 360


class Storage:
    """A stand-in card in the data folder's ``sd``, with the board's folder names."""

    PICS = "photos"
    VIDS = "videos"

    def __init__(self, root):
        self.root = root + "/sd"
        _mkdirs(self.root + "/" + self.PICS)
        _mkdirs(self.root + "/" + self.VIDS)
        self.card_in = True
        self.full = False

    def mounted(self):
        return self.card_in

    def ready(self):
        """True when a photo can be saved (the board's has flash behind the card)."""
        return self.card_in

    def free(self):
        if not self.card_in:
            return 0
        if self.full:
            return 1024 * 1024
        try:
            st = os.statvfs(self.root)
            return st[0] * st[4]
        except (AttributeError, OSError):
            return 8 * 1024 * 1024 * 1024

    def _numbers(self, folder, prefix, suffix):
        out = []
        for name in os.listdir(self.root + "/" + folder):
            if name.startswith(prefix) and name.endswith(suffix):
                try:
                    out.append(int(name[len(prefix):-len(suffix)]))
                except ValueError:
                    pass
        return out

    def photos(self):
        if not self.card_in:
            return []
        nums = sorted(self._numbers(self.PICS, "pic_", ".jpg"), reverse=True)
        return ["%s/%s/pic_%04d.jpg" % (self.root, self.PICS, n) for n in nums]

    def next_photo(self):
        nums = self._numbers(self.PICS, "pic_", ".jpg")
        return "%s/%s/pic_%04d.jpg" % (self.root, self.PICS, (max(nums) if nums else 0) + 1)

    def next_video(self):
        nums = self._numbers(self.VIDS, "video_", ".mjpeg")
        return "%s/%s/video_%d.mjpeg" % (self.root, self.VIDS, (max(nums) if nums else 0) + 1)

    def remove(self, path):
        os.remove(path)


class Recorder:
    """Writes the preview as MJPEG (one JPEG after another) at quality 80."""

    def __init__(self, preview, storage):
        self.preview = preview
        self.storage = storage
        self.recording = False
        self._f = None
        self._enc = jpegio.JpegEncoder(quality=80)
        self.frames = 0

    def start(self, magnify, resolution=None):
        self._f = open(self.storage.next_video(), "wb")
        self.frames = 0
        self.recording = True

    def tick(self, buf):
        if self.recording:
            self._f.write(self._enc.encode(buf, OUT, OUT))
            self.frames += 1

    def stop(self):
        if self._f is not None:
            self._f.close()
            self._f = None
        self.recording = False


class IntervalSleep:
    """Deep sleep, played on a desktop: a black screen until a key or the
    interval's timer."""

    def __init__(self, scope, minute_ms=MINUTE_MS):
        self.scope = scope
        self.minute_ms = minute_ms
        self.sleeping = False
        self._cover = None
        self._timer = None
        self._on_wake = None
        self._reason = None

    def wake_reason(self):
        r, self._reason = self._reason, None
        return r

    def sleep(self, ms, on_wake):
        self.sleeping = True
        self._on_wake = on_wake
        if self._cover is None:
            self._cover = lv.obj(lv.layer_top())
            self._cover.remove_style_all()
            self._cover.set_size(lv.pct(100), lv.pct(100))
            self._cover.set_style_bg_color(lv.color_hex(0x000000), 0)
            self._cover.set_style_bg_opa(255, 0)
        self._cover.remove_flag(lv.obj.FLAG.HIDDEN)
        self._timer = self.scope.after(ms * self.minute_ms // 60000, lambda t: self.wake("timer"))

    def wake(self, reason):
        """A key ("button") or the timer: boot again, as the board would."""
        if not self.sleeping:
            return
        self.sleeping = False
        if self._timer is not None:
            self._timer.deinit()
            self._timer = None
        if reason == "button":
            self._cover.add_flag(lv.obj.FLAG.HIDDEN)
        self._reason = reason
        self._on_wake(reason)

    def show(self):
        """The screen comes back after a timer wake ends in a button boot."""
        if self._cover is not None:
            self._cover.add_flag(lv.obj.FLAG.HIDDEN)


class UsbDisk:
    def __init__(self):
        self.state = "instruction"
        self._fns = []

    def on_change(self, fn):
        self._fns.append(fn)

    def offer(self):
        pass

    def plug(self, connected):
        self.state = "connected" if connected else "instruction"
        for fn in self._fns:
            fn(self.state)


class Accel:
    def __init__(self):
        self.angle = 0

    def rotation(self):
        return self.angle


class Lights:
    def __init__(self):
        self.flash_on = False
        self.backlight_on = True

    def flash(self, on):
        self.flash_on = on

    def backlight(self, on):
        self.backlight_on = on


class Detector:
    """Boxes round the walking figure; a desktop has no model to run."""

    def __init__(self, preview):
        self.preview = preview

    def people(self, buf, w, h):
        return [self.preview.figure + (None,)]

    def faces(self, buf, w, h):
        x, y, r = self.preview.head
        pts = ((x - r // 3, y - r // 4), (x + r // 3, y - r // 4), (x, y + r // 8),
               (x - r // 3, y + r // 2), (x + r // 3, y + r // 2))
        return [(x - r, y - r, x + r, y + r, pts)]

    def objects(self, buf, w, h):
        return [(w // 3, h // 3, 2 * w // 3, 9 * h // 10, "person", 0.87)]


def build(scope):
    preview = Preview()
    storage = Storage(scope.data_dir)
    lights = Lights()
    return Hardware(
        preview=preview,
        photo=Photo(preview, storage, lights),
        recorder=Recorder(preview, storage),
        sleep=IntervalSleep(scope),
        storage=storage,
        usb=UsbDisk(),
        accel=Accel(),
        lights=lights,
        detector=Detector(preview),
        desktop=True,
    )
