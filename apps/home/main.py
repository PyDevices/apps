# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Start Home when the board starts: the board's main.py, for the apps in /apps.

Put it on the board with
``omip.install("github:PyDevices/apps/apps/home/main.py", target="/")``.

A round screen, or one too small for Home's grid of tiles, opens on Watch
instead, where Watch is installed: a watch face, then a wheel of the same
apps. To choose for yourself, set ``HOME`` to ``"home"`` or ``"watch"``.
"""

import appkit

HOME = None  # None: Watch on a round or small screen, else Home

# A script app Home started runs here, before the display opens. Where timers
# run it in the background, this returns True and Home comes back when it quits.
if not appkit.run_pending_script():
    from display_driver import app
    from appkit.shell import is_round, is_small
    from touchkit import net, shell

    shell.quiet_app_timers(app)
    launcher = shell.TouchLauncher(app, home="home")
    launcher.scan("apps")
    if HOME is not None:
        launcher.home = HOME
    elif "watch" in launcher.names and (is_round() or is_small()):
        launcher.home = "watch"
    launcher.shell = shell.TouchShell(launcher)
    launcher.boot(launcher.home)
    # Join a known network and start WebREPL, now the display is up.
    net.boot()
    appkit.serve()
