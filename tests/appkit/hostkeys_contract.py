# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit's hostkeys on real LVGL with no window: a USB keyboard on the
board's host port types into the focused field.

    python -m unittest discover -s tests/appkit -p test_hostkeys.py

The stand-in is the firmware's ``_usbhost`` C module, so omnipython's real
``usb.core``, ``usb.host.endpoints`` and ``usb.host.hid`` run on top of it:
keyboards are plugged in and pulled out by changing its list and counters,
and type by queueing boot-protocol reports on their interrupt endpoint.
``HOSTKEYS_USB_TREE`` holds those three modules in one ``usb`` package, and
``HOSTKEYS_ENDPOINTKIT`` is the folder endpointkit is in; test_hostkeys.py
sets both. ``HOSTKEYS_PLANT=<name>`` breaks the bridge one way from `PLANTS`,
and the checks must then fail. Exits 1 if a check fails, 2 if LVGL or the
USB packages aren't there.
"""

import os
import sys


def _up(path):
    return path.rsplit("/", 1)[0] if "/" in path else "."


_HERE = _up(__file__)
_TESTS = _up(_HERE)
_ROOT = _up(_TESTS)
_TREE = os.getenv("HOSTKEYS_USB_TREE")
_ENDPOINTKIT = os.getenv("HOSTKEYS_ENDPOINTKIT")
if not _TREE or not _ENDPOINTKIT:
    print("can't run the hostkeys checks: HOSTKEYS_USB_TREE and HOSTKEYS_ENDPOINTKIT aren't set")
    sys.exit(2)
# lib first: tests/appkit would hide the real appkit.
sys.path[:0] = [_ROOT + "/lib", _TESTS, _TREE, _ENDPOINTKIT]

try:
    import lvgl as lv
except ImportError as e:
    print("can't run the hostkeys checks:", e)
    sys.exit(2)

failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


# -- the stand-in host port -------------------------------------------------------


def _utf16(text):
    out = bytearray([2 + 2 * len(text), 3])
    for c in text:
        out += bytes([ord(c) & 0xFF, ord(c) >> 8])
    return bytes(out)


def _config(*parts):
    blob = bytes([9, 2, 0, 0, 1, 1, 0, 0x80, 50]) + b"".join(parts)
    return blob[:2] + bytes([len(blob) & 0xFF, len(blob) >> 8]) + blob[4:]


# A boot keyboard: interface 0, HID class, boot subclass, keyboard protocol,
# a 65-byte report descriptor and an 8-byte interrupt IN endpoint.
BOOT_KEYBOARD = _config(bytes([9, 4, 0, 0, 1, 3, 1, 1, 0]), bytes([9, 0x21, 0x11, 1, 0, 1, 0x22, 65, 0]),
                        bytes([7, 5, 0x81, 3, 8, 0, 10]))


class Keyboard:
    def __init__(self, pid, product):
        self.vid, self.pid, self.product = 0x03F0, pid, product
        self.reports = []
        self.stalled = False

    def device_descriptor(self):
        return bytes([18, 1, 0, 2, 0, 0, 0, 64, self.vid & 0xFF, self.vid >> 8, self.pid & 0xFF, self.pid >> 8,
                      0, 1, 0, 2, 0, 1])


class FakeUsbHost:
    """What usb.core calls on the firmware's _usbhost."""

    def __init__(self):
        self.running = False
        self.attaches = self.detaches = 0
        self.devices = {}   # id -> Keyboard
        self.claimed = {}   # id -> interfaces claimed
        self._next = 1
        self.polls = 0
        self.starts = []    # full_speed of each start
        self.no_host = False

    def plug(self, kb):
        dev_id = self._next
        self._next += 1
        self.devices[dev_id] = kb
        self.claimed[dev_id] = set()
        self.attaches += 1
        return dev_id

    def pull(self, dev_id):
        del self.devices[dev_id]
        self.detaches += 1

    def _dev(self, dev_id):
        if dev_id not in self.devices:
            raise OSError(19, "no such device")
        return self.devices[dev_id]

    # -- _usbhost's own calls

    def host_start(self, classes, full_speed=False):
        self.running = True
        self.starts.append(full_speed)

    def host_stop(self):
        self.running = False

    def host_stats(self):
        if self.no_host:
            return None
        return (self.running, self.attaches, self.detaches, 0, len(self.devices), 1)

    def host_devices(self):
        return tuple((i, k.vid, k.pid, None, None, {"hid"}, "full") for i, k in self.devices.items())

    def host_desc(self, dev_id):
        self._dev(dev_id)
        return BOOT_KEYBOARD

    def host_ctrl(self, dev_id, setup, buf, timeout):
        kb = self._dev(dev_id)
        request_type, request, value = setup[0], setup[1], setup[2] | setup[3] << 8
        if request != 6:
            return 0   # SET_PROTOCOL, SET_IDLE, CLEAR_FEATURE
        kind, number = value >> 8, value & 0xFF
        if request_type == 0x80 and kind == 1:
            reply = kb.device_descriptor()
        elif request_type == 0x80 and kind == 3:
            reply = {0: bytes([4, 3, 9, 4]), 2: _utf16(kb.product)}[number]
        else:
            raise OSError(32, "stall")
        n = min(len(reply), len(buf))
        buf[:n] = reply[:n]
        return n

    def host_claim(self, dev_id, interface, alternate=0):
        self._dev(dev_id)
        fresh = interface not in self.claimed[dev_id]
        self.claimed[dev_id].add(interface)
        return fresh

    def host_release(self, dev_id, interface):
        self.claimed[dev_id].discard(interface)
        self._dev(dev_id)

    def host_poll(self, dev_id, endpoint, buf):
        self.polls += 1
        kb = self._dev(dev_id)
        if kb.stalled:
            raise OSError(32, "stall")
        if not kb.reports:
            return 0
        report = kb.reports.pop(0)
        buf[: len(report)] = report
        return len(report)

    def host_xfer(self, dev_id, endpoint, buf, timeout, raise_on_timeout=True):
        return self.host_poll(dev_id, endpoint, buf)


