# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Write each app's package.json, so one line installs an app on a board.

    python tools/app_packages.py           # write every package.json
    python tools/app_packages.py --check   # fail if one is out of date
    python tools/app_packages.py --check --omnipython ../omnipython
                                           # and if omnipython-desktop leaves out a package the apps need

On the board, ``omip.install("github:PyDevices/apps/apps/<name>")`` then puts
the app's files in ``/apps/<name>``, where Home finds them, and what it imports
from the OmniPython index, micropython-lib or another repository in ``/lib``.

A program whose ``apps`` folder holds one app (``programs/camera`` holds
eyecam) gets a package.json of its own, so
``omip.install("github:PyDevices/apps/programs/<program>")`` installs that app
the same way. The program's other files, such as its ``main.py``, are left to
lines of their own.

An app that imports from another app (``from ..perch import stage``) installs
that app as well.

Two more files install every app at once, both from the main branch:
``apps/package.json``, the bundle, so ``omip.install("github:PyDevices/apps/apps")``
puts every app in ``/apps``, and ``apps/pyproject.toml``, so
``pip install "omnipython-apps @ git+https://github.com/PyDevices/apps#subdirectory=apps"``
installs them as the package ``apps``, with the libraries from the same branch.

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

#: This repository's libraries: every folder in lib/ with an __init__.py. The
#: index publishes them all as one package, applibs, so an app that imports any
#: of them installs that.
LIBS = sorted(
    name for name in os.listdir(LIB) if os.path.isfile(os.path.join(LIB, name, "__init__.py"))
)
APPLIBS = "applibs"

#: Import name -> package on the OmniPython index, besides this repository's libraries.
INDEX = {
    "audioeffects": "audioeffects",
    "audioinstruments": "audioinstruments",
    "bledev": "bledev",
    "endpointkit": "endpointkit",
    "icons": "icons",
    "midiports": "midiports",
    "palettes": "palettes",
    "pygraphics": "pygraphics",
}

#: A module of an index package -> an index package it needs that the package
#: itself leaves optional. The instrument and effect panels draw with controlkit,
#: and load without it until a panel is built.
OPTIONAL = {
    "audioeffects.panel_view": "controlkit",
    "audioinstruments.panel_view": "controlkit",
}

#: This repository's library -> index packages it imports only where they're
#: installed, which an app that uses the library doesn't install for it.
#: appkit's connections lists a computer's MIDI ports where midiports is there.
WHERE_INSTALLED = {
    "appkit": {"midiports"},
}

#: Import name -> a package.json in another repository, at its main branch.
ELSEWHERE = {
    "castdisplay": "github:PyDevices/omnipython/packages/castdisplay",
    "vtterm": "github:PyDevices/omnipython/packages/vtterm",
}

#: Import name -> package on micropython-lib. omip skips it where the firmware
#: has it frozen in, and on CircuitPython.
UPSTREAM = {
    "requests": "requests",
}

#: A module of omnipython -> the micropython-lib package it runs over, which
#: omnipython leaves to the firmware: usb_hid is CircuitPython's usb_hid over
#: usb-device-hid. omip skips it where the firmware has it frozen in, and on
#: CircuitPython, whose usb_hid is built in.
BOARD_UPSTREAM = {
    "usb_hid": "usb-device-hid",
}

#: A library here -> what it needs over HTTP (see appkit.net): requests from
#: micropython-lib on MicroPython, and on CircuitPython adafruit_requests from
#: Adafruit's library bundle, since CircuitPython's core has no HTTP client.
#: omip skips the first where the firmware has it frozen in, and reads the
#: second only on CircuitPython.
HTTP = {
    "deskkit": (("requests",), ("adafruit_requests",)),
    "sayso": (("requests",), ("adafruit_requests",)),
}

#: omnipython, which every board config installs, and the board config itself.
BOARD = {
    "appdev", "audiodev", "backends", "board_config", "board_peripherals", "boarddev", "display_driver",
    "displaydev", "events", "hmilink", "keys", "medialink", "mp4mux", "multimer", "orientation", "usb_hid",
    "wifi", "wifi_manager",
}

