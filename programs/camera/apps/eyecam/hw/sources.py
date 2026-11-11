# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Where the picture comes from: a MIPI-CSI camera, a USB camera, or a test card.

Every source answers the same four calls, which is all the preview, the photo
and the video paths use:

``size()``
    ``(width, height)`` of its frames.
``frame(timeout=200)``
    The newest frame as RGB565 bytes (the chip's byte order), or None when
    none arrived in *timeout* ms. The buffer is borrowed: it stays valid
    until the next call.
``start()`` and ``stop()``
    Begin and end streaming. ``frame`` before ``start`` starts it.
``deinit()``
    Let go of the hardware.

``open_source`` chooses from what the board has, ``first_source`` being the
rule.
"""

import time

CSI = "csi"
UVC = "uvc"
TESTCARD = "testcard"
KINDS = (CSI, UVC, TESTCARD)


def first_source(openers, forced=None):
    """The first source that opens, trying the one named by *forced* (a board
    config's ``camera_source``) first, then the MIPI camera, the USB camera
    and the test card in that order.

    *openers* maps each kind to a function that returns a source, or None
    (or raises) when the board hasn't got one. Only the kinds tried are
    opened, so a board with a MIPI camera never starts the USB host. The test
    card's opener always works.
    """
    order = [k for k in KINDS if k != forced]
    if forced in KINDS:
        order.insert(0, forced)
    for kind in order:
        make = openers.get(kind)
        if make is None:
            continue
        try:
            got = make()
        except Exception as e:
            print("eyecam: no %s source: %s" % (kind, e))
            got = None
        if got is not None:
            return got
    return None


def _aligned(n, align=64):
    import uctypes

    raw = bytearray(n + align)
    off = (-uctypes.addressof(raw)) % align
    return raw, memoryview(raw)[off:off + n]


class CsiSource:
    """The board's own camera (cameraif), as ``board_config.camera`` makes it."""

    kind = CSI

    def __init__(self, camera):
        self.cam = camera

    def size(self):
        s = self.cam.size()
        return s[0], s[1]

    def frame(self, timeout=200):
        return self.cam.frame(timeout=timeout)

    def start(self):
        pass  # cameraif streams from the first frame() call

    def stop(self):
        pass

    def deinit(self):
        self.cam.deinit()


class UvcSource:
    """A USB camera on the host port, MJPEG decoded by the JPEG engine.

    Built on ``usb.host.video.Camera`` the way usbhost's ``uvc_display.py``
    does it: the camera negotiates a mode, its frames arrive as whole JPEGs,
    and ``jpegio.JpegDecoder(hardware=True)`` turns each into RGB565 in a
    buffer made once. A frame that doesn't decode is skipped, so the last
    good picture stays up.
    """

    kind = UVC
    # A webcam's isochronous packets must fit the host's IN limit, which a
    # session started for "uvc" sets at 600 bytes.
    IN_LIMIT = 600

    def __init__(self, dev, max_size=(1280, 720), fps=25):
        import jpegio
        from usb.host.video import Camera

        try:
            self._dec = jpegio.JpegDecoder(hardware=True)
        except (OSError, TypeError):
            self._dec = jpegio.JpegDecoder()
        self.cam = Camera(dev, encoding="mjpeg", max_size=max_size, fps=fps, in_limit=self.IN_LIMIT)
        self.w, self.h = self.cam.width, self.cam.height
        self._jpeg = bytearray(self.cam.frame_bytes)
        self._raw, self._rgb = _aligned(self.w * self.h * 2)
        self._running = False

    def size(self):
        return self.w, self.h

    def start(self):
        if not self._running:
            self.cam.start()
            self._running = True

    def stop(self):
        if self._running:
            self.cam.stop()
            self._running = False

    def frame(self, timeout=200):
        self.start()
        deadline = time.ticks_add(time.ticks_ms(), timeout)
        while True:
            n = self.cam.read(self._jpeg)
            if n > 0:
                try:
                    self._dec.open(memoryview(self._jpeg)[:n])
                    if (self._dec.width, self._dec.height) == (self.w, self.h):
                        self._dec.decode(self._rgb)
                        return self._rgb
                except (ValueError, MemoryError, RuntimeError):
                    pass  # a torn or odd frame: wait for the next
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                return None
            time.sleep_ms(5)

    def deinit(self):
        self.stop()


class TestCardSource:
    """The test picture, still, in the shape of a camera: for a board that has
    no camera at all."""

    kind = TESTCARD
    __test__ = False  # not a unittest case

    def __init__(self, path):
        import jpegio

        dec = jpegio.JpegDecoder()
        self.w, self.h = dec.open(path)
        self._raw, self._rgb = _aligned(self.w * self.h * 2)
        dec.decode(self._rgb)

    def size(self):
        return self.w, self.h

    def frame(self, timeout=200):
        return self._rgb

    def start(self):
        pass

    def stop(self):
        pass

    def deinit(self):
        pass


def pick_mode(formats, cur):
    """The sensor mode a preview wants from *formats* (cameraif's
    ``(name, width, height)`` list): the smallest landscape one whose short
    side is at least 480, since a bigger one only costs frame rate (the
    OV5647's default is 800x1280 at 16 fps, its 800x640 does 32). Returns the
    ``(width, height)``, or None to keep the current mode (*cur*) when it
    already is that, is landscape and big enough, or nothing fits."""
    if cur[0] >= cur[1] and cur[1] >= 480:
        return None  # already a landscape mode that is big enough (the Eye's 1080P)
    best = None
    for f in formats:
        w, h = f[1], f[2]
        if w >= h and h >= 480 and (best is None or w * h < best[0] * best[1]):
            best = (w, h)
    return None if best is None or best == tuple(cur[:2]) else best


def landscape(cam):
    """*cam* itself, or the same camera reopened in the mode ``pick_mode``
    chose, through the board package's ``camera()`` maker. A board whose
    package can't make one keeps the mode it has."""
    try:
        mode = pick_mode(cam.formats(), cam.size())
        if mode is None:
            return cam
        import board_peripherals
        make = board_peripherals.camera
    except (AttributeError, ImportError, OSError):
        return cam
    cam.deinit()
    try:
        return make(format=mode)
    except Exception as e:
        print("eyecam: mode %dx%d: %s; keeping the default" % (mode[0], mode[1], e))
        return make()


def open_source(board_config, testcard_path, usb_wait_ms=3000):
    """Open the best source this board has. A missing camera is not an error:
    the test card is the last choice."""

    def csi():
        cam = getattr(board_config, "camera", None)  # made on first use
        return CsiSource(landscape(cam)) if cam is not None else None

    def uvc():
        dev = _usb_camera(usb_wait_ms)
        return UvcSource(dev) if dev is not None else None

    return first_source(
        {CSI: csi, UVC: uvc, TESTCARD: lambda: TestCardSource(testcard_path)},
        getattr(board_config, "camera_source", None),
    )


def _usb_camera(wait_ms):
    """A UVC camera on the host port, or None (no host, or nothing plugged in)."""
    try:
        import usb.core
        from usb.host.video import Camera
    except ImportError:
        return None
    usb.core.start(classes=("uvc",))
    deadline = time.ticks_add(time.ticks_ms(), wait_ms)
    while True:
        dev = usb.core.find(custom_match=Camera.match)
        if dev is not None or time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            return dev
        time.sleep_ms(250)
