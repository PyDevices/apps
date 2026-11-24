# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The apps as a MicroPython manifest: freeze every app, or the ones you choose.

From a firmware's manifest::

    include("path/to/apps/apps")                       # every app
    include("path/to/apps/apps", apps="home,clock")    # these, and the apps they import from

or name this folder in omnipython-builds' ``build_mp.py --modules all,path/to/apps/apps``.

The shared libraries in ``lib/`` (appkit and the rest) are frozen with them,
from the repository's own ``manifest.py``; ``libs=False`` leaves them out for a
build that brings its own. The apps are frozen as the package ``frozen_apps``,
and Home lists them beside any in ``/apps``. What they need from elsewhere,
LVGL, icons and ttfio, the instruments, comes from the firmware's other
modules: an app whose module is missing says so when it starts.

Each app's ``app.json`` is checked here, and its icon against the icons
package's names, which this finds in ``$OMNIPYTHON_LIBRARY`` (build_mp.py
sets it) or on the build's import path. ``index_dir=`` says where the index is
written (default: a temporary folder). ``native=False`` takes the
``@micropython.native`` decorators out of the frozen copies, for a port with
no native code emitter; it's the default for the Windows and webassembly
ports when build_mp.py names the target.
"""

import importlib.util
import os
import sys

if 0:

    def include(*args, **kwargs):
        pass

    def module(*args, **kwargs):
        pass

    def package(*args, **kwargs):
        pass

    class options:  # noqa: N801
        apps = libs = index_dir = native = None

        def defaults(**kwargs):
            pass


_target = os.environ.get("OMNIPYTHON_TARGET", "")
options.defaults(apps=None, libs=True, index_dir=None, native=_target.split("/")[0] not in ("windows", "webassembly"))

_here = os.getcwd()  # include() runs a manifest from its own folder
if options.libs:
    include(os.path.dirname(_here))

_spec = importlib.util.spec_from_file_location(
    "apps_freeze_index", os.path.join(os.path.dirname(_here), "lib", "appkit", "index.py")
)
_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_index)
_tree = os.environ.get("OMNIPYTHON_LIBRARY")
_icons = os.path.join(_tree, "icons") if _tree else None
if _icons and os.path.isdir(_icons):
    sys.path.insert(0, _icons)
try:
    _index.freeze_apps(_here, module, package, options.index_dir, options.apps, options.native)
finally:
    if _icons in sys.path:
        sys.path.remove(_icons)
