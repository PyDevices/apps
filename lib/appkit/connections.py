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
chosen) and microphones (its ``pcm_in`` records from wherever ``audio.in``
is chosen), the USB host port's devices, and Bluetooth speakers. What the
firmware lacks is left out without a word. A board whose screen is drawn in
memory can be mirrored to a browser from "Cast to": it's off until chosen
there, and the browser asks for the board's WebREPL password. Looking for
Rokus costs a board time on every screen, so the Cast app registers
castdisplay's Rokus itself when it opens.

The USB host port's devices come from `usb_host`. On a board whose host
port is its own, apart from the port the REPL uses (an ESP32-P4, an
ESP32-S31, the GIGA), it starts the port, so a keyboard there types into
text fields through `appkit.hostkeys` and a USB sound card is listed from
boot. On an ESP32-S2 or S3 the host would take the REPL's port, so its
devices are listed only once a program has started it.

On a computer it's everything the computer's own libraries can list, each
one only where it's installed: `hostnet` for the operating system's network
link (reported only), audiodev's sound outputs and inputs, midiports' MIDI
ports, displaydev's keyboard, mouse and gamepads, and castdisplay's Rokus.

In a browser page it's what the browser lets a page reach: its speakers and
microphones, through audiodev, Web MIDI's ports and the page's other tabs,
through midiports, and the gamepads the browser shows it, through
displaydev. A browser offers MIDI only once the person allows
it, so until then each MIDI kind lists one "Allow MIDI" entry, and tapping it
in the picker has the browser ask.

A browser page starts again for every app opened from Home, so there the
choices are kept in the page's storage (`remember_in_page`) and come back
when it does.

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

#: The platforms that are a browser page: MicroPython's WebAssembly port and Pyodide.
BROWSERS = ("webassembly", "emscripten")

#: Chips whose USB host has a controller of its own, so starting it leaves
#: the REPL's USB port alone, and whether that host is full speed only.
#: On an ESP32-S2 or S3 the host and the REPL share the one port, so the
#: host port is used there only once something else has started it.
USB_HOST_APART = {"ESP32P4": False, "ESP32S31": False, "STM32H747": True}

_done = []
_usb = []


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
    return usb_host(registry)


def _bt_audio(registry):
    import btclassic

    if not hasattr(btclassic, "AudioSource"):
        return False  # btclassic without the A2DP source
    from audiodev import bt_audio

    bt_audio.register(registry)
    return True


def _mirror(registry):
    from castdisplay import endpoints

    register = getattr(endpoints, "register_mirror", None)
    if register is None:
        return False  # a castdisplay from before the mirror
    drv = getattr(sys.modules.get("board_config"), "display_drv", None)
    if drv is None or not hasattr(drv, "framebuffers") or drv.framebuffers() is None:
        return False  # no screen in memory to send
    from appkit import keys

    register(registry, push_key=keys.push)
    return True


#: A board's providers beside wifinet: the name `register` reports, and what
#: registers it, returning False when the firmware can't drive it. The apps
#: that need more register it when they open (Cast registers castdisplay).
BOARD_PROVIDERS = (
    ("audiodev", _board_audio),
    ("usb.host", _usb_host),
    ("btclassic", _bt_audio),
    ("mirror", _mirror),
)

#: A browser page's providers: the name `register` reports, and what registers it.
WEB_PROVIDERS = (
    ("audiodev", _audiodev),
    ("midiports", _midiports),
    ("displaydev", _displaydev),
)

#: A computer's providers: the name `register` reports, and what registers it.
HOST_PROVIDERS = (
    ("hostnet", _hostnet),
    ("audiodev", _audiodev),
    ("midiports", _midiports),
    ("displaydev", _displaydev),
    ("castdisplay", _castdisplay),
)


def name_page(name_of):
    """In a browser, have the page's other tabs call this one what
    *name_of()* returns, asked each time they list it, so a picker there
    offers "Tab: Synth Station". Does nothing anywhere else, or with a
    midiports from before the tabs."""
    if sys.platform not in BROWSERS:
        return
    try:
        from midiports import tabs
    except ImportError:
        return
    tabs.name_of = name_of


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
    elif sys.platform in BROWSERS:
        providers = WEB_PROVIDERS
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
    if sys.platform in BROWSERS:
        remember_in_page(registry)
    _done.append(names)
    return names


