# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The Gamepad app on real LVGL with no window, its USB on both ends stood in.

The gamepad side drives pydevices' real ``usb_hid``, whose USB interface is
replaced by one that keeps what it would send. The tester side reads through
the real ``usb.host.hid_generic``, from a stand-in device that answers with
``usb_hid``'s own gamepad descriptor and plays back those reports. So a press
on the screen of one goes through both modules and lights the other.

    PYDEVICES_DIR=../pydevices python tests/gamepad_contract.py

``GAMEPAD_SHOTS=<folder>`` also saves each screen as a raw RGB565 frame
(a ``w h`` line, then the pixels). Exits 1 if a check fails.
"""

import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_PYDEVICES = os.getenv("PYDEVICES_DIR") or os.path.join(_ROOT, "..", "pydevices")
_USB = os.path.join(_PYDEVICES, "packages", "usb")
# lib first: tests/appkit would hide the real appkit.
sys.path[:0] = [os.path.join(_ROOT, "lib"), _ROOT, _HERE, os.path.join(_USB, "usb-hid")]
sys.path.append(os.path.join(_PYDEVICES, "lib"))

W, H = 800, 416
failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


# -- USB stood in ------------------------------------------------------------


class USBError(OSError):
    pass


class USBTimeoutError(USBError):
    pass


class _Interface:
    """micropython-lib's HIDInterface, keeping what it would put on the wire."""

    protocol = 1
    _int_ep = 0x81
    open = False
    wire = []

    def __init__(self, *args, **kwargs):
        pass

    def is_open(self):
        return _Interface.open

    def busy(self):
        return False

    def submit_xfer(self, ep, data):
        _Interface.wire.append(bytes(data))


class _UsbDevice:
    inits = []

    def init(self, *itfs, builtin_driver=False):
        _UsbDevice.inits.append(len(itfs))


_device = _UsbDevice()


def _module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


class _Host:
    started = []
    stopped = 0
    pad = None


def _find(custom_match=None, **kwargs):
    pad = _Host.pad
    if pad is None or (custom_match is not None and not custom_match(pad)):
        return None
    return pad


def _start(full_speed=False, classes=None, force=False):
    _Host.started.append((full_speed, classes))


def _stop():
    _Host.stopped += 1


usb = _module("usb", __path__=[os.path.join(_USB, "usb-host-hid", "usb")])
core = _module("usb.core", USBError=USBError, USBTimeoutError=USBTimeoutError, find=_find, start=_start, stop=_stop)
usb.core = core
usb_device = _module("usb.device", get=lambda: _device)
usb.device = usb_device
_module("usb.device.hid", HIDInterface=_Interface)
_module("micropython", const=lambda x: x)
_module("machine", USBDevice=object)
_module("_usbhost", host_start=None)

try:
    import usb_hid
    from usb.host import hid_generic  # noqa: F401 - the app imports it; this says whether it can

    usb_hid.Device.GAMEPAD
except (ImportError, AttributeError) as e:
    print("SKIP: pydevices' usb-hid and usb-host-hid aren't at %s (%s); set PYDEVICES_DIR" % (_PYDEVICES, e))
    sys.exit(2)

usb_hid.time = types.SimpleNamespace(
    ticks_ms=lambda: 0, ticks_add=lambda a, b: a + b, ticks_diff=lambda a, b: a - b, sleep_ms=lambda ms: None
)


def _config(desc_len, packet=64):
    return bytes([9, 2, 34, 0, 1, 1, 0, 0xA0, 50,
                  9, 4, 0, 0, 1, 3, 0, 0, 0,
                  9, 0x21, 0x11, 0x01, 0, 1, 0x22, desc_len & 255, desc_len >> 8,
                  7, 5, 0x81, 3, packet, 0, 1])


class FakePad:
    """A device on the host port that answers as the board's own gamepad does."""

    idVendor, idProduct = 0x303A, 0x4002
    manufacturer, product = "Espressif", "Gamepad"

    def __init__(self, descriptor):
        self.descriptor = descriptor
        self._cfg = _config(len(descriptor))
        self.reports = []
        self.gone = False

    def configuration_descriptor(self):
        return self._cfg

    def set_configuration(self):
        pass

    def ctrl_transfer(self, request_type, request, value=0, index=0, data=None, timeout=None):
        if request_type == 0x81 and request == 6 and value == 0x2200:
            return self.descriptor[:data]
        return 0

    def read(self, endpoint, buf, timeout=None, raise_on_timeout=True):
        if self.gone:
            raise USBError(19, "no device")
        if not self.reports:
            return 0
        report = self.reports.pop(0)
        buf[:len(report)] = report
        return len(report)

    def _release_all(self):
        pass


