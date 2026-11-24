# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The tester's side: a gamepad on the USB host port, read as it changes.

`Watch` looks for a gamepad, reads its events and keeps what it holds now,
and finds it again after it's unplugged. It takes ``usb.core`` and
``usb.host.hid_generic`` as arguments, so the tests hand it stand-ins.
"""

#: How often the tester looks for a gamepad while it has none, in ms.
LOOK_MS = 1000
#: The most events read in one `Watch.poll`, so a busy pad can't hold up the screen.
MOST = 64
#: Short names for the axes a gamepad can have, by hid_generic's Axis code.
AXIS_NAMES = {
    0x010030: "X",
    0x010031: "Y",
    0x010032: "Z",
    0x010033: "Rx",
    0x010034: "Ry",
    0x010035: "Rz",
    0x010036: "Slider",
    0x010037: "Dial",
    0x010038: "Wheel",
    0x0200BA: "Rudder",
    0x0200BB: "Throttle",
    0x0200C4: "Accel",
    0x0200C5: "Brake",
    0x0200C8: "Steer",
}
#: Short names for the vendor values many gamepads send after their sticks,
#: by usage: the PS3 layout's pressure for each control, then its motion
#: sensors (acceleration across, up and forward, and turning).
EXTRA_NAMES = {
    0xFF000020: "Rt", 0xFF000021: "Lt", 0xFF000022: "Up", 0xFF000023: "Dn",
    0xFF000024: "Y", 0xFF000025: "B", 0xFF000026: "A", 0xFF000027: "X",
    0xFF000028: "LB", 0xFF000029: "RB", 0xFF00002A: "LT", 0xFF00002B: "RT",
    0xFF00002C: "aX", 0xFF00002D: "aY", 0xFF00002E: "aZ", 0xFF00002F: "rot",
}
#: Each field in hid_generic's ``Gamepad.fields`` starts with its kind.
_BUTTON, _AXIS, _HAT = 0, 1, 2


def _name(dev):
    maker = getattr(dev, "manufacturer", None) or "%04x" % dev.idVendor
    product = getattr(dev, "product", None) or "%04x" % dev.idProduct
    return "%s %s" % (maker, product)


class Watch:
    """The gamepad on the host port, if there is one, and what it holds.

    Read `buttons` (the numbers held), `axes` (axis code to -1.0 to 1.0) and
    `hats` (hat index to 0 up to 7 up-left, clockwise, or -1 centred) after
    each `poll`, and `extras`, the pad's vendor values (pressure, motion) in
    its report's order. `layout` says which buttons, axes and hats the pad
    has, and the usage and range of each extra, and changes only when a
    different pad is found.
    """

    def __init__(self, core, hid_generic):
        self.core = core
        self.hid = hid_generic
        self.pad = None
        self.name = None
        self.layout = None
        self.buttons = set()
        self.axes = {}
        self.hats = {}
        self.extras = []
        self.events = 0
        self.status = "no gamepad yet: plug one into the USB host port"
        self._looked = None

    def _forget(self):
        self.pad = None
        self.name = None
        self.layout = None
        self.buttons = set()
        self.axes = {}
        self.hats = {}
        self.extras = []

    def look(self):
        """Look for a gamepad now. Returns True when one was found."""
        hid = self.hid
        dev = self.core.find(custom_match=hid.Gamepad.match)
        if dev is None:
            return False
        pad = hid.Gamepad(dev)
        buttons, axes, hats = [], [], 0
        for f in pad.fields:
            if f[0] == _BUTTON:
                buttons.append(f[6])
            elif f[0] == _AXIS:
                axes.append(f[6])
            elif f[0] == _HAT:
                hats += 1
        self.pad = pad
        self.name = _name(dev)
        # A library from before extras has none to give.
        extras = tuple(getattr(pad, "extra_info", ()))
        self.layout = (tuple(sorted(buttons)), tuple(axes), hats, extras)
        self.extras = list(getattr(pad, "extras", ()))
        self.status = self.name
        return True

    def poll(self, now_ms, since):
        """Read what the pad sent since the last poll. *now_ms* is the time
        and *since* a ``ticks_diff``-like function, so a pad that isn't there
        is looked for only every `LOOK_MS`. Returns True when anything changed."""
        if self.pad is None:
            if self._looked is not None and since(now_ms, self._looked) < LOOK_MS:
                return False
            self._looked = now_ms
            try:
                return self.look()
            except (OSError, ValueError) as e:
                # A device that went while it was being read, or one whose
                # descriptor isn't a pad's after all: say so, look again.
                self.status = "couldn't read the gamepad: %s" % (e,)
                return False
        pad, hid = self.pad, self.hid
        changed = False
        try:
            for _ in range(MOST):
                reports = getattr(pad, "reports", 0)
                ev = pad.read(1)  # ms; 0 would wait forever, as in pyusb
                if not ev:
                    # A report that only moved the extras makes no event:
                    # read on while reports still come.
                    if getattr(pad, "reports", 0) != reports:
                        continue
                    break
                changed = True
                self.events += 1
                kind = ev[0]
                if kind == hid.BUTTON_DOWN:
                    self.buttons.add(ev[1])
                elif kind == hid.BUTTON_UP:
                    self.buttons.discard(ev[1])
                elif kind == hid.AXIS:
                    self.axes[ev[1]] = pad.scaled(ev[1])
                elif kind == hid.HAT:
                    self.hats[ev[1]] = ev[2]
            extras = getattr(pad, "extras", None)
            if extras and extras != self.extras:
                self.extras = list(extras)
                changed = True
        except self.core.USBError:
            # Unplugged: drop it and look again.
            self.close()
            self.status = "the gamepad went: plug it in again"
            self._looked = now_ms
            return True
        return changed

    def close(self):
        pad = self.pad
        self._forget()
        if pad is not None:
            try:
                pad.close()
            except Exception as e:  # noqa: BLE001 - it's gone either way
                print("gamepad: closing the pad:", e)
