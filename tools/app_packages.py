# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Write each app's package.json, so one line installs an app on a board.

    python tools/app_packages.py           # write apps/*/package.json
    python tools/app_packages.py --check   # fail if one is out of date

On the board, ``omip.install("github:PyDevices/apps/apps/<name>")`` then puts
the app's files in ``/apps/<name>``, where Home finds them, and what it imports
from the OmniPython index, micropython-lib or another repository in ``/lib``.

What an app needs is read from its imports, and from the imports of this
repository's libraries it uses. Every name an app imports has to be known
below: from an index, from the firmware or the board config, or one of the
app's own modules. A new name stops the script until it's added to a table.
"""

import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS = os.path.join(ROOT, "apps")
LIB = os.path.join(ROOT, "lib")

#: Import name -> package on the OmniPython index.
INDEX = {
    "appkit": "appkit",
    "audioeffects": "audioeffects",
    "audioinstruments": "audioinstruments",
    "bledev": "bledev",
    "controlkit": "controlkit",
    "deskkit": "deskkit",
    "hmilink": "hmilink",
    "iconkit": "iconkit",
    "medialink": "medialink",
    "midiports": "midiports",
    "palettes": "palettes",
    "programkit": "programkit",
    "pygraphics": "pygraphics",
    "sayso": "sayso",
    "songmodel": "songmodel",
    "soundmodule": "soundmodule",
    "spectrum": "spectrum",
    "touchkit": "touchkit",
}

#: Import name -> a package.json in another repository, at its main branch.
ELSEWHERE = {
    "vtterm": "github:PyDevices/pydevices/packages/vtterm",
}

#: Import name -> package on micropython-lib. omip skips it where the firmware
#: has it frozen in, and on CircuitPython.
UPSTREAM = {
    "requests": "requests",
}

#: pydevices, which every board config installs, and the board config itself.
BOARD = {
    "appdev", "audiodev", "backends", "board_config", "board_peripherals", "boarddev", "display_driver",
    "displaydev", "events", "keys", "multimer", "orientation", "wifi", "wifi_manager",
}

#: The interpreter's own modules and the firmware's C modules. An app that
#: imports an optional one says so on the screen when it's missing.
FIRMWARE = {
    "_audioif", "_thread", "array", "asyncio", "audioairwindows", "audiobiquad", "audiobusio", "audiocore",
    "audiofeatures", "audiomixer", "audiomp3", "audiopump", "audiospeed", "cameraif", "castif", "earful",
    "errno", "esp32", "espdl", "gc", "image", "json", "lvgl", "machine", "math", "mdns", "micropython",
    "microcontroller", "network", "numpy", "os", "platform", "random", "scipy", "select", "socket", "struct",
    "synthio", "sys", "tflite", "time", "uasyncio", "uctypes", "ulab", "usb",
}

#: Optional modules no package carries yet: Cast's HLS and cast-receiver modes.
UNPACKAGED = {"cast_display", "hls_display"}

#: What isn't installed from an app's folder.
SKIP_DIRS = {"tests", "docs", "__pycache__"}
SKIP_FILES = {"package.json", "AGENTS.md", "README.md"}


def app_files(folder):
    """The files an app's folder installs, as paths inside it, sorted."""
    out = []
    for here, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in files:
            if name in SKIP_FILES or name.endswith((".md", ".pyc")):
                continue
            out.append(os.path.relpath(os.path.join(here, name), folder).replace(os.sep, "/"))
    return sorted(out)


def imported(paths):
    """The top-level names the Python files in *paths* import, leaving out relative imports."""
    names = set()
    for path in paths:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def python_files(folder):
    out = []
    for here, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != "examples"]
        out.extend(os.path.join(here, name) for name in files if name.endswith(".py"))
    return sorted(out)


def lib_needs(name, seen):
    """Add to *seen* the index packages this repository's library *name* imports, and theirs."""
    if not os.path.isdir(os.path.join(LIB, name)):
        return
    for other in imported(python_files(os.path.join(LIB, name))):
        if other in INDEX and INDEX[other] not in seen:
            seen.add(INDEX[other])
            lib_needs(other, seen)


def needs(name):
    """``(deps, upstream)`` for app *name*, as package.json lists them."""
    folder = os.path.join(APPS, name)
    local = {path.split("/")[0].rpartition(".py")[0] or path.split("/")[0] for path in app_files(folder)}
    index, elsewhere, upstream, unknown = set(), set(), set(), set()
    for module in imported(python_files(folder)):
        if module in local or module in BOARD or module in FIRMWARE or module in UNPACKAGED:
            continue
        if module == "apps":
            continue  # another app, which Home brings up on its own
        if module in INDEX:
            index.add(INDEX[module])
        elif module in ELSEWHERE:
            elsewhere.add(ELSEWHERE[module])
        elif module in UPSTREAM:
            upstream.add(UPSTREAM[module])
        else:
            unknown.add(module)
    if unknown:
        raise SystemExit(
            "apps/%s imports %s, which tools/app_packages.py doesn't know: add each to INDEX, "
            "ELSEWHERE, UPSTREAM, BOARD or FIRMWARE" % (name, ", ".join(sorted(unknown)))
        )
    closure = set()
    for package in sorted(index):
        closure.add(package)
    for package in sorted(index):
        lib_needs(package, closure)
    deps = [[package, "latest"] for package in sorted(closure)]
    deps += [[url, "main"] for url in sorted(elsewhere)]
    return deps, [[package, "latest"] for package in sorted(upstream)]


def render(name):
    """The text of app *name*'s package.json."""
    folder = os.path.join(APPS, name)
    with open(os.path.join(folder, "app.json"), encoding="utf-8") as f:
        info = json.load(f)
    deps, upstream = needs(name)
    body = {
        "description": "%s, an app for Home" % info.get("title", name),
        "target": "apps/" + name,
        "urls": [[path, path] for path in app_files(folder)],
        "deps": deps,
    }
    if upstream:
        body["upstream"] = upstream
    body["generated"] = "by tools/app_packages.py from the app's folder; edit the app, not this"
    return json.dumps(body, indent=2) + "\n"


def apps():
    return sorted(e for e in os.listdir(APPS) if os.path.isfile(os.path.join(APPS, e, "app.json")))


def main(argv):
    check = "--check" in argv
    stale = []
    for name in apps():
        path = os.path.join(APPS, name, "package.json")
        text = render(name)
        try:
            with open(path, encoding="utf-8") as f:
                current = f.read()
        except OSError:
            current = None
        if current == text:
            continue
        if check:
            stale.append(path)
        else:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print("wrote", os.path.relpath(path, ROOT))
    for entry in os.listdir(APPS):
        orphan = os.path.join(APPS, entry, "package.json")
        if entry not in apps() and os.path.isfile(orphan):
            stale.append(orphan + " (no app.json beside it)")
    if stale:
        sys.exit(
            "out of date: %s\nRun python tools/app_packages.py and commit the result."
            % ", ".join(os.path.relpath(p, ROOT) for p in stale)
        )


if __name__ == "__main__":
    main(sys.argv[1:])
