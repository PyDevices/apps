# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Run Stompbox on a computer and script it, to prove it from a recording.

    micropython -X heapsize=128M tools/stompbox/drive.py [--clips DIR]
        [--clip NAME] [--effect NAME] [--play] [--record OUT.wav]
        [--turn T:key=value ...] [--master T:LEVEL ...] [--meter]
        [--shot T:OUT.raw ...] [--live ID] [--out ID] [--quit-after SECONDS]
        [--size WxH]

--turn moves a knob T seconds after start, through the same path a hand takes,
and --master moves the master, 0 to 1. --record writes what goes to the output.
--meter prints the level meter each time it changes. --shot saves the screen T
seconds after start, as a line "W H" and then the pixels in RGB565.
"""

import os
import sys

here = __file__.replace("\\", "/")
ROOT = here[: here.rfind("/tools/")] if "/tools/" in here else "."
sys.path.insert(0, ROOT + "/lib")
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def setenv(name, value):
    """For this process and what it imports: CPython's os.getenv reads
    os.environ, which os.putenv leaves alone."""
    os.putenv(name, value)
    if hasattr(os, "environ"):
        os.environ[name] = value


opts = {"clip": None, "effect": None, "play": False, "record": None, "turns": [],
        "quit": None, "meter": False, "shots": []}
size = "800x480"
argv = sys.argv[1:]
while argv:
    a = argv.pop(0)
    if a == "--clips":
        setenv("STOMPBOX_CLIPS", argv.pop(0))
    elif a == "--clip":
        opts["clip"] = argv.pop(0)
    elif a == "--effect":
        opts["effect"] = argv.pop(0)
    elif a == "--play":
        opts["play"] = True
    elif a == "--record":
        opts["record"] = argv.pop(0)
    elif a == "--turn":
        t, kv = argv.pop(0).split(":", 1)
        k, v = kv.split("=", 1)
        opts["turns"].append((float(t), k, float(v)))
    elif a == "--master":
        t, v = argv.pop(0).split(":", 1)
        opts["turns"].append((float(t), None, float(v)))
    elif a == "--meter":
        opts["meter"] = True
    elif a == "--shot":
        t, path = argv.pop(0).split(":", 1)
        opts["shots"].append((float(t), path))
    elif a == "--live":
        setenv("STOMPBOX_LIVE", "1")
        setenv("STOMPBOX_INPUT", argv.pop(0))
    elif a == "--out":
        setenv("STOMPBOX_OUT", argv.pop(0))
    elif a == "--quit-after":
        opts["quit"] = float(argv.pop(0))
    elif a == "--size":
        size = argv.pop(0)
    else:
        raise SystemExit("unknown option " + a)
opts["turns"].sort(key=lambda turn: turn[0])
opts["shots"].sort()
w, h = size.lower().split("x")
setenv("OMNIPYTHON_WIDTH", w)
setenv("OMNIPYTHON_HEIGHT", h)
setenv("OMNIPYTHON_SCALE", "1")

import appkit  # noqa: E402
import lvgl as lv  # noqa: E402
from display_driver import app as window  # noqa: E402
from multimer import ticks_diff, ticks_ms  # noqa: E402

t0 = [None]
begun = [False]
shown = [None]


def shot(path):
    """The screen as LVGL draws it, so it needs no window."""
    snap = lv.snapshot_take(lv.screen_active(), lv.COLOR_FORMAT.RGB565)
    w, h, stride = snap.header.w, snap.header.h, snap.header.stride
    pixels = bytes(snap.data.__dereference__(snap.data_size))
    with open(path, "wb") as f:
        f.write(("%d %d\n" % (w, h)).encode())
        for y in range(h):
            f.write(pixels[y * stride:y * stride + w * 2])
    lv.draw_buf_destroy(snap)


def begin(a):
    if opts["effect"] in a.effects:
        a.pick_effect(a.effects.index(opts["effect"]))
    elif opts["effect"]:
        a.set_show_all(True)
        a.pick_effect(a.effects.index(opts["effect"]))
    if opts["clip"]:
        for i, name in enumerate(a.clip_names()):
            if name == opts["clip"]:
                a.pick_clip(i)
    if opts["record"]:
        a.engine.record(opts["record"])
    if opts["play"]:
        a.toggle_play()


def poll(_):
    mod = sys.modules.get("apps.stompbox.app")
    a = mod.current if mod is not None else None
    if a is None:
        return
    if not begun[0]:
        begun[0] = True
        t0[0] = ticks_ms()
        begin(a)
    elapsed = ticks_diff(ticks_ms(), t0[0]) / 1000
    while opts["turns"] and opts["turns"][0][0] <= elapsed:
        _, key, value = opts["turns"].pop(0)
        if key is None:
            a.set_master(value)
            key = "master"
        else:
            a.screen.knobs[key].turn(value)
        print("%.2f s: %s = %.3f" % (elapsed, key, value))
    if opts["meter"] and shown[0] != (a.level_steps, a.clip):
        shown[0] = (a.level_steps, a.clip)
        print("%.2f s: level %d of %d%s" % (
            elapsed, a.level_steps, a.screen.level_bar.get_max_value(), "  CLIP" if a.clip else ""))
    while opts["shots"] and opts["shots"][0][0] <= elapsed:
        _, path = opts["shots"].pop(0)
        shot(path)
        print("%.2f s: screen saved to %s" % (elapsed, path))
    if opts["quit"] is not None and elapsed >= opts["quit"]:
        opts["quit"] = None
        n = a.engine.stop_recording()
        if n is not None:
            print("recorded %d frames to %s" % (n, opts["record"]))
        window.request_quit()


keep = lv.timer_create(poll, 20, None)
appkit.run("stompbox")
