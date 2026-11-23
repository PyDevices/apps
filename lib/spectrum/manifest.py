# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
# spectrum's MicroPython manifest. From a board's manifest.py:
#
#   include("/path/to/apps/lib/spectrum")                  spectrum
#   include("/path/to/apps/lib/spectrum", requires=True)   spectrum, pygraphics and touchkit
#
# The require() lines below are what spectrum needs that it doesn't carry: a mip
# install of spectrum brings them along. A firmware build freezes them only with
# requires=True, from a library the build has registered (micropython-lib, or
# omnipython-lib with add_library), so including this file alone freezes
# spectrum and nothing more.

options.defaults(requires=False)

if options.requires:
    require("pygraphics")
    require("touchkit")

package("spectrum", base_path="..")  # this folder is spectrum itself; its parent holds the package
