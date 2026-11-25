# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Import every module of every installed app, and fail if one doesn't load.

    pip install "./apps"                  # the apps and everything they need
    python tools/import_every_app.py      # every module of every app

Every app has to load on every Python, whether or not it can run there. An app
that needs something this Python lacks (a ``machine`` module, a USB device
port, an MP3 decoder) imports what it needs inside ``main()`` and says so on
its screen with ``touchkit.ui.missing``, which offers to hide it from Home.
An import that fails here is a missing dependency in ``tools/app_packages.py``,
or an app that reaches for hardware at import time.

A script app (one whose ``app.json`` has ``"script"``) runs when it's imported,
so this imports its modules with its folder on the path, as the launcher does.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from pathlib import Path

SKIP_DIRS = {"__pycache__", "docs", "examples", "studies", "tests", "tools"}
SKIP_FILES = {"__init__.py", "main.py", "manifest.py"}


def modules(folder: Path, dotted: str) -> list[str]:
    """Every module and subpackage under *folder*, as dotted names."""
    found = []
    for entry in sorted(folder.iterdir()):
        if entry.suffix == ".py" and entry.name not in SKIP_FILES:
            found.append(f"{dotted}.{entry.stem}")
        elif entry.is_dir() and entry.name not in SKIP_DIRS and (entry / "__init__.py").is_file():
            found.append(f"{dotted}.{entry.name}")
            found.extend(modules(entry, f"{dotted}.{entry.name}"))
    return found


def import_all(root: Path, package: str) -> list[str]:
    """Import every app's modules; return one line for each that failed."""
    failures = []
    count = 0
    for app in sorted(path for path in root.iterdir() if (path / "app.json").is_file()):
        script = "script" in json.loads((app / "app.json").read_text(encoding="utf-8"))
        if script:
            sys.path.insert(0, str(app))
            names = [name.split(".", 1)[1] for name in modules(app, "x")]
        else:
            names = [f"{package}.{app.name}", *modules(app, f"{package}.{app.name}")]
        for name in names:
            count += 1
            try:
                __import__(name)
            except BaseException as error:  # an app may raise anything, SystemExit included
                failures.append(f"{name}: {type(error).__name__}: {error}")
        if script:
            sys.path.remove(str(app))
            for name in names:
                sys.modules.pop(name, None)
        gc.collect()
    print(f"{count} modules imported from {root}, {len(failures)} failed")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", default="apps", help="the installed apps package (default: apps)")
    args = parser.parse_args()
    root = Path(__import__(args.package).__file__).parent
    failures = import_all(root, args.package)
    for line in failures:
        print("FAIL", line)
    # Some apps start threads when they're imported, and Python would wait on
    # them at exit, so this leaves at once.
    sys.stdout.flush()
    os._exit(1 if failures else 0)


if __name__ == "__main__":
    main()
