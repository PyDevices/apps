# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Watch on a round 240 by 240 screen, on real LVGL with no window.

The repository's own apps run through a real Launcher under touchkit's
TouchShell, with Watch as the home screen, as Home's ``main.py`` makes it on
a round or small screen. Watch opens on the hybrid face with the date, the
battery and the steps under it; a swipe turns to the next face and the
choice is saved; a tap opens the wheel, which holds every app Home shows,
in the order of Home's tabs, the middle one named beside its disc. A swipe
up the wheel brings the next app to the middle, a tap on it opens it, and
the Shell's Home button brings Watch back, on its face. In a browser page
the line under the face is left out.

    APPKIT_DATA=/tmp/watch python tests/appkit/watch_contract.py

``WATCH_SHOTS=<folder>`` saves each screen as a raw RGB565 frame.
``WATCH_PLANT=<name>`` breaks it one way from `PLANTS`, and the checks must
then fail. Exits 1 if a check fails, 2 if something it needs isn't there.
"""

import os
import sys


def _up(path):
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _join(*parts):
    return "/".join(parts)


_HERE = _up(__file__)
_TESTS = _up(_HERE)
_ROOT = _up(_TESTS)
_LIB = os.getenv("OMNIPYTHON_LIB") or _join(_ROOT, "..", "omnipython", "lib")
_OMNI = _up(_LIB)
_PATHS = [_join(_ROOT, "lib"), _HERE, _TESTS, _join(_OMNI, "packages", "endpointkit"), _LIB]
if sys.implementation.name != "micropython":
    _PATHS.insert(3, _join(_OMNI, "packages", "icons"))
    _PATHS.append(_join(_OMNI, "utils"))
sys.path[:0] = _PATHS

try:
    import endpointkit
    import icons  # noqa: F401
    import lvgl as lv
    from endpointkit import fake
except ImportError as e:
    print("can't run the Watch checks:", e)
    sys.exit(2)

import _headless  # noqa: E402

failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


W = 240
SHOTS = os.getenv("WATCH_SHOTS")


class _Battery:
    percent = 82
    charging = False


class _Accel:
    features_running = True
    steps = 1234


class _Board:
    PERIPHERALS = frozenset({"battery", "accelerometer"})
    display_drv = type("drv", (), {"round": True, "width": 240, "height": 240})()
    accelerometer = _Accel()


class _Peripherals:
    PERIPHERALS = _Board.PERIPHERALS

    @staticmethod
    def battery():
        return _Battery()


sys.modules["board_config"] = _Board()
sys.modules["board_peripherals"] = _Peripherals()
_headless.display(W, W)
_headless.pointer()

import time  # noqa: E402

from appkit import connections  # noqa: E402
from appkit import launcher as L  # noqa: E402
from appkit.shell import is_round, is_small  # noqa: E402
from appdev import App  # noqa: E402
from touchkit import shell as touch  # noqa: E402

connections.register = lambda registry=None: []
fake.bench(endpointkit.registry, delay=1)

check(is_round(), "the screen is round")
check(is_small(), "a 240 by 240 screen is small")

la = L.Launcher(App.current() or App())
la.scan(_join(_ROOT, "apps"))
la.home = "watch"

import apps.home as home  # noqa: E402
import apps.watch as watch  # noqa: E402
from apps.watch import faces  # noqa: E402
from apps.watch import wheel as wheel_mod  # noqa: E402

# -- plants: each must make a check fail -------------------------------------


def _plant_no_battery():
    # The line under the face leaves the battery out.
    watch.battery_text = lambda battery: None


def _plant_own_order():
    # The wheel lists the apps by name, not in Home's order.
    real = watch.in_order
    watch.in_order = lambda info, hidden=(): sorted(real(info, hidden))


def _plant_tap_does_nothing():
    # A tap on the middle app only brings it to the middle again.
    wheel_mod.Wheel._tapped = lambda self, i: self.show(i)


def _plant_face_forgotten():
    # A new face is shown but not saved.
    watch._save_face = lambda scope, name: None


def _plant_no_arc():
    # Every disc stays on one straight line.
    wheel_mod.arc = lambda r, dy: 0


def _plant_classic_first():
    # Watch opens on Grand Classic, not the hybrid face.
    faces.DEFAULT = "Grand Classic"


def _plant_glance_in_browser():
    # A browser page shows the line under the face anyway.
    watch.shows_glances = lambda: True


def _plant_hidden_listed():
    # An app hidden from Home is on the wheel anyway.
    real = watch.in_order
    watch.in_order = lambda info, hidden=(): real(info)


PLANTS = {
    "no_battery": _plant_no_battery,
    "own_order": _plant_own_order,
    "tap_does_nothing": _plant_tap_does_nothing,
    "face_forgotten": _plant_face_forgotten,
    "no_arc": _plant_no_arc,
    "hidden_listed": _plant_hidden_listed,
    "classic_first": _plant_classic_first,
    "glance_in_browser": _plant_glance_in_browser,
}
plant = os.getenv("WATCH_PLANT")
if plant:
    PLANTS[plant]()
home_order = [t[0] for _, tiles in home._pages(la.info, ("weather",)) for t in tiles]
watch_order = [t[0] for t in watch.in_order(la.info, ("weather",))]
del home, watch, faces, wheel_mod


def settle(ms=200):
    for _ in range(ms // 20):
        _headless.advance(20)


def coords(obj):
    obj.update_layout()
    a = lv.area_t()
    obj.get_coords(a)
    return a.x1, a.y1, a.x2 - a.x1 + 1, a.y2 - a.y1 + 1


def tap_at(x, y):
    _headless.touch(x, y, True, 50)
    _headless.touch(x, y, False, 50)
    settle()


def tap(obj):
    x, y, w, h = coords(obj)
    tap_at(x + w // 2, y + h // 2)


def drag(x0, y0, x1, y1):
    n = 12
    _headless.touch(x0, y0, True, 20)
    for k in range(1, n + 1):
        _headless.touch(x0 + (x1 - x0) * k // n, y0 + (y1 - y0) * k // n, True, 15)
    _headless.touch(x1, y1, False, 20)
    settle(1000)


def walk(obj, cls, out=None):
    out = [] if out is None else out
    for i in range(obj.get_child_count()):
        c = obj.get_child(i)
        if c.check_type(cls):
            out.append(c)
        walk(c, cls, out)
    return out


def texts(obj):
    return [c.get_text() for c in walk(obj, lv.label_class) if not c.has_flag(lv.obj.FLAG.HIDDEN)]


def glance_lines(face_view):
    """The shown text of the line under the face: a label of the face's own,
    not one of the dial's."""
    out = []
    for i in range(face_view.get_child_count()):
        c = face_view.get_child(i)
        if c.check_type(lv.label_class) and not c.has_flag(lv.obj.FLAG.HIDDEN):
            out.append(c.get_text())
    return out


