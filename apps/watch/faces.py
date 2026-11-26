# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Watch's faces: the hybrid face, then every skin of Clock's analog clock.

A face is made with `make` on a square parent and has ``update_time()``,
which Watch calls a few times a second; it redraws when the second changes.
"""

from deskkit import localtime
from deskkit.clockface import AnalogClock
from deskkit.hybridface import HybridWatch

HYBRID = "OmniPython Hybrid"
DEFAULT = HYBRID


def names():
    """Every face, the default first."""
    return (HYBRID,) + AnalogClock.skin_names()


def make(name, parent, size):
    """Face *name* on *parent*, *size* pixels square. An unknown name
    gets the default face."""
    if name not in AnalogClock.skin_names():
        return HybridWatch(parent, size, localtime.now)
    return AnalogClock(parent, (size, size), localtime.clock_time, name)
