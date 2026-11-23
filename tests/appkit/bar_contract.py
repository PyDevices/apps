# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit's status bar on real LVGL with no window, over endpointkit's fakes.

Apps from ``sample_bar`` run through a real Launcher with ``Shell(bar=True)``:
one under the bar with an item of its own, one that takes the whole screen,
and one that opens the picker and the on-screen keyboard. Each check reads
the bar's items, the app's area and what the Shell holds.

    python tests/appkit/bar_contract.py
    micropython tests/appkit/bar_contract.py

endpointkit, icons and (on CPython) ttfio come from the omnipython checkout
`_harness` finds (``OMNIPYTHON_LIB``, or one beside this repository).
``BAR_SHOTS=<folder>`` saves the screen as a raw RGB565 frame.
``BAR_PLANT=<name>`` breaks the bar one way from `PLANTS`, and the checks
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
# lib first: tests/appkit would hide the real appkit.
_PATHS = [_join(_ROOT, "lib"), _HERE, _TESTS,
          _join(_OMNI, "packages", "endpointkit"), _LIB]
# On MicroPython icons and ttfio come built in, so the font stays in flash and off the heap.
if sys.implementation.name != "micropython":
    _PATHS.insert(3, _join(_OMNI, "packages", "icons"))
    _PATHS.append(_join(_OMNI, "utils"))   # ttfio over freetype-py
sys.path[:0] = _PATHS

try:
    import endpointkit
    import icons  # noqa: F401
    import lvgl as lv
    from endpointkit import fake
except ImportError as e:
    print("can't run the bar checks:", e)
    sys.exit(2)

import _headless

failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


SW, SH = 480, 320
SHOTS = os.getenv("BAR_SHOTS")

# A board config with a battery behind an ADC: 3.75 V is half full.
class _Battery:
    def __init__(self):
        self.volts = 3.75

    def voltage(self):
        return self.volts


class _Board:
    pass


board = _Board()
cell = _Battery()
board.battery = lambda: cell
sys.modules["board_peripherals"] = board
# No display driver or BOOT button: only the display made here.
sys.modules["board_config"] = _Board()

_headless.display(SW, SH)
_headless.pointer()

from appkit import bar as B  # noqa: E402
from appkit import keys  # noqa: E402
from appkit import launcher as L  # noqa: E402
from appkit.shell import Shell  # noqa: E402
from appkit import connections  # noqa: E402

# The fakes are this device: the Shell registers no real provider beside them.
connections.register = lambda registry=None: []
from touchkit import shell as touch  # noqa: E402
from touchkit import ui  # noqa: E402

# The board's theme goes on once, before any shell, as on a board, where
# the one TouchShell sets it and hover wraps it.
ui.apply_theme()
ui.apply_theme = lambda: None
from appdev import App  # noqa: E402
from sample_bar import seen  # noqa: E402

# -- plants: each must make a check fail -------------------------------------


def _plant_redraws_all():
    real = B.Bar._draw
    B.Bar._draw = lambda self, item, force=False: real(self, item, True)


def _plant_root_under_bar():
    Shell.make_root = lambda self, scope: scope.screen()


def _plant_items_stay():
    real = B.Bar.add
    B.Bar.add = lambda self, item, owner=None: real(self, item)


def _plant_overlays_die():
    import appkit.scope

    appkit.scope.keep = lambda obj: obj


def _plant_home_everywhere():
    B.Bar.set_home = lambda self, visible: None


def _plant_no_way_home():
    Shell._corner_home = lambda self, scope: False


def _plant_touch_header_behind_bar():
    from touchkit import shell as touch

    touch.TouchShell.bar_area = lambda self, screen: screen


PLANTS = {
    "redraws_all": _plant_redraws_all,
    "root_under_bar": _plant_root_under_bar,
    "items_stay": _plant_items_stay,
    "overlays_die": _plant_overlays_die,
    "home_everywhere": _plant_home_everywhere,
    "no_way_home": _plant_no_way_home,
    "touch_header_behind_bar": _plant_touch_header_behind_bar,
}
plant = os.getenv("BAR_PLANT")
if plant:
    PLANTS[plant]()


