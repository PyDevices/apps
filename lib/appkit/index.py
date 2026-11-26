# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Build the app index a frozen build reads beside the apps folder.

MicroPython can freeze ``.py`` files but not an ``app.json``, so at build
time this turns every ``<apps>/<app>/app.json`` into one module,
``_appkit_apps``, frozen with the apps in the package ``frozen_apps``.
``Launcher.scan("apps")`` reads it as well as the apps folder, so a board
can have some apps frozen and others in ``/apps``. The package has a name of
its own because ``/apps`` on the filesystem is the package ``apps``, and
MicroPython looks for a package's modules in one place only.

The other files an app reads beside its code (Backline's songs) are frozen
too, as bytes in one more module, ``_appkit_files``; `appkit.assets` reads
them where the files aren't on the filesystem.

From a MicroPython ``manifest.py``, include appkit's own manifest with the
apps folder, as an absolute path::

    import os
    include("/path/to/appkit", apps=os.path.abspath("apps"))

or call `freeze_apps` yourself. From a shell::

    python -m appkit.index apps -o build/_appkit_apps.py

This module runs on CPython at build time and imports nothing from appkit,
so it can be loaded on its own: ``python lib/appkit/index.py apps``.
"""

import json
import os
import sys

MODULE = "_appkit_apps"
#: The module holding the frozen apps' other files.
FILES_MODULE = "_appkit_files"
#: The package a frozen build's apps are in, whatever their folder's name.
PACKAGE = "frozen_apps"
#: Folders an app keeps beside its code that a board has no use for.
SKIP_DIRS = ("__pycache__", "docs", "examples", "studies", "tests", "tools")
#: Files in an app's folder that aren't frozen: the board's ``main.py`` (Home's
#: goes to the board's root), and what a person or an installer reads.
SKIP_FILES = ("main.py", "package.json", "pyproject.toml")
#: An apps folder's ``__init__.py``, when it has none of its own.
INIT_TEXT = "# The apps folder is a package: appkit imports each app in it as %s.<app>.\n" % PACKAGE


_names = None


def _tile_icons():
    """The icon names a Home tile can show: the icons package's built-in ones.

    They're read from the package's font module, without importing ``icons``
    itself, so a firmware build's host needs neither ttfio nor FreeType."""
    global _names
    if _names is None:
        import importlib.util

        spec = importlib.util.find_spec("icons")
        if spec is None or not spec.submodule_search_locations:
            raise ImportError(
                "appkit's index needs the icons package to check app icons: pip install omnipython-desktop, "
                "or put packages/icons from the omnipython repository on the import path"
            )
        folder = list(spec.submodule_search_locations)[0]
        path = os.path.join(folder, "_material.py")
        if not os.path.isfile(path):
            raise ImportError(
                "appkit's index found an icons package at %s with no _material.py: "
                "it isn't omnipython's. Put packages/icons from the omnipython repository first "
                "on the import path" % (folder,)
            )
        font_spec = importlib.util.spec_from_file_location("appkit_icon_names", path)
        font = importlib.util.module_from_spec(font_spec)
        font_spec.loader.exec_module(font)
        _names = font.NAMES.decode().split("\n")[:-1]
    return _names


def check_icon(entry, info, path):
    """Raise ``ValueError`` when the app *entry* (``info`` is its app.json, read from *path*)
    shows a tile and has no ``"icon"`` the icons package has. An app with ``"tile": false`` needs none."""
    if info.get("tile", True) is False:
        return
    icon = info.get("icon")
    if icon is None:
        raise ValueError(
            '%s: app %r has no "icon". Every app with a tile needs one: add "icon": "<Material icon name>" '
            'to its app.json, taken from icons.names(), or set "tile": false.' % (path, entry)
        )
    names = _tile_icons()
    if icon not in names:
        raise ValueError(
            "%s: app %r names icon %r, which the icons package hasn't. "
            "icons.names() lists the ones it has." % (path, entry, icon)
        )


def collect(folder):
    """``[(entry, app.json contents), ...]`` for every app in *folder*, sorted.

    Raises:
        ValueError: An app.json isn't a JSON object, or an app with a tile has no
            ``"icon"`` or one the icons package hasn't.
    """
    apps = []
    for entry in sorted(os.listdir(folder)):
        path = os.path.join(folder, entry, "app.json")
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            try:
                info = json.load(f)
            except ValueError as exc:
                raise ValueError("%s: %s" % (path, exc))
        if not isinstance(info, dict):
            raise ValueError("%s: not a JSON object" % (path,))
        check_icon(entry, info, path)
        apps.append((entry, info))
    return apps


def render(apps, source=None):
    """The ``_appkit_apps`` module's text for *apps* (see `collect`)."""
    lines = [
        "# Generated by appkit.index%s: do not edit." % (" from " + source if source else ""),
        "# The package the apps are frozen in, and (entry folder, app.json",
        "# contents) for each app, in order.",
        "PACKAGE = %r" % (PACKAGE,),
        "APPS = (",
    ]
    for entry, info in apps:
        lines.append("    (%r, %r)," % (entry, info))
    lines.append(")")
    return "\n".join(lines) + "\n"


def write(folder, out=None):
    """Write the index of *folder* to *out* (a file, or a folder to put
    ``_appkit_apps.py`` in; default: the current folder). Returns the file's path."""
    apps = collect(folder)
    if out is None:
        out = "."
    if os.path.isdir(out):
        out = os.path.join(out, MODULE + ".py")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(apps, os.path.basename(os.path.normpath(folder)) + "/*/app.json"))
    return out


