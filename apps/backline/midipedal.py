# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Play Backline from a MIDI foot controller: each switch learned, then bound
to a pedal or to one action.

A `MidiPedal` holds four slots, one for each switch. Arm a slot with
`MidiPedal.learn` and press the switch: the message it sends fills the slot.
Then bind the slot to one of `BINDINGS`:

- ``"pedal_a"`` or ``"pedal_b"``: the switch is that pedal, with its taps,
  holds and double taps. The switch must say when it goes down and when it
  comes up: a controller change of 64 or more and then one below 64 (a
  momentary switch), or a note on and then its note off.
- ``"start"``, ``"fill"``, ``"next"``, ``"outro"``, ``"stop"`` or
  ``"tap_tempo"``: the switch does that one thing each time it's pressed. A
  program change, or a controller that only ever sends one value, can only
  do this, since it never says when the foot comes up.

Messages that no slot holds are ignored, so the same port can carry a
keyboard or a clock.

The map saves as plain lists and strings (`MidiPedal.saved`), so it goes in
the app's settings as it is. `open_input` opens the MIDI input that
settings name; it is the one place that knows how.

Example::

    pedals = MidiPedal(on_pedal=box.pedal, on_action=box.action)
    pedals.learn(0)
    pedals.feed(b"\\xb0\\x50\\x7f")   # switch 1 sends CC 80 = 127: slot 1 learns it
    pedals.feed(b"\\xb0\\x50\\x7f")   # pedal A goes down
    pedals.feed(b"\\xb0\\x50\\x00")   # and comes up: a tap
