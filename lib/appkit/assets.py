# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Read the files an app keeps beside its code, whether it's installed or frozen.

An app finds its own files from its ``__file__``, as Backline does its songs::

    from appkit import assets

    here = __file__.replace("\\\\", "/")
    SONGS = here[: here.rfind("/")] + "/songs"
    for name in assets.listdir(SONGS):
        text = assets.read(SONGS + "/" + name)

Where the app is in ``/apps``, these are the files there. Where it is frozen
into the firmware, a freeze can't carry files, so ``appkit.index`` froze
them as bytes in ``_appkit_files``, and these read them from there.
"""

import os

#: The package frozen apps are in (see ``appkit.index``).
PACKAGE = "frozen_apps"

_files = None


def _frozen():
    """The frozen apps' files, ``{path: bytes}``; empty when there are none."""
    global _files
    if _files is None:
        try:
            import _appkit_files

            _files = _appkit_files.FILES
        except ImportError:
            _files = {}
    return _files


def _key(path):
    """*path* as ``_appkit_files`` names it, from the frozen package's name on, or None."""
    path = path.replace("\\", "/")
    i = path.find(PACKAGE + "/")
    if i < 0 or (i > 0 and path[i - 1] != "/"):
        return None
    return path[i:]


def read(path, binary=False):
    """The contents of the file at *path*: text, or bytes with *binary*.

    Raises:
        OSError: There is no such file, on the filesystem or frozen.
    """
    try:
        with open(path, "rb" if binary else "r") as f:
            return f.read()
    except OSError:
        key = _key(path)
        data = _frozen().get(key) if key else None
        if data is None:
            raise
    return data if binary else data.decode()


def listdir(folder):
    """The names in *folder*, sorted: on the filesystem, or frozen.

    Raises:
        OSError: There is no such folder, on the filesystem or frozen.
    """
    try:
        return sorted(os.listdir(folder))
    except OSError:
        key = _key(folder)
        if key:
            prefix = key.rstrip("/") + "/"
            names = set()
            for path in _frozen():
                if path.startswith(prefix):
                    names.add(path[len(prefix) :].split("/")[0])
            if names:
                return sorted(names)
        raise
