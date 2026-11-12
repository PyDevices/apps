# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
# appkit's MicroPython manifest. From a board's manifest.py:
#
#   include("/path/to/apps/lib/appkit")          appkit alone
#
#   import os
#   include("/path/to/apps/lib/appkit", apps=os.path.abspath("apps"))
#                                                 appkit, every app in apps/,
#                                                 and their index, _appkit_apps
#
# appkit's Home and apps draw with iconkit, which is a package of its own in the
# pydevices repository (packages/iconkit): freeze it beside appkit, as you do
# pydevices itself, or its Home fails to import.
#
# apps= must be an absolute path: this file runs from appkit's own folder.
# index_dir= says where to write _appkit_apps.py (default: a temporary folder).

options.defaults(apps=None, index_dir=None)

package("appkit", base_path="..")  # this folder is appkit itself; its parent holds the package

if options.apps:
    import importlib.util
    import os

    if not os.path.isabs(options.apps):
        raise ValueError("appkit manifest: apps=%r must be an absolute path" % (options.apps,))
    spec = importlib.util.spec_from_file_location("appkit_index", os.path.abspath("index.py"))
    index = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(index)
    index.freeze_apps(options.apps, module, package, options.index_dir)