#: The interpreter's own modules and the firmware's C modules. An app that
#: imports an optional one says so on the screen when it's missing.
FIRMWARE = {
    "_audioif", "_thread", "_usbhost", "array", "asyncio", "audioairwindows", "audiobiquad", "audiobusio", "audiocore",
    "audiofeatures", "audiomixer", "btclassic", "audiomp3", "audiopump", "audiosampler", "audiospeed", "cameraif", "castif", "earful",
    "errno", "esp32", "espdl", "framebuf", "gc", "h264enc", "icons", "image", "jpegio", "json", "lvgl", "machine",
    "math", "mdns", "micropython", "microcontroller", "network", "numpy", "offheap", "os", "platform", "ppa", "random",
    "scipy", "select", "socket", "ssl", "struct", "svgio", "synthio", "sys", "tflite", "time", "uasyncio", "uctypes", "ulab",
    "usb",
}

#: What isn't installed from an app's folder.
#: Folders an app keeps beside its code that a board has no use for.
SKIP_DIRS = {"tests", "docs", "tools", "studies", "__pycache__"}
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


def sibling_apps(paths):
    """The other apps the Python files in *paths* import from, as ``from ..perch import stage`` does."""
    names = set()
    for path in paths:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 2:
                names.update([node.module.split(".")[0]] if node.module else [alias.name for alias in node.names])
    return names


def python_files(folder):
    out = []
    for here, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != "examples"]
        out.extend(os.path.join(here, name) for name in files if name.endswith(".py"))
    return sorted(out)


def lib_needs(name, seen):
    """Add to *seen* what this repository's library *name* imports: index
    packages, and libraries here (by their own names), and theirs."""
    if name not in LIBS:
        return
    for other in imported(python_files(os.path.join(LIB, name))):
        if other in WHERE_INSTALLED.get(name, ()):
            continue
        if other in LIBS and other not in seen:
            seen.add(other)
            lib_needs(other, seen)
        elif other in INDEX and INDEX[other] not in seen:
            seen.add(INDEX[other])


def needs(folder):
    """``(deps, upstream, circuitpython)`` for the app in *folder*, as package.json lists them."""
    local = {path.split("/")[0].rpartition(".py")[0] or path.split("/")[0] for path in app_files(folder)}
    index, elsewhere, upstream, unknown = set(), set(), set(), set()
    for module in imported(python_files(folder)):
        if module in BOARD_UPSTREAM:
            upstream.add(BOARD_UPSTREAM[module])
        if module in local or module in BOARD or module in FIRMWARE:
            continue
        if module == "apps":
            continue  # another app, which Home brings up on its own
        if module in LIBS:
            index.add(module)
        elif module in INDEX:
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
    # closure names this repository's libraries one by one; they install as applibs.
    packages = {APPLIBS if package in LIBS else package for package in closure}
    deps = [[package, "latest"] for package in sorted(packages)]
    deps += [[url, "main"] for url in sorted(elsewhere)]
    # an app that draws with another's modules installs that app too
    top = [os.path.join(folder, name) for name in os.listdir(folder) if name.endswith(".py")]
    for other in sorted(sibling_apps(top)):
        if not os.path.isfile(os.path.join(APPS, other, "app.json")):
            raise SystemExit("%s imports from ..%s, which isn't an app here" % (os.path.relpath(folder, ROOT), other))
        deps.append(["github:PyDevices/apps/apps/" + other, "main"])
    for package in closure:
        upstream.update(HTTP.get(package, ((), ()))[0])
    bundle = sorted({name for package in closure for name in HTTP.get(package, ((), ()))[1]})
    return deps, [[package, "latest"] for package in sorted(upstream)], [[name, "latest"] for name in bundle]