fake = FakeUsbHost()
sys.modules["_usbhost"] = fake

try:
    import endpointkit
    import usb.core
    from usb.host import endpoints
except ImportError as e:
    print("can't run the hostkeys checks:", e)
    sys.exit(2)

import _headless  # noqa: E402
from appkit import connections, hostkeys, keys  # noqa: E402
from appkit.hostkeys import HostKeys  # noqa: E402

# -- plants -------------------------------------------------------------------


class _Mute:
    @staticmethod
    def hid_key(usage, modifiers=0):
        return None


class _Stays:
    """Types, but leaves the on-screen keyboard open."""

    @staticmethod
    def hid_key(usage, modifiers=0):
        key = keys.hid_char(usage, modifiers)
        if key is not None:
            keys.indev()
            code = ord(key) if isinstance(key, str) else key
            keys._queue.append((code, True))
            keys._queue.append((code, False))
        return key


def _plant_drops_keys():
    hostkeys.keys = _Mute


def _plant_keyboard_stays():
    hostkeys.keys = _Stays


def _plant_always_reading():
    real = HostKeys._fit_timer

    def fit(self):
        real(self)
        if self._timer is None:
            self._timer = lv.timer_create(lambda t: self.read(), self.read_ms, None)

    HostKeys._fit_timer = fit


def _plant_ignores_choice():
    HostKeys.in_use = lambda self: [ep for ep in self.registry.endpoints("keys") if endpoints.device(ep) is not None]


def _plant_unplug_raises():
    hostkeys._ENODEV = -1


def _plant_stall_swallowed():
    real = HostKeys.read

    def read(self):
        try:
            real(self)
        except usb.core.USBError:
            pass

    HostKeys.read = read


def _plant_never_looks():
    real = HostKeys.__init__

    def init(self, registry, read_ms=hostkeys.READ_MS, look_ms=None):
        real(self, registry, read_ms)

    HostKeys.__init__ = init


def _plant_s3_takes_the_port():
    connections.USB_HOST_APART["ESP32S3"] = False