def shown(obj):
    while obj is not None:
        if obj.has_flag(lv.obj.FLAG.HIDDEN):
            return False
        obj = obj.get_parent()
    return True


def wait_for(name):
    for _ in range(60):
        if la.current == name:
            break
        time.sleep(0.05)
        settle(40)
    settle()


def shot(name):
    if SHOTS:
        _headless.refresh()
        _headless.save_raw(_join(SHOTS, name + ".raw"), W, W)


L.restart_into = lambda name, count=1: (_ for _ in ()).throw(OSError("no restarts in these checks"))

# Weather is hidden, as a person would from its can't-run screen.
la.hide("weather", "no network here")

shell = touch.TouchShell(la)
la.shell = shell
la.boot("watch")
settle(600)
scope = la.scope
check(la.current == "watch", "Watch is the home screen: %r" % (la.current,))
shot("face")

face_view = scope.root.get_child(0)
wheel_view = scope.root.get_child(1)
check(shown(face_view) and not shown(wheel_view), "Watch opens on its face")
line = glance_lines(face_view)
check(bool(line), "a line of glances under the face: %r" % (texts(face_view),))
line = line[0] if line else ""
check("82%" in line, "the battery is on it: %r" % (line,))
check("1234 steps" in line, "today's steps are on it: %r" % (line,))
check(("online" in line) or ("offline" in line), "the network is on it: %r" % (line,))
dial = face_view.get_child(0)
check(dial.get_child_count() > 0, "a face is drawn")
_DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
check(any(t[:3] in _DAYS for t in texts(dial)),
      "it opens on the hybrid face, the day in its window: %r" % (texts(dial),))

# -- faces --------------------------------------------------------------------------

drag(200, 120, 40, 120)
check(shown(face_view), "a swipe sideways stays on the face")
try:
    with open(scope.data_dir + "/face.json") as f:
        saved = f.read()
except OSError:
    saved = ""
check("Grand Classic" in saved, "the next face, Grand Classic, is saved: %r" % (saved,))
shot("face_next")
drag(40, 120, 200, 120)
try:
    with open(scope.data_dir + "/face.json") as f:
        saved = f.read()
