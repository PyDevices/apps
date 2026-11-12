# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
# appkit's MicroPython manifest. From a board's manifest.py:
#
#   include("/path/to/apps/lib/appkit")          appkit and iconkit
#
#   import os
#   include("/path/to/apps/lib/appkit", apps=os.path.abspath("apps"))
#                                                 appkit, iconkit, every app in
#                                                 apps/, and their index, _appkit_apps
#
# appkit's Home and apps draw with iconkit, a package of its own in the pydevices
# repository (packages/iconkit). It is frozen with appkit, from the folder that
# iconkit= names: that repository's packages/iconkit, or <tree>/iconkit in an
# omnipython-lib tree. Without iconkit=, $PYDEVICES_LIBRARY (the tree build_mp.py
# sets) is used. With neither, this manifest raises: it never freezes appkit
# without the icons its Home needs. A build that gets appkit from the library
# with require("appkit", library="omnipython-lib") gets iconkit from the library
# instead, and doesn't include this file.
#
# apps= must be an absolute path: this file runs from appkit's own folder.
# index_dir= says where to write _appkit_apps.py (default: a temporary folder).

options.defaults(apps=None, index_dir=None, iconkit=None)


def _iconkit_folder():
    """(the folder with iconkit's manifest.py, the folder its source imports from)."""
    import os

    named = options.iconkit
    if named is None:
        tree = os.environ.get("PYDEVICES_LIBRARY")
        named = os.path.join(tree, "iconkit") if tree else None
    if named is None:
        raise ValueError(
            "appkit manifest: iconkit is not found. appkit's Home draws with it. Pass "
            'iconkit="/path/to/pydevices/packages/iconkit", or set PYDEVICES_LIBRARY to an '
            "omnipython-lib tree that has iconkit (build_mp.py does)"
        )
    named = os.path.abspath(named)
    # packages/iconkit keeps its source in lib/iconkit, a library tree in iconkit/iconkit.
    for source in (os.path.join(named, "lib"), named):
        if os.path.isfile(os.path.join(source, "iconkit", "__init__.py")) and os.path.isfile(
            os.path.join(named, "manifest.py")
        ):
            return named, source
    raise ValueError(
        "appkit manifest: %s is not iconkit's folder: it has no manifest.py beside lib/iconkit or iconkit. "
        "Pass iconkit= the packages/iconkit folder of the pydevices repository" % (named,)
    )


_iconkit, _iconkit_source = _iconkit_folder()

package("appkit", base_path="..")  # this folder is appkit itself; its parent holds the package
include(_iconkit)  # the icons appkit's Home and apps draw with

if options.apps:
    import importlib.util
    import os
    import sys

    if not os.path.isabs(options.apps):
        raise ValueError("appkit manifest: apps=%r must be an absolute path" % (options.apps,))
    spec = importlib.util.spec_from_file_location("appkit_index", os.path.abspath("index.py"))
    index = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(index)
    # index.freeze_apps checks each app's icon against iconkit, imported here on the host.
    sys.path.insert(0, _iconkit_source)
    try:
        index.freeze_apps(options.apps, module, package, options.index_dir)
    finally:
        sys.path.remove(_iconkit_source)
