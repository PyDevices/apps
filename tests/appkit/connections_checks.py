# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""`appkit.connections`: which providers a device registers.

    python connections_checks.py          # from tests/appkit, with the harness's paths

Once as a computer, which gets hostnet, then as a board with Wi-Fi, which
gets wifinet and the sound outputs its firmware can drive: a stand-in
``network`` module with a station on "Home" and "Cafe" in range, a stand-in
castdisplay it must leave alone, and stand-in ``board_peripherals``,
``usb`` and ``btclassic`` modules. The board is an ESP32-P4, so its USB host
port is started; other chips check that only the P4, the S31 and the GIGA
start it. Then a board whose firmware has none of those, which must register
them without a word. Exit status 0 when every
check passes.
"""

import os
import sys


def _up(path):
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _join(*parts):
    return "/".join(parts)


_HERE = _up(__file__)
_TESTS = _up(_HERE)
_ROOT = _up(_TESTS)
_LIB = os.getenv("OMNIPYTHON_LIB") or _join(_ROOT, "..", "omnipython", "lib")
_OMNI = _up(_LIB)
# lib first: tests/appkit would hide the real appkit. utils holds hostnet.
sys.path[:0] = [_join(_ROOT, "lib"), _HERE, _TESTS,
                _join(_OMNI, "packages", "endpointkit"),
                _join(_OMNI, "packages", "icons"),
                _join(_OMNI, "packages", "iconkit", "lib"), _LIB, _join(_OMNI, "utils")]

FAILS = []


def check(cond, what):
    if not cond:
        FAILS.append(what)
        print("FAIL", what)


import endpointkit  # noqa: E402
from appkit import connections  # noqa: E402

PLANT = os.getenv("CONNECTIONS_PLANT")
if PLANT == "no_wifi":
    connections._wifi = lambda: False
elif PLANT == "board_finds_rokus":
    connections.BOARD_PROVIDERS = (("castdisplay", connections._castdisplay),)
elif PLANT == "board_skips_audio":
    connections.BOARD_PROVIDERS = ()
elif PLANT == "starts_usb_host":
    # Starts the host port wherever there is one, the REPL's port or not.
    def _always_starts():
        import usb.core

        return {"full_speed": False} if usb.core.stats() is not None else None
    connections._usb_host_start = _always_starts
elif PLANT == "never_starts_usb_host":
    def _never_starts():
        import usb.core

        return {} if usb.core.stats() is not None else None
    connections._usb_host_start = _never_starts
elif PLANT == "noisy_absence":
    def _usb_raises(registry):
        import usb.core

        if usb.core.stats() is None:
            raise OSError("this firmware has no USB host")
        return True
    connections.BOARD_PROVIDERS = tuple((n, _usb_raises if n == "usb.host" else add)
                                        for n, add in connections.BOARD_PROVIDERS)


def ids(reg):
    return [ep.id for ep in reg.endpoints("net")]


# A computer: the operating system's link, reported.
reg = endpointkit.Registry()
names = connections.register(reg)
host_names = [name for name, _ in connections.HOST_PROVIDERS]
check(names[:1] == ["hostnet"], "a computer registers hostnet first: %r" % (names,))
check(all(name in host_names for name in names), "and only a computer's own libraries: %r" % (names,))
check(ids(reg) and ids(reg)[0] == "host-net:default", "the host's link is listed: %r" % ids(reg))
check(connections.register(reg) is names and len(reg.providers("net")) == 1, "registering again does nothing")


class WLAN:
    """A station on Home, with Cafe in range too."""

    def __init__(self, which):
        self.which = which

    def active(self, on=None):
        return True

    def isconnected(self):
        return True

    def ifconfig(self, cfg=None):
        return ("10.0.0.9", "255.255.255.0", "10.0.0.1", "10.0.0.1")

    def config(self, key):
        return {"ssid": "Home", "mac": b"\x00\x11\x22\x33\x44\x55"}[key]

    def scan(self):
        return [(b"Home", b"", 1, -50, 3, False), (b"Cafe", b"", 6, -70, 3, False)]


class Network:
    STA_IF = 0
    AP_IF = 1
    WLAN = WLAN

    @staticmethod
    def hostname(name=None):
        return "board"


class Rokus:
    """castdisplay's provider, counting its registrations."""

    registered = []

    @staticmethod
    def register(registry=None):
        Rokus.registered.append(registry)


class Castdisplay:
    endpoints = Rokus


class Factory:
    """A board's audio_out: a factory role, called with a format."""

    capability = None

    def __call__(self, format=None, **kwargs):
        return ("codec", format)


class BoardPeripherals:
    PERIPHERALS = frozenset({"audio_out"})
    FACTORY_ROLES = frozenset({"audio_out"})
    audio_out = Factory()


class UsbCore:
    host = True
    started = []

    @staticmethod
    def stats():
        return {"running": bool(UsbCore.started)} if UsbCore.host else None

    @staticmethod
    def running():
        return bool(UsbCore.started)

    @staticmethod
    def start(full_speed=False, classes=None):
        UsbCore.started.append(full_speed)


class UsbEndpoints:
    """usb.host.endpoints: register starts the port unless told not to, as the real one does."""

    registered = []

    @staticmethod
    def register(registry=None, start=True, full_speed=False):
        UsbEndpoints.registered.append(registry)
        if start:
            UsbCore.start(full_speed=full_speed)


