# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Find and save an app's files on the SD card, then flash, then the data root.

Each kind of file has one folder name, the same in all three places. For
``photos`` on a board that is:

==============  ==============================================
the SD card     ``/sd/photos``
flash           ``/photos`` (``/flash/photos`` on an STM32)
the data root   ``/data/photos`` (``/flash/data/photos`` on an STM32)
==============  ==============================================

An app reads from all three, in that order, and writes to the first one
that takes a file: the card when it's in and mounted for writing, else
flash, else the data root. On a desktop there is no card and no flash, so
the data root's folder is the only place (``~/.local/share/appkit/photos``
on Linux).

Example:
    Mount the card while the app is open, then save and list::

        places.hold_card(scope, write=True)
        folder = places.write_folder("photos")
        songs = places.files("music", (".mp3",))
"""

import os
import sys

from . import data

#: Where the SD card is mounted.
SD = "/sd"

DIR_MODE = 0x4000  # S_IFDIR, in os.stat's mode on every interpreter


def flash_root(platform=None):
    """The top of flash: ``""`` (so ``/photos``), or ``/flash`` on an STM32,
    whose ``/`` only holds mounts."""
    return "/flash" if (platform or sys.platform) == "pyboard" else ""


def folders(name):
    """The folders a kind of file lives in, in the order they're looked at.

    Args:
        name: the folder name, such as ``"photos"``.

    Returns:
        The card's, flash's and the data root's folder on a board; the data
        root's alone on a desktop.
    """
    in_data = data.join(data.root(), name)
    if data.desktop():
        return [in_data]
    return [SD + "/" + name, flash_root() + "/" + name, in_data]


def where_text(name):
    """The folders, for a message: ``/sd/music, /music or /data/music``."""
    places = folders(name)
    if len(places) == 1:
        return places[0]
    return ", ".join(places[:-1]) + " or " + places[-1]


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _is_dir(path):
    try:
        return bool(os.stat(path)[0] & DIR_MODE)
    except OSError:
        return False


def find(name, filename):
    """The first ``<folder>/<filename>`` that exists, or None."""
    for folder in folders(name):
        path = folder + "/" + filename
        if _exists(path):
            return path
    return None


def files(name, extensions, deep=False):
    """Every file of a kind, from all its folders.

    Args:
        name: the folder name, such as ``"music"``.
        extensions: a tuple of lowercase endings with the dot, ``(".mp3",)``.
        deep: look in the folders under them too.

    Returns:
        Full paths: the card's first, then flash's, then the data root's,
        each in name order.
    """
    found = []
    for folder in folders(name):
        found.extend(_scan(folder, extensions, deep))
    return found


def _scan(folder, extensions, deep):
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    found = []
    for n in names:
        path = folder + "/" + n
        if deep and _is_dir(path):
            found.extend(_scan(path, extensions, deep))
        else:
            low = n.lower()
            for ext in extensions:  # MicroPython's endswith takes no tuple
                if low.endswith(ext):
                    found.append(path)
                    break
    return found


def write_folder(name):
    """The first folder a file of this kind can be written in, made if missing.

    That's the card's when it's mounted and writable, else flash's, else the
    data root's.

    Raises:
        OSError: none of them takes a file.
    """
    tried = []
    for folder in folders(name):
        # Never make /sd itself: with no card in, it would be a folder on flash.
        if folder.startswith(SD + "/") and not _exists(SD):
            continue
        try:
            data.makedirs(folder)
            probe = folder + "/.write-test"
            with open(probe, "wb") as f:
                f.write(b"\n")
            os.remove(probe)
            return folder
        except OSError as e:
            tried.append("%s (%s)" % (folder, e))
    raise OSError("nowhere to write %s: %s" % (name, "; ".join(tried) or "no folders"))


def mount_card(write=False):
    """Mount the SD card at `SD`.

    Returns:
        The card, to pass to `unmount_card`; True when something else already
        has it mounted; False when there's no card (the board has no
        ``sdcard`` role, or the card won't mount).
    """
    if data.desktop():
        return False
    if _exists(SD):
        return True  # someone else's mount: leave it
    try:
        import board_peripherals as bp

        card = bp.sdcard()
    except Exception as e:  # noqa: BLE001 - no card role or no card: flash and data still work
        print("no SD card:", e)
        return False
    try:
        os.mount(card, SD, readonly=not write)
    except Exception as e:  # noqa: BLE001
        print("SD card didn't mount:", e)
        try:
            card.deinit()
        except Exception:  # noqa: BLE001
            pass
        return False
    return card


def unmount_card(card):
    """Undo `mount_card`; a mount that wasn't ours is left alone."""
    if card in (True, False, None):
        return
    try:
        os.umount(SD)
    finally:
        card.deinit()


def hold_card(scope, write=False):
    """Mount the card while *scope*'s app is open; returns what `mount_card` did."""
    card = mount_card(write)
    scope.on_close(lambda: unmount_card(card))
    return card