#: Where a browser page keeps its choices: the page's localStorage, by this key.
PAGE_KEY = "omnipython-connections"


def _page_storage():
    """The page's ``localStorage``, or None where there's none to use."""
    try:
        import js

        return js.localStorage
    except Exception:  # noqa: BLE001 - no js, no storage, or storage refused
        return None


def remember_in_page(registry, storage=None):
    """Keep *registry*'s choices in the browser page's storage, and bring
    back the ones kept before. A page starts again for each app opened from
    Home, so without this a choice made in Home's Connections would be gone
    by the time the app opens. *storage* stands in for ``localStorage``.
    Returns True when the choices are kept."""
    import json

    storage = storage if storage is not None else _page_storage()
    if storage is None:
        return False
    try:
        kept = json.loads(storage.getItem(PAGE_KEY) or "{}")
    except Exception as exc:  # noqa: BLE001 - nothing kept, or not ours to read
        print("appkit.connections: the page's kept choices can't be read: %s" % exc)
        kept = {}
    for kind, ids in kept.items():
        if kind in endpointkit.KINDS and ids and not registry.chosen(kind):
            try:
                registry.select(kind, ids)
            except Exception as exc:  # noqa: BLE001 - a choice that no longer fits is left behind
                print("appkit.connections: kept %s choice dropped: %s" % (kind, exc))

    def save(event, kind):
        if event != endpointkit.SELECTION:
            return
        forget = [p.name + ":" for p in registry.providers() if not getattr(p, "remember", True)]
        out = {}
        for k in endpointkit.KINDS:
            ids = [i for i in registry.chosen(k) if not any(i.startswith(f) for f in forget)]
            if ids:
                out[k] = ids
        try:
            storage.setItem(PAGE_KEY, json.dumps(out))
        except Exception as exc:  # noqa: BLE001 - storage full or refused: choices last this page only
            print("appkit.connections: the page's choices can't be kept: %s" % exc)

    registry.subscribe(None, save)
    return True


def _machine():
    """The chip this firmware was built for, as ``sys.implementation._machine``
    names it, without dashes: ``"ESP32P4"``. Empty on a computer."""
    return getattr(sys.implementation, "_machine", "").replace("-", "").upper()


def _board():
    """True on a board running MicroPython: a computer's pyusb, or
    CircuitPython's usb.core, isn't the host port `usb_host` drives."""
    return sys.platform not in HOSTS and sys.implementation.name == "micropython"


def _usb_host_start():
    """How to start this board's USB host port: ``{"full_speed": ...}``,
    ``{}`` when it's running already, or None to leave it alone (no host
    in this firmware, a computer, or a host that shares the REPL's port)."""
    if not _board():
        return None
    try:
        import usb.core
    except ImportError:
        return None
    if usb.core.stats() is None:
        return None
    if usb.core.running():
        return {}
    machine = _machine()
    for chip, full_speed in USB_HOST_APART.items():
        if chip in machine:
            return {"full_speed": full_speed}
    return None


def usb_host(registry=None):
    """Register what's plugged into this board's USB host port
    (`usb.host.endpoints`), once, starting the port when it has a
    controller of its own; returns True when it's registered.

    False on a computer, on firmware without a USB host, on a board whose
    host shares the REPL's port and isn't running, and where endpointkit
    or usb-host-endpoints isn't installed.
    """
    if _usb:
        return _usb[0]
    ok = False
    start = _usb_host_start() if endpointkit is not None else None
    if start is not None:
        try:
            from usb.host import endpoints
        except ImportError:
            endpoints = None
            print("appkit.connections: install usb-host-endpoints to use the USB host port's keyboards and devices")
        if endpoints is not None:
            reg = registry if registry is not None else endpointkit.registry
            if start:
                import usb.core

                usb.core.start(**start)
            endpoints.register(reg, start=False)
            ok = True
    _usb.append(ok)
    return ok


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