def _plant_replug_missed():
    HostKeys._forget_gone = lambda self, want: None


PLANTS = {
    "drops_keys": _plant_drops_keys,
    "keyboard_stays": _plant_keyboard_stays,
    "always_reading": _plant_always_reading,
    "ignores_choice": _plant_ignores_choice,
    "unplug_raises": _plant_unplug_raises,
    "stall_swallowed": _plant_stall_swallowed,
    "replug_missed": _plant_replug_missed,
    "s3_takes_the_port": _plant_s3_takes_the_port,
    "never_looks": _plant_never_looks,
}
plant = os.getenv("HOSTKEYS_PLANT")
if plant:
    PLANTS[plant]()

# -- helpers -------------------------------------------------------------------------

SHIFT = 0x02
USAGE = {"h": 0x0B, "i": 0x0C, "o": 0x12, "k": 0x0E, "a": 0x04, "b": 0x05, "c": 0x06, "x": 0x1B, "y": 0x1C,
         "!": 0x1E}


def type_on(kb, text):
    """Queue the reports a boot keyboard sends for *text*: each key down, then all keys up."""
    for ch in text:
        mods = SHIFT if ch.isupper() or ch == "!" else 0
        kb.reports.append(bytes([mods, 0, USAGE[ch.lower()], 0, 0, 0, 0, 0]))
        kb.reports.append(bytes(8))


