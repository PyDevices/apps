# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""What the apps that play say about the MIDI devices in the hub.

Instruments and the midiEngine hear every USB MIDI device at once, through
``midiports.usb_host.all_ports()``. :class:`Watch` names the ones open now,
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


def open_desktop():
    """``(port, name)`` of a desktop's first MIDI input, or None when it has
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

    ins = [p for p in mp.available() if p.direction in (midiports.IN, midiports.INOUT)]
    if not ins:
        return None
    midi_in, midi_out = mp.ports(ins[0].name)
    if midi_out is not None:
        midi_out.close()
    if midi_in is None:
        return None
    return midi_in, ins[0].name
