# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
# appkit's MicroPython manifest. From a board's manifest.py:
#
#   include("/path/to/apps/lib/appkit")          appkit
#
#   import os
#   include("/path/to/apps/lib/appkit", apps=os.path.abspath("apps"))
#                                                 appkit, every app in apps/,
#                                                 and their index, _appkit_apps
#
# appkit's Home and apps draw with the icons package from the omnipython
# repository (packages/icons), and icons draws with ttfio, a C module. This
# manifest freezes neither: the firmware needs both built in, as
# omnipython-builds' build_mp.py does with --modules ttfio,icons.
#
# With apps=, the index checks each app's icon against the icons package's
# names, here on the host. It finds the package in $OMNIPYTHON_LIBRARY (the
# omnipython-lib tree build_mp.py sets) or on the host's import path, and
# raises when it's in neither.
#
# apps= must be an absolute path: this file runs from appkit's own folder.
# index_dir= says where to write _appkit_apps.py (default: a temporary folder).

options.defaults(apps=None, index_dir=None)

package("appkit", base_path="..")  # this folder is appkit itself; its parent holds the package

if options.apps:
    import importlib.util
    import os
    import sys

    if not os.path.isabs(options.apps):
        raise ValueError("appkit manifest: apps=%r must be an absolute path" % (options.apps,))
    spec = importlib.util.spec_from_file_location("appkit_index", os.path.abspath("index.py"))
    index = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(index)
    # index.freeze_apps checks each app's icon against the icons package's names.
    tree = os.environ.get("OMNIPYTHON_LIBRARY")
    source = os.path.join(tree, "icons") if tree else None
    if source:
        sys.path.insert(0, source)
    try:
        index.freeze_apps(options.apps, module, package, options.index_dir)
    finally:
        if source:
            sys.path.remove(source)
