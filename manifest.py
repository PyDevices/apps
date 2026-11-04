# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""applibs as a MicroPython manifest: freeze every shared library in lib/.

Each folder in ``lib/`` is one top-level package, so a board imports
``controlkit``, ``songmodel`` and the rest under their own names, exactly as
after a ``mip`` install. The list is read from ``lib/`` itself, so a new
shared folder is included without anyone editing this file.

From a firmware's manifest::

    include("path/to/apps")

Apps (``apps/``) are not frozen here: they are programs, not libraries.
Examples, tests, docs and each folder's own ``manifest.py`` are left out.
"""

import os

if 0:

    def package(*args, **kwargs):
        pass


_LEFT_OUT = ("__pycache__", "build", "docs", "examples", "tests")


def _sources(name):
    root = os.path.join("lib", name)
    found = []
    for path, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in _LEFT_OUT and not d.endswith(".egg-info"))
        rel = os.path.relpath(path, root)
        for f in sorted(files):
            if f.endswith(".py") and f != "manifest.py":
                found.append(f if rel == "." else os.path.join(rel, f))
    return found


for _name in sorted(os.listdir("lib")):
    if _name.startswith(".") or _name in _LEFT_OUT:
        continue
    if os.path.isdir(os.path.join("lib", _name)):
        package(_name, files=_sources(_name), base_path="lib", opt=3)  # type: ignore[name-defined]  # noqa: PGH003
