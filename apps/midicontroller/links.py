# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Where the controller's MIDI goes: each way out this board has.

`choices` lists what this board can do, in the order the app offers them:

``usb``
    The board is a USB MIDI device on its native USB port (an ESP32-S2, S3
    or P4), for a computer, a phone or a host board. Needs midiports and
    micropython-lib's ``usb-device-midi``.
``host``
    A synth or a sound module plugged into the board's USB host port (an
    ESP32-P4, say). Every MIDI device on the port hears it, and ones
    plugged in later join. Needs midiports and ``usb-core``.
``ble``
    The board advertises BLE-MIDI, for a computer, a phone or a tablet.
    Needs bledev and firmware with Bluetooth.
``out:<endpoint id>``
    On a computer or in a browser page, one of the MIDI outputs the
    Connections picker lists under MIDI out: a synth, a DAW's virtual port,
    a loopback, or what Web MIDI offers. Choosing one here chooses it there,
    for the whole device, and a choice made there is what the controller
    plays, every output chosen at once. What comes back is the MIDI ins
    chosen there. Needs midiports and endpointkit. In a browser the person
    allows MIDI first: until then the one choice is "Allow MIDI", and
    choosing it has the browser ask, then plays the first output.

`open_link` opens one and hands back a `Link`: ``write`` for the output,
``read_into`` for what comes back (CC feedback), a status line, ``close``.
"""

import sys

#: The name the board advertises over BLE, which a computer lists as its MIDI port.
BLE_NAME = "MIDI Controller"


class Link:
    """One open way out. *out* is a MIDI output port, *inp* an input or None."""

    def __init__(self, key, label, out, inp=None, closer=None):
        self.key = key
        self.label = label
        self.out = out
        self.inp = inp
        self._closer = closer
        self.closed = False

    def write(self, buf, nbytes=None):
        if self.out is None:
            raise OSError("%s: not connected" % self.label)
        return self.out.write(buf, len(buf) if nbytes is None else nbytes)

    def read_into(self, buf):
        """What has come in, into *buf*: how many bytes, or 0."""
        if self.inp is None:
            return 0
        return self.inp.readinto(buf) or 0

    def poll(self):
        """Run anything the link needs between touches."""

    def status(self):
        return self.label

    def close(self):
        if self.closed:
            return
        self.closed = True
        for port in (self.inp, self.out):
            if port is not None:
                try:
                    port.close()
                except Exception:  # noqa: BLE001 - closing the rest matters more
                    pass
        if self._closer is not None:
            self._closer()


class UsbLink(Link):
    """The board as a USB MIDI device."""

    def __init__(self, ports, itf, closer):
        Link.__init__(self, "usb", "USB", ports[1], ports[0], closer)
        self.itf = itf

    def status(self):
        is_open = getattr(self.itf, "is_open", None)
        if is_open is not None and not is_open():
            return "USB: waiting for a computer"
        return "USB: connected"


class HostLink(Link):
    """Every MIDI device on the board's USB host port."""

    def status(self):
        n = len(getattr(self.inp, "devices", ()) or ())
        if not n:
            return "USB host: plug a synth into the host port"
        return "USB host: %d device%s" % (n, "" if n == 1 else "s")


async def _yield():
    import asyncio

    await asyncio.sleep_ms(0)


