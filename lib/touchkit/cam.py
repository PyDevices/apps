# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit.cam -- what the camera apps share: opening the CSI camera, its
settings, and where photos go.

Flip, mirror, light and brightness are the Camera app's, kept in its
``scope.store()`` while the board stays up, so Security, Detect and Cast
see the camera as Camera left it. Photos are in a ``photos`` folder
(`appkit.places`): ``/sd/photos`` on the card, ``/photos`` on flash and
``/data/photos``. They're read from all three and saved to the first that
takes a file.
"""

import os

from appkit import data, places

# The whole sensor, 2x2 binned: Flip and Mirror show the same picture turned
# over (the 800x800 default is a window, and reads a different patch when
# turned), and binning halves the grain in a dim room. The default if not.
FORMAT = "MIPI_2lane_24Minput_RAW10_1280x960_binning_45fps"
# Brightness: the driver's "exposure" is the auto exposure's target, not a
# shutter time; cameraif takes it as a percent of the driver's 2-235. The
# camera starts at a target of 140, which is 59%.
BRIGHT = 59
# Light: the auto exposure's gain ceiling (OV5647 0x3A18/0x3A19). In a dim
# room the gain sits at the ceiling, so raising it is what brightens the
# picture, with more grain. A middle step (0x1F8) made the auto exposure
# hunt: the picture flickered.
LIGHT = (("Normal", 0x0F8), ("Night", 0x3F8))
PHOTOS = "photos"  # the folder name, on the card, flash and the data root


class NoCameraPort(OSError):
    """The board has no CSI camera port at all (a desktop, say), as opposed
    to a port with no camera on it."""


def no_camera_text(err, app):
    """What *app* shows when `open_camera` raised *err*."""
    if isinstance(err, NoCameraPort):
        here = "computer" if data.desktop() else "board"
        return "No camera: %s\n\n%s needs the board's CSI camera, which this %s doesn't have." % (err, app, here)
    return "No camera: %s\n\nConnect one to the CSI port, then open %s again." % (err, app)


def options(scope):
    """The camera settings the camera apps share: the Camera app's store."""
    opts = scope.store("camera")
    for k, v in (("light", 0), ("flip", False), ("mirror", False), ("bright", BRIGHT)):
        opts.setdefault(k, v)
    return opts


def open_camera(opts):
    """The CSI camera, turned as *opts* say, with its colour order right.

    Raises when the board has no camera, or it doesn't answer: an app shows
    that and carries on without one.
    """
    import board_peripherals as bp

    if not hasattr(bp, "camera"):
        raise NoCameraPort("board_peripherals has no camera role")
    # cameraif writes both at open and picks the ISP's colour order from them
    # (every OV5647 mode opens mirrored unless told otherwise).
    kw = {"flip": opts["flip"], "mirror": opts["mirror"]}
    try:
        return bp.camera(format=FORMAT, **kw)
    except Exception as e:
        # A sensor without the binned mode takes the default one; with no
        # sensor at all this raises again, below.
        print("camera: %s: %s; the default format instead" % (FORMAT, e))
        return bp.camera(**kw)


def apply_controls(c, opts):
    """Brightness and the light level (the AE target, the gain ceiling)."""
    ceiling = LIGHT[opts["light"] % len(LIGHT)][1]
    try:
        c.exposure(opts["bright"])
        c.reg(0x3A18, ceiling >> 8)
        c.reg(0x3A19, ceiling & 0xFF)
    except Exception as e:
        print("camera: controls:", e)


def preview_size(cam, longest):
    """The preview's ``(width, height)``, its longer side *longest*."""
    cw, ch = cam.size()[:2]
    return (longest, longest * ch // cw) if cw >= ch else (longest * cw // ch, longest)


def mount_sd(readonly=True):
    """Mount the SD card at ``/sd``: `appkit.places.mount_card`, for the camera apps."""
    return places.mount_card(write=not readonly)


def unmount_sd(card):
    places.unmount_card(card)


#: Where a photo is, in its key: the card, flash or the data root.
TAGS = ("card", "flash", "data")


def _tagged():
    folders = places.folders(PHOTOS)
    return list(zip(TAGS[-len(folders):], folders))  # a desktop has the data root alone


def photos(scope=None):
    """``[(key, path)]`` of every photo, newest name first. The key says
    where it lives (``card/IMG_0001.jpg``, ``flash/...``, ``data/...``), so
    the same name in two places is two photos."""
    out = []
    for tag, d in _tagged():
        try:
            for f in os.listdir(d):
                if f.lower().endswith(".jpg"):
                    out.append((tag + "/" + f, d + "/" + f))
        except OSError:
            pass
    out.sort(key=lambda kp: (kp[0].rsplit("/", 1)[1], kp[0]), reverse=True)
    return out


def next_name(scope=None):
    """A new photo's path, in `places.write_folder` (the card when it's
    mounted for writing): numbered after the highest ``IMG_`` anywhere, so a
    name means one photo. OSError when there's nowhere to write."""
    folder = places.write_folder(PHOTOS)
    n = 0
    for _, d in _tagged():
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for f in names:
            if f.startswith("IMG_") and f.endswith(".jpg"):
                try:
                    n = max(n, int(f[4:8]))
                except ValueError:
                    pass
    return "%s/IMG_%04d.jpg" % (folder, n + 1)
