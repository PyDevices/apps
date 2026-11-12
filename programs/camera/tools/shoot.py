# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Drive the app on the desktop with key presses and save a screenshot of
each page and popup state. Run from the sketch folder with the desktop
MicroPython (see the README); ARGB captures go to $EYECAM_SHOTS and
tools/shots_to_png.py turns them into PNGs. A capture is LVGL's snapshot
of the screen and of the top layer; the window shows the same pixels.

Each step is (milliseconds to wait first, action). Actions: a key name
("m", "up", "down", "enter", "+", "-", "s", "f", "u", "r"), "shot NAME",
"tap X Y" and "swipe X Y DY" (panel pixels; a touch press, and a drag), "page" (print the state),
"knob+" / "knob-" (three quick detents), "quit".
"""

import os
import sys

import events
import keys
import multimer

import displaydev.sdldisplay as sdl

_queue = []
_orig = sdl.get_events


def _get_events():
    got = _orig()
    if _queue:
        got = (got or []) + _queue[:]
        del _queue[:]
    return got


sdl.get_events = _get_events

KEYS = {
    "m": keys.K_m, "up": keys.K_UP, "down": keys.K_DOWN, "enter": keys.K_RETURN,
    "+": keys.K_PLUS, "-": keys.K_MINUS, "s": keys.K_s, "f": keys.K_f, "u": keys.K_u, "r": keys.K_r,
}
OUT = os.getenv("EYECAM_SHOTS") or "shots"


def press(name):
    k = KEYS[name]
    _queue.append(events.Key(events.KEYDOWN, name, k, 0, 0, None))
    _queue.append(events.Key(events.KEYUP, name, k, 0, 0, None))


def touch(kind, x, y):
    t = {"down": events.MOUSEBUTTONDOWN, "up": events.MOUSEBUTTONUP}[kind]
    _queue.append(events.Button(t, (x, y), 1, False, None))


def move(x, y, dx, dy):
    _queue.append(events.Motion(events.MOUSEMOTION, (x, y), (dx, dy), 1, False, None))


def shot(name):
    """LVGL's own render of the active screen, with the top layer over it."""
    import lvgl as lv

    with open("%s/%s.rgb" % (OUT, name), "wb") as f:
        for layer in (lv.screen_active(), lv.layer_top()):
            snap = lv.snapshot_take(layer, lv.COLOR_FORMAT.ARGB8888)
            h = snap.header
            data = snap.data.__dereference__(h.stride * h.h)
            f.write(b"%d %d %d\n" % (h.w, h.h, h.stride))
            f.write(bytes(data))
            snap.destroy()
    print("shot", name)


def run(steps):
    it = iter(steps)

    def nxt(t=None):
        try:
            wait, action = next(it)
        except StopIteration:
            return
        multimer.after(max(1, wait), lambda t: do(action))

    def do(action):
        if action.startswith("shot "):
            shot(action[5:])
        elif action == "quit":
            print("done")
            sys.exit(0)
        elif action.startswith("page"):
            import apps.eyecam as app

            print("page", app.eye.page, "mag", app.eye.mag, "events", app.eye.events[-3:])
        elif action.startswith("tap "):  # tap X Y: a press and release on the panel
            x, y = (int(v) for v in action.split()[1:])
            touch("down", x, y)
            multimer.after(80, lambda t: touch("up", x, y))
        elif action.startswith("swipe "):  # swipe X Y DY: drag DY pixels down (negative: up)
            x, y, dy = (int(v) for v in action.split()[1:])
            touch("down", x, y)
            for i in range(1, 6):
                multimer.after(40 * i, lambda t, i=i: move(x, y + dy * i // 5, 0, dy // 5))
            multimer.after(260, lambda t: touch("up", x, y + dy))
        elif action in ("knob+", "knob-"):
            for _ in range(3):
                press("+" if action == "knob+" else "-")
        else:
            press(action)
        nxt()

    nxt()


def load(path):
    steps = []
    with open(path) as f:
        for line in f:
            line = line.split("#")[0].strip()
            if line:
                ms, action = line.split(None, 1)
                steps.append((int(ms), action))
    return steps


try:
    os.mkdir(OUT)
except OSError:
    pass
run(load(sys.argv[1] if len(sys.argv) > 1 else "tools/shots.txt"))

import appkit  # noqa: E402

appkit.run("eyecam")