class BleLink(Link):
    """BLE-MIDI, served from this board; a central connects to it.

    bledev runs on asyncio, and appkit runs no event loop, so `poll` runs
    the loop's ready tasks for one pass each time it's called.
    """

    def __init__(self, bledev_midi, ble, asyncio, name=BLE_NAME):
        Link.__init__(self, "ble", "BLE", None)
        self._midi = bledev_midi
        self._ble = ble
        self._asyncio = asyncio
        self.name = name
        self.state = "advertising as %s" % name
        self._task = asyncio.create_task(self._keep())

    async def _keep(self):
        while not self.closed:
            try:
                port = await self._midi.serve(self._ble, name=self.name)
            except Exception as e:  # noqa: BLE001 - say so, and advertise again
                self.state = str(e) or "couldn't advertise"
                await self._asyncio.sleep_ms(1000)
                continue
            self.out = self.inp = port
            self.state = "connected"
            while not self.closed and port.connection.is_connected():
                await self._asyncio.sleep_ms(200)
            self.out = self.inp = None
            if not self.closed:
                self.state = "disconnected, advertising as %s" % self.name

    def poll(self):
        self._asyncio.run(_yield())

    def read_into(self, buf):
        try:
            return Link.read_into(self, buf)
        except Exception:  # noqa: BLE001 - the link dropped; _keep advertises again
            self.out = self.inp = None
            return 0

    def status(self):
        return "BLE: %s" % self.state

    def close(self):
        port = self.out
        self.closed = True
        self.out = self.inp = None
        if port is not None:
            try:
                self._asyncio.run(port.close())
            except Exception:  # noqa: BLE001 - it's gone either way
                pass
        self._task.cancel()
        try:
            self.poll()
        except Exception:  # noqa: BLE001
            pass


#: The platforms that are a browser page.
BROWSERS = ("webassembly", "emscripten")
#: The platforms whose MIDI ports the Connections picker lists: computers and browser pages.
CONNECTED_PLATFORMS = ("win32", "linux", "darwin") + BROWSERS


def _chosen():
    """``(endpointkit, midiports.endpoints)`` with this device's MIDI ports
    registered, or None where the picker lists none (a board, or neither
    library installed)."""
    if sys.platform not in CONNECTED_PLATFORMS:
        return None
    try:
        import endpointkit
        from midiports import endpoints
    except ImportError:
        return None
    try:
        endpoints.register()  # the Shell's picker registers them too: whichever is first
    except OSError:  # no MIDI ports on this computer's system
        return None
    return endpointkit, endpoints


class ChosenLink(Link):
    """The MIDI outputs chosen in the Connections picker, all at once, and the inputs chosen there for feedback.

    The ports are the picker's: closing the link leaves them open for the
    next program.
    """

    def __init__(self, key, kit, endpoints, first=False):
        Link.__init__(self, key, "MIDI out", endpoints.fan_out(), endpoints.merged_in())
        self._kit = kit
        self._first = first

    def poll(self):
        kit = self._kit
        if self._first and not kit.selection("midi.out"):
            # Allowed now: play the first output, as a board plays its first way out.
            for ep in kit.endpoints("midi.out"):
                if ep.state in (kit.AVAILABLE, kit.CONNECTED):
                    kit.select("midi.out", ep.id)
                    self.key = "out:" + ep.id
                    self._first = False
                    break

    def names(self):
        """What the controller plays now, for a person: the chosen outputs' names."""
        kit = self._kit
        chosen = kit.selected("midi.out")
        if chosen:
            return ", ".join(ep.label for ep in chosen)
        for ep in kit.endpoints("midi.out"):
            if ep.state == kit.NEEDS_PAIRING:
                return "allow MIDI when the browser asks"
            if ep.state == kit.UNAVAILABLE:
                return ep.caps.get("why") or ep.label
        if kit.selection("midi.out"):
            return "waiting for %s" % kit.selection("midi.out")[0].split(":", 1)[-1]
        return "nothing chosen"

    def status(self):
        return "MIDI out: %s" % self.names()

    def close(self):
        self.closed = True


def choices():
    """``[(key, label), ...]``: each way out this board has."""
    out = []
    if sys.platform in BROWSERS:
        # A page has no USB port or radio of its own: a build that carries
        # the USB host's module for boards still reaches no device from here.
        return _connected(out)
    try:
        import machine

        if hasattr(machine, "USBDevice"):
            import usb.device.midi  # noqa: F401 - usb-device-midi is what the link needs
            from midiports import usb_device  # noqa: F401

            out.append(("usb", "USB device"))
    except ImportError:
        pass
    try:
        import _usbhost

        if hasattr(_usbhost, "host_start"):
            from midiports import usb_host  # noqa: F401

            out.append(("host", "USB host"))
    except ImportError:
        pass
    try:
        import bledev.auto

        # A browser's and a desktop's BLE (webble, bleak) are central only,
        # and the controller has to be the peripheral a computer connects to.
        if bledev.auto.backend_name() not in (None, "webble", "bleak"):
            import bledev.midi  # noqa: F401

            out.append(("ble", "Bluetooth LE"))
    except ImportError:
        pass
    return _connected(out)


