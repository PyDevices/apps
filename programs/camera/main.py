# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Start Camera when the board starts, full screen, as the ESP32-P4X-EYE does.

Install the app with ``omip.install("github:PyDevices/apps/programs/camera")``,
then put this file at the board's root as its main.py with
``omip.install("github:PyDevices/apps/programs/camera/main.py", target="/")``.
Home's main.py, installed the same way, takes the board back to Home.
On a desktop, run it from this folder (see the README).

A board with a ``secrets.py`` joins its Wi-Fi and starts WebREPL once Camera
is on the screen, as Home does. Without one, Camera runs offline.
"""

import appkit

# A script app Home started runs here, before the display opens.
if not appkit.run_pending_script():
    from display_driver import app

    launcher = appkit.Launcher(app)
    launcher.scan("apps")
    launcher.shell = appkit.Shell(launcher)
    launcher.boot("eyecam")
    try:
        import secrets  # noqa: F401
    except ImportError:
        pass
    else:
        from touchkit import net

        # Join a known network and start WebREPL, now Camera is up.
        net.boot()
    if appkit.host() != "browser":
        appkit.serve(app)