def sibling_apps(folder):
    """The other apps the app in *folder* imports from, as
    ``from ..perch import stage`` does, read from its top-level modules."""
    import ast

    names = set()
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            tree = ast.parse(f.read(), name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 2:
                names.update([node.module.split(".")[0]] if node.module else [alias.name for alias in node.names])
    return names


def choose(folder, names=None):
    """The apps in *folder* to freeze: every one, or those in *names* (a list,
    or a comma-separated string) and the apps they import from. ``ValueError``
    names one that isn't there."""
    apps = collect(folder)
    if names is None:
        return apps
    if isinstance(names, str):
        names = [n.strip() for n in names.split(",") if n.strip()]
    have = dict(apps)
    wanted = []
    todo = list(names)
    while todo:
        name = todo.pop(0)
        if name in wanted:
            continue
        if name not in have:
            raise ValueError("no app %r in %s (have: %s)" % (name, folder, ", ".join(sorted(have))))
        wanted.append(name)
        todo.extend(sorted(sibling_apps(os.path.join(folder, name))))
    return [(entry, info) for entry, info in apps if entry in wanted]


def _walk(where):
    """``(code, other)``: the paths inside app folder *where* a freeze takes,
    ``.py`` files and the rest, sorted."""
    code, other = [], []
    for here, dirs, files in os.walk(where):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            rel = os.path.relpath(os.path.join(here, name), where).replace(os.sep, "/")
            if name.startswith(".") or name in SKIP_FILES or name.endswith((".pyc", ".md")):
                continue
            if name == "app.json" and rel == name:
                continue  # in the index
            (code if name.endswith(".py") else other).append(rel)
    return code, other


def render_files(files):
    """The ``_appkit_files`` module's text: *files* is ``{path: bytes}``."""
    lines = [
        "# Generated by appkit.index: do not edit.",
        "# The frozen apps' other files, by path, as appkit.assets reads them.",
        "FILES = {",
    ]
    for path in sorted(files):
        lines.append("    %r: %r," % (path, files[path]))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _without_native(text):
    """*text* with its ``@micropython.native`` and ``@micropython.viper`` lines
    taken out, so a port with no native code emitter can freeze it."""
    keep = []
    for line in text.split("\n"):
        if line.strip() in ("@micropython.native", "@micropython.viper"):
            continue
        keep.append(line)
    return "\n".join(keep)


def freeze_apps(folder, module, package, out_dir=None, names=None, native=True):
    """From a MicroPython manifest: freeze the apps in *folder* and their index.

    *module* and *package* are the manifest's own functions; *names* chooses
    some of the apps (see `choose`), and by default every one is frozen. The
    apps are frozen in the package ``frozen_apps`` (``frozen_apps.<app>``, as
    ``scan()`` imports them), whatever their folder is called: their ``.py``
    files are copied to ``<out_dir>/frozen_apps`` first, with an
    ``__init__.py`` made for the package. Folders a board has no use for
    (``tests``, ``docs``, ``tools`` and the like) are left out, and so is
    ``main.py``. An app's other files go in ``_appkit_files``. *native* False
    takes the ``@micropython.native`` decorators out, for a port with no
    native code emitter (the Windows and webassembly ports), where they don't
    compile. A script
    entry's module is frozen at the top level when it is a file in the app's
    folder (``<app>/<script>.py``), with the other modules beside it, which it
    imports by their own names; otherwise the build must freeze it elsewhere,
    like any library. The index is written to *out_dir* (default: a new
    temporary folder) and frozen as ``_appkit_apps``.
    """
    import shutil
    import tempfile

    folder = os.path.abspath(folder)
    if out_dir is None:
        out_dir = tempfile.mkdtemp(prefix="appkit-index-")
    elif not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    apps = choose(folder, names)
    with open(os.path.join(out_dir, MODULE + ".py"), "w", encoding="utf-8") as f:
        f.write(render(apps, os.path.basename(os.path.normpath(folder)) + "/*/app.json"))
    module(MODULE + ".py", base_path=out_dir)
    stage = os.path.join(out_dir, PACKAGE)
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    with open(os.path.join(stage, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(INIT_TEXT)
    module(PACKAGE + "/__init__.py", base_path=out_dir)
    files = {}
    for entry, info in apps:
        where = os.path.join(folder, entry)
        script = info.get("script")
        if script:
            if os.path.isfile(os.path.join(where, script + ".py")):
                # The script imports the modules beside it by their own names,
                # as it does from its folder on sys.path, so they go in at the
                # top level with it.
                code, _ = _walk(where)
                own = os.path.join(out_dir, "_scripts", entry)
                if os.path.isdir(own):
                    shutil.rmtree(own)
                os.makedirs(own)
                for rel in code:
                    if "/" in rel:
                        continue
                    with open(os.path.join(where, rel), encoding="utf-8") as f:
                        text = f.read()
                    with open(os.path.join(own, rel), "w", encoding="utf-8", newline="\n") as f:
                        f.write(text if native else _without_native(text))
                    module(rel, base_path=own)
            continue
        if not os.path.isfile(os.path.join(where, "__init__.py")):
            raise ValueError("%s has an app.json but no __init__.py" % (where,))
        code, other = _walk(where)
        for rel in code:
            dest = os.path.join(stage, entry, rel)
            if not os.path.isdir(os.path.dirname(dest)):
                os.makedirs(os.path.dirname(dest))
            if native:
                shutil.copy2(os.path.join(where, rel), dest)
            else:
                with open(os.path.join(where, rel), encoding="utf-8") as f:
                    text = _without_native(f.read())
                with open(dest, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            module(PACKAGE + "/" + entry + "/" + rel, base_path=out_dir)
        for rel in other:
            with open(os.path.join(where, rel), "rb") as f:
                files[PACKAGE + "/" + entry + "/" + rel] = f.read()
    if files:
        with open(os.path.join(out_dir, FILES_MODULE + ".py"), "w", encoding="utf-8") as f:
            f.write(render_files(files))
        module(FILES_MODULE + ".py", base_path=out_dir)
    return out_dir


def main(argv=None):
    """``python -m appkit.index APPS [-o OUT]``: write ``_appkit_apps.py``."""
    argv = list(sys.argv[1:] if argv is None else argv)
    out = None
    if "-o" in argv:
        i = argv.index("-o")
        if i + 1 >= len(argv):
            argv = []
        else:
            out = argv[i + 1]
            del argv[i : i + 2]
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print("usage: python -m appkit.index APPS_FOLDER [-o OUT]")
        print("Writes %s.py, the index of every APPS_FOLDER/<app>/app.json, for a frozen build." % MODULE)
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    path = write(argv[0], out)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