def _connected(out):
    """*out* with the MIDI outputs the Connections picker lists added."""
    chosen = _chosen()
    if chosen is not None:
        kit = chosen[0]
        for ep in kit.endpoints("midi.out"):
            if ep.state != kit.UNAVAILABLE:
                out.append(("out:" + ep.id, ep.label))
    return out


def missing():
    """A line saying what this board lacks, for when `choices` is empty."""
    chosen = _chosen()
    if chosen is not None:
        kit = chosen[0]
        for ep in kit.endpoints("midi.out"):
            if ep.state == kit.UNAVAILABLE and ep.caps.get("why"):
                return "No MIDI out here: %s." % ep.caps["why"]
        return "No MIDI out here: plug in a MIDI device or start a synth, then choose it in Connections."
    if sys.platform in BROWSERS:
        return "No Web MIDI here: this page needs midiports and endpointkit."
    return ("No way out for MIDI here: this needs a USB device or host port with midiports, "
            "Bluetooth LE with bledev, or a computer's MIDI ports with endpointkit.")


def _start_host():
    import usb.core

    # A synth is a full-speed device, and full speed reaches one behind a
    # hub too. A host that already ran at high speed since power-up can't
    # change on a board whose hub can't be power-cycled, so it stays there.
    try:
        usb.core.start(full_speed=True)
    except OSError as e:
        if e.args and e.args[0] != 95:  # EOPNOTSUPP: an earlier app ran it at high speed
            raise
        usb.core.start()
    return usb.core


def _free_port():
    """Stop a USB host that holds the one USB port of an ESP32-S2 or S3.

    The device has to start after the host stops: started while a host
    runs, it never enumerates, and stopping the host afterwards doesn't
    bring it back until the board resets.
    """
    if not any(chip in getattr(sys.implementation, "_machine", "") for chip in ("ESP32S2", "ESP32S3")):
        return
    try:
        import usb.core
    except ImportError:
        return
    if usb.core.running():
        usb.core.stop()
        print("midicontroller: stopped the USB host, which shares this board's USB port")


def open_link(key):
    """Open the way out named *key*, one of `choices`' keys."""
    if key == "usb":
        import usb.device
        from midiports import usb_device

        _free_port()
        itf = usb_device.MIDIPortsInterface()
        usb.device.get().init(itf, builtin_driver=True)

        def give_back():
            # The port is the board's serial port alone again.
            usb.device.get().init(builtin_driver=True)

        return UsbLink(itf.ports, itf, give_back)
    if key == "host":
        from midiports import usb_host

        core = _start_host()
        inp, out = usb_host.all_ports()
        return HostLink("host", "USB host", out, inp, core.stop)
    if key == "ble":
        import asyncio

        import bledev.auto
        import bledev.midi

        return BleLink(bledev.midi, bledev.auto.adapter(), asyncio)
    if key.startswith("out:"):
        chosen = _chosen()
        if chosen is None:
            raise OSError("no MIDI ports to choose from here")
        kit, endpoints = chosen
        ep_id = key[4:]
        ep = kit.find(ep_id)
        first = ep is not None and ep.state == kit.NEEDS_PAIRING
        if first:
            kit.pair(ep_id)  # the browser asks the person
        elif ep is not None and ep.state == kit.UNAVAILABLE:
            raise OSError(ep.caps.get("why") or "%s isn't available" % ep.label)
        else:
            # Chosen for the whole device; one not plugged in yet is used when it is.
            kit.select("midi.out", ep_id)
        return ChosenLink(key, kit, endpoints, first)
    raise ValueError("no MIDI link %r" % (key,))