# -- The screen ----------------------------------------------------------------

import lvgl as lv  # noqa: E402

import _headless  # noqa: E402

_headless.display(W, H)
_headless.pointer()

from touchkit import ui  # noqa: E402

ui.apply_theme()

import apps.gamepad as gamepad  # noqa: E402
from apps.gamepad import pad as padmod  # noqa: E402


class Scope:
    """What the launcher's shell hands an app: a root, its size, timers."""

    def __init__(self):
        self.root = lv.obj(lv.screen_active())
        ui.plain(self.root)
        self.root.set_size(W, H)
        self.size = (W, H)
        self.rect = (0, 0, W, H)
        self.timers = []
        self.once = []
        self.closers = []

    def every(self, ms, cb):
        self.timers.append(cb)

    def after(self, ms, cb):
        self.once.append(cb)

    def on_close(self, fn):
        self.closers.append(fn)

    def run(self):
        once, self.once = self.once, []
        for cb in once + list(self.timers):
            cb(None)
        _headless.advance(40)

    def close(self):
        for fn in self.closers:
            fn()
        self.root.delete()


def centre(obj):
    a = lv.area_t()
    obj.get_coords(a)
    return (a.x1 + a.x2) // 2, (a.y1 + a.y2) // 2, (a.x2 - a.x1 + 1) // 2


def tap(x, y, hold=False):
    _headless.touch(x, y, True, 40)
    _headless.touch(x, y, True, 40)
    if not hold:
        _headless.touch(x, y, False, 40)


def let_go():
    _headless.touch(0, 0, False, 40)


def shot(name):
    folder = os.getenv("GAMEPAD_SHOTS")
    _headless.refresh()
    if folder:
        _headless.save_raw(os.path.join(folder, name + ".raw"), W, H)


def last_report():
    """The last report on the wire: its ID, then the seven bytes."""
    return _Interface.wire[-1] if _Interface.wire else None


def same_color(a, b):
    return (a.red, a.green, a.blue) == (b.red, b.green, b.blue)


def find_label(obj, text):
    for i in range(obj.get_child_count()):
        child = obj.get_child(i)
        if child.check_type(lv.label_class) and child.get_text() == text:
            return obj
        found = find_label(child, text)
        if found is not None:
            return found
    return None


# -- A board that can do both asks which ---------------------------------------

scope = Scope()
gamepad.main(scope)
_headless.advance(40)
shot("chooser")
check(gamepad.sides() == ["device", "host"], "a board with both ports offers both sides")
be = find_label(scope.root, "Be a gamepad")
check(be is not None, "the chooser offers to be a gamepad")
check(find_label(scope.root, "Test a gamepad") is not None, "the chooser offers to test a gamepad")

# -- The gamepad side ----------------------------------------------------------

_Interface.open = False
x, y, _ = centre(be)
tap(x, y)
scope.run()
check(_UsbDevice.inits[-1:] == [1], "choosing the gamepad starts the USB device with the HID interface")
check(usb_hid.devices == (usb_hid.Device.GAMEPAD,), "the USB device serves the gamepad")
check(not _Interface.wire, "nothing goes on the wire before a host has the board")

_Interface.open = True
scope.run()
check(last_report() == bytes([4, 0, 0, 0, 0, 0, 0, 0]),
      "once a host has the board, the pad at rest goes: %r" % (last_report(),))

# be_gamepad hands back its state and widgets; open it again the direct way
# to reach them.
scope.close()
scope = Scope()
_Interface.wire.clear()
st = gamepad.be_gamepad(scope)
_headless.advance(40)
dpad, stick = st["dpad"], st["stick"]

