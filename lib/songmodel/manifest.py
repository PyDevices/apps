# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
# songmodel's MicroPython manifest. From a board's manifest.py:
#
#   include("/path/to/apps/lib/songmodel")                  songmodel
#   include("/path/to/apps/lib/songmodel", requires=True)   songmodel and hmilink
#
# The require() lines below are what songmodel needs that it doesn't carry: a mip
# install of songmodel brings them along. A firmware build freezes them only with
# requires=True, from a library the build has registered (micropython-lib, or
# omnipython-lib with add_library), so including this file alone freezes
# songmodel and nothing more.

options.defaults(requires=False)

if options.requires:
    require("hmilink")

package("songmodel", base_path="..")  # this folder is songmodel itself; its parent holds the package
