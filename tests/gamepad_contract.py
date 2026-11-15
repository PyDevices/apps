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

Each screen is drawn under the board shell's own header, on a display of
``GAMEPAD_SCREEN`` (``800x480`` unless set), and checked for text that is
cut off or drawn over. ``GAMEPAD_SHOTS=<folder>`` also saves each screen as
a raw RGB565 frame (a ``w h`` line, then the pixels). Exits 1 if a check
fails.
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
# The shell's header draws through appkit, which wants iconkit.
sys.path += [os.path.join(_PYDEVICES, "lib"), os.path.join(_PYDEVICES, "packages", "iconkit", "lib"),
             os.path.join(_PYDEVICES, "packages", "_boardname")]

SW, SH = (int(n) for n in (os.getenv("GAMEPAD_SCREEN") or "800x480").split("x"))
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
    product = None

    def init(self, *itfs, builtin_driver=False, product_str=None):
        _UsbDevice.inits.append(len(itfs))
        _UsbDevice.product = product_str


_device = _UsbDevice()


def _module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


class _Host:
    started = []
    stopped = 0
    running = False
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
    _Host.running = False


boarddev = _module("boarddev")
boarddev.name = lambda: "test-board"
usb = _module("usb", __path__=[os.path.join(_USB, "usb-host-hid", "usb")])
core = _module("usb.core", USBError=USBError, USBTimeoutError=USBTimeoutError, find=_find, start=_start, stop=_stop,
               running=lambda: _Host.running)
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

_headless.display(SW, SH)
_headless.pointer()

from touchkit import ui  # noqa: E402
from touchkit.shell import TouchShell  # noqa: E402

ui.apply_theme()
# The app's area: the screen below the shell's header.
W, H = SW, SH - ui.HEADER
_shell = types.SimpleNamespace(launcher=types.SimpleNamespace(home="home", info={"gamepad": {"title": "Gamepad"}}))
TouchShell.make_home_button(_shell)

import apps.gamepad as gamepad  # noqa: E402
from apps.gamepad import pad as padmod  # noqa: E402


class Scope:
    """What the launcher's shell hands an app: a root, its size, timers."""

    name = "gamepad"

    def __init__(self):
        # The shell's own header above, as on a board.
        self.scr = ui.plain(lv.obj(lv.screen_active()))
        self.scr.set_size(SW, SH)
        self.scr.update_layout()
        self.root = TouchShell.make_root(_shell, self)
        self.size = (W, H)
        self.rect = (0, 0, W, H)
        self.timers = []
        self.once = []
        self.closers = []

    def screen(self):
        return self.scr

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
        self.scr.delete()


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


def _area(obj):
    a = lv.area_t()
    obj.get_coords(a)
    return a.x1, a.y1, a.x2, a.y2


