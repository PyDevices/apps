# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The Touch app on real LVGL with no window, tapped through a stand-in touch device.

The stand-in is shaped like a board's: ``_read`` gives the touch controller's
point, ``_map_point`` puts it through a rotation table entry, and LVGL's
pointer reads it on every frame, as the board's input loop does. Each case
says how the controller reads a tap on a target and which mask the table
holds; the app is tapped on each of its five targets, one at a time, and what
it saves is checked against what it should have found.

    python tests/touchcal_contract.py

``TOUCHCAL_SCREEN`` (``240x320`` unless set) is the display's size. Exits 1
if a check fails, and 2 when LVGL isn't there.
"""

import json
import os
import sys
import tempfile
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
# lib first: tests/appkit would hide the real appkit.
sys.path[:0] = [os.path.join(_ROOT, "lib"), _ROOT, _HERE]

try:
    import lvgl as lv
except ImportError:
    print("LVGL isn't installed for this Python")
    sys.exit(2)

import _headless

SW, SH = (int(n) for n in (os.getenv("TOUCHCAL_SCREEN") or "240x320").split("x"))
failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


SWAP_XY, REVERSE_X, REVERSE_Y = 1, 2, 4


class FakeTouch:
    """A board's touch device: the controller's point from ``_read``, mapped by one table entry."""

    def __init__(self, width, height, mask):
        self._display = types.SimpleNamespace(width=width, height=height)
        self._rotation_table = (mask, 0, 0, 0)
        self._mask = mask
        self.rotation = 0
        self.point = None

    def _read(self):
        return () if self.point is None else (self.point,)

    def _map_point(self, point):
        x, y = int(point[0]), int(point[1])
        if self._mask & SWAP_XY:
            x, y = y, x
        if self._mask & REVERSE_X:
            x = self._display.width - x - 1
        if self._mask & REVERSE_Y:
            y = self._display.height - y - 1
        return (x, y)


_headless.display(SW, SH)
dev = FakeTouch(SW, SH, 0)
sys.modules["board_config"] = types.SimpleNamespace(display_drv=types.SimpleNamespace(touch_device=dev))


def _read(indev, data):
    # What display_driver does each frame: read, map, hand LVGL the point.
    points = dev._read()
    if points:
        x, y = dev._map_point(points[0])
        data.point.x = x
        data.point.y = y
        data.state = lv.INDEV_STATE.PRESSED
    else:
        data.state = lv.INDEV_STATE.RELEASED


indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.POINTER)
indev.set_read_cb(_read)

import touchkit.ui  # noqa: E402  (after the display: its fonts and colours need LVGL running)

from apps import touchcal  # noqa: E402


class Scope:
    """What the app uses of an appkit scope."""

    def __init__(self, data_dir):
        self.name = "touchcal"
        self.data_dir = data_dir
        self.root = lv.obj(None)
        lv.screen_load(self.root)
        self._timers = []
        self._adopted = []

    def every(self, ms, callback):
        t = lv.timer_create(lambda _t: callback(_t), ms, None)
        self._timers.append(t)
        return t

    def after(self, ms, callback):
        t = lv.timer_create(lambda _t: callback(_t), ms, None)
        t.set_repeat_count(1)
        return t

    def adopt(self, obj, close=None):
        self._adopted.append((obj, close))
        return obj

    def close(self):
        for t in self._timers:
            t.delete()
        for obj, close in reversed(self._adopted):
            close(obj) if close else obj.delete()
        self.root.delete()


def texts(obj):
    """Every label's text under *obj*."""
    out = []
    for i in range(obj.get_child_count()):
        child = obj.get_child(i)
        if child.check_type(lv.label_class):
            out.append(child.get_text())
        out.extend(texts(child))
    return out


