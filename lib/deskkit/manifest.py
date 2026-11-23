# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
# deskkit's MicroPython manifest. From a board's manifest.py:
#
#   include("/path/to/apps/lib/deskkit")                  deskkit
#   include("/path/to/apps/lib/deskkit", requires=True)   deskkit, appkit and requests
#
# The require() lines below are what deskkit needs that it doesn't carry: a mip
# install of deskkit brings them along. A firmware build freezes them only with
# requires=True, from a library the build has registered (micropython-lib, or
# omnipython-lib with add_library), so including this file alone freezes
# deskkit and nothing more.

options.defaults(requires=False)

if options.requires:
    require("appkit")
    require("requests")

package("deskkit", base_path="..")  # this folder is deskkit itself; its parent holds the package
