# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Start Home when the board starts: the board's main.py, for the apps in /apps.

Put it on the board with
``omip.install("github:PyDevices/apps/apps/home/main.py", target="/")``.
"""

import appkit

# A script app Home started runs here, before the display opens. Where timers
# run it in the background, this returns True and Home comes back when it quits.
if not appkit.run_pending_script():
    from display_driver import app
    from touchkit import shell

    shell.quiet_app_timers(app)
    launcher = shell.TouchLauncher(app, home="home")
    launcher.scan("apps")
    launcher.shell = shell.TouchShell(launcher)
    launcher.boot("home")
    appkit.serve()
