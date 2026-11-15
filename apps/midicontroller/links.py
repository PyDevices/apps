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
``pc:<name>``
    One of a computer's MIDI outputs, by name: a synth, a DAW's virtual
    port, a loopback. On Windows and Linux, with midiports.
``web:<name>``
    In a browser page, one of the MIDI outputs Web MIDI offers, by name,
    through midiports' ``webmidi``. The browser asks the person first;
    until they answer there is one choice, ``web``, the first output.

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


class WebLink(Link):
    """A browser's MIDI output, and its input of the same name for feedback."""

    def status(self):
        name = getattr(self.out, "name", None)
        if name:
            return "Web MIDI: %s" % name
        why = getattr(self.out, "why", None)
        if why:
            return "Web MIDI: %s" % why
        return "Web MIDI: waiting for the browser (allow MIDI if it asks)"


_web_outputs = None


def _webmidi():
    """midiports' webmidi if this is a browser page that can send, or None."""
    if sys.platform not in ("webassembly", "emscripten"):
        return None
    try:
        from midiports import webmidi
    except ImportError:
        return None
    return webmidi if hasattr(webmidi, "page_out") else None


def _desktop():
    """midiports' module for this computer's own ports, or None."""
    try:
        if sys.platform == "win32":
            from midiports import windows

            return windows
        if sys.platform == "linux":
            from midiports import linux

            return linux
    except ImportError:
        pass
    return None


def choices():
    """``[(key, label), ...]``: each way out this board has."""
    out = []
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
    desk = _desktop()
    if desk is not None:
        try:
            for p in desk.available():
                if p.direction == "out":
                    out.append(("pc:" + p.name, p.name))
        except Exception:  # noqa: BLE001 - no MIDI service: offer none
            pass
    webmidi = _webmidi()
    if webmidi is not None:
        global _web_outputs
        if _web_outputs is None:
            _web_outputs = webmidi.page_out()  # asks the browser now, and lists its outputs
        names = _web_outputs.names
        out.extend(("web:" + n, n) for n in names)
        if not names:
            out.append(("web", "Web MIDI"))
    return out


def missing():
    """A line saying what this board lacks, for when `choices` is empty."""
    if sys.platform in ("webassembly", "emscripten"):
        return "No Web MIDI here: this page needs midiports' webmidi with page_out."
    return ("No way out for MIDI here: this needs a USB device or host port with midiports, "
            "Bluetooth LE with bledev, or a computer's MIDI ports.")


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


def open_link(key):
    """Open the way out named *key*, one of `choices`' keys."""
    if key == "usb":
        import usb.device
        from midiports import usb_device

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
    if key.startswith("pc:"):
        name = key[3:]
        desk = _desktop()
        if desk is None:
            raise OSError("no MIDI ports on this computer")
        outs = [p for p in desk.available() if p.direction == "out" and p.name == name]
        if not outs:
            raise OSError("no MIDI output named %r" % name)
        ins = [p for p in desk.available() if p.direction == "in" and p.name == name]
        out = desk.open_port(outs[0])
        try:
            inp = desk.open_port(ins[0]) if ins else None
        except OSError:
            inp = None  # another program holds it: send without feedback
        return Link(key, name, out, inp)
    if key == "web" or key.startswith("web:"):
        webmidi = _webmidi()
        if webmidi is None:
            raise OSError("no Web MIDI output in this page")
        name = key[4:]
        out = webmidi.page_out(name)
        try:
            inp = webmidi.page_in(name)
        except Exception:  # noqa: BLE001 - send without feedback
            inp = None
        return WebLink(key, "Web MIDI", out, inp)
    raise ValueError("no MIDI link %r" % (key,))
