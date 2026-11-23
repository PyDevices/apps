# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
# programkit's MicroPython manifest. From a board's manifest.py:
#
#   include("/path/to/apps/lib/programkit")                  programkit
#   include("/path/to/apps/lib/programkit", requires=True)   programkit and pygraphics
#
# The require() lines below are what programkit needs that it doesn't carry: a
# mip install of applibs, which holds programkit, brings them along. A
# firmware build freezes them only with requires=True, from a library the
# build has registered (micropython-lib, or omnipython-lib with add_library),
# so including this file alone freezes programkit and nothing more.

options.defaults(requires=False)

if options.requires:
    require("pygraphics")

package("programkit", base_path="..")  # this folder is programkit itself; its parent holds the package