def render(folder, prefix=""):
    """The text of the package.json for the app in *folder*. *prefix* is the
    app's folder as seen from the package.json, when that sits higher up."""
    name = os.path.basename(folder)
    with open(os.path.join(folder, "app.json"), encoding="utf-8") as f:
        info = json.load(f)
    deps, upstream, circuitpython = needs(folder)
    body = {
        "description": "%s, an app for Home" % info.get("title", name),
        "target": "apps/" + name,
        "urls": [[path, prefix + path] for path in app_files(folder)],
        "deps": deps,
    }
    if upstream:
        body["upstream"] = upstream
    if circuitpython:
        body["circuitpython"] = circuitpython
    body["generated"] = "by tools/app_packages.py from the app's folder; edit the app, not this"
    return json.dumps(body, indent=2) + "\n"


#: Where pip takes the libraries from: the same branch as the apps.
APPLIBS_URL = "omnipython-applibs[apps] @ git+https://github.com/PyDevices/apps"

#: The omnipython packages pip users get inside omnipython-desktop. ``--check
#: --omnipython <checkout>`` fails when that checkout's mip-split.toml doesn't
#: mark one of them ``pypi-desktop``, so an app can't need one the wheel leaves out.
#: 0.8.1.dev9 is the first release with hmilink, mp4mux, castdisplay and vtterm.
DESKTOP = "omnipython-desktop>=0.8.1.dev9"
IN_DESKTOP = ("castdisplay", "endpointkit", "hmilink", "icons", "midiports", "mp4mux", "vtterm")

#: What pip installs for each package an app needs on a board (its package.json
#: deps and upstream), so ``pip install omnipython-apps`` brings everything the
#: board install does.
PIP = {
    APPLIBS: APPLIBS_URL,
    "audioeffects": "omnipython-audioeffects",
    "audioinstruments": "omnipython-audioinstruments",
    "bledev": "omnipython",
    "medialink": "omnipython",
    "palettes": "omnipython-palettes",
    "pygraphics": "omnipython-pygraphics",
    "requests": "requests",
}
for _name in IN_DESKTOP:
    PIP[_name] = DESKTOP
    PIP["github:PyDevices/omnipython/packages/" + _name] = DESKTOP

#: A module a board's firmware has built in that pip installs on a computer:
#: ulab's numpy and scipy are the real ones there.
FIRMWARE_PIP = {
    "numpy": "numpy",
    "scipy": "scipy",
}

#: A package an app needs on a board that pip has no use for, and why.
NOT_FOR_PIP = {
    # CircuitPython has usb_hid built in; on a computer there is no USB device stack.
    "usb-hid": "makes the board a USB keyboard or gamepad, through MicroPython's machine.USBDevice",
}


def check_desktop_split(omnipython):
    """The names in `IN_DESKTOP` that the omnipython checkout *omnipython*
    doesn't put in omnipython-desktop, read from its mip-split.toml."""
    import tomllib

    with open(os.path.join(omnipython, "mip-split.toml"), "rb") as f:
        split = tomllib.load(f)
    return [name for name in IN_DESKTOP if not split.get(name, {}).get("pypi-desktop")]


def render_bundle():
    """The text of ``apps/package.json``: every app, each from its own package.json."""
    body = {
        "description": "Every app for Home",
        "target": "apps",
        "urls": [["__init__.py", "__init__.py"]],
        "deps": [["github:PyDevices/apps/apps/" + name, "main"] for name in apps()],
        "generated": "by tools/app_packages.py from the apps folder; edit the apps, not this",
    }
    return json.dumps(body, indent=2) + "\n"


def pip_layout():
    """``(packages, package_data)`` for pip: each folder of an app that holds
    Python is a package, ``apps.<app>...``, and the app's other files are data
    of the package nearest them. What a board leaves out, pip leaves out too."""
    packages, data = ["apps"], {}
    for name in apps():
        folder = os.path.join(APPS, name)
        files = app_files(folder)
        dirs = {""}
        for path in files:
            if path.endswith(".py"):
                dirs.add(path.rpartition("/")[0])
        for d in sorted(dirs):
            packages.append("apps." + name + ("." + d.replace("/", ".") if d else ""))
        for path in files:
            if path.endswith(".py"):
                continue
            home = path.rpartition("/")[0]
            while home not in dirs:
                home = home.rpartition("/")[0]
            pkg = "apps." + name + ("." + home.replace("/", ".") if home else "")
            data.setdefault(pkg, []).append(path[len(home) + 1 :] if home else path)
    return sorted(packages), data


