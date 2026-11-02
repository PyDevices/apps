# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Which SoundFonts the midiEngine can play: ``$SOUNDFONT`` alone when it
is set, else every ``.sf2`` in the folders below, each folder's in name
order. On a desktop the folder is ``~/soundfonts``
(``%USERPROFILE%\\soundfonts`` on Windows); on a board ``/sd/soundfonts``
(the card, mounted while the app is open) and then ``/soundfonts`` on
flash. With more than one, the app asks which.

No LVGL here, so the contract runs it on CPython and MicroPython alike.
"""

import os
import sys

#: A computer rather than a board: CPython, or MicroPython on a desktop
#: operating system (micropython.exe, the unix port); appkit.data's test.
DESKTOP = sys.implementation.name == "cpython" or sys.platform in (
    "linux", "darwin", "win32", "cygwin", "freebsd", "openbsd", "netbsd")
SD_SOUNDFONTS = "/sd/soundfonts"
FLASH_SOUNDFONTS = "/soundfonts"


def getenv(name):
    fn = getattr(os, "getenv", None)
    return fn(name) if fn is not None else None


def home():
    """A desktop user's folder, with forward slashes (``%USERPROFILE%``,
    else ``$HOME``): ``os.path.expanduser`` isn't in MicroPython."""
    return (getenv("USERPROFILE") or getenv("HOME") or "").replace("\\", "/")


def folders(desktop):
    """Where to look, in order."""
    if desktop:
        return [home() + "/soundfonts"]
    return [SD_SOUNDFONTS, FLASH_SOUNDFONTS]


def size_of(path):
    try:
        return os.stat(path)[6]
    except OSError:
        return None


def candidates(where, env=None):
    """``[(path, bytes)]``: ``[env]`` alone when it is set (asked for by
    name, so never a choice), else every ``.sf2`` in the folders *where*.
    A folder that isn't there is skipped; bytes is None when the file
    can't be read."""
    if env:
        return [(env, size_of(env))]
    found = []
    for folder in where:
        try:
            names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".sf2"))
        except OSError:
            continue
        for n in names:
            path = folder + "/" + n
            found.append((path, size_of(path)))
    return found


def name_of(path):
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]


def mb_text(size):
    if size is None:
        return "?"
    return "%.1f MB" % (size / 1048576)
