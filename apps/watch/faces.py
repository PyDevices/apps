# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Watch's faces: every skin of Clock's analog clock, then the hybrid face.

A face is made with `make` on a square parent and has ``update_time()``,
which Watch calls a few times a second; it redraws when the second changes.
"""

from deskkit import localtime
from deskkit.clockface import AnalogClock
from deskkit.hybridface import HybridWatch

DEFAULT = "Grand Classic"
HYBRID = "OmniPython Hybrid"


def names():
    """Every face, the default first."""
    return AnalogClock.skin_names() + (HYBRID,)


def make(name, parent, size):
    """Face *name* on *parent*, *size* pixels square. An unknown name
    gets the default face."""
    if name == HYBRID:
        return HybridWatch(parent, size, localtime.now)
    if name not in AnalogClock.skin_names():
        name = DEFAULT
    return AnalogClock(parent, (size, size), localtime.clock_time, name)
