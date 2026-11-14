# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Write each app's package.json, so one line installs an app on a board.

    python tools/app_packages.py           # write every package.json
    python tools/app_packages.py --check   # fail if one is out of date

On the board, ``omip.install("github:PyDevices/apps/apps/<name>")`` then puts
the app's files in ``/apps/<name>``, where Home finds them, and what it imports
from the OmniPython index, micropython-lib or another repository in ``/lib``.

A program whose ``apps`` folder holds one app (``programs/camera`` holds
eyecam) gets a package.json of its own, so
``omip.install("github:PyDevices/apps/programs/<program>")`` installs that app
the same way. The program's other files, such as its ``main.py``, are left to
lines of their own.

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
PROGRAMS = os.path.join(ROOT, "programs")
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
    "mp4mux": "mp4mux",
    "palettes": "palettes",
    "programkit": "programkit",
    "pygraphics": "pygraphics",
    "sayso": "sayso",
    "songmodel": "songmodel",
    "soundmodule": "soundmodule",
    "spectrum": "spectrum",
    "touchkit": "touchkit",
}

#: A module of an index package -> an index package it needs that the package
#: itself leaves optional. The instrument and effect panels draw with controlkit,
#: and load without it until a panel is built.
OPTIONAL = {
    "audioeffects.panel_view": "controlkit",
    "audioinstruments.panel_view": "controlkit",
}

#: Import name -> a package.json in another repository, at its main branch.
ELSEWHERE = {
    "castdisplay": "github:PyDevices/pydevices/packages/castdisplay",
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
    "errno", "esp32", "espdl", "framebuf", "gc", "h264enc", "image", "jpegio", "json", "lvgl", "machine",
    "math", "mdns", "micropython", "microcontroller", "network", "numpy", "os", "platform", "ppa", "random",
    "scipy", "select", "socket", "struct", "synthio", "sys", "tflite", "time", "uasyncio", "uctypes", "ulab",
    "usb",
}

#: What isn't installed from an app's folder.
SKIP_DIRS = {"tests", "docs", "__pycache__"}
#: Home's main.py goes to the board's root, with a line of its own.
SKIP_FILES = {"package.json", "AGENTS.md", "README.md", "main.py"}


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


def imported(paths, dotted=False):
    """The top-level names the Python files in *paths* import, leaving out
    relative imports. With *dotted*, every module named in full as well:
    ``from a import b`` gives ``a`` and ``a.b``."""
    names = set()
    for path in paths:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name if dotted else alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if dotted:
                    names.add(node.module)
                    names.update(node.module + "." + alias.name for alias in node.names)
                else:
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


def needs(folder):
    """``(deps, upstream)`` for the app in *folder*, as package.json lists them."""
    local = {path.split("/")[0].rpartition(".py")[0] or path.split("/")[0] for path in app_files(folder)}
    index, elsewhere, upstream, unknown = set(), set(), set(), set()
    for module in imported(python_files(folder)):
        if module in local or module in BOARD or module in FIRMWARE:
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
    for module in imported(python_files(folder), dotted=True):
        if module in OPTIONAL:
            index.add(OPTIONAL[module])
    if unknown:
        raise SystemExit(
            "%s imports %s, which tools/app_packages.py doesn't know: add each to INDEX, "
            "ELSEWHERE, UPSTREAM, BOARD or FIRMWARE" % (os.path.relpath(folder, ROOT), ", ".join(sorted(unknown)))
        )
    closure = set()
    for package in sorted(index):
        closure.add(package)
    for package in sorted(index):
        lib_needs(package, closure)
    deps = [[package, "latest"] for package in sorted(closure)]
    deps += [[url, "main"] for url in sorted(elsewhere)]
    return deps, [[package, "latest"] for package in sorted(upstream)]


def render(folder, prefix=""):
    """The text of the package.json for the app in *folder*. *prefix* is the
    app's folder as seen from the package.json, when that sits higher up."""
    name = os.path.basename(folder)
    with open(os.path.join(folder, "app.json"), encoding="utf-8") as f:
        info = json.load(f)
    deps, upstream = needs(folder)
    body = {
        "description": "%s, an app for Home" % info.get("title", name),
        "target": "apps/" + name,
        "urls": [[path, prefix + path] for path in app_files(folder)],
        "deps": deps,
    }
    if upstream:
        body["upstream"] = upstream
    body["generated"] = "by tools/app_packages.py from the app's folder; edit the app, not this"
    return json.dumps(body, indent=2) + "\n"


def apps():
    return sorted(e for e in os.listdir(APPS) if os.path.isfile(os.path.join(APPS, e, "app.json")))


def program_app(program):
    """The one app in program *program*'s ``apps`` folder, or None when it has none.

    A program with two would need a package.json for each, which nothing
    installs yet, so it stops the script.
    """
    folder = os.path.join(PROGRAMS, program, "apps")
    if not os.path.isdir(folder):
        return None
    found = sorted(e for e in os.listdir(folder) if os.path.isfile(os.path.join(folder, e, "app.json")))
    if len(found) > 1:
        raise SystemExit("programs/%s/apps holds %s: one package.json installs one app" % (program, ", ".join(found)))
    return found[0] if found else None


def packages():
    """``(package.json path, its text)`` for each app here and each program that holds one."""
    out = []
    for name in apps():
        out.append((os.path.join(APPS, name, "package.json"), render(os.path.join(APPS, name))))
    for program in sorted(os.listdir(PROGRAMS)):
        name = program_app(program)
        if name is not None:
            folder = os.path.join(PROGRAMS, program, "apps", name)
            out.append((os.path.join(PROGRAMS, program, "package.json"), render(folder, "apps/%s/" % name)))
    return out


def main(argv):
    check = "--check" in argv
    stale = []
    wanted = packages()
    for path, text in wanted:
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
    paths = [path for path, _ in wanted]
    for top in (APPS, PROGRAMS):
        for entry in os.listdir(top):
            orphan = os.path.join(top, entry, "package.json")
            if orphan not in paths and os.path.isfile(orphan):
                stale.append(orphan + " (no app for it)")
    if stale:
        sys.exit(
            "out of date: %s\nRun python tools/app_packages.py and commit the result."
            % ", ".join(os.path.relpath(p, ROOT) for p in stale)
        )


if __name__ == "__main__":
    main(sys.argv[1:])