def _meets(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _within(a, b):
    return b[0] <= a[0] and b[1] <= a[1] and a[2] <= b[2] and a[3] <= b[3]


def _shown(obj, chain, out):
    for i in range(obj.get_child_count()):
        child = obj.get_child(i)
        if not child.has_flag(lv.obj.FLAG.HIDDEN):
            out.append((child, chain))
            _shown(child, chain + (child,), out)
    return out


def _text_fits(lbl):
    """Whether all of a label's text fits its own box: no dots, nothing cut."""
    if lbl.get_long_mode() == lv.label.LONG_MODE.DOTS and lbl.get_text().endswith("..."):
        return False  # LVGL has already put the dots in for what didn't fit
    size = lv.point_t()
    wrap = lbl.get_long_mode() == lv.label.LONG_MODE.WRAP
    w = lbl.get_content_width()
    lv.text_get_size(size, lbl.get_text(), lbl.get_style_text_font(0), lbl.get_style_text_letter_space(0),
                     lbl.get_style_text_line_space(0), w if wrap else 32767, lv.TEXT_FLAG.NONE)
    return size.x <= w and size.y <= lbl.get_content_height()


def tidy(where):
    """No text cut off or drawn over, and no control on top of another."""
    lv.screen_active().update_layout()
    screen = (0, 0, SW - 1, SH - 1)
    shown = _shown(lv.screen_active(), (), [])
    drawn = [(o, c) for o, c in shown if o.check_type(lv.label_class) or o.get_style_bg_opa(0) > 0
             or o.get_style_border_width(0) > 0]
    for lbl, chain in shown:
        if not lbl.check_type(lv.label_class) or not lbl.get_text():
            continue
        text = lbl.get_text()
        a = _area(lbl)
        check(_text_fits(lbl), "%s: %r fits its label" % (where, text))
        check(_within(a, screen), "%s: %r is on the screen: %r" % (where, text, a))
        for up in chain:
            check(_within(a, _area(up)), "%s: %r is inside what holds it: %r in %r" % (where, text, a, _area(up)))
        for other, other_chain in drawn:
            if other is lbl or other in chain or (other.check_type(lv.label_class) and not other.get_text()):
                continue
            if _meets(a, _area(other)):
                what = other.get_text() if other.check_type(lv.label_class) else "a %s" % type(other).__name__
                check(False, "%s: %r and %r are drawn over each other" % (where, text, what))
    # The app's own controls side by side, none on another.
    tops = [o for o, c in drawn if len(c) in (2, 3) and not o.check_type(lv.label_class)]
    for i, o in enumerate(tops):
        for p in tops[i + 1:]:
            if o.get_parent() == p.get_parent() and _meets(_area(o), _area(p)):
                check(False, "%s: two controls overlap at %r and %r" % (where, _area(o), _area(p)))


def shot(name):
    folder = os.getenv("GAMEPAD_SHOTS")
    _headless.refresh()
    tidy(name)
    if folder:
        _headless.save_raw(os.path.join(folder, "%s_%dx%d.raw" % (name, SW, SH)), SW, SH)


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
check(_UsbDevice.product == "test-board", "the computer lists the gamepad under the board's name: %r" % (_UsbDevice.product,))
check(not _Interface.wire, "nothing goes on the wire before a host has the board")
shot("gamepad_no_host")

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
check(last_report() == bytes([4, 0, 0, 1, 0, 0, 0, 0]),
      "the top of the d-pad sends the hat north: %r" % (last_report(),))
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
shown = [m.get_text() for m in view["hat"] if same_color(m.get_style_text_color(0), ui.ACCENT)]
check(shown == ["E"], "the hat's E lights alone: %r" % (shown,))
pad.reports = [bytes([4, 0b00010001, 0b10000000, 6, 0, 0x81, 0, 0])]
scope.run()
shown = [m.get_text() for m in view["hat"] if same_color(m.get_style_text_color(0), ui.ACCENT)]
check(shown in (["SW"], ["S", "W"]), "south-west lights SW, or S and W where only four fit: %r" % (shown,))
pad.reports = [bytes([4, 0b00010001, 0b10000000, 3, 0, 0x81, 0, 0])]
scope.run()
shot("tester")

pad.gone = True
scope.run()
check(st["view"] is None and "went" in w.status, "unplugging it says so and waits again: %r" % (w.status,))
scope.close()
check(_Host.stopped == 1, "closing the tester stops the host")

# -- On a board with one USB port, the gamepad takes it from the host ------------

_Host.running = True
stopped = _Host.stopped
scope = Scope()
gamepad.be_gamepad(scope)
check(_Host.stopped == stopped, "where host and device have their own ports, the host keeps running")
scope.close()
_one_port = gamepad._one_port
gamepad._one_port = lambda: True
scope = Scope()
gamepad.be_gamepad(scope)
check(_Host.stopped == stopped + 1 and not _Host.running,
      "where they share one port, the gamepad stops the host before it starts the device")
scope.close()
gamepad._one_port = _one_port
_Host.running = False

# -- One side only ---------------------------------------------------------------

del sys.modules["_usbhost"]
_module("_usbhost")
scope = Scope()
gamepad.main(scope)
check(find_label(scope.root, "Be a gamepad") is None, "a board with only a device port goes straight to the gamepad")
scope.close()

# -- What a board lacks ------------------------------------------------------------

sys.modules["usb_hid"] = None
scope = Scope()
check(gamepad.be_gamepad(scope) is None, "without usb-hid the gamepad says what's missing")
_headless.advance(40)
shot("missing_usb_hid")
scope.close()

del sys.modules["usb.host.hid_generic"]
del sys.modules["usb.host"].hid_generic
sys.modules["usb.host.hid_generic"] = None
scope = Scope()
check(gamepad.test_gamepad(scope) is None, "without hid_generic the tester says what's missing")
_headless.advance(40)
shot("missing_hid_generic")
scope.close()

del sys.modules["machine"].USBDevice
scope = Scope()
gamepad.main(scope)
_headless.advance(40)
check(find_label(scope.root, "no USB port for this") is not None, "a board with neither port says so")
shot("missing_ports")
scope.close()

print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
