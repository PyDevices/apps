# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The MIDI Controller app on real LVGL with no window, its USB stood in.

The board side is pydevices' real ``midiports.usb_device``, on a stand-in
for micropython-lib's ``MIDIInterface`` that keeps each USB-MIDI event it
would send, and hands in ones a host sent. A computer's own ports are a
stand-in too: a synth that only listens, and a loopback that hands back
what it was sent. So each touch on the screen is read back as the bytes
on the wire, and what comes in is seen to move the controls.

    PYDEVICES_DIR=../pydevices python tests/midicontroller_contract.py

Each view is drawn under the board shell's own header, on a display of
``MIDICONTROLLER_SCREEN`` (``800x480`` unless set), and checked for text
that is cut off or drawn over. ``MIDICONTROLLER_SHOTS=<folder>`` also saves
each view as a raw RGB565 frame (a ``w h`` line, then the pixels). Exits 1
if a check fails, 2 if midiports or LVGL isn't there.
"""

import json
import os
import shutil
import sys
import tempfile
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_PYDEVICES = os.getenv("PYDEVICES_DIR") or os.path.join(_ROOT, "..", "pydevices")
# lib first: tests/appkit would hide the real appkit.
sys.path[:0] = [os.path.join(_ROOT, "lib"), _ROOT, _HERE, os.path.join(_PYDEVICES, "packages", "midiports")]
# multimer, and the shell's header, which draws through iconkit.
sys.path += [os.path.join(_PYDEVICES, "lib"), os.path.join(_PYDEVICES, "packages", "iconkit", "lib")]

SW, SH = (int(n) for n in (os.getenv("MIDICONTROLLER_SCREEN") or "800x480").split("x"))
failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


def _module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


# -- USB stood in ------------------------------------------------------------


class _MIDIInterface:
    """micropython-lib's MIDIInterface, keeping each event it would send."""

    open = True
    wire = []

    def __init__(self, rxlen=16, txlen=16):
        pass

    def is_open(self):
        return _MIDIInterface.open

    def send_event(self, cin, b0, b1, b2):
        _MIDIInterface.wire.append((cin, b0, b1, b2))
        return True


class _UsbDevice:
    inits = []

    def init(self, *itfs, builtin_driver=False):
        _UsbDevice.inits.append(itfs)


_device = _UsbDevice()
usb = _module("usb", __path__=[])
usb.device = _module("usb.device", __path__=[], get=lambda: _device)
usb.device.midi = _module("usb.device.midi", MIDIInterface=_MIDIInterface)
_module("machine", USBDevice=object)
# No USB host port and no Bluetooth on this board.
sys.modules["_usbhost"] = None
sys.modules["bledev"] = None

# -- A computer's MIDI ports stood in ---------------------------------------------


class PortInfo:
    def __init__(self, name, direction):
        self.id = name + direction
        self.name = name
        self.direction = direction


class _Port:
    def __init__(self, info):
        self.info = info
        self.sent = bytearray()
        self.inbox = bytearray()
        self.closed = False

    def write(self, buf, nbytes):
        self.sent += bytes(buf[:nbytes])
        if self.info.name == "Loop":
            _desk.ports[("Loop", "in")].inbox += bytes(buf[:nbytes])
        return nbytes

    def readinto(self, buf, nbytes=None):
        n = min(len(buf), len(self.inbox))
        if not n:
            return None
        buf[:n] = self.inbox[:n]
        del self.inbox[:n]
        return n

    def close(self):
        self.closed = True


class _Desk:
    ports = {}

    def available(self):
        return [PortInfo("Synth", "out"), PortInfo("Loop", "in"), PortInfo("Loop", "out")]

    def open_port(self, info):
        p = self.ports[(info.name, info.direction)] = _Port(info)
        return p


_desk = _Desk()
try:
    import midiports
    from midiports import usb_device  # noqa: F401 - the app's USB link is this module
except ImportError as e:
    print("SKIP: pydevices' midiports isn't at %s (%s); set PYDEVICES_DIR" % (_PYDEVICES, e))
    sys.exit(2)