def pip_requirements():
    """What ``omnipython-apps`` depends on: a pip requirement for each package
    any app needs on a board (see `PIP`), sorted, each once."""
    wanted, unknown = set(), set()
    for name in apps():
        deps, upstream, _ = needs(os.path.join(APPS, name))
        for package, _ in deps + upstream:
            if package.startswith("github:PyDevices/apps/") or package in NOT_FOR_PIP:
                continue
            if package in PIP:
                wanted.add(PIP[package])
            else:
                unknown.add(package)
        for module in imported(python_files(os.path.join(APPS, name))):
            if module in FIRMWARE_PIP:
                wanted.add(FIRMWARE_PIP[module])
    if unknown:
        raise SystemExit(
            "the apps need %s, which tools/app_packages.py has no pip requirement for: "
            "add each to PIP, or to NOT_FOR_PIP with the reason" % ", ".join(sorted(unknown))
        )
    return sorted(wanted, key=lambda r: (r.startswith("omnipython-applibs"), r))


def render_pyproject():
    """The text of ``apps/pyproject.toml``."""
    packages, data = pip_layout()
    lines = [
        "# Generated by tools/app_packages.py from the apps folder; edit the apps, not this.",
        "#",
        "# pip install \"omnipython-apps @ git+https://github.com/PyDevices/apps#subdirectory=apps\"",
        "",
        "[build-system]",
        'requires = ["setuptools>=69.0"]',
        'build-backend = "setuptools.build_meta"',
        "",
        "[project]",
        'name = "omnipython-apps"',
        "# The apps install from the main branch, so the version never changes.",
        'version = "0"',
        'description = "Every app for Home, from the main branch"',
        'authors = [{ name = "Brad Barnett" }]',
        'license = { text = "MIT" }',
        "# Everything the apps need, as on a board: tools/app_packages.py's PIP table.",
        "dependencies = [",
    ]
    lines += ["    %s," % json.dumps(r) for r in pip_requirements()]
    lines += [
        "]",
        "",
        "[tool.setuptools]",
        'package-dir = { "apps" = "." }',
        "packages = [",
    ]
    lines += ["    %s," % json.dumps(p) for p in packages]
    lines += ["]", "", "[tool.setuptools.package-data]"]
    for pkg in sorted(data):
        lines.append("%s = [%s]" % (json.dumps(pkg), ", ".join(json.dumps(f) for f in sorted(data[pkg]))))
    return "\n".join(lines) + "\n"


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
    """``(path, text)`` for each app's package.json, each program's that holds one,
    the bundle and the pyproject."""
    out = []
    for name in apps():
        out.append((os.path.join(APPS, name, "package.json"), render(os.path.join(APPS, name))))
    for program in sorted(os.listdir(PROGRAMS)):
        name = program_app(program)
        if name is not None:
            folder = os.path.join(PROGRAMS, program, "apps", name)
            out.append((os.path.join(PROGRAMS, program, "package.json"), render(folder, "apps/%s/" % name)))
    out.append((os.path.join(APPS, "package.json"), render_bundle()))
    out.append((os.path.join(APPS, "pyproject.toml"), render_pyproject()))
    return out


def main(argv):
    check = "--check" in argv
    stale = []
    if "--omnipython" in argv:
        i = argv.index("--omnipython")
        if i + 1 >= len(argv):
            sys.exit("--omnipython needs the path of an omnipython checkout")
        left_out = check_desktop_split(argv[i + 1])
        if left_out:
            sys.exit(
                "the apps need %s from omnipython-desktop, which %s/mip-split.toml doesn't mark "
                "pypi-desktop = true" % (", ".join(left_out), argv[i + 1])
            )
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
