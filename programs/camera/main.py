# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Start Camera when the board starts, full screen, as the ESP32-P4X-EYE does.

Install the app with ``omip.install("github:PyDevices/apps/programs/camera")``,
then put this file at the board's root as its main.py with
``omip.install("github:PyDevices/apps/programs/camera/main.py", target="/")``.
Home's main.py, installed the same way, takes the board back to Home.
On a desktop, run it from this folder (see the README).
"""

import appkit

appkit.run("eyecam")
