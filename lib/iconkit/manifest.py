# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
# iconkit's MicroPython manifest. From a board's manifest.py:
#
#   include("/path/to/apps/lib/iconkit")
#
# Both icon sets are frozen, so the masks stay in flash: the 24 px set is
# 72 KB and the 48 px set another 72 KB. appkit's manifest includes this one.

package("iconkit", base_path="..")  # this folder is iconkit itself; its parent holds the package