"""

try:
    from time import ticks_diff
except ImportError:  # CPython
    def ticks_diff(a, b):
        return a - b

CC = "cc"
NOTE = "note"
PC = "pc"

#: What a slot can be bound to, in the order a menu lists them.
BINDINGS = ("pedal_a", "pedal_b", "start", "fill", "next", "outro", "stop", "tap_tempo", "none")
#: A short name for each, for a menu.
LABELS = {"pedal_a": "Pedal A", "pedal_b": "Pedal B", "start": "Start", "fill": "Fill", "next": "Next part",
          "outro": "Outro", "stop": "Stop", "tap_tempo": "Tap tempo", "none": "Nothing"}
#: The bindings that need a press and a release, and which pedal each is.
PEDALS = {"pedal_a": 0, "pedal_b": 1}
#: What a learned switch that can't be a pedal is bound to instead.
ONE_SHOT = "fill"

SLOTS = 4
#: Switch 1 is the main pedal, 2 the second pedal, 3 taps the tempo and 4
#: stops. No message is filled in: learn each switch, since a foot
#: controller's factory messages differ from one model to the next.
DEFAULT = ("pedal_a", "pedal_b", "tap_tempo", "stop")


def new_slots():
    return [{"msg": None, "bind": b} for b in DEFAULT]


def describe_msg(msg):
    """``"CC 80 ch 1"``, ``"Note 36 ch 10"``, ``"PC 3 ch 1"``, or ``"-"``."""
    if not msg:
        return "-"
    kind, ch, num = msg
    return "%s %d ch %d" % ({CC: "CC", NOTE: "Note", PC: "PC"}.get(kind, kind), num, ch + 1)


def can_pedal(msg):
    """Whether a switch sending ``msg`` can say when it comes up."""
    return not msg or msg[0] != PC


def messages(data):
    """``(status, data1, data2)`` for each channel message in ``data``.

    Whole messages, as midiports' inputs hand them out. System messages
    (clock, SysEx) are skipped, and so is a stray data byte."""
    i = 0
    n = len(data)
    while i < n:
        status = data[i]
        if status < 0x80:
            i += 1
            continue
        if status >= 0xF0:
            if status == 0xF0:
                while i < n and data[i] != 0xF7:
                    i += 1
            elif status in (0xF1, 0xF3):
                i += 1
            elif status == 0xF2:
                i += 2
            i += 1
            continue
        size = 2 if (status & 0xE0) == 0xC0 else 3
        if i + size > n:
            return
        yield status, data[i + 1], data[i + 2] if size == 3 else 0
        i += size


def read(status, d1, d2):
    """``(msg, press)``: what a message is, as a slot stores it, and whether
    it is a switch going down (True), coming up (False), or neither (None,
    and ``msg`` None)."""
    kind = status & 0xF0
    ch = status & 0x0F
    if kind == 0xB0:
        return [CC, ch, d1], d2 >= 64
    if kind == 0x90:
        return [NOTE, ch, d1], d2 > 0
    if kind == 0x80:
        return [NOTE, ch, d1], False
    if kind == 0xC0:
        return [PC, ch, d1], True
    return None, None


class TapTempo:
    """A tempo from taps: the average of the last few gaps between them.

    A gap longer than ``reset_ms`` starts again, so the first tap after a
    pause is the first of a new count.
    """

    def __init__(self, reset_ms=2000, keep=4, lo=40.0, hi=240.0):
        self.reset_ms = reset_ms
        self.keep = keep
        self.lo = lo
        self.hi = hi
        self.taps = []

    def tap(self, now):
        """A tap at ``now`` (ms). Returns the tempo in BPM once two taps
        are close enough, else None."""
        if self.taps and ticks_diff(now, self.taps[-1]) > self.reset_ms:
            self.taps = []
        self.taps.append(now)
        self.taps = self.taps[-(self.keep + 1):]
        if len(self.taps) < 2:
            return None
        span = ticks_diff(self.taps[-1], self.taps[0]) / (len(self.taps) - 1)
        if span <= 0:
            return None
        return max(self.lo, min(self.hi, round(60000.0 / span, 1)))


class MidiPedal:
    """Four learned switches, each a pedal or an action.

    Args:
        slots: the saved map (`saved`), or None for `DEFAULT`.
        on_pedal: ``on_pedal(which, down)`` when a pedal-bound switch moves.
        on_action: ``on_action(name)`` when an action-bound switch is pressed.
        on_change: ``on_change()`` when a slot is learned or bound.
    """

    def __init__(self, slots=None, on_pedal=None, on_action=None, on_change=None):
        self.slots = new_slots()
        if slots:
            for i, s in enumerate(slots[:SLOTS]):
                msg = s.get("msg")
                bind = s.get("bind")
                self.slots[i] = {"msg": list(msg) if msg else None,
                                 "bind": bind if bind in BINDINGS else DEFAULT[i]}
        self.on_pedal = on_pedal
        self.on_action = on_action
        self.on_change = on_change
        #: The slot waiting for a switch, or None.
        self.learning = None
        #: The last message read, as `describe_msg` says it, for a screen.
        self.last = ""
        self.down = [False] * SLOTS
        self._buf = bytearray(64)

    # -- the map ------------------------------------------------------------------

    def learn(self, i):
        """Fill slot ``i`` from the next switch pressed; None (or -1) stops."""
        self.learning = i if i is not None and 0 <= i < SLOTS else None
        self._changed()

    def bind(self, i, binding):
        """Bind slot ``i`` to one of `BINDINGS`.

        Raises:
            ValueError: ``binding`` isn't one, or it is a pedal and the
                slot's switch sends a program change, which has no release.
        """
        if binding not in BINDINGS:
            raise ValueError("bind a switch to one of %s, not %r" % (", ".join(BINDINGS), binding))
        if binding in PEDALS and not can_pedal(self.slots[i]["msg"]):
            raise ValueError("a program change never says the switch came up: bind it to an action")
        self._let_go(i)
        self.slots[i]["bind"] = binding
        self._changed()

    def clear(self, i):
        """Forget slot ``i``'s message."""
        self._let_go(i)
        self.slots[i]["msg"] = None
        self._changed()

    def saved(self):
        """The map, as settings keep it."""
        return [{"msg": s["msg"], "bind": s["bind"]} for s in self.slots]

    def describe(self):
        """The map and what can be chosen, for a panel."""
        return {"slots": self.saved(), "learning": -1 if self.learning is None else self.learning,
                "bindings": [[b, LABELS[b]] for b in BINDINGS], "last": self.last}

    def _changed(self):
        if self.on_change is not None:
            self.on_change()

    def _let_go(self, i):
        """A pedal that is down when its slot changes comes up, so it never sticks."""
        if self.down[i]:
            self.down[i] = False
            which = PEDALS.get(self.slots[i]["bind"])
            if which is not None and self.on_pedal is not None:
                self.on_pedal(which, False)

    # -- what arrives ---------------------------------------------------------------

    def read_port(self, port):
        """Everything waiting on a midiports input. Returns how many bytes."""
        got = 0
        buf = self._buf
        while port.any():
            n = port.readinto(buf)
            if not n:
                break
            got += n
            self.feed(memoryview(buf)[:n])
        return got

    def feed(self, data):
        """Act on the MIDI bytes in ``data``."""
        for status, d1, d2 in messages(data):
            self.handle(status, d1, d2)

    def handle(self, status, d1, d2):
        """Act on one channel message. Returns the slot it moved, or None."""
        msg, press = read(status, d1, d2)
        if msg is None:
            return None
        self.last = describe_msg(msg)
        if self.learning is not None:
            if not press:
                return None           # the foot coming up from before the slot was armed
            return self._learn(msg)
        for i, s in enumerate(self.slots):
            if s["msg"] == msg:
                self._act(i, s, press)
                return i
        return None

    def _learn(self, msg):
        i = self.learning
        self.learning = None
        for j, s in enumerate(self.slots):
            if j != i and s["msg"] == msg:     # one switch, one slot
                self._let_go(j)
                s["msg"] = None
        self._let_go(i)
        slot = self.slots[i]
        slot["msg"] = msg
        if slot["bind"] in PEDALS and not can_pedal(msg):
            slot["bind"] = ONE_SHOT
        self._changed()
        return i

    def _act(self, i, slot, press):
        bind = slot["bind"]
        which = PEDALS.get(bind)
        if which is not None:
            if press == self.down[i]:
                return                 # a repeat of where the switch already is
            self.down[i] = press
            if self.on_pedal is not None:
                self.on_pedal(which, press)
            return
        if press and bind != "none" and self.on_action is not None:
            self.on_action(bind)