x, y, r = centre(dpad)
tap(x, y - r * 4 // 5, hold=True)
check(last_report() == bytes([4, 0, 0, 1, 0, 0, 0, 0]), "the top of the d-pad sends the hat north: %r" % (last_report(),))
shot("gamepad_up")
let_go()
check(last_report() == bytes([4, 0, 0, 0, 0, 0, 0, 0]), "letting go of the d-pad centres the hat")
tap(x + r * 3 // 5, y + r * 3 // 5, hold=True)
check(last_report()[3] == 4, "the d-pad's lower right sends the hat south-east (4)")
let_go()
tap(x, y)
check(last_report()[3] == 0, "the middle of the d-pad is no direction")

x, y, r = centre(stick)
tap(x + r, y, hold=True)
rep = last_report()
check(rep[4] > 100 and rep[5] == 0, "the stick's right edge sends X near 127 and Y at 0: %r" % (rep,))
_headless.touch(x, y - 2 * r, True, 40)
rep = last_report()
check(rep[4] == 0 and rep[5] == 256 - 127, "past the stick's top it sends Y at -127: %r" % (rep,))
shot("gamepad_stick")
let_go()
check(last_report() == bytes([4, 0, 0, 0, 0, 0, 0, 0]), "letting go of the stick centres it")

for number in (padmod.A, padmod.B, padmod.X, padmod.Y, padmod.L, padmod.R, padmod.SELECT, padmod.START):
    x, y, _ = centre(st["buttons"][number])
    tap(x, y, hold=True)
    mask = 1 << number - 1
    rep = last_report()
    check(rep[1] | rep[2] << 8 == mask, "button %d alone sends its bit: %r" % (number, rep))
    let_go()
    check(last_report()[1:3] == b"\0\0", "button %d lets go" % number)

x, y, _ = centre(st["buttons"][padmod.A])
tap(x, y, hold=True)
shot("gamepad")
let_go()
sent = list(_Interface.wire)
scope.close()
check(_UsbDevice.inits[-1] == 0, "closing the app gives the port back to the serial port alone")

# -- The tester side, reading what the gamepad side sent -----------------------

_Host.pad = None
scope = Scope()
st = gamepad.test_gamepad(scope)
check(_Host.started[-1] == (True, ("hid",)), "the tester starts the host at full speed for HID")
scope.run()
check(st["view"] is None, "with nothing plugged in the tester waits")
shot("tester_empty")

pad = FakePad(usb_hid.Device.GAMEPAD.report_descriptor)
_Host.pad = pad
# The tester looks once a second; let it look now.
st["watch"]._looked = None
scope.run()
view = st["view"]
check(view is not None, "the tester finds the gamepad")
check(sorted(view["lamps"]) == list(range(1, 17)), "it shows the pad's sixteen buttons")
check(sorted(view["bars"]) == [0x010030, 0x010031, 0x010032, 0x010035], "it shows X, Y, Z and Rz")
check(len(view["dots"]) == 2 and view["hat"] is not None, "it draws both sticks and the hat")

# Play back what the screen above sent: the hat north, then the stick right.
pad.reports = [r for r in sent if r[3] == 1][:1]
scope.run()
w = st["watch"]
check(w.hats.get(0) == 0, "the hat reads north on the tester")
pad.reports = [r for r in sent if r[4] > 100][:1]
scope.run()
check(w.hats.get(0) == -1, "and centred again when the stick moves alone")
check(w.axes.get(0x010030, 0) > 0.9, "the stick right reads X near 1.0 on the tester: %r" % (w.axes,))
check(view["bars"][0x010030].get_value() > 90, "X's bar is near full")
pad.reports = [bytes([4, 0b00010001, 0b10000000, 3, 0, 0x81, 0, 0])]
scope.run()
check(w.buttons == {1, 5, 16}, "buttons 1, 5 and 16 held: %r" % (w.buttons,))
lit = [n for n, lamp in view["lamps"].items() if same_color(lamp.get_style_bg_color(0), ui.ACCENT)]
check(sorted(lit) == [1, 5, 16], "exactly their lamps light: %r" % (lit,))
check(w.hats.get(0) == 2, "the hat reads east")
shot("tester")

pad.gone = True
scope.run()
check(st["view"] is None and "went" in w.status, "unplugging it says so and waits again: %r" % (w.status,))
scope.close()
check(_Host.stopped == 1, "closing the tester stops the host")

# -- One side only ---------------------------------------------------------------

del sys.modules["_usbhost"]
_module("_usbhost")
scope = Scope()
gamepad.main(scope)
check(find_label(scope.root, "Be a gamepad") is None, "a board with only a device port goes straight to the gamepad")
scope.close()

print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
