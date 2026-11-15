# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The level meter: the peak of what the engine plays, and whether it clipped.

The engine hands `Level` each stretch of audio the pump has sent out. `read`
gives the highest peak since the last read, as a share of full scale before
the master, and whether it came within half a decibel of it.
"""

FULL_SCALE = 32767
#: A peak this close to full scale lights the clip light: -0.5 dB.
CLIP_AT = 0.944
#: The most samples looked at in one stretch, the newest ones. A tick that
#: comes late brings more than that, and the meter mustn't make it later.
SCAN = 4096
#: The meter's bottom in decibels, and the decibels in one step of its bar.
FLOOR_DB = -48
STEP_DB = 2
STEPS = -FLOOR_DB // STEP_DB

# The level at the bottom of each step, from the top one down, so a level is
# placed with compares.
_EDGES = tuple(10 ** (-STEP_DB * k / 20) for k in range(STEPS))


class Level:
    def __init__(self):
        self._peak = 0

    def feed(self, samples):
        """Take in a stretch of signed 16-bit samples, every channel together.

        ``max`` and ``min`` walk the buffer in C, so every sample is seen and
        a single one at full scale is enough to light the clip light.
        """
        if len(samples) > SCAN:
            samples = samples[len(samples) - SCAN:]
        if not len(samples):
            return
        high = max(samples)
        low = -min(samples)
        if low > high:
            high = low
        if high > self._peak:
            self._peak = high

    def read(self, master=1.0):
        """``(level, clipped)`` since the last read.

        *master* is the gain between the effect and the audio that was fed
        in. The level is the peak before it, 0.0 to 1.0, so the meter shows
        what the effect puts out wherever the master is. With the master at
        0 nothing reaches the meter and both are zero.
        """
        peak = self._peak
        self._peak = 0
        if master <= 0 or not peak:
            return 0.0, False
        level = peak / (FULL_SCALE * master)
        if level > 1.0:
            level = 1.0
        return level, level >= CLIP_AT


def steps(level):
    """A level in 0.0 to 1.0 as lit steps of the bar, 0 to `STEPS`."""
    for k in range(STEPS):
        if level >= _EDGES[k]:
            return STEPS - k
    return 0