class UsbHost:
    endpoints = UsbEndpoints


class Usb:
    core = UsbCore
    host = UsbHost


class Btclassic:
    """btclassic with its A2DP source; registering must not touch the radio."""

    class Bluetooth:
        def __init__(self):
            raise AssertionError("registering turned the Bluetooth radio on")

    class AudioSource:
        pass


heard = []
connections.print = lambda *a: heard.append(" ".join(str(x) for x in a))

# A board with Wi-Fi: its networks, joined from the picker, its sound
# outputs, and no looking for Rokus, though castdisplay is there: Cast does
# that when it opens.
sys.modules["network"] = Network
sys.modules["castdisplay"] = Castdisplay
sys.modules["board_peripherals"] = BoardPeripherals
sys.modules["usb"] = Usb
sys.modules["usb.core"] = UsbCore
sys.modules["usb.host"] = UsbHost
sys.modules["usb.host.endpoints"] = UsbEndpoints
sys.modules["btclassic"] = Btclassic
# An ESP32-P4, whose host port is apart from the REPL's.
connections._board = lambda: True
connections._machine = lambda: "ESP32P4"
del connections._done[:]
del connections._usb[:]
reg = endpointkit.Registry()
names = connections.register(reg)
board_names = [name for name, _ in connections.BOARD_PROVIDERS]
check(names[:1] == ["wifinet"], "a board with Wi-Fi registers wifinet: %r" % (names,))
check(all(name in board_names for name in names[1:]), "and nothing of a computer's: %r" % (names,))
check(names[1:] == ["audiodev", "usb.host", "btclassic"], "and every sound output its firmware has: %r" % (names,))
check(UsbEndpoints.registered == [reg], "the USB host port's devices are registered")
check(UsbCore.started == [False], "and on an ESP32-P4 the port is started, at high speed: %r" % UsbCore.started)
check(connections.usb_host() is True and UsbEndpoints.registered == [reg] and UsbCore.started == [False],
      "the Shell asking again registers nothing more and starts nothing")
audio = [ep.id for ep in reg.endpoints("audio.out")]
check(audio == ["board-out:main"], "the board's own output is listed, and no speaker before a scan: %r" % audio)
from audiodev import endpoints as _audio_endpoints  # noqa: E402

check(isinstance(BoardPeripherals.audio_out, _audio_endpoints.RoutedAudioOut),
      "the board's audio_out now follows the audio.out choice")
check(not heard, "nothing is printed: %r" % heard)
check("castdisplay" not in names and not Rokus.registered, "a board doesn't look for Rokus: %r" % (names,))
check(reg.selection("net") == ["wifi:Home"], "the network the board is on is chosen: %r" % reg.selection("net"))
reg.poll()
check(ids(reg) == ["wifi:Home", "wifi:Cafe"], "the networks in range are listed after a scan: %r" % ids(reg))
check(reg.find("wifi:Cafe").state == endpointkit.NEEDS_PAIRING, "a new secured network asks for its password")
check(not reg.providers("net") or all(p.name != "host-net" for p in reg.providers("net")), "a board doesn't report a host link")

# Where the port is started: only on a chip whose host has a controller
# of its own. Elsewhere it's registered only once a program has started it.


def usb_host_on(machine, board=True, running=False):
    UsbCore.started[:] = [True] if running else []
    UsbEndpoints.registered[:] = []
    del connections._usb[:]
    connections._board = lambda: board
    connections._machine = lambda: machine
    ok = connections.usb_host(endpointkit.Registry())
    return ok, UsbCore.started[1:] if running else list(UsbCore.started), len(UsbEndpoints.registered)


check(usb_host_on("ESP32S31") == (True, [False], 1), "an ESP32-S31: started at high speed")
check(usb_host_on("STM32H747") == (True, [True], 1), "the GIGA: started at full speed, all its port does")
check(usb_host_on("ESP32S3") == (False, [], 0), "an ESP32-S3, whose host would take the REPL's port: not started")
check(usb_host_on("ESP32S2") == (False, [], 0), "an ESP32-S2: the same")
check(usb_host_on("ESP32S3", running=True) == (True, [], 1), "unless a program started it: registered, not restarted")
check(usb_host_on("ESP32P4", board=False) == (False, [], 0), "a computer: not started, not registered")
UsbCore.started[:] = []
connections._board = lambda: True
connections._machine = lambda: "ESP32P4"

# A board whose firmware has a USB stack but no host port, btclassic
# without the A2DP source, and an audio_out that isn't a factory role: it
# registers none of them, and says nothing about it.
UsbCore.host = False
del Btclassic.AudioSource
BoardPeripherals.FACTORY_ROLES = frozenset()
BoardPeripherals.audio_out = ("an object, not a factory",)
UsbEndpoints.registered[:] = []
del heard[:]
del connections._done[:]
del connections._usb[:]
_audio_endpoints._routes[:] = []
reg = endpointkit.Registry()
names = connections.register(reg)
check(names == ["wifinet"], "a board without them registers wifinet alone: %r" % (names,))
check(not UsbEndpoints.registered and not UsbCore.started and not reg.endpoints("audio.out"),
      "no USB host started, no sound output listed")
check(not heard, "and nothing is printed: %r" % heard)

if FAILS:
    print("%d checks failed" % len(FAILS))
    sys.exit(1)
print("connections: all checks passed on", sys.implementation.name)
