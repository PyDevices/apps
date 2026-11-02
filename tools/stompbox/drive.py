"""Run Stompbox on a computer and script it, to prove it from a recording.

    micropython -X heapsize=128M tools/stompbox/drive.py [--clips DIR]
        [--clip NAME] [--effect NAME] [--play] [--record OUT.wav]
        [--turn T:key=value ...] [--live ID] [--out ID] [--quit-after SECONDS]
        [--size WxH]

--turn moves a knob T seconds after start, through the same path a hand takes.
--record writes what goes to the output.
"""

import os
import sys

here = __file__.replace("\\", "/")
ROOT = here[: here.rfind("/tools/")] if "/tools/" in here else "."
sys.path.insert(0, ROOT + "/lib")
sys.path.insert(0, ROOT)
os.chdir(ROOT)

opts = {"clip": None, "effect": None, "play": False, "record": None, "turns": [],
        "quit": None}
size = "800x480"
argv = sys.argv[1:]
while argv:
    a = argv.pop(0)
    if a == "--clips":
        os.putenv("STOMPBOX_CLIPS", argv.pop(0))
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
    elif a == "--live":
        os.putenv("STOMPBOX_LIVE", "1")
        os.putenv("STOMPBOX_INPUT", argv.pop(0))
    elif a == "--out":
        os.putenv("STOMPBOX_OUT", argv.pop(0))
    elif a == "--quit-after":
        opts["quit"] = float(argv.pop(0))
    elif a == "--size":
        size = argv.pop(0)
    else:
        raise SystemExit("unknown option " + a)
opts["turns"].sort()
w, h = size.lower().split("x")
os.putenv("PYDEVICES_WIDTH", w)
os.putenv("PYDEVICES_HEIGHT", h)
os.putenv("PYDEVICES_SCALE", "1")

import appkit  # noqa: E402
import lvgl as lv  # noqa: E402
from display_driver import app as window  # noqa: E402
from multimer import ticks_diff, ticks_ms  # noqa: E402

t0 = [None]
begun = [False]


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
        a.screen.knobs[key].turn(value)
        print("%.2f s: %s = %.3f" % (elapsed, key, value))
    if opts["quit"] is not None and elapsed >= opts["quit"]:
        opts["quit"] = None
        n = a.engine.stop_recording()
        if n is not None:
            print("recorded %d frames to %s" % (n, opts["record"]))
        window.request_quit()


keep = lv.timer_create(poll, 20, None)
appkit.run("stompbox")
