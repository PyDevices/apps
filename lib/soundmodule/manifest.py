# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
# soundmodule's MicroPython manifest. From a board's manifest.py:
#
#   include("/path/to/apps/lib/soundmodule")                  soundmodule
#   include("/path/to/apps/lib/soundmodule", requires=True)   soundmodule, audioinstruments and audioeffects
#
# The require() lines below are what soundmodule needs that it doesn't carry: a mip
# install of soundmodule brings them along. A firmware build freezes them only with
# requires=True, from a library the build has registered (micropython-lib, or
# omnipython-lib with add_library), so including this file alone freezes
# soundmodule and nothing more.

options.defaults(requires=False)

if options.requires:
    require("audioinstruments")
    require("audioeffects")

package("soundmodule", base_path="..")  # this folder is soundmodule itself; its parent holds the package
