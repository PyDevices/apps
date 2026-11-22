# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The endpointkit providers this device has, registered once for the picker and the bar.

The Shell calls `register` the first time it makes the picker or the status
bar, so their lists show what the device really has::

    from appkit import connections

    connections.register()

Today that's the network: on a board with Wi-Fi, `wifinet` (networks in
range, joined from the picker); on a computer, `hostnet` (the operating
system's link, reported only). A board without Wi-Fi gets neither.
"""

import sys

try:
    import endpointkit
except ImportError:
    endpointkit = None

#: The platforms where the operating system owns networking.
HOSTS = ("linux", "win32", "darwin")

_done = []


def _wifi():
    """True when this firmware has a Wi-Fi station: MicroPython's ``network.WLAN`` or CircuitPython's ``wifi``."""
    if sys.implementation.name == "circuitpython":
        try:
            import wifi  # noqa: F401
        except ImportError:
            return False
        return True
    try:
        import network
    except ImportError:
        return False
    return hasattr(network, "WLAN")


def register(registry=None):
    """Register the device's providers in *registry* (endpointkit's own when
    None), once; later calls do nothing. Returns the names registered."""
    if _done:
        return _done[0]
    if endpointkit is None:
        return []  # the picker and the bar have nothing to show either
    registry = registry if registry is not None else endpointkit.registry
    names = []
    if _wifi():
        import wifinet

        wifinet.register(registry)
        names.append("wifinet")
    elif sys.platform in HOSTS:
        import hostnet

        hostnet.register(registry)
        names.append("hostnet")
    _done.append(names)
    return names
