# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Weather fits its screen, on real LVGL with no window.

Weather runs through a real Launcher on one screen size, with a forecast
already in hand. Its three screens (now, the five days, and the ZIP pad a
long press brings up) must each keep every word and key on the screen,
inside the circle on a round one, none on top of another or under the
Shell's Home button, and the "now"
screen must use most of the screen's height rather than a corner of it.

    WEATHER_SIZE=240x240r APPKIT_DATA=/tmp/weather python tests/appkit/weather_contract.py

``WEATHER_SIZE`` is ``<width>x<height>``, with ``r`` for a round screen.
``WEATHER_SHOTS=<folder>`` saves each screen as a raw RGB565 frame.
``WEATHER_PLANT=<name>`` breaks it one way from `PLANTS`, and the checks
must then fail. Exits 1 if a check fails, 2 if something it needs isn't there.
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
    print("can't run the Weather checks:", e)
    sys.exit(2)

import _headless  # noqa: E402

failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


SIZE = os.getenv("WEATHER_SIZE", "240x240r")
ROUND = SIZE.endswith("r")
W, H = (int(n) for n in SIZE.rstrip("r").split("x"))
SHOTS = os.getenv("WEATHER_SHOTS")


class _Board:
    PERIPHERALS = frozenset()
    display_drv = type("drv", (), {"round": ROUND, "width": W, "height": H})()


sys.modules["board_config"] = _Board()
_headless.display(W, H)
_headless.pointer()

from appkit import connections  # noqa: E402
from appkit import launcher as L  # noqa: E402
from appdev import App  # noqa: E402
from deskkit import forecast  # noqa: E402

connections.register = lambda registry=None: []
fake.bench(endpointkit.registry, delay=1)
L.restart_into = lambda name, count=1: (_ for _ in ()).throw(OSError("no restarts in these checks"))

# A forecast already in hand, for the town the network says it's in.
forecast.ip_place = {"name": "Kennett Square", "lat": 39.85, "lon": -75.71, "from_ip": True, "units": "F"}
forecast.latest = {
    "temp": 41.2, "feels": 35.4, "code": 61, "is_day": True, "hi": 44.0, "lo": 33.1,
    "as_of": "10:15", "utc_offset": -18000,
    "days": [("Thu", 61, 44.0, 33.1, 80), ("Fri", 3, 47.5, 30.2, 10), ("Sat", 0, 51.0, 35.0, 0),
             ("Sun", 71, 36.0, 28.0, 65), ("Mon", 95, 58.0, 49.0, 100)],
}
forecast.keep_fresh = lambda scope, on_update=None: None

la = L.Launcher(App.current() or App())
la.scan(_join(_ROOT, "apps"))

import apps.weather as weather  # noqa: E402
from apps.weather import sizing  # noqa: E402

# -- plants: each must make a check fail -------------------------------------


def _plant_full_size():
    # Everything keeps the size it has on a 480-pixel screen.
    sizing.scale = lambda width, height: 1.0


def _plant_corner():
    # Everything is drawn for a screen twice the size of the one it is on.
    sizing.scale = lambda width, height: min(width, height) / 960


def _plant_under_home():
    # The words start at the top of the screen, under the Home button.
    sizing.below_home = lambda scope, gap=4, centred=True: 0


def _plant_square_rows():
    # The five days' rows run to the edges of the square, round screen or not.
    sizing.half_width = lambda width, height, round_, top, bottom, margin=6: width // 2 - margin


PLANTS = {
    "full_size": _plant_full_size,
    "corner": _plant_corner,
    "square_rows": _plant_square_rows,
    "under_home": _plant_under_home,
}
plant = os.getenv("WEATHER_PLANT")
if plant:
    PLANTS[plant]()
del weather, sizing


