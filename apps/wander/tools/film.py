# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Run the app on a display in memory and write what it shows, from MicroPython.

    micropython -X heapsize=256M tools/film.py OUT_DIR [SCRIPT] [WIDTH HEIGHT]

Run it from the app's folder, in a checkout of the apps repository. SCRIPT is
"tour" (the default: every frame of a twelve-second tour, as f0000.bmp and
on), or "stills" (named pictures of each place and view). Frames are 16-bit
BMP files. The timings printed at the end are this machine's: what svgio
spent building, parsing and drawing, and LVGL on each frame.
"""

import sys
import time

sys.path.insert(0, "..")
sys.path.insert(0, "../../tests")

import _headless  # noqa: E402
import lvgl as lv  # noqa: E402

import wander  # noqa: E402
from wander.stage import TICK_MS  # noqa: E402
from wander.tools.still import write_bmp  # noqa: E402


class Scope:
    """As much of an appkit scope as the app uses."""

    def __init__(self, size):
        self.size = size
        self.root = lv.obj(None)
        lv.screen_load(self.root)
        self.ticks = []
        self.closers = []

    def every(self, ms, callback):
        self.ticks.append(callback)

    def on_close(self, fn):
        self.closers.append(fn)


class Film:
    def __init__(self, out, size):
        self.out = out
        self.w, self.h = size
        self.frame = _headless.display(self.w, self.h)
        _headless.pointer()
        self.scope = Scope(size)
        wander.main(self.scope)
        self.stage, self.dock = self.scope.wander
        self.count = 0
        self.lvgl_us = 0
        self.lvgl_max = 0
        self.steps = 0
        self.tick_max = 0

    def step(self, save=None):
        """One tick of the app, one LVGL frame, and maybe one picture written."""
        t0 = time.ticks_us()
        for tick in self.scope.ticks:
            tick()
        t1 = time.ticks_us()
        _headless.advance(TICK_MS)
        _headless.refresh()
        spent = time.ticks_diff(time.ticks_us(), t1)
        self.lvgl_us += spent
        self.lvgl_max = max(self.lvgl_max, spent)
        self.tick_max = max(self.tick_max, time.ticks_diff(t1, t0))
        self.steps += 1
        if save is True:
            write_bmp("%s/f%04d.bmp" % (self.out, self.count), self.frame, self.w, self.h)
            self.count += 1
        elif save:
            write_bmp("%s/%s.bmp" % (self.out, save), self.frame, self.w, self.h)

    def run(self, ticks, save=None):
        for _ in range(ticks):
            self.step(save)

    def settle(self, save=None):
        """Run until the change being drawn is done."""
        self.step(save)
        while self.stage.busy:
            self.step(save)

    def touch(self, x, y, save=None):
        _headless.touch(x, y, True, 0)
        self.step(save)
        self.step(save)
        _headless.touch(x, y, False, 0)
        self.step(save)

    def press(self, index, save=None):
        """A finger on the dock's button *index*, shown first if it was hidden."""
        if self.dock.left <= 0:
            self.touch(12, 12, save)
        area = lv.area_t()
        self.dock.buttons[index].get_coords(area)
        self.touch((area.x1 + area.x2) // 2, (area.y1 + area.y2) // 2, save)

    def on_hue(self):
        x, y = self.stage._origin()
        return int(x), int(y - self.h * 0.12)

    def report(self):
        s = self.stage.stats
        print("svgio: text built %d ms, garbage collected %d ms, parsed %d ms, drawn %d ms; %d poses, %d bands" % (s["text"] // 1000, s["tidy"] // 1000, s["parse"] // 1000, s["draw"] // 1000, s["poses"], s["bands"]))
        print("slowest band %d us, slowest pose %d us, slowest tick %d us" % (s["band_us"], s["pose_us"], self.tick_max))
        print("LVGL frame: mean %d us, slowest %d us, over %d frames" % (self.lvgl_us // max(self.steps, 1), self.lvgl_max, self.steps))
        print("pictures held: now %d KB, peak %d KB" % (self.stage.held_bytes() // 1024, s["peak"] // 1024))


def tour(film):
    """Twelve seconds: a walk, a blink, the tongue, new colours, another place, a closer view."""
    stage = film.stage
    film.settle(True)
    stage.cues[:] = ["blink", "stroll", "tongue"]
    stage._wait = 4
    while stage.cues:
        film.step(True)
    film.run(28, True)
    film.press(1, True)  # autumn: the colours come over it as the coast is redrawn
    film.settle(True)
    film.run(22, True)
    film.touch(*film.on_hue(), save=True)  # a finger on it
    film.run(30, True)
    film.press(0, True)  # the workbench
    film.settle(True)
    stage.cues[:] = ["look"]
    film.run(40, True)
    film.press(2, True)  # closer
    film.settle(True)
    film.run(30, True)


def stills(film):
    stage = film.stage
    film.settle()
    film.run(8, "app_coast")
    film.touch(12, 12)
    film.run(3, "app_coast_dock")
    for name in ("autumn", "winter", "night", "spring"):
        stage.go(variant=name)
        film.settle()
        film.run(60, "app_coast_%s" % name)
    stage.go(variant="winter", view="mid")
    film.settle()
    film.run(5, "app_coast_winter_mid")
    stage.go(view="close")
    film.settle()
    film.run(5, "app_coast_winter_close")
    stage.go("bench", view="wide")
    film.settle()
    film.run(5, "app_bench")
    stage.go(variant="copper")
    film.step()
    film.step()
    film.run(1, "app_bench_shift")  # half way from one set of colours to the next
    film.settle()
    film.run(5, "app_bench_copper")
    stage.go(view="close")
    film.settle()
    film.run(5, "app_bench_close")
    stage.go("desk", view="wide")
    film.settle()
    film.run(5, "app_desk")
    stage.cues[:] = ["turn"]
    stage._wait = 0
    film.run(30, "app_desk_hello")
    stage.go(variant="evening", view="mid")
    film.settle()
    film.run(5, "app_desk_evening_mid")
    stage.go(variant="night", view="wide")
    film.settle()
    film.run(20, "app_desk_night")


def main():
    out = sys.argv[1]
    script = sys.argv[2] if len(sys.argv) > 2 else "tour"
    size = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (800, 480)
    film = Film(out, size)
    {"tour": tour, "stills": stills}[script](film)
    film.report()
    for fn in film.scope.closers:
        fn()


main()
