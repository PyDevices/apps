# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The factory's knob rule: three detents in one direction, each within
500 ms of the last, make one step. Turning back starts the count again."""

import time

DETENTS = 3
TIMEOUT_MS = 500


class Knob:
    def __init__(self):
        self._dir = 0
        self._count = 0
        self._last = 0

    def detent(self, direction):
        """Feed one detent (+1 or -1). Returns the step it completes, or 0."""
        now = time.ticks_ms()
        if self._count and time.ticks_diff(now, self._last) > TIMEOUT_MS:
            self._count = 0
        if direction != self._dir:
            self._dir = direction
            self._count = 0
        self._last = now
        self._count += 1
        if self._count >= DETENTS:
            self._count = 0
            return direction
        return 0
