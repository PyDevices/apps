# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The shared controls' contract, run on whichever interpreter runs this file.

Builds each control on a display with no window and drives it the way a host
and a hand do. Prints one ``PASS name`` or ``FAIL name: why`` line per check,
and exits 1 if anything failed. ``--plant`` makes a slider stop reporting its
changes, so the callback checks must fail: that is how test_controls.py knows
they can.

    micropython controls_contract.py [--plant]
"""

import sys

import _headless
import lvgl as lv

PLANT = "--plant" in sys.argv[1:]

_headless.display(800, 480)
_headless.pointer()

from controlpanel import LampButton, LedMeter, PadGrid, Slider  # noqa: E402
from controlpanel import slider as slider_module  # noqa: E402
from controlpanel.theme import BLACK  # noqa: E402

if PLANT:
    # A slider that moves its cap but never tells its host.
    def _silent_change(self, value):
        value = 0 if value < 0 else (127 if value > 127 else int(value))
        if value != self.value:
            self._show(value)

    slider_module.Slider._change = _silent_change

failures = []


def check(name, ok, why=""):
    if ok:
        print("PASS " + name)
    else:
        print("FAIL %s: %s" % (name, why))
        failures.append(name)


def screen():
    scr = lv.obj(None)
    lv.screen_load(scr)
    return scr


def point_at(obj):
    """Where the middle of *obj* is on the screen."""
    area = lv.area_t()
    obj.get_coords(area)
    return (area.x1 + area.x2) // 2, (area.y1 + area.y2) // 2


# ---- Slider ------------------------------------------------------------------

scr = screen()
events = []
slider = Slider(scr, 20, 20, 60, 200, BLACK, legend="Cutoff", value=40, led=True,
                on_change=lambda s, v: events.append(v))
_headless.refresh()
check("slider opens on its value", slider.value == 40, str(slider.value))

slider.set_value(300)
check("set_value clamps high", slider.value == 127, str(slider.value))
slider.set_value(-5)
check("set_value clamps low", slider.value == 0, str(slider.value))
check("set_value does not call on_change", events == [], str(events))

slider.set_value(60)
cx, cy = point_at(slider.cap)
_headless.touch(cx, cy, False)
_headless.touch(cx, cy, True)
for i in range(1, 11):
    _headless.touch(cx, cy - 3 * i, True)
_headless.touch(cx, cy - 30, False)
check("dragging the cap up raises the value", slider.value > 60, str(slider.value))
check("a drag reports its change once", events and events[-1] == slider.value, str(events))
_headless.refresh()

group = lv.group_create()
group.add_obj(slider.obj)
lv.group_focus_obj(slider.obj)
before = slider.value
group.send_data(lv.KEY.RIGHT)
check("the arrow key steps it up", slider.value == before + 1, "%d -> %d" % (before, slider.value))
group.send_data(lv.KEY.END)
check("End goes to the top", slider.value == 127, str(slider.value))
group.send_data(lv.KEY.HOME)
check("Home goes to the bottom", slider.value == 0, str(slider.value))

slider.set_led(0xFF2814)
check("the lamp lights", slider.lamp is not None and slider.lamp.rgb == 0xFF2814)
slider.set_led(None)
check("the lamp goes out", slider.lamp is not None and slider.lamp.rgb is None)

horizontal = Slider(scr, 100, 20, 200, 40, BLACK, legend="Mix", vertical=False, value=127)
horizontal.set_led(0x010203)
check("a slider without led=True has no lamp", horizontal.lamp is None)
check("a horizontal slider opens at its value", horizontal.value == 127)
scr.delete()

# ---- LedMeter ----------------------------------------------------------------

scr = screen()
meter = LedMeter(scr, 20, 20, 30, 200, BLACK, segments=16, legend="Out")
_headless.refresh()
meter.set_level(0.5)
check("half a level lights half the segments", meter._lit == 8, str(meter._lit))
meter.set_level(1.0)
check("full scale lights every segment", meter._lit == 16, str(meter._lit))
check("the top segment is red", meter._segments[15][1] == "red", str(meter._segments[15][1]))
check("the bottom segment is green", meter._segments[0][1] == "green", str(meter._segments[0][1]))
meter.set_level(-1)
check("a level below zero is zero", meter._lit == 0 and meter.level == 0.0)
scr.delete()

# ---- LampButton --------------------------------------------------------------

scr = screen()
presses = []
momentary = LampButton(scr, 10, 10, 60, 26, BLACK, legend="Tap", on_press=lambda b, v: presses.append(v))
_headless.refresh()
momentary.cap.send_event(lv.EVENT.CLICKED, None)
check("a momentary press calls on_press with True", presses == [True], str(presses))
check("a momentary lamp is lit at all times", momentary.lamp.rgb is not None)

toggled = []
button = LampButton(scr, 100, 10, 60, 26, BLACK, legend="Run", toggle=True, lamp=0x00FF00,
                    on_press=lambda b, v: toggled.append(v))
button.cap.send_event(lv.EVENT.CLICKED, None)
check("a toggle turns on at a press", button.on and toggled == [True], str(toggled))
check("a toggle's lamp shows its colour while on", button.lamp.rgb == 0x00FF00)
button.cap.send_event(lv.EVENT.CLICKED, None)
check("a second press turns it off", not button.on and toggled == [True, False], str(toggled))
check("a toggle's lamp goes out when off", button.lamp.rgb is None)
button.set_on(True)
check("set_on lights the lamp without a call", button.on and len(toggled) == 2)
button.set_lamp(None)
check("set_lamp(None) darkens the lamp", button.lamp.rgb is None)
scr.delete()

# ---- PadGrid -----------------------------------------------------------------

scr = screen()
hits = []
grid = PadGrid(scr, 10, 10, 320, 120, BLACK, cols=8, rows=2, on_press=lambda g, i: hits.append(i))
_headless.refresh()
grid.set_color(3, 0x00FF00)
check("a pad takes a colour", grid.colors[3] == 0x00FF00)
grid.set_color(3, None)
check("a pad goes dark with None", grid.colors[3] is None)
grid._pads[9].send_event(lv.EVENT.CLICKED, None)
check("a press reports its pad index", hits == [9], str(hits))
try:
    grid.set_color(16, 0x010203)
    check("an index past the grid is refused", False, "no error")
except IndexError:
    check("an index past the grid is refused", True)
scr.delete()

print("FAILED: %d" % len(failures) if failures else "ALL PASSED")
sys.exit(1 if failures else 0)