def press(point, ms):
    """Hold the stand-in touch at *point* for *ms*, then lift it."""
    dev.point = point
    for _ in range(ms // 30 + 1):
        _headless.advance(30)
    dev.point = None
    for _ in range(3):
        _headless.advance(30)


def numbers_on(sheet):
    return [t for t in texts(sheet) if t.isdigit()]


def run(name, controller, mask):
    """Tap each target where ``controller(x, y)`` says the touch controller reads it; return what the app saved."""
    folder = tempfile.mkdtemp()
    dev._mask = mask
    dev._rotation_table = (mask, 0, 0, 0)
    scope = Scope(folder)
    touchcal.main(scope)
    _headless.advance(50)
    sheet = lv.layer_sys().get_child(lv.layer_sys().get_child_count() - 1)
    for n, (x, y) in enumerate(touchcal.target_places(SW, SH), 1):
        shown = texts(sheet)
        numbers = [t for t in shown if t.isdigit()]
        check(numbers == [str(n)], "%s: target %d alone on the screen (numbers shown: %s)" % (name, n, numbers))
        press(controller(x, y), 90)
        if n < 5:
            check("Got it" in texts(sheet), "%s: target %d says Got it" % (name, n))
        for _ in range(25):
            _headless.advance(30)
    path = os.path.join(folder, touchcal.FILE)
    check(os.path.exists(path), "%s: the run is saved to %s" % (name, touchcal.FILE))
    with open(path) as f:
        record = json.load(f)
    check(len(record["taps"]) == 5, "%s: five taps saved, got %d" % (name, len(record["taps"])))
    check(sheet.has_flag(lv.obj.FLAG.HIDDEN), "%s: the targets go after the fifth tap" % name)
    shown = texts(scope.root)
    check(any(t in ("Touch is right", "Touch is off") for t in shown), "%s: the verdict is on the screen: %s" % (name, shown))
    scope.close()
    check(dev._read.__func__ is FakeTouch._read, "%s: closing the app gives the device its own read back" % name)
    return record


W1, H1 = SW - 1, SH - 1

# The controller reads where the screen is: nothing to fix.
r = run("identity", lambda x, y: (x, y), 0)
a = r["analysis"]
check(a["ok"], "identity: every tap on its target: %s" % a)
check(a["fix"]["mask"] == 0, "identity: the right mask is 0: %s" % a["fix"])
check(r["taps"][0]["raw"] == list(touchcal.target_places(SW, SH)[0]), "identity: the raw point is saved: %s" % r["taps"][0])

# The controller's x runs right to left, and the table doesn't reverse it.
r = run("mirror x", lambda x, y: (W1 - x, y), 0)
a = r["analysis"]
check(not a["ok"], "mirror x: taps off their targets")
check(a["seen"]["mask"] == REVERSE_X, "mirror x: seen as a mirrored x: %s" % a["seen"])
check(any("Left and right" in w for w in a["words"]), "mirror x: said in words: %s" % a["words"])
check(a["fix"]["mask"] == REVERSE_X and a["fix"]["table"][0] == REVERSE_X, "mirror x: fix is REVERSE_X: %s" % a["fix"])
check(a["fix"]["calibration"] is None, "mirror x: no calibration to change: %s" % a["fix"])
check(r["taps"][0]["mapped"] == [W1 - r["taps"][0]["target"][0], r["taps"][0]["target"][1]], "mirror x: mapped point saved: %s" % r["taps"][0])

# The controller's axes are the other way round, and the table doesn't swap them.
r = run("swap", lambda x, y: (y, x), 0)
a = r["analysis"]
check(not a["ok"], "swap: taps off their targets")
check(a["fix"]["mask"] == SWAP_XY, "swap: fix is SWAP_XY: %s" % a["fix"])
check(any("swapped" in w for w in a["words"]), "swap: said in words: %s" % a["words"])

# The same controller with SWAP_XY already in the table: right.
r = run("swap fixed", lambda x, y: (y, x), SWAP_XY)
check(r["analysis"]["ok"], "swap fixed: every tap on its target: %s" % r["analysis"])

# The same finger twice, a long press, and the run after it.
folder = tempfile.mkdtemp()
dev._mask = 0
dev._rotation_table = (0, 0, 0, 0)
scope = Scope(folder)
touchcal.main(scope)
_headless.advance(50)
sheet = lv.layer_sys().get_child(lv.layer_sys().get_child_count() - 1)
places = touchcal.target_places(SW, SH)
press(places[0], 90)
press(places[0], 90)  # a bounce, at once
for _ in range(25):
    _headless.advance(30)
check(numbers_on(sheet) == ["2"], "a bounce on target 1 doesn't count: showing %s" % numbers_on(sheet))
press(places[0], 90)  # the same spot again, soon after
for _ in range(25):
    _headless.advance(30)
check(numbers_on(sheet) == ["2"], "a second tap on target 1 soon after doesn't count: showing %s" % numbers_on(sheet))
press(places[1], 90)
for _ in range(25):
    _headless.advance(30)
check(numbers_on(sheet) == ["3"], "a tap on target 2 moves on: showing %s" % numbers_on(sheet))
for _ in range(40):
    _headless.advance(30)
press(places[2], touchcal.HOLD_MS + 100)
_headless.advance(30)
check(numbers_on(sheet) == ["1"], "a long press starts over: showing %s" % numbers_on(sheet))
for n, (x, y) in enumerate(places, 1):
    press((x, y), 90)
    for _ in range(25):
        _headless.advance(30)
with open(os.path.join(folder, touchcal.FILE)) as f:
    record = json.load(f)
check([t["target"] for t in record["taps"]] == [list(p) for p in places], "after starting over, the five taps are the new run's: %s" % record["taps"])
scope.close()

if failures:
    print("%d of %d checks failed" % (len(failures), checks[0]))
    sys.exit(1)
print("all %d checks passed at %dx%d" % (checks[0], SW, SH))
