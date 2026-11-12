# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The ESP32-P4X-EYE's camera app: run the eyecam app alone, full screen.

Put this file, and apps/eyecam/, on the board, and have main.py import it.
On a desktop, run it from this folder (see the README).
"""
import appkit

appkit.run("eyecam")