def settle(ms=200):
    for _ in range(ms // 20):
        _headless.advance(20)


def box(obj):
    """The area *obj* covers on screen, scaled as it's drawn."""
    obj.update_layout()
    a = lv.area_t()
    obj.get_coords(a)
    x1, y1, x2, y2 = a.x1, a.y1, a.x2, a.y2
    scale = obj.get_style_transform_scale_x(0)
    if scale and scale != 256:
        cx, cy, hw, hh = (x1 + x2) / 2, (y1 + y2) / 2, (x2 - x1) / 2, (y2 - y1) / 2
        x1, x2 = cx - hw * scale / 256, cx + hw * scale / 256
        # The line's empty space above and below the digits doesn't count.
        hh = hh * scale / 256 * 3 / 4
        y1, y2 = cy - hh, cy + hh
    return x1, y1, x2, y2


def inside(b, what):
    x1, y1, x2, y2 = b
    ok = x1 >= 0 and y1 >= 0 and x2 < W and y2 < H
    check(ok, "%s is on the screen: %r" % (what, b))
    if ROUND and ok:
        r = W / 2
        worst = max(((x - r + 0.5) ** 2 + (y - r + 0.5) ** 2) ** 0.5 for x in (x1, x2) for y in (y1, y2))
        check(worst <= r + 1, "%s is inside the circle: %r, %.0f from the middle" % (what, b, worst))


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def parts(panel):
    """``(what, obj)`` for each word, key and icon *panel* shows."""
    out = []
    for i in range(panel.get_child_count()):
        c = panel.get_child(i)
        if c.has_flag(lv.obj.FLAG.HIDDEN):
            continue
        if c.check_type(lv.label_class):
            out.append((repr(c.get_text()), c))
        elif c.check_type(lv.button_class):
            out.append(("a key", c))
        else:
            out.append(("an icon", c))
    return out


def fits(panel, name):
    found = parts(panel)
    check(len(found) > 3, "the %s screen shows something: %d parts" % (name, len(found)))
    boxes = [(what, box(obj)) for what, obj in found]
    button = la.shell.home_button
    if button is not None and not button.has_flag(lv.obj.FLAG.HIDDEN):
        boxes.append(("the Home button", box(button)))
    for what, b in boxes:
        inside(b, "on the %s screen, %s" % (name, what))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if overlap(boxes[i][1], boxes[j][1]):
                check(False, "on the %s screen, %s and %s overlap: %r %r"
                      % (name, boxes[i][0], boxes[j][0], boxes[i][1], boxes[j][1]))
    return boxes


def shot(name):
    if SHOTS:
        _headless.refresh()
        _headless.save_raw(_join(SHOTS, "weather_%s_%s.raw" % (SIZE, name)), W, H)


from touchkit import shell as touch  # noqa: E402

la.home = "watch" if ROUND else "home"
la.shell = touch.TouchShell(la)
la.boot("weather")
settle(600)
check(la.current == "weather", "Weather is open: %r" % (la.current,))
b = la.shell.home_button
check(b is not None and not b.has_flag(lv.obj.FLAG.HIDDEN), "the Home button is over Weather")
root = la.scope.root


def panels():
    return [root.get_child(i) for i in range(root.get_child_count())
            if not root.get_child(i).check_type(lv.label_class)]


now, days = panels()[:2]
boxes = fits(now, "now")
boxes = [(what, b) for what, b in boxes if what != "the Home button"]
top = min(b[1] for _, b in boxes)
bottom = max(b[3] for _, b in boxes)
check(bottom - top >= H * 55 // 100, "the now screen fills the height: %d of %d" % (bottom - top, H))
shot("now")

now.add_flag(lv.obj.FLAG.HIDDEN)
days.remove_flag(lv.obj.FLAG.HIDDEN)
settle()
fits(days, "days")
shot("days")

# A long press: the ZIP pad.
_headless.touch(W // 2, H // 2, True, 50)
for _ in range(60):
    _headless.touch(W // 2, H // 2, True, 20)
_headless.touch(W // 2, H // 2, False, 50)
settle()
pad = panels()[-1]
check(pad.get_child_count() > 12, "a long press brings up the ZIP pad")
fits(pad, "ZIP pad")
shot("zip")

if la.scope is not None:
    la.scope.stop_timers()
print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
