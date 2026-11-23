# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
# touchkit's MicroPython manifest. From a board's manifest.py:
#
#   include("/path/to/apps/lib/touchkit")                  touchkit
#   include("/path/to/apps/lib/touchkit", requires=True)   touchkit, appkit and deskkit
#
# The require() lines below are what touchkit needs that it doesn't carry: a
# mip install of applibs, which holds touchkit, brings them along. A firmware
# build freezes them only with requires=True, from a library the build has
# registered (micropython-lib, or omnipython-lib with add_library), so
# including this file alone freezes touchkit and nothing more.

options.defaults(requires=False)

if options.requires:
    require("appkit")
    require("deskkit")

package("touchkit", base_path="..")  # this folder is touchkit itself; its parent holds the package