except OSError:
    saved = ""
check("Hybrid" in saved, "back to the hybrid face, saved: %r" % (saved,))

# -- in a browser page, no line under the face ----------------------------------

real_host = L.host
L.host = lambda: "browser"
# To the wheel and back, by its time at the top: the face reads its line again.
catch = face_view.get_child(face_view.get_child_count() - 1)
catch.send_event(lv.EVENT.PRESSED, None)
catch.send_event(lv.EVENT.CLICKED, None)
check(shown(wheel_view), "a tap opens the wheel")
settle()
for i in range(wheel_view.get_child_count()):
    c = wheel_view.get_child(i)
    if c.check_type(lv.label_class) and ":" in c.get_text():
        c.send_event(lv.EVENT.CLICKED, None)
settle()
check(shown(face_view), "its time goes back to the face")
check(not glance_lines(face_view), "in a browser page there's no line under the face: %r" % (glance_lines(face_view),))
shot("face_browser")
L.host = real_host

# -- the wheel ----------------------------------------------------------------------

tap_at(120, 120)
check(shown(wheel_view) and not shown(face_view), "a tap opens the wheel")
wh = None
for c in walk(wheel_view, lv.obj_class):
    if c.get_child_count() > 3 and c.get_scroll_dir() == lv.DIR.VER:
        wh = c
        break
check(wh is not None, "the wheel scrolls up and down")
order = watch_order
check(wh is not None and wh.get_child_count() == len(home_order),
      "every app Home shows is on the wheel: %d, Home %d" % (wh.get_child_count() if wh else 0, len(home_order)))
check(order == home_order, "in the order of Home's tabs: %r / %r" % (order[:6], home_order[:6]))
check("weather" not in order, "a hidden app stays off the wheel")
first_title = la.info[home_order[0]].get("title", home_order[0])
check(first_title in texts(wheel_view), "the middle app is named: %r not in %r" % (first_title, texts(wheel_view)))
shot("wheel")

if wh is not None:
    discs = [wh.get_child(i).get_child(0) for i in range(min(3, wh.get_child_count()))]
    xs = [coords(d)[0] + coords(d)[2] // 2 for d in discs]
    ws = [coords(d)[2] for d in discs]
    check(ws[0] > ws[1], "the middle disc is the large one: %r" % (ws,))
    check(xs[1] != xs[0], "the discs follow an arc: %r" % (xs,))
    # A swipe up the wheel: the next app comes to the middle.
    drag(70, 160, 70, 100)
    settle(1000)
    mid = None
    for t in home_order:
        if la.info[t].get("title", t) in texts(wheel_view):
            mid = t
    check(mid is not None and mid != home_order[0], "a swipe up turns the wheel: %r" % (mid,))
    shot("wheel_turned")
    # Bring Info to the middle, then tap it to open it.
    target = "info"
    i = home_order.index(target)
    wh.get_child(i).scroll_to_view(False)
    settle(600)
    check(la.info[target]["title"] in texts(wheel_view), "Info comes to the middle")
    tap(wh.get_child(i).get_child(0))
    wait_for(target)
    check(la.current == target, "a tap on the middle app opens it: %r, wanted %r" % (la.current, target))
    shot("app")
    b = shell.home_button
    check(b is not None and not b.has_flag(lv.obj.FLAG.HIDDEN), "the app has the Home button")
    if b is not None:
        tap(b)
        wait_for("watch")
    check(la.current == "watch", "Home brings Watch back: %r" % (la.current,))
    check(shown(la.scope.root.get_child(0)), "on its face")

# -- the wheel goes back to the face when left alone ------------------------------

# Opened after the screen sat untouched for longer than the wheel waits (by
# a key, or a script, neither of which touches the screen), the wheel stays
# until it has been left alone itself. The wait is cut short here.
sys.modules["apps.watch"].WHEEL_IDLE_MS = 400
root = la.scope.root
catch = root.get_child(0).get_child(root.get_child(0).get_child_count() - 1)
settle(1000)
catch.send_event(lv.EVENT.CLICKED, None)
settle(100)
time.sleep(0.4)
settle(100)
check(shown(root.get_child(1)), "a wheel just opened stays open, however long the screen sat untouched")
settle(1000)
time.sleep(0.4)
settle(100)
check(shown(root.get_child(0)) and not shown(root.get_child(1)), "left alone, it goes back to the face")

# Watch's clock ticks on a timer, which would keep the program alive once
# this script ends.
if la.scope is not None:
    la.scope.stop_timers()
print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
