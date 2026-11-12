# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Ostinato on the desktop: ``python -m ostinato`` from a checkout.

The browser version and the desktop app share everything in ``app/`` and the apps repo's ``songmodel`` and ``iconkit``. What
differs lives in ``desktop/``: the runner that hosts the engines (processes
or threads), the mixer that plays them through WASAPI, Windows MIDI, and the
page (dialogs, autosave, shortcuts, the control socket the checks use).
Importing this package puts both on ``sys.path`` the way the browser's
workers see their files, desktop first so its counterparts win.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The apps repo's lib/ holds what Ostinato shares with Vamp (songmodel: the song and
# its link) and iconkit, its icons. From a checkout it's two folders up; a staged copy
# (tools/win_stage.sh) carries it in lib/ beside the rest.
LIB = os.path.join(ROOT, "lib")
if not os.path.isdir(os.path.join(LIB, "songmodel")):
    LIB = os.path.join(os.path.dirname(os.path.dirname(ROOT)), "lib")
PATHS = [os.path.join(ROOT, *p.split("/")) for p in
         ("desktop/ui", "desktop", "app/ui", "app/engine", "vendor/lib")] + [LIB]

for _p in reversed(PATHS):
    if _p not in sys.path:
        sys.path.insert(0, _p)
