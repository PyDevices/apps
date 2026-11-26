# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What the apps that play say about the MIDI devices in the hub.

Instruments and the midiEngine hear every USB MIDI device at once, through
``midiports.usb_host.all_ports()``; on a computer or in a browser page,
the MIDI inputs chosen in Connections, or every input until some are. `Watch` names the ones open now,
for the status line, and notices when one comes or goes.
`ble_available` says whether a board can take Bluetooth MIDI too.
"""

import sys

#: The platforms that are a browser page, whose MIDI inputs are Web MIDI's.
BROWSERS = ("webassembly", "emscripten")


def ble_available():
    """True on a board whose firmware has Bluetooth LE, as
    ``midiports.ble.available()`` says, without importing the port: that
    waits until the player turns it on. Starts nothing."""
    if sys.implementation.name not in ("micropython", "circuitpython"):
        return False
    if sys.platform in ("webassembly", "emscripten"):
        return False
    for mod in ("bluetooth", "_bleio"):
        try:
            __import__(mod)
            return True
        except ImportError:
            pass
    return False


def ble_text(port):
    """The status line for a Bluetooth MIDI input."""
    if port.state == "connected":
        return "MIDI: Bluetooth"
    return "Bluetooth MIDI: waiting as %s" % (port.name,)


def name(dev):
    """A device's product string, or its vid:pid when it has none."""
    try:
        product = dev.product
    except Exception:  # a device that won't answer a string request
        product = None
    return product or "%04x:%04x" % (dev.idVendor, dev.idProduct)


class Watch:
    """The status line for a merged port's devices, worked out only when
    they change."""

    def __init__(self):
        self._devices = []
        self.text = None

    def changed(self, port):
        """True when the devices differ from the last call; ``text`` is then
        what to show, None when there are none."""
        devices = port.devices
        if devices == self._devices:
            return False
        self._devices = list(devices)
        if not devices:
            self.text = None
        else:
            self.text = "MIDI: " + " + ".join(name(d) for d in devices)
        return True


class Merged:
    """Every MIDI input a desktop has, read as one port, the way the hub's
    merged port reads: ``any()``, ``read()``, ``close()``."""

    def __init__(self, ports):
        self.ports = ports

    def any(self):
        return sum(p.any() for p in self.ports)

    def read(self):
        data = b""
        for p in self.ports:
            if p.any():
                data += p.read()
        return data

    def close(self):
        for p in self.ports:
            p.close()


def open_chosen():
    """``(port, names)`` of the inputs chosen for ``midi.in`` (the connections
    picker, or ``endpointkit.select``), read as one port through
    ``midiports.endpoints``, which opened them; None when none is chosen, or
    endpointkit or the computer's MIDI ports aren't registered."""
    try:
        import endpointkit
        from midiports import endpoints
    except ImportError:
        return None
    try:
        port = endpoints.merged_in()
    except KeyError:  # the computer's MIDI ports aren't registered
        return None
    chosen = [ep for ep in endpointkit.selected("midi.in") if ep.provider is port.provider]
    if not chosen:
        return None
    return port, " + ".join(ep.label for ep in chosen)


def open_desktop():
    """``(port, names)`` of a desktop's MIDI inputs: the ones chosen for
    ``midi.in`` when there are any (`open_chosen`), else all of them, since
    the first is as likely a software synth's as a keyboard's; None when it
    has none (or no ``midiports`` backend). The port reads like the merged
    hub port: ``any()``, ``read()``, ``close()``. A browser page is the
    same, with every input Web MIDI offers until some are chosen."""
    found = open_chosen()
    if found is not None:
        return found
    if sys.platform in BROWSERS:
        try:
            from midiports import webmidi
        except ImportError:
            return None
        return Merged([webmidi.page_in()]), "Web MIDI"
    if sys.platform.startswith("win"):
        from midiports import windows as mp
    elif sys.platform.startswith("linux"):
        from midiports import linux as mp
    else:
        return None
    import midiports

    ports = []
    names = []
    for info in mp.available():
        if info.direction not in (midiports.IN, midiports.INOUT):
            continue
        try:
            midi_in, midi_out = mp.ports(info.name)
        except OSError:  # another program has it open
            continue
        if midi_out is not None:
            midi_out.close()
        if midi_in is not None:
            ports.append(midi_in)
            names.append(info.name)
    if not ports:
        return None
    return Merged(ports), " + ".join(names)
