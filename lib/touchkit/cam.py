# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit.cam -- what the camera apps share: opening the CSI camera, its
settings, and where photos go.

Flip, mirror, light and brightness are the Camera app's, kept in its
``scope.store()`` while the board stays up, so Security, Detect and Cast
see the camera as Camera left it. Photos go to the Camera app's data
folder (``/data/camera/photos`` on the board); the SD card's
``/sd/photos`` is only read.
"""

import os

from appkit import data

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
SD_PHOTOS = "/sd/photos"


class NoCameraPort(OSError):
    """The board has no CSI camera port at all (a desktop, say), as opposed
    to a port with no camera on it."""


def no_camera_text(err, app):
    """What *app* shows when :func:`open_camera` raised *err*."""
    if isinstance(err, NoCameraPort):
        return "No camera: %s\n\n%s needs the board's CSI camera, which this computer doesn't have." % (err, app)
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


def photos_dir(scope):
    """The flash folder photos go to, in the Camera app's data folder, made
    if missing. *scope* is the asking app's (any of the camera apps)."""
    return data.makedirs(data.join(scope.data_dir_of("camera"), "photos"))


def mount_sd(readonly=True):
    """Mount the SD card at ``/sd``: the card object (unmount it with
    :func:`unmount_sd`), True when someone else has it mounted, or False
    without a card."""
    try:
        os.stat("/sd")
        return True  # someone else's mount
    except OSError:
        pass
    try:
        import board_peripherals as bp

        card = bp.sdcard()
        os.mount(card, "/sd", readonly=readonly)
        return card
    except Exception as e:
        print("camera: no SD card:", e)
        return False


def unmount_sd(card):
    if card in (True, False, None):
        return  # not ours
    try:
        os.umount("/sd")
    finally:
        card.deinit()


def photos(scope):
    """``[(key, path)]`` of every photo, newest name first. The key says
    where it lives (``flash/IMG_0001.jpg``, ``card/...``), so the same name
    in both places is two photos."""
    out = []
    for d, tag in ((SD_PHOTOS, "card"), (photos_dir(scope), "flash")):
        try:
            for f in os.listdir(d):
                if f.endswith(".jpg"):
                    out.append((tag + "/" + f, d + "/" + f))
        except OSError:
            pass
    out.sort(key=lambda kp: (kp[0].rsplit("/", 1)[1], kp[0]), reverse=True)
    return out


def next_name(scope):
    """A new photo's path: numbered after the highest on the card or in
    flash, so a name means one photo."""
    folder = photos_dir(scope)
    n = 0
    for d in (SD_PHOTOS, folder):
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