for _name in ("linux", "windows"):
    sys.modules["midiports." + _name] = _desk
    setattr(midiports, _name, _desk)

# -- The screen ----------------------------------------------------------------

try:
    import lvgl as lv
except ImportError as e:
    print("SKIP: LVGL for CPython isn't installed (%s)" % e)
    sys.exit(2)

import _headless  # noqa: E402

_headless.display(SW, SH)
_headless.pointer()

from touchkit import ui  # noqa: E402
from touchkit.shell import TouchShell  # noqa: E402

ui.apply_theme()
W, H = SW, SH - ui.HEADER
_shell = types.SimpleNamespace(
    launcher=types.SimpleNamespace(home="home", info={"midicontroller": {"title": "MIDI Controller"}}))
TouchShell.make_home_button(_shell)

import apps.midicontroller as app  # noqa: E402
from apps.midicontroller import links  # noqa: E402

DATA = tempfile.mkdtemp(prefix="midicontroller-")


class Scope:
    """What the launcher's shell hands an app: a root, its size, timers."""

    name = "midicontroller"
    data_dir = DATA

    def __init__(self):
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


def _area(obj):
    a = lv.area_t()
    obj.get_coords(a)
    return a.x1, a.y1, a.x2, a.y2


def centre(obj):
    x1, y1, x2, y2 = _area(obj)
    return (x1 + x2) // 2, (y1 + y2) // 2


def tap(obj, dx=0, dy=0, hold=False):
    x, y = centre(obj)
    x, y = x + dx, y + dy
    _headless.touch(x, y, False, 40)
    _headless.touch(x, y, True, 40)
    _headless.touch(x, y, True, 40)
    if not hold:
        _headless.touch(x, y, False, 40)


