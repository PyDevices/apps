# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""MIDI in: every keyboard the program can reach, read as one stream.

On a board with a USB host port that's every MIDI device plugged into it,
merged by ``midiports.usb_host.all_ports()``; devices plugged in later are
heard too. A board without one whose ``board_peripherals`` lists a
``usb_midi`` role becomes a USB MIDI device the computer plays. On Windows
and Linux it's every MIDI input port the computer has, through
``midiports.windows`` or ``midiports.linux``. In a browser it's every MIDI
input the browser offers, through ``midiports.webmidi``.

Bluetooth MIDI is one more input, on a board whose firmware has Bluetooth LE:
`Inputs.set_ble` makes the board a BLE-MIDI instrument, advertised under the
app's name, that a controller, a phone or a computer connects to, through
``midiports.ble``. It's off until the player turns it on, so nothing about
Bluetooth starts or takes memory before then.

`Parser` turns the bytes into calls on an object you pass, with no
allocation per message, so a quiet keyboard costs nothing beside the audio.
"""

import sys

#: Ask the USB host for full speed: a full-speed keyboard behind a hub on
#: the board's host port is only heard that way, and a high-speed device
#: falls back to full speed, which is plenty for MIDI.
USB_FULL_SPEED = True
#: What ``Inputs.why`` says when a computer has no MIDI input at all.
NO_INPUT = "no MIDI input on this computer"
#: The platforms that are a computer, with MIDI ports of their own.
DESKTOPS = ("win32", "linux", "darwin")
#: The most reads of one port in one poll.
READS_PER_POLL = 64
#: The name a board advertises its Bluetooth MIDI under.
BLE_NAME = "Synth Station"


def ble_available():
    """True on a board whose firmware has Bluetooth LE, as
    ``midiports.ble.available()`` says, without importing the port: that
    waits until the player turns it on. Starts nothing."""
    if sys.implementation.name not in ("micropython", "circuitpython"):
        return False
    if sys.platform in ("webassembly", "emscripten"):
        return False
    for name in ("bluetooth", "_bleio"):
        try:
            __import__(name)
            return True
        except ImportError:
            pass
    return False


def _name(dev):
    """A USB device's product string, or its vid:pid when it has none."""
    try:
        product = dev.product
    except Exception:  # a device that won't answer a string request
        product = None
    return product or "%04x:%04x" % (dev.idVendor, dev.idProduct)