def open_input(prefs=None, spec=None):
    """The MIDI input Backline reads its switches from, or None for none.

    ``spec``, else ``prefs["midi_in"]``, else ``$BACKLINE_MIDI``, as
    ``KIND`` or ``KIND:NAME``:

    - ``picker``: whatever MIDI inputs the device picker has chosen
      (endpointkit's ``midi.in``), read as one.
    - ``windows:NAME`` or ``linux:NAME``: a computer's MIDI port whose name
      holds NAME, such as a foot controller paired over Bluetooth or plugged
      in over USB.
    - ``usb_host``: every USB MIDI device plugged into the board.
    - ``usb_device``: the board as a USB MIDI device, played from a computer.
    - ``ble:NAME``: the board advertises Bluetooth LE MIDI as NAME, and a
      phone, a computer or a controller that connects plays it.
    - ``uart:ID:RX``: 5-pin DIN or TRS MIDI on UART ``ID``, pin ``RX``.

    Raises:
        ValueError: The kind isn't one of these.
        ImportError: midiports, or what the kind needs, isn't installed.
        OSError: No port of that name.
    """
    if spec is None and prefs is not None:
        spec = prefs.get("midi_in")
    if spec is None:
        import os

        getenv = getattr(os, "getenv", None)
        spec = getenv("BACKLINE_MIDI") if getenv is not None else None
    if not spec:
        return None
    kind, _, name = spec.partition(":")
    if kind == "picker":
        from midiports import endpoints

        endpoints.register()
        return endpoints.merged_in()
    if kind == "windows":
        from midiports import windows as host
    elif kind == "linux":
        from midiports import linux as host
    else:
        host = None
    if host is not None:
        midi_in, _out = host.ports(name)
        if midi_in is None:
            raise OSError("no MIDI input named %r" % (name,))
        return midi_in
    if kind == "usb_host":
        from midiports import usb_host

        return usb_host.all_ports()[0]
    if kind == "usb_device":
        from midiports import usb_device

        return usb_device.ports()[0]
    if kind == "ble":
        from midiports import ble

        return ble.ports(name or "Backline")[0]
    if kind == "uart":
        from midiports import uart

        uid, _, rx = name.partition(":")
        return uart.ports(int(uid), rx=int(rx))[0]
    raise ValueError("MIDI in from picker, windows:NAME, linux:NAME, usb_host, usb_device, ble:NAME or uart:ID:RX, "
                     "not %r" % (spec,))