def drag(obj, dy, dx=0):
    x, y = centre(obj)
    _headless.touch(x, y, False, 40)
    _headless.touch(x, y, True, 40)
    for i in range(1, 11):
        _headless.touch(x + dx * i // 10, y + dy * i // 10, True, 40)
    _headless.touch(x + dx, y + dy, False, 40)


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
        return False
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
    tops = [o for o, c in drawn if len(c) in (2, 3) and not o.check_type(lv.label_class)]
    for i, o in enumerate(tops):
        for p in tops[i + 1:]:
            if o.get_parent() == p.get_parent() and _meets(_area(o), _area(p)):
                check(False, "%s: two controls overlap at %r and %r" % (where, _area(o), _area(p)))


def shot(name):
    folder = os.getenv("MIDICONTROLLER_SHOTS")
    for _ in range(4):
        _headless.advance(100)  # let the tabs' colour changes finish
    _headless.refresh()
    tidy(name)
    if folder:
        _headless.save_raw(os.path.join(folder, "%s_%dx%d.raw" % (name, SW, SH)), SW, SH)


def find_label(obj, text):
    """The object holding a label of exactly *text*."""
    for i in range(obj.get_child_count()):
        child = obj.get_child(i)
        if child.check_type(lv.label_class) and child.get_text() == text:
            return obj
        found = find_label(child, text)
        if found is not None:
            return found
    return None


def press_label(ctl, text):
    b = find_label(ctl.body, text)
    check(b is not None, "a button says %r" % text)
    if b is not None:
        tap(b)
    ctl.scope.run()


def wire():
    """The USB-MIDI events sent since the last call."""
    out = list(_MIDIInterface.wire)
    del _MIDIInterface.wire[:]
    return out


def tab(ctl, key):
    tap(ctl.tabs[key])
    ctl.scope.run()
    check(ctl.view == key, "the %s tab opens its view" % key)


# -- Opening: the status line, the tabs, the board's ways out ------------------------

check(links.choices() == [("usb", "USB device"), ("pc:Synth", "Synth"), ("pc:Loop", "Loop")],
      "the board offers USB and the computer's outputs: %r" % (links.choices(),))
scope = Scope()
ctl = app.main(scope)
scope.run()
itf = ctl.link.itf if ctl.link is not None else None
check(ctl.link is not None and ctl.link.key == "usb", "it opens on the first way out, USB")
check(_UsbDevice.inits and len(_UsbDevice.inits[-1]) == 1, "it starts the USB device with the MIDI interface")
st = _area(ctl.status)
for key, b in ctl.tabs.items():
    check(_area(b)[1] > st[3], "the %s tab is below the status line, not over it" % key)
check(_area(ctl.body)[1] > st[3], "the view is below the status line")
check("USB: connected" in ctl.status.get_text() and "ch 1" in ctl.status.get_text(),
      "the status line says where it sends and on which channel: %r" % ctl.status.get_text())

# -- Pads --------------------------------------------------------------------------

check(ctl.view == "pads", "it opens on the pads")
shot("pads")
grid = ctl.grid
wire()
tap(grid.pad(12), dy=-(_area(grid.pad(12))[3] - _area(grid.pad(12))[1]) // 3, hold=True)
sent = wire()
check(len(sent) == 1 and sent[0][:3] == (9, 0x90, 36), "the bottom left pad plays note 36 on channel 1: %r" % sent)
hard = sent[0][3] if sent else 0
_headless.touch(*centre(grid.pad(12)), False, 40)
sent = wire()
check(sent == [(8, 0x80, 36, 0)], "letting go of it ends the note: %r" % sent)
tap(grid.pad(12), dy=(_area(grid.pad(12))[3] - _area(grid.pad(12))[1]) // 3)
sent = wire()
soft = sent[0][3] if sent else 0
check(32 <= soft < hard <= 127, "a touch nearer the top of a pad plays harder: %d then %d" % (hard, soft))
tap(grid.pad(3))
sent = wire()
check(sent and sent[0][:3] == (9, 0x90, 51), "the top right pad plays note 51: %r" % sent)

press_label(ctl, "B")
check(ctl.surface.settings["bank"] == 1, "bank B is chosen")
tap(ctl.grid.pad(12))
sent = wire()
check(sent and sent[0][:3] == (9, 0x90, 52), "in bank B the bottom left pad plays 52: %r" % sent)
check(find_label(ctl.grid.pad(12), "E3") is not None, "and its legend says E3")
shot("pads_bank_b")
press_label(ctl, "A")

# A note coming in lights its pad.
itf.on_midi_event(9, 0x90, 37, 100)
scope.run()
check(ctl.grid.colors[13] is not None, "a note 37 coming in lights the pad that plays it")
itf.on_midi_event(8, 0x80, 37, 0)
scope.run()
check(ctl.grid.colors[13] is None, "and its end puts it out")

# -- Knobs -------------------------------------------------------------------------

tab(ctl, "knobs")
shot("knobs")
knob = ctl.parts["knob0"]
drag(knob.obj, -60)
sent = wire()
check(sent and sent[-1][:3] == (0xB, 0xB0, 70) and sent[-1][3] > 0, "turning the first knob sends CC 70: %r" % sent[-3:])
check(knob.value == (sent[-1][3] if sent else -1), "the knob shows what it sent")
itf.on_midi_event(0xB, 0xB0, 74, 100)
scope.run()
check(ctl.parts["knob4"].value == 100, "CC 74 coming in turns the fifth knob to 100: %r" % ctl.parts["knob4"].value)
check(not wire(), "and sends nothing back")
# A knob just moved by hand ignores its own echo for a moment.
moved = knob.value
itf.on_midi_event(0xB, 0xB0, 70, 3)
scope.run()
check(knob.value == moved, "a knob just turned isn't pulled back by what comes in")

# -- Faders -------------------------------------------------------------------------

tab(ctl, "faders")
shot("faders")
f = ctl.parts["fader15"]
drag(f.cap, -40)
sent = wire()
check(sent and sent[-1][:3] == (0xB, 0xB0, 117), "the last fader sends CC 117: %r" % sent[-2:])
itf.on_midi_event(0xB, 0xB0, 102, 90)
scope.run()
check(ctl.parts["fader0"].value == 90, "CC 102 coming in moves the first fader")

# -- Mixer ---------------------------------------------------------------------------

tab(ctl, "mixer")
shot("mixer")
tap(ctl.parts["mute0"].cap)
tap(ctl.parts["solo2"].cap)
sent = wire()
check(sent == [(0xB, 0xB0, 14, 127), (0xB, 0xB2, 15, 127)],
      "mute on strip 1 and solo on strip 3 go out on channels 1 and 3: %r" % sent)
tap(ctl.parts["mute0"].cap)
check(wire() == [(0xB, 0xB0, 14, 0)], "a second press lets mute go")
check(ctl.parts["solo2"].on and not ctl.parts["mute0"].on, "the lamps say which are on")
itf.on_midi_event(0xB, 0xB7, 7, 30)
itf.on_midi_event(0xB, 0xB4, 14, 127)
scope.run()
check(ctl.parts["mix7"].value == 30, "volume on channel 8 moves strip 8's fader")
check(ctl.parts["mute4"].on, "mute on channel 5 lights strip 5's mute")
shot("mixer_lit")

# -- XY and the transport ------------------------------------------------------------

tab(ctl, "xy")
shot("xy")
x1, y1, x2, y2 = _area(ctl.xy)
_headless.touch(x2 - 2, y1 + 2, False, 40)
_headless.touch(x2 - 2, y1 + 2, True, 40)
_headless.touch(x2 - 2, y1 + 2, False, 40)
sent = wire()
ccs = {(e[1], e[2]): e[3] for e in sent}
check(ccs.get((0xB0, 16), 0) > 120 and ccs.get((0xB0, 17), 0) > 120, "the XY pad's top right sends CC 16 and 17 near 127: %r" % sent)
tap(ctl.parts["tr3"].cap)
check(wire() == [(0xB, 0xB0, 23, 127), (0xB, 0xB0, 23, 0)], "Play sends CC 23 on and off")

# -- Keys -----------------------------------------------------------------------------

tab(ctl, "keys")
shot("keys")
tap(ctl.keys[0], dy=(_area(ctl.keys[0])[3] - _area(ctl.keys[0])[1]) // 3)
sent = wire()
check(sent and sent[0][:3] == (9, 0x90, 60) and sent[-1][:3] == (8, 0x80, 60), "the first key plays middle C: %r" % sent)
tap(ctl.keys[1])
sent = wire()
check(sent and sent[0][:3] == (9, 0x90, 61), "the first black key plays C#: %r" % sent)
press_label(ctl, "Oct " + lv.SYMBOL.RIGHT)
tap(ctl.keys[0])
sent = wire()
check(sent and sent[0][:3] == (9, 0x90, 72), "an octave up, it plays 72: %r" % sent)
drag(ctl.parts["mod"].cap, -50)
sent = wire()
check(sent and sent[-1][:3] == (0xB, 0xB0, 1), "the mod wheel sends CC 1: %r" % sent[-2:])

# -- Setup: the channel, the velocity, the way out ---------------------------------------

tab(ctl, "setup")
shot("setup")

def setup_arrows():
    return [o for o, _ in _shown(ctl.body, (), []) if o.check_type(lv.label_class) and o.get_text() == lv.SYMBOL.RIGHT]


arrows = setup_arrows()
check(len(arrows) == 3, "Setup has three rows to step: %d" % len(arrows))
tap(arrows[1].get_parent())
scope.run()
check(ctl.surface.settings["channel"] == 2, "the channel steps up to 2")
tap(setup_arrows()[2].get_parent())
scope.run()
check(ctl.surface.settings["velocity"] == 32, "velocity steps from the touch to fixed: %r" % ctl.surface.settings["velocity"])
tab(ctl, "pads")
wire()
tap(ctl.grid.pad(12))
sent = wire()
check(sent and sent[0] == (9, 0x91, 36, 32), "pads play on channel 2 at the fixed velocity: %r" % sent)
tab(ctl, "setup")
tap(setup_arrows()[0].get_parent())
scope.run()
check(ctl.link.key == "pc:Synth", "the way out steps to the computer's Synth")
check(_UsbDevice.inits[-1] == (), "and the USB port is the serial port alone again")
tap(setup_arrows()[0].get_parent())
scope.run()
check(ctl.link.key == "pc:Loop", "then to Loop")
shot("setup_loop")
check(_desk.ports[("Synth", "out")].closed, "the Synth's port is closed when it moves on")
tab(ctl, "knobs")
drag(ctl.parts["knob2"].obj, -60)
loop = _desk.ports[("Loop", "out")].sent
check(loop[-3:-1] == bytes([0xB1, 72]), "the knob's CC goes to Loop: %r" % bytes(loop[-6:]))
scope.run()
check("Loop" in ctl.status.get_text(), "the status line says Loop: %r" % ctl.status.get_text())

# -- Editing the mapping ----------------------------------------------------------------------

tab(ctl, "setup")
press_label(ctl, "Edit mapping")
check(ctl.edit, "Edit mapping turns editing on")
tab(ctl, "pads")
shot("map_pads")
tap(ctl.parts["map:pad0"])
scope.run()
check(ctl.editing == "pad0", "tapping a pad in the map opens its editor")
shot("editor_pad")
press_label(ctl, "+10")
press_label(ctl, "CC")
check(ctl.surface.map["pad0"] == ("cc", 46), "+10 and CC make the pad CC 46: %r" % (ctl.surface.map["pad0"],))
press_label(ctl, "Done")
tab(ctl, "knobs")
shot("map_knobs")
tap(ctl.parts["map:knob0"])
scope.run()
shot("editor_knob")
check(find_label(ctl.body, "Note") is None, "a knob's editor offers no Note: it stays a CC")
press_label(ctl, "-1")
check(ctl.surface.map["knob0"] == ("cc", 69), "-1 makes the first knob CC 69")
press_label(ctl, "Done")
for view in ("faders", "mixer", "xy", "keys"):
    tab(ctl, view)
    shot("map_" + view)
tab(ctl, "setup")
press_label(ctl, "Edit mapping")
check(not ctl.edit, "a second tap ends editing")

# -- Saved, and back after a restart ------------------------------------------------------

scope.close()
with open(os.path.join(DATA, "config.json")) as f:
    saved = json.load(f)
check(saved.get("channel") == 2 and saved.get("output") == "pc:Loop", "closing saves the channel and the way out: %r" % saved)
check(saved.get("map") == {"pad0": ["cc", 46], "knob0": ["cc", 69]}, "and only the mapping edits: %r" % saved.get("map"))
check("bank" not in saved and "octave" in saved, "a setting at its default isn't saved")
scope = Scope()
ctl = app.main(scope)
scope.run()
check(ctl.link.key == "pc:Loop" and ctl.view == "setup", "it opens again on Loop and the view it closed on")
check(ctl.surface.map["pad0"] == ("cc", 46), "with the edited mapping")
press_label(ctl, "Reset mapping")
check(ctl.surface.map["pad0"] == ("note", 36), "Reset mapping puts the defaults back")
loop_in = _desk.ports[("Loop", "out")]
loop_in.sent[:] = b""
press_label(ctl, "All notes off")
check(bytes([0xB1, 123, 0]) in bytes(loop_in.sent), "All notes off sends CC 123 on the channel: %r" % bytes(loop_in.sent))
scope.close()

# -- A board with no way out ---------------------------------------------------------------

os.remove(os.path.join(DATA, "config.json"))
_real_choices = links.choices
links.choices = lambda: []
scope = Scope()
ctl = app.main(scope)
scope.run()
check(ctl.link is None and "no MIDI out" in ctl.status.get_text(), "with no way out it says so: %r" % ctl.status.get_text())
tap(ctl.grid.pad(0))
check(ctl.surface.last is not None, "the pads still play, to nowhere")
shot("no_output")
scope.close()
links.choices = _real_choices

shutil.rmtree(DATA, ignore_errors=True)
print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
