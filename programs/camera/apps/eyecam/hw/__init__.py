# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The camera app's hardware seams.

The pages never touch hardware. They ask these objects, which come in two
sets with the same methods: ``hw.desktop`` (stand-ins that run anywhere) and
``hw.board`` (the ESP32-P4X-EYE). ``build(scope)`` picks one and returns a
``Hardware`` holding them all.

Preview
    Cut from a source (``hw.sources``): a MIPI-CSI camera, a USB camera or a
    test card, whichever the board has.
    ``frame(magnify)`` -> a 240x240 RGB565 ``bytearray`` (LVGL's byte
    order), the centre of the sensor cropped for zoom 1..4 and scaled, as
    the factory's PPA pass does; the same buffer every call.
    ``source()`` -> ``(buf, w, h)``, the whole latest frame, for photos.
    ``rotate(degrees)`` turns the picture to undo a display rotation.
Photo
    ``take(magnify, resolution, flash)`` -> the saved file's path, or None.
    Backlight off and the flash LED on (if asked) while it runs, as the
    factory does. JPEG quality 90, 1920x1080, 1280x720 or 640x480.
Recorder
    ``start(magnify)``, ``stop()``, ``recording``. ``tick()`` from the frame
    loop adds a frame.
IntervalSleep
    ``wake_reason()`` -> "timer", "button" or None (a normal boot).
    ``sleep(ms, on_wake)``: the board deep-sleeps and boots again; the
    desktop blanks the screen and calls ``on_wake(reason)`` instead.
Storage
    ``mounted()``, ``free()`` (bytes), ``photos()`` (paths, newest first),
    ``next_photo()``, ``next_video()``, ``remove(path)``. On a desktop the
    card is a folder in the app's data folder.
UsbDisk
    ``state``: "instruction" (no host), "connected"; ``on_change(fn)``;
    ``offer()`` puts the card on USB if it isn't yet.
Accel
    ``rotation()`` -> 0, 90, 180 or 270, the side the board is turned to.
Lights
    ``flash(on)``, ``backlight(on)``.
Detector
    ``people(buf, w, h)`` and ``faces(buf, w, h)`` -> boxes
    ``(x0, y0, x1, y1, keypoints)``; ``objects(buf, w, h)`` -> boxes
    ``(x0, y0, x1, y1, name, score)`` for the album's YOLO overlay.
"""

import sys


class Hardware:
    def __init__(self, **parts):
        for k, v in parts.items():
            setattr(self, k, v)


def on_board():
    return sys.platform not in ("linux", "darwin", "win32", "webassembly")


def build(scope):
    """All the seams for wherever this runs."""
    if on_board():
        from . import board as impl
    else:
        from . import desktop as impl
    return impl.build(scope)
