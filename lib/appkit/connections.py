# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The endpointkit providers this device has, registered once for the picker and the bar.

The Shell calls `register` the first time it makes the picker or the status
bar, so their lists show what the device really has::

    from appkit import connections

    connections.register()

On a board with Wi-Fi that's `wifinet`, the networks in range, joined from
the picker. Every board also gets the sound outputs its firmware can drive:
its own output (and its ``audio_out`` then plays wherever ``audio.out`` is
chosen), the USB host port's devices, and Bluetooth speakers. What the
firmware lacks is left out without a word. Looking for Rokus costs a board
time on every screen, so the Cast app registers castdisplay itself when it
opens.

On a computer it's everything the computer's own libraries can list, each
one only where it's installed: `hostnet` for the operating system's network
link (reported only), audiodev's sound outputs and inputs, midiports' MIDI
ports, displaydev's keyboard, mouse and gamepads, and castdisplay's Rokus.

An app hears a choice move with `AppScope.follow`, and `device` turns what
it hears into the name a computer's audio backend opens. On a board it
opens ``audio_out`` again, which plays on the new choice.
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


def _hostnet(registry):
    import hostnet

    hostnet.register(registry)


def _audiodev(registry):
    from audiodev import endpoints

    endpoints.register(registry)


def _midiports(registry):
    from midiports import endpoints

    endpoints.register(registry)


def _displaydev(registry):
    from displaydev import endpoints

    endpoints.register(registry)


def _castdisplay(registry):
    from castdisplay import endpoints

    endpoints.register(registry)


def _board_audio(registry):
    import board_peripherals
    from audiodev import endpoints

    if "audio_out" not in getattr(board_peripherals, "FACTORY_ROLES", ()):
        return False  # no audio out, or one that can't be routed
    endpoints.route(board_peripherals, registry)
    return True


def _usb_host(registry):
    import usb.core
    from usb.host import endpoints

    if usb.core.stats() is None:
        return False  # usb.core is installed, but this firmware has no USB host
    endpoints.register(registry)
    return True


def _bt_audio(registry):
    import btclassic

    if not hasattr(btclassic, "AudioSource"):
        return False  # btclassic without the A2DP source
    from audiodev import bt_audio

    bt_audio.register(registry)
    return True


#: A board's providers beside wifinet: the name `register` reports, and what
#: registers it, returning False when the firmware can't drive it. The apps
#: that need more register it when they open (Cast registers castdisplay).
BOARD_PROVIDERS = (
    ("audiodev", _board_audio),
    ("usb.host", _usb_host),
    ("btclassic", _bt_audio),
)

#: A computer's providers: the name `register` reports, and what registers it.
HOST_PROVIDERS = (
    ("hostnet", _hostnet),
    ("audiodev", _audiodev),
    ("midiports", _midiports),
    ("displaydev", _displaydev),
    ("castdisplay", _castdisplay),
)


def register(registry=None):
    """Register the device's providers in *registry* (endpointkit's own when
    None), once; later calls do nothing. Returns the names registered.

    A computer's library that isn't installed is left out without a word.
    One that's installed but can't start here (no sound backend, no MIDI on
    this system) is left out with a line saying why. On a board, a
    library the firmware has but can't use (no USB host, no A2DP source)
    is left out without a word.
    """
    if _done:
        return _done[0]
    if endpointkit is None:
        return []  # the picker and the bar have nothing to show either
    registry = registry if registry is not None else endpointkit.registry
    names = []
    providers = BOARD_PROVIDERS
    if _wifi():
        import wifinet

        wifinet.register(registry)
        names.append("wifinet")
    elif sys.platform in HOSTS:
        providers = HOST_PROVIDERS
    for name, add in providers:
        try:
            if add(registry) is False:
                continue
        except ImportError:
            continue
        except Exception as exc:  # noqa: BLE001 - one library can't keep the rest off the picker
            print("appkit.connections: no %s here: %s" % (name, exc))
            continue
        names.append(name)
    _done.append(names)
    return names


def device(endpoints):
    """The device name a computer's backend opens for the first of
    *endpoints* (what `AppScope.follow` hands its callback), or None for the
    system default: nothing chosen, or a board's endpoint, which names none
    because a board's ``audio_out`` follows the choice itself.

    Pass it on as ``device=`` only when it isn't None, since a board's
    ``audio_out`` takes no such argument.
    """
    for ep in endpoints:
        return ep.caps.get("device")
    return None