class Inputs:
    """The open MIDI inputs, read together.

    ``kind`` is ``"usb"``, ``"device"``, ``"desktop"``, ``"web"`` or None when there's nothing to
    open; ``why`` then says why in a sentence. ``names()`` lists the
    devices heard now.
    """

    def __init__(self):
        self.kind = None
        self.why = None
        self.ports = []
        self._desktop_names = []
        self._usb = False
        self._buf = bytearray(64)
        #: The Bluetooth MIDI input while it's on, and why it stopped if it did.
        self.ble = None
        self.ble_why = None

    # ---- opening --------------------------------------------------------------

    def open(self):
        """Open whatever this computer or board has. Never raises."""
        # A computer reads its own MIDI ports, even where a usb.core is
        # importable (PyUSB, or a desktop build that carries the package).
        if getattr(sys, "platform", "") in DESKTOPS:
            self._open_desktop()
            return self
        if getattr(sys, "platform", "") == "webassembly":
            self._open_web()
            return self
        try:
            import usb.core

            start = usb.core.start  # PyUSB on a desktop has no host to start
        except (ImportError, AttributeError):
            start = None
        if start is not None:
            try:
                from midiports import usb_host
            except ImportError:
                self.why = "midiports isn't installed"
                return self
            try:
                start(full_speed=USB_FULL_SPEED)
                self._usb = True
                port, out = usb_host.all_ports()
                if out is not None:
                    out.close()
            except Exception as e:
                self.why = "the USB host didn't start: %s" % (e,)
                return self
            self.ports = [port]
            self.kind = "usb"
            return self
        if self._open_device():
            return self
        self._open_desktop()
        return self

    def _open_device(self):
        """Make this board a USB MIDI device, where its board says it may
        (a ``usb_midi`` role): starting one re-enumerates the USB port."""
        try:
            import board_peripherals as bp
        except ImportError:
            return False
        if "usb_midi" not in getattr(bp, "PERIPHERALS", ()):
            return False
        try:
            port, _out = bp.usb_midi()
        except Exception as e:
            self.why = "the USB MIDI device didn't start: %s" % (e,)
            return True
        self.ports = [port]
        self.kind = "device"
        return True

    def _open_desktop(self):
        platform = getattr(sys, "platform", "")
        try:
            import midiports

            if platform.startswith("win"):
                from midiports import windows as backend
            elif platform.startswith("linux"):
                from midiports import linux as backend
            else:
                self.why = "no MIDI ports on this platform"
                return
        except ImportError:
            self.why = "midiports isn't installed"
            return
        try:
            found = [p for p in backend.available() if p.direction in (midiports.IN, midiports.INOUT)]
        except Exception as e:
            self.why = "couldn't list MIDI ports: %s" % (e,)
            return
        for info in found:
            try:
                midi_in, midi_out = backend.ports(info.name)
            except Exception:
                continue
            if midi_out is not None:
                midi_out.close()
            if midi_in is not None:
                self.ports.append(midi_in)
                self._desktop_names.append(info.name)
        if self.ports:
            self.kind = "desktop"
        else:
            self.why = NO_INPUT

    def _open_web(self):
        try:
            from midiports import webmidi
        except ImportError:
            self.why = "midiports isn't installed"
            return
        self.ports = [webmidi.page_in()]
        self.kind = "web"

    def set_ble(self, on, parser=None, name=BLE_NAME):
        """Turn the Bluetooth MIDI input on or off. Turning it on starts
        advertising as *name*; an error starting it is raised. Turning it
        off hands *parser* a note-off for every note it left sounding."""
        if on and self.ble is None:
            from midiports import ble

            self.ble_why = None
            try:
                self.ble, _out = ble.ports(name)  # the output stays unused: closing it closes the link
            except Exception as e:
                self.ble_why = str(e) or type(e).__name__
                raise
        elif not on and self.ble is not None:
            port = self.ble
            self.ble = None
            port.close()
            if parser is not None:
                buf = self._buf
                try:
                    for _ in range(READS_PER_POLL):
                        n = port.readinto(buf)
                        if not n:
                            break
                        parser.feed(buf, n)
                except Exception as e:  # the link had stopped: said, as in poll
                    self.ble_why = str(e) or type(e).__name__

    def ble_text(self):
        """What the Bluetooth MIDI input is doing, for the status line, or
        None while it's off."""
        port = self.ble
        if port is None:
            return "Bluetooth MIDI stopped: %s" % (self.ble_why,) if self.ble_why else None
        if port.state == "connected":
            return "Bluetooth"
        return "Bluetooth: waiting as %s" % (port.name,)

    # ---- reading --------------------------------------------------------------

    def names(self):
        """The devices heard now, as a list of strings."""
        if self.kind == "usb":
            found = [_name(d) for d in getattr(self.ports[0], "devices", ())]
        elif self.kind == "web":
            found = list(self.ports[0].names)
        elif self.kind == "device":
            found = ["USB MIDI"]
        else:
            found = list(self._desktop_names)
        if self.ble is not None and self.ble.state == "connected":
            found.append("Bluetooth")
        return found

    def poll(self, parser):
        """Feed everything waiting on every port to *parser*."""
        buf = self._buf
        ble = self.ble
        if ble is not None:
            try:
                for _ in range(READS_PER_POLL):
                    n = ble.readinto(buf)
                    if not n:
                        break
                    parser.feed(buf, n)
            except Exception as e:  # the link stopped: said on the status line, not retried
                self.ble = None
                self.ble_why = str(e) or type(e).__name__
                ble.close()
        for port in self.ports:
            any_ = getattr(port, "any", None)
            # Ask first where the port can say: reading an empty USB port
            # still costs a transfer.
            if any_ is not None and not any_():
                continue
            # A merged port hands over one message a read, so read until
            # it's empty, but leave a flood for the next tick.
            for _ in range(READS_PER_POLL):
                n = port.readinto(buf)
                if not n:
                    break
                parser.feed(buf, n)

    def close(self):
        self.set_ble(False)
        ports = self.ports
        self.ports = []
        for port in ports:
            try:
                port.close()
            except Exception:
                pass
        if self._usb:
            self._usb = False
            try:
                import usb.core

                usb.core.stop()
            except Exception:
                pass


class Parser:
    """MIDI bytes to calls on *sink*, from every channel.

    *sink* has ``note_on(note, velocity, channel)``, ``note_off(note, channel)``,
    ``control(controller, value, channel)``, ``bend(value, channel)`` (0 to
    16383, centre 8192) and ``program(number, channel)``, with channels
    counted from 0. Running status is followed; SysEx, real-time and system
    common messages are skipped.
    """

    def __init__(self, sink):
        self.sink = sink
        self._status = 0
        self._first = -1
        self._sysex = False

    def feed(self, buf, n):
        sink = self.sink
        for i in range(n):
            b = buf[i]
            if b >= 0xF8:  # real time: may land anywhere, even mid-message
                continue
            if b >= 0x80:
                self._first = -1
                self._sysex = b == 0xF0
                # System common carries no running status: drop its data.
                self._status = b if b < 0xF0 else 0
                continue
            status = self._status
            if self._sysex or not status:
                continue
            kind = status & 0xF0
            if kind == 0xC0:
                sink.program(b, status & 0x0F)
                continue
            if kind == 0xD0:
                continue
            if self._first < 0:
                self._first = b
                continue
            first = self._first
            self._first = -1
            if kind == 0x90:
                if b:
                    sink.note_on(first, b, status & 0x0F)
                else:
                    sink.note_off(first, status & 0x0F)
            elif kind == 0x80:
                sink.note_off(first, status & 0x0F)
            elif kind == 0xB0:
                sink.control(first, b, status & 0x0F)
            elif kind == 0xE0:
                sink.bend(first | (b << 7), status & 0x0F)
