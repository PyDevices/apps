# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Start Home when the board starts: the board's main.py, for the apps in /apps.

Put it on the board with
``omip.install("github:PyDevices/apps/apps/home/main.py", target="/")``.
"""

import appkit

appkit.run_pending_script()  # a script app Home started runs here, before the display opens

from display_driver import app  # noqa: E402
from touchkit import shell  # noqa: E402

shell.quiet_app_timers(app)
launcher = shell.TouchLauncher(app, home="home")
launcher.scan("apps")
launcher.shell = shell.TouchShell(launcher)
launcher.boot("home")
appkit.serve()
