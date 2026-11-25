# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Shell: look after the board's files from its own screen, typed on a keyboard.

The Shell is the REPL app with micropython-lib's upysh loaded into the
prompt, as ``from upysh import *`` would: ``ls``, ``pwd``, ``cd("lib")``,
``cat("boot.py")``, ``head``, ``cp``, ``mv``, ``rm``, ``mkdir``, ``rmdir``,
``newfile``, ``clear``, and ``man`` to list them. Everything else the REPL
app does, keyboards, colors, scrollback and the shared dupterm slot, is the
same, because it is the REPL app.

It needs upysh (``mip.install("upysh")``), and what the REPL app needs.
"""

import __main__

from touchkit import ui

from ..repl import main as repl_main


def main(scope):
    try:
        import upysh
    except ImportError:
        ui.missing(scope, "upysh isn't installed", 'The Shell runs micropython-lib\'s upysh.\nInstall it with mip.install("upysh").')
        return
    # The REPL runs in __main__'s globals, so its names are what the prompt sees.
    for name in dir(upysh):
        if not name.startswith("_"):
            setattr(__main__, name, getattr(upysh, name))
    repl_main(scope)
