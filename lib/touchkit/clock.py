# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""devkit.clock -- sleeping for milliseconds on every interpreter.

``time.sleep_ms`` is MicroPython's; CPython and CircuitPython have only
``time.sleep``. The tick functions are ``multimer``'s (``ticks_ms``,
``ticks_diff``, ``ticks_add``), which are the same on all three.
"""

import time

try:
    sleep_ms = time.sleep_ms
except AttributeError:

    def sleep_ms(ms):
        time.sleep(ms / 1000)
