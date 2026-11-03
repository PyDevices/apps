# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What the apps that play say about the MIDI devices in the hub.

Instruments and the midiEngine hear every USB MIDI device at once, through
``midiports.usb_host.all_ports()``. `Watch` names the ones open now,
for the status line, and notices when one comes or goes.
"""


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


def open_desktop():
    """``(port, names)`` of a desktop's MIDI inputs, all of them, since the
    first is as likely a software synth's as a keyboard's, or None when it has
    none (or no ``midiports`` backend). The port reads like the merged hub
    port: ``any()``, ``read()``, ``close()``."""
    import sys

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