def settle(ms=200):
    for _ in range(ms // 20):
        _headless.advance(20)


def safe_read(hk):
    """Run one read; the error it raised, or None."""
    try:
        hk.read()
    except Exception as e:  # noqa: BLE001 - the checks say which errors are right
        return e
    return None


# -- a field, a registry and the host port --------------------------------------------

_headless.display(480, 320)
scr = lv.obj(None)
lv.screen_load(scr)
group = lv.group_create()
group.set_default()
field = lv.textarea(scr)
field.set_one_line(True)
group.add_obj(field)
keys.attach(field)
lv.group_focus_obj(field)

reg = endpointkit.Registry()
endpoints.register(reg)
hk = HostKeys(reg)

polls = fake.polls
settle(400)
check(not hk.open and hk._timer is None and fake.polls == polls,
      "nothing plugged in: nothing opened and no reads (%d)" % (fake.polls - polls))

# -- a keyboard types, and the on-screen keyboard gets out of the way ----------------

hp = Keyboard(0x0941, "HP Wireless Keyboard")
hp_id = fake.plug(hp)
reg.poll()
check(len(hk.open) == 1 and hk._timer is not None, "plugging one in opens it: %r" % (list(hk.open),))
keys.show(field)
settle(40)
check(keys.is_shown(), "the on-screen keyboard is open on the field")
type_on(hp, "Hi!")
settle()
check(field.get_text() == "Hi!", "the USB keyboard types into the focused field: %r" % (field.get_text(),))
check(not keys.is_shown(), "and the on-screen keyboard closes when it does")

# -- the choice: the chosen keyboard only, every one while none is chosen ----------------

other = Keyboard(0x0942, "Other Keyboard")
other_id = fake.plug(other)
reg.poll()
check(len(hk.open) == 2, "a second keyboard opens too while none is chosen")
ids = [ep.id for ep in reg.endpoints("keys")]
other_ep = [i for i in ids if "0942" in i]
hp_ep = [i for i in ids if "0941" in i]
reg.select("keys", other_ep)
check(list(hk.open) == other_ep, "choosing one closes the other: %r" % (list(hk.open),))
check(not fake.claimed[hp_id], "and lets go of its interface")
field.set_text("")
type_on(hp, "x")
type_on(other, "y")
settle()
check(field.get_text() == "y", "only the chosen keyboard types: %r" % (field.get_text(),))
reg.select("keys", [])
check(len(hk.open) == 2, "clearing the choice opens both again")
hp.reports[:] = []

# A keyboard that isn't on the host port (a computer's own) is left to its provider.
from endpointkit.fake import FakeProvider  # noqa: E402

reg.register(FakeProvider("keys", "desktop-keys", [("kbd", "Keyboard")]))
check(len(hk.open) == 2, "a keys endpoint off the host port isn't opened")

# -- pulling one out -----------------------------------------------------------------------

field.set_text("")
type_on(hp, "a")
settle()
fake.pull(hp_id)
type_on(other, "b")
err = safe_read(hk)
check(err is None, "a keyboard pulled out raises nothing: %r" % (err,))
check(hp_ep[0] not in hk.open, "it's closed")
settle()
check(field.get_text() == "ab", "the other one keeps typing: %r" % (field.get_text(),))
reg.poll()
check(list(hk.open) == other_ep, "the host drops it, and only the other is open")
fake.pull(other_id)
reg.poll()
settle()
check(not hk.open and hk._timer is None, "the last one pulled out: nothing open, no more reads")

# -- plugged back in -------------------------------------------------------------------

hp_id = fake.plug(hp)
reg.poll()
field.set_text("")
type_on(hp, "ok")
settle()
check(field.get_text() == "ok", "plugged back in, it types again: %r" % (field.get_text(),))

# Out and in between two polls: the host lists the same keyboard, as a new device.
fake.pull(hp_id)
hp_id = fake.plug(hp)
err = safe_read(hk)
check(err is None, "a replug between polls raises nothing: %r" % (err,))
reg.poll()
type_on(hp, "c")
settle()
check(field.get_text() == "okc", "and it types after the next poll: %r" % (field.get_text(),))

# -- a keyboard that fails is closed, loudly ----------------------------------------------

hp.stalled = True
type_on(hp, "x")
err = safe_read(hk)
check(isinstance(err, usb.core.USBError) and err.errno == 32, "a stall is raised: %r" % (err,))
check(not hk.open, "and that keyboard is closed")
hp.stalled = False
hp.reports[:] = []

# -- close -------------------------------------------------------------------------

hk.close()
check(not hk.open and hk._timer is None, "close stops reading")
fake.plug(Keyboard(0x0943, "Third Keyboard"))
reg.poll()
check(not hk.open, "and a keyboard plugged in after isn't opened")

# -- with nothing else polling the registry, it looks itself ---------------------------

looking = HostKeys(reg, look_ms=100)
there = len(fake.devices)
check(there and len(looking.open) == there, "a new one opens the keyboards already there")
late_id = fake.plug(Keyboard(0x0944, "Late Keyboard"))
settle(200)
check(len(looking.open) == there + 1, "and finds one plugged in later on its own: %r" % (list(looking.open),))
fake.pull(late_id)
settle(200)
check(len(looking.open) == there, "and one pulled out")
looking.close()

# -- which boards the Shell registers the host port on (connections.usb_host) -----------


def usb_host_on(machine, board=True, running=False):
    """`connections.usb_host` on a pretend board: whether it registered, and
    the full_speed of each host start it made."""
    usb.core.stop()
    if running:
        usb.core.start()
    del fake.starts[:]
    del connections._usb[:]
    connections._board = lambda: board
    connections._machine = lambda: machine
    ok = connections.usb_host(endpointkit.Registry())
    return ok, list(fake.starts)


check(usb_host_on("ESP32P4", board=False) == (False, []), "a computer: the host port is left alone")
check(usb_host_on("ESP32P4") == (True, [False]), "an ESP32-P4: registered, the host started at high speed")
check(usb_host_on("ESP32S31") == (True, [False]), "an ESP32-S31: the same")
check(usb_host_on("STM32H747") == (True, [True]), "the GIGA: started at full speed, all its port does")
check(usb_host_on("ESP32S3") == (False, []), "an ESP32-S3, whose host would take the REPL's port: left alone")
check(usb_host_on("ESP32S3", running=True) == (True, []), "unless something started it: registered, not restarted")
fake.no_host = True
check(usb_host_on("ESP32P4") == (False, []), "firmware without a USB host: nothing")
fake.no_host = False
check(connections.usb_host() is False and fake.starts == [], "asked again, it answers the same and starts nothing")

print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
