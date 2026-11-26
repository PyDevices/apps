# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The tester's side: a gamepad on the USB host port, read as it changes.

`Watch` looks for a gamepad, reads its events and keeps what it holds now,
and finds it again after it's unplugged. It takes ``usb.core`` and
``usb.host.hid_generic`` as arguments, so the tests hand it stand-ins.
`PageWatch` is the same for a browser page: the pad chosen for ``gamepad``
in Connections, or the first the browser shows, read through the Gamepad
API.
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
#: sensors: tilting left and right (roll), moving up and down (lift),
#: tilting forward and back (pitch), and turning flat (yaw).
EXTRA_NAMES = {
    0xFF000020: "Rt", 0xFF000021: "Lt", 0xFF000022: "Up", 0xFF000023: "Dn",
    0xFF000024: "Y", 0xFF000025: "B", 0xFF000026: "A", 0xFF000027: "X",
    0xFF000028: "LB", 0xFF000029: "RB", 0xFF00002A: "LT", 0xFF00002B: "RT",
    0xFF00002C: "roll", 0xFF00002D: "lift", 0xFF00002E: "pitch", 0xFF00002F: "yaw",
}
#: The order the vendor values that aren't a button's go in on the screen:
#: the d-pad's pressure clockwise from up, then the motion sensors.
EXTRA_ORDER = (0xFF000022, 0xFF000020, 0xFF000023, 0xFF000021, 0xFF00002C, 0xFF00002D, 0xFF00002E, 0xFF00002F)
#: Which button each pressure value belongs to, on a pad in the PS3 layout:
#: 1 is the left face button, 2 the bottom, 3 the right, 4 the top, then the
#: shoulders and triggers, as that layout numbers them.
PRESSURE_OF = {
    0xFF000027: 1, 0xFF000026: 2, 0xFF000025: 3, 0xFF000024: 4,
    0xFF000028: 5, 0xFF000029: 6, 0xFF00002A: 7, 0xFF00002B: 8,
}
#: Vendor values that rest in the middle and move only a little either way,
#: drawn as a bar from the middle: (middle, how far either way fills it). A
#: PS3-layout pad's yaw sensor gives about 120 either side of 512 for a
#: quick turn.
CENTRED = {0xFF00002F: (512, 128)}
#: What a pad in the PS3 layout calls each button, by number.
BUTTON_NAMES = ("X", "A", "B", "Y", "LB", "RB", "LT", "RT", "Back", "Start", "L3", "R3", "Home")
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


#: What the tester says in a browser without gamepads.
NO_GAMEPAD_API = "This browser has no Gamepad API"
#: The browser's standard gamepad layout, as the tester names its axes: the
#: left stick, then the right.
PAGE_AXES = (0x010030, 0x010031, 0x010032, 0x010035)
#: The standard layout's d-pad buttons (up, down, left, right), counted from 1,
#: which the tester shows as a hat.
PAGE_DPAD = (13, 14, 15, 16)
#: Hat directions for the d-pad's buttons held (up, down, left, right):
#: 0 up, clockwise to 7 up-left.
_HAT_OF = {
    (1, 0, 0, 0): 0, (1, 0, 0, 1): 1, (0, 0, 0, 1): 2, (0, 1, 0, 1): 3,
    (0, 1, 0, 0): 4, (0, 1, 1, 0): 5, (0, 0, 1, 0): 6, (1, 0, 1, 0): 7,
}

# Every pad the page sees, one per line: index, id, mapping, then the
# buttons' values and the axes' values, comma-separated.
_PADS = """() => {
    const nav = globalThis.navigator;
    if (!nav || !nav.getGamepads) return null;
    const lines = [];
    for (const pad of nav.getGamepads()) {
        if (!pad || !pad.connected) continue;
        lines.push([pad.index, pad.id.replace(/[\\t\\n]/g, ' '), pad.mapping,
            pad.buttons.map((b) => b.pressed ? Math.max(b.value, 0.5).toFixed(2) : b.value.toFixed(2)).join(','),
            pad.axes.map((a) => a.toFixed(3)).join(',')].join('\\t'));
    }
    return lines.join('\\n');
}"""


