# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Draw Backline's desk view in memory and save it as a PNG, playing a song for real.

    python tools/backline/desk_shot.py OUT.png [--size 800x480] [--song rock]
        [--kit rhythm909] [--at BEATS] [--tab perform|edit] [--tap PITCH:STEP]
        [--pedals MAP] [--learn SLOT]

The box plays SONG with no audio output, its clock moved by hand, and the
desk draws from it through an hmilink panel, as it does in the app. The
picture is taken BEATS beats after the first tap (6.5). ``--tap`` presses a
cell of the step grid first, as a finger would. ``--pedals`` shows the
editor's Pedals section with MAP, the switches' map as JSON
(`backline.midipedal.MidiPedal.saved`), and ``--learn`` arms one slot. Needs LVGL, svgio, icons,
hmilink, audiodsp and audioinstruments, and Pillow to write the PNG.
"""

import json
import sys

here = __file__.replace("\\", "/")
ROOT = here[: here.rfind("/tools/")] if "/tools/" in here else "."
sys.path[:0] = [ROOT + "/apps", ROOT + "/lib", ROOT + "/tests", ROOT + "/tools/backline"]

import audiocore  # noqa: E402
import hmilink  # noqa: E402
import lvgl as lv  # noqa: E402
from hmilink import local  # noqa: E402

import _headless  # noqa: E402
from backline import box as boxmod  # noqa: E402
from backline.desk import Desk  # noqa: E402
from shot import save_png  # noqa: E402


def main(argv):
    out = argv[0]
    opts = {"--size": "800x480", "--song": "rock", "--kit": None, "--at": "6.5", "--tab": "perform", "--tap": None,
            "--pedals": None, "--learn": None}
    i = 1
    while i < len(argv):
        opts[argv[i]] = argv[i + 1]
        i += 2
    w, h = [int(n) for n in opts["--size"].lower().split("x")]
    frame = _headless.display(w, h)
    _headless.pointer().set_display(_headless._state["display"])
    scr = lv.obj(None)
    lv.screen_load(scr)
    frames = [0]
    ms = [0]
    pedal_map = json.loads(opts["--pedals"]) if opts["--pedals"] else None
    box = boxmod.Box(lambda: frames[0], song=opts["--song"], kit=opts["--kit"], now_ms=lambda: ms[0],
                     pedal_map=pedal_map)
    box.device._tele_ms = 0
    panel = hmilink.Panel(local.connect(box.device.add(local.serve())))
    box.poll()
    panel.poll()
    desk = Desk(scr, (w, h), panel)
    desk.show_tab(opts["--tab"])
    e = box.engine
    spb = 48000 * 60.0 / e.project["tempo"]

    def run(beats):
        end = frames[0] + int(beats * spb)
        while frames[0] < end:
            box.service()
            audiocore.get_buffer(box.bus.output)
            frames[0] += 256
            ms[0] = frames[0] * 1000 // 48000
            if frames[0] % 2048 == 0:
                box.poll()
                box.device._telemetry()
                desk.poll()
                _headless.advance(5)

    e.gesture(0, "tap")
    run(float(opts["--at"]))
    if opts["--tap"]:
        pitch, step = [int(n) for n in opts["--tap"].split(":")]
        x, y = desk.editor.grid.center(pitch, step % desk.editor.cols)
        _headless.touch(x, y, True, 40)
        _headless.touch(x, y, False, 40)
        box.poll()
        desk.poll()
    if opts["--pedals"]:
        desk.show_tab("edit")
        desk.editor._toggle_pedals()
        if opts["--learn"] is not None:
            box.midi.learn(int(opts["--learn"]))
        box.poll()
    box.device._telemetry()
    desk.poll()
    _headless.advance(30)
    _headless.refresh()
    save_png(out, frame, w, h)
    print("%s: %dx%d, %s, tab %s" % (out, w, h, e.telemetry()["part"], desk.tab))
    box.close()


if __name__ == "__main__":
    main(sys.argv[1:])
