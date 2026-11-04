# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""DeskShell on real LVGL with no window: a finger swipes, and the hours pass.

``DESK_PLANT`` swaps in a fault that a check below must catch; test_deskkit.py
runs each one.
"""

import os
import sys

_HERE = __file__.rsplit("/", 1)[0]
# lib first: tests/appkit would hide the real appkit.
sys.path[:0] = [_HERE + "/../lib", _HERE]
_PYDEVICES = os.getenv("PYDEVICES_LIB") or _HERE + "/../../pydevices/lib"
sys.path.append(_PYDEVICES)


class _Pin:
    state = 1

    def value(self, v):
        _Pin.state = v


class _Board:
    backlight = _Pin()


class _Stub:
    pass


sys.modules["board_config"] = _Board
for _name in ("requests", "wifi_manager"):
    sys.modules[_name] = _Stub()

import lvgl as lv

import _headless

SIZE = 480
_headless.display(SIZE, SIZE)
_headless.pointer()

from deskkit import localtime
from deskkit.shell import DeskShell, tune_touch

PLANT = os.getenv("DESK_PLANT")


class _Launcher:
    home = None
    current = "clock"

    def __init__(self):
        self.asked = []

    def request(self, name):
        self.asked.append(name)
        self.current = name


class _Scope:
    def screen(self):
        scr = lv.obj(None)
        lv.screen_load(scr)
        return scr


# The real panel's indev: display_driver asks for 255 px.
_headless.pointer().set_gesture_min_distance(255)
if PLANT != "untuned_touch":
    tune_touch(_headless.pointer())


def check(ok, what):
    if not ok:
        print("FAILED:", what)
        sys.exit(1)


localtime.offset_s = 0
launcher = _Launcher()
shell = DeskShell(launcher, ("clock", "weather"), awake=(7, 18), weekends=False, idle_ms=60_000)
root = shell.make_root(_Scope())
lv.refr_now(None)

if PLANT == "swapped_swipes":
    _real = launcher.request
    launcher.request = lambda name: _real("clock" if name == "weather" else "weather")
if PLANT == "no_idle_return":
    shell.idle_ms = 10**9


def swipe(x0, y0, x1, y1):
    _headless.touch(x0, y0, False)
    _headless.touch(x0, y0, True)
    steps = 6
    for i in range(1, steps + 1):
        _headless.touch(x0 + (x1 - x0) * i // steps, y0 + (y1 - y0) * i // steps, True)
    _headless.touch(x1, y1, False)
    _headless.advance(50)


# Slow swipes recorded from a CST820 on a real panel, repeated positions and all.
# Neither reached 255 px between repeats.
_RECORDED = (
    (479, 479, 479, 478, 476, 473, 468, 459, 447, 433, 417, 401, 386, 371, 371, 355, 336, 317, 299, 282, 265, 251, 237, 222),
    (447, 444, 439, 433, 425, 414, 403, 389, 374, 358, 358, 341, 322, 304, 285, 268, 254, 242, 232, 222, 212, 203, 193, 183, 172, 172, 161, 150, 140),
)


def replay(xs):
    _headless.touch(xs[0], 250, True, 40)
    for x in xs:
        _headless.touch(x, 250, True, 40)
    _headless.touch(xs[-1], 250, False, 40)
    _headless.advance(50)


for _xs in _RECORDED:
    launcher.current = "clock"
    del launcher.asked[:]
    replay(_xs)
    check(launcher.asked == ["weather"], "a recorded slow swipe: %r" % (launcher.asked,))
launcher.current = "clock"
del launcher.asked[:]

swipe(380, 240, 80, 240)
check(launcher.asked == ["weather"], "a swipe left from the clock asks for weather: %r" % (launcher.asked,))
del launcher.asked[:]
swipe(80, 240, 380, 240)
check(launcher.asked == ["clock"], "a swipe right from weather asks for the clock: %r" % (launcher.asked,))
del launcher.asked[:]
swipe(240, 380, 240, 80)
check(not launcher.asked, "a swipe up belongs to the app: %r" % (launcher.asked,))

launcher.current = "weather"
# A minute with no touch goes home.
_headless.advance(61_000)
_headless.advance(1_100)
check(launcher.asked == ["clock"], "idle returns to the first app: %r" % (launcher.asked,))

# Noon on a Wednesday, then midnight, then a Saturday noon, all a minute idle.
_noon_wed = (2026, 11, 4, 12, 0, 0, 2, 308)
_midnight = (2026, 11, 4, 0, 0, 0, 2, 308)
_noon_sat = (2026, 11, 7, 12, 0, 0, 5, 311)
localtime.is_set = lambda: True
localtime.offset_s = 0
for moment, lit in ((_noon_wed, 1), (_midnight, 0), (_noon_sat, 0), (_noon_wed, 1)):
    localtime.now = lambda: moment
    _headless.advance(1_100)
    if PLANT == "never_dark":
        shell._set_lit(True)
    check(_Pin.state == lit, "the backlight at %r should be %d" % (moment[:6], lit))

# A touch lights a dark screen.
localtime.now = lambda: _midnight
_headless.advance(1_100)
check(_Pin.state == 0, "dark at midnight")
_headless.touch(240, 240, True, 100)
_headless.touch(240, 240, False, 100)
_headless.advance(1_100)
check(_Pin.state == 1, "a tap wakes it")
_headless.advance(61_000)
_headless.advance(1_100)
check(_Pin.state == 0, "and it goes dark again")

# Without the real time, never dark.
localtime.is_set = lambda: False
_headless.advance(1_100)
check(_Pin.state == 1, "an unset clock keeps the screen on")

# Asking for the ZIP code, swipes and idle both leave it alone.
localtime.is_set = lambda: True
localtime.offset_s = None
launcher.current = "weather"
del launcher.asked[:]
swipe(80, 240, 380, 240)
_headless.advance(61_000)
_headless.advance(1_100)
check(not launcher.asked, "no leaving the ZIP code screen: %r" % (launcher.asked,))
localtime.offset_s = 0

# Nor before the place, and so the timezone, is known.
localtime.is_set = lambda: True
localtime.now = lambda: _midnight
_Pin.state = 0
shell._lit = False
localtime.offset_s = None
_headless.advance(1_100)
check(_Pin.state == 1, "no timezone yet keeps the screen on")

print("desk contract: ok")