def settle(ms=200):
    for _ in range(ms // 20):
        _headless.advance(20)


def coords(obj):
    obj.update_layout()
    a = lv.area_t()
    obj.get_coords(a)
    return a.x1, a.y1, a.x2 - a.x1 + 1, a.y2 - a.y1 + 1


def tap(obj):
    x, y, w, h = coords(obj)
    _headless.touch(x + w // 2, y + h // 2, True, 50)
    _headless.touch(x + w // 2, y + h // 2, False, 50)


def icon_of(b, name):
    for n, icon, text in b.status():
        if n == name:
            return icon
    return None


def text_of(b, name):
    for n, icon, text in b.status():
        if n == name:
            return text
    return None


# -- a launcher with the bar ----------------------------------------------------

# An app that doesn't close cleanly makes the launcher restart the program;
# here that's recorded and refused, so the run carries on and the check says so.
restarts = []


def _no_restart(name, count=1):
    restarts.append(name)
    raise OSError("restarts are recorded, not done, in these checks")


L.restart_into = _no_restart

fakes = fake.bench(endpointkit.registry, delay=1)
la = L.Launcher(App.current() or App(), {"framed": "sample_bar.framed", "whole": "sample_bar.whole",
                                         "chooser": "sample_bar.chooser"}, home="whole")
la.info["whole"] = {"bar": "none"}
shell = Shell(la, bar=True)
la.shell = shell
bar = shell.bar
check(bar is not None and shell.home_button is None, "bar=True makes the bar, with Home on it, not the corner button")
check(coords(bar.root) == (0, 0, SW, B.HEIGHT), "the bar is the top strip: %r" % (coords(bar.root),))
check([i.name for i in bar.items] == ["clock", "net", "bluetooth", "audio", "battery"],
      "the built-in items this device has: %r" % ([i.name for i in bar.items],))
clock = text_of(bar, "clock")
check(clock is not None and len(clock) == 5 and clock[2] == ":", "the clock: %r" % (clock,))
check(icon_of(bar, "net") == "wifi", "connected over Wi-Fi: %r" % (icon_of(bar, "net"),))
check(icon_of(bar, "battery") == "battery_3_bar" and text_of(bar, "battery") == "50%",
      "half a battery from its voltage: %r %r" % (icon_of(bar, "battery"), text_of(bar, "battery")))
check(icon_of(bar, "audio") is None and icon_of(bar, "bluetooth") is None, "no audio out or Bluetooth chosen: nothing")

la.switch("framed")
scope = seen["framed"]
check(scope.bar is bar and bar.is_shown(), "an app gets the bar on its scope, showing")
check(scope.rect == (0, B.HEIGHT, SW, SH - B.HEIGHT), "and the screen below it: %r" % (scope.rect,))
check(bar.home is not None and not bar.home.has_flag(lv.obj.FLAG.HIDDEN), "Home shows away from home")
check(icon_of(bar, "casting") == "cast" and text_of(bar, "casting") == "Den", "the app's own item is on the bar")
labels = [s[2] for s in bar._shown.values() if s[2] is not None]
check(labels and all(lb.get_style_text_color(0).red == 0xFF and lb.get_style_text_color(0).blue == 0xFF
                     for lb in labels), "the bar's text is in its own colour, not the theme's")
_headless.refresh()
if SHOTS:
    _headless.save_raw(_join(SHOTS, "bar.raw"), SW, SH)

# Hidden for a while, the app's area grows to the whole screen, and back.
scope.bar.hide()
check(not bar.is_shown() and scope.rect == (0, 0, SW, SH), "hide gives the app the whole screen: %r" % (scope.rect,))
scope.bar.show()
check(bar.is_shown() and scope.rect == (0, B.HEIGHT, SW, SH - B.HEIGHT), "show gives the strip back: %r" % (scope.rect,))

# The items follow endpointkit, and only what changed is redrawn.
net_box = bar._shown["net"][0]
bar.tick()
check(bar._shown["net"][0] == net_box, "an item that didn't change isn't redrawn")
fakes["wlan"].set_state("home", endpointkit.AVAILABLE)
bar.tick()
check(icon_of(bar, "net") == "wifi_off", "Wi-Fi dropping shows: %r" % (icon_of(bar, "net"),))
fakes["wlan"].set_state("home", endpointkit.CONNECTED)
bar.tick()
endpointkit.select("audio.out", "i2s:0")
check(icon_of(bar, "audio") == "headphones", "choosing the jack shows at once: %r" % (icon_of(bar, "audio"),))
endpointkit.select("audio.out", ["a2dp:spk"])
bar.tick()
check(icon_of(bar, "bluetooth") == "bluetooth", "a chosen Bluetooth speaker shows Bluetooth")
fakes["a2dp"].set_state("spk", endpointkit.CONNECTED)
bar.tick()
check(icon_of(bar, "bluetooth") == "bluetooth_connected", "and connected when it connects")
endpointkit.select("audio.out", None)
cell.volts = None
for _ in range(30):
    bar.tick()
check(icon_of(bar, "battery") is None, "a battery that reads nothing leaves the bar")
cell.volts = 4.2

# The connections button opens the picker.
tap(bar.connections)
check(shell.picker is not None and shell.picker.is_open(), "the connections button opens the picker")
shell.picker.close()

# The app wanting the whole screen gets it, and the first app's item goes with it.
la.switch("whole")
settle()
scope = seen["whole"]
check(not bar.is_shown() and scope.rect == (0, 0, SW, SH), '"bar": "none" gets the whole screen: %r' % (scope.rect,))
check(bar.home is not None and bar.home.has_flag(lv.obj.FLAG.HIDDEN), "and on the home screen there's no Home")
check(all(i.name != "casting" for i in bar.items), "a closed app's item leaves the bar")
check(restarts == [], "and nothing on the bar holds the closed app: %r" % (restarts,))

# Home goes home.
la.switch("framed")
settle()
tap(bar.home)
# The launcher switches from a timer on the real clock: wait for it, up to 3 s.
import time  # noqa: E402

for _ in range(60):
    if la.current == "whole":
        break
    time.sleep(0.05)
    settle(40)
check(la.current == "whole", "Home on the bar goes home: %r" % (la.current,))

# The picker and the keyboard, first made while an app ran, outlive it.
la.switch("chooser")
settle()
picker = shell.picker
board_kb = keys.keyboard()
la.switch("framed")
settle()
alive = True
try:
    picker.root.get_child_count()
    board_kb.get_child_count()
except Exception:
    alive = False
check(alive and picker.root.get_parent() is not None, "the picker and keyboard survive the app that opened them")
if alive:
    got = shell.open_picker("audio.out")
    check(got.is_open() and got.kind == "audio.out", "and the picker opens again")
    got.close()

# A bad "bar" value is refused by name.
la.info["framed"] = {"bar": "sometimes"}
try:
    shell.bar_mode(seen["framed"])
    said = None
except ValueError as e:
    said = str(e)
check(said is not None and "sometimes" in said, "an unknown bar value says so: %r" % (said,))
la.info["framed"] = {}

# The compact cap: the clock, the network and the battery, and a tap opens the picker.
opened = []
cap = B.Bar(compact=True, on_picker=opened.append, tick_ms=0)
check([i.name for i in cap.items] == ["clock", "net", "battery"], "the cap's items: %r" % ([i.name for i in cap.items],))
x, y, w, h = coords(cap.root)
check(w < SW // 2 and y >= 0, "the cap is small, at the top: %r" % ((x, y, w, h),))
tap(cap.root)
check(opened == [None], "tapping the cap opens the picker: %r" % (opened,))
cap.close()

# An app that takes the whole screen, away from home, keeps a way home: the
# corner button, since the bar and its Home are hidden.
la.info["chooser"] = {"bar": "none"}
la.switch("chooser")
settle()
corner = shell.home_button
check(corner is not None and not corner.has_flag(lv.obj.FLAG.HIDDEN) and not bar.is_shown(),
      '"bar": "none" away from home gets the corner Home button')
la.info["chooser"] = {}
la.switch("framed")
settle()
check(corner is None or corner.has_flag(lv.obj.FLAG.HIDDEN), "under the bar the corner button hides again")
la.switch("whole")
settle()

# Under the compact cap the bar has no Home: every app away from home gets
# the corner button, and the whole screen.
la.shell = None
bar.close()
if corner is not None:
    corner.add_flag(lv.obj.FLAG.HIDDEN)   # the old shell's, left alone
real_min = B.FULL_MIN
B.FULL_MIN = (SW + 1, SH)
small = Shell(la, bar=True)
la.shell = small
B.FULL_MIN = real_min
la.switch("framed")
settle()
scope = seen["framed"]
check(small.bar.compact and small.bar.home is None, "a narrow screen gets the cap, with no Home on it")
check(scope.rect == (0, 0, SW, SH), "under the cap the app gets the whole screen: %r" % (scope.rect,))
check(small.home_button is not None and not small.home_button.has_flag(lv.obj.FLAG.HIDDEN),
      "and the corner Home button")
la.switch("whole")
settle()
check(small.home_button.has_flag(lv.obj.FLAG.HIDDEN), "which hides on the home screen")

# touchkit's shell under the bar: the bar, then a shorter header, so the app's
# area is where it was without the bar; hiding the bar moves both up.
la.shell = None
small.bar.close()
small.home_button.add_flag(lv.obj.FLAG.HIDDEN)
la.info["whole"] = {}   # Home under the bar, as a board's is
board_shell = touch.TouchShell(la)
la.shell = board_shell

check(board_shell.bar is not None and board_shell.home_button is None, "TouchShell shows the bar by default")
la.switch("framed")
settle()
scope = seen["framed"]
check(scope.rect == (0, ui.HEADER, SW, SH - ui.HEADER), "TouchShell's app area is below the bar and header: %r" % (scope.rect,))
check(coords(scope.header)[1] == B.HEIGHT, "its header sits below the bar: %r" % (coords(scope.header),))
scope.bar.hide()
check(scope.rect == (0, ui.HEADER - B.HEIGHT, SW, SH - ui.HEADER + B.HEIGHT) and coords(scope.header)[1] == 0,
      "hiding the bar moves the header and the app up: %r" % (scope.rect,))
scope.bar.show()
la.switch("whole")
settle()
scope = seen["whole"]
check(scope.rect == (0, B.HEIGHT, SW, SH - B.HEIGHT), "TouchShell's home screen is below the bar: %r" % (scope.rect,))

print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