def page_pads(read=None):
    """The pads the browser shows this page, as ``(index, name, mapping,
    buttons, axes)``: buttons are 0.0 to 1.0, axes -1.0 to 1.0. None when the
    browser has no Gamepad API. *read* stands in for the browser in a test."""
    if read is None:
        import js

        read = js.eval(_PADS)
    text = read()
    if text is None:
        return None
    pads = []
    for line in str(text).split("\n") if text else ():
        index, name, mapping, buttons, axes = line.split("\t")
        pads.append((int(index), name, mapping,
                     [float(v) for v in buttons.split(",")] if buttons else [],
                     [float(v) for v in axes.split(",")] if axes else []))
    return pads


class _PagePad:
    """What the tester reads of a pad besides its state: ``axes``, the raw values."""

    def __init__(self):
        self.axes = {}


class PageWatch:
    """A gamepad the browser shows the page, read like `Watch` reads one on
    the USB host port: the one chosen for ``gamepad`` in Connections, or the
    first there is.

    Args:
        pads (callable): returns `page_pads`'s list; the browser's when None.
        chosen (callable): returns the names chosen for ``gamepad``;
            endpointkit's choice when None.
    """

    def __init__(self, pads=None, chosen=None):
        self._pads = pads or page_pads
        self._chosen = chosen or _chosen_pads
        self.pad = None
        self.name = None
        self.layout = None
        self.buttons = set()
        self.axes = {}
        self.hats = {}
        self.extras = []
        self.events = 0
        self.status = "no gamepad yet: press a button on one, and the browser shows it to the page"
        self._last = None

    def _pick(self, pads):
        """The chosen pad, by the name Connections lists it under (a second
        pad of the same name is "#2"), or the first when none is chosen."""
        names = self._chosen()
        if not names:
            return pads[0] if pads else None
        labels = []
        for pad in pads:
            label, n = pad[1], 2
            while label in labels:
                label = "%s #%d" % (pad[1], n)
                n += 1
            labels.append(label)
        for want in names:
            if want in labels:
                return pads[labels.index(want)]
        return None

    def poll(self, now_ms=None, since=None):
        """Read the chosen pad now. Returns True when anything changed."""
        pads = self._pads()
        if pads is None:
            changed = self.status != NO_GAMEPAD_API
            self.status = NO_GAMEPAD_API
            return changed
        pad = self._pick(pads)
        if pad is None:
            if self.pad is None:
                return False
            self.close()
            self.status = "the gamepad went: press a button on it again"
            return True
        index, name, mapping, buttons, axes = pad
        standard = mapping == "standard"
        dpad = PAGE_DPAD if standard and len(buttons) >= 16 else ()
        numbers = tuple(n for n in range(1, len(buttons) + 1) if n not in dpad)
        codes = PAGE_AXES[:len(axes)] if standard else tuple(0x010030 + i for i in range(len(axes)))
        layout = (numbers, codes, 1 if dpad else 0, ())
        changed = False
        if self.pad is None or self.name != name or self.layout != layout:
            self.pad = _PagePad()
            self.name = name
            self.layout = layout
            self.status = name
            changed = True
        held = {n for n in numbers if buttons[n - 1] >= 0.5}
        if held != self.buttons:
            self.buttons = held
            changed = True
        for code, value in zip(codes, axes):
            if self.axes.get(code) != value:
                self.axes[code] = value
                self.pad.axes[code] = int(value * 32767)
                changed = True
        if dpad:
            key = tuple(1 if buttons[n - 1] >= 0.5 else 0 for n in dpad)
            hat = _HAT_OF.get(key, -1)
            if self.hats.get(0, -1) != hat:
                self.hats[0] = hat
                changed = True
        if changed:
            self.events += 1
        return changed

    def close(self):
        self.pad = None
        self.name = None
        self.layout = None
        self.buttons = set()
        self.axes = {}
        self.hats = {}



def _chosen_pads():
    try:
        import endpointkit
    except ImportError:
        return []
    return [ep.label for ep in endpointkit.selected("gamepad")]
