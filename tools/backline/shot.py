# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Draw Backline's floor view in memory and save it as a PNG, playing a song for real.

    python tools/backline/shot.py OUT.png [--size 480x320] [--song rock]
        [--kit rhythm909] [--at BEATS] [--press A|B] [--tap-fill]

The box plays SONG with no audio output, its clock moved by hand, and the
view draws from it through an hmilink panel, as it does in the app. The
picture is taken BEATS beats after the first tap (6.5), optionally with a
pedal held down, or with a fill just asked for. Needs LVGL, svgio, hmilink,
audiodsp and audioinstruments, and Pillow to write the PNG.
"""

import sys

here = __file__.replace("\\", "/")
ROOT = here[: here.rfind("/tools/")] if "/tools/" in here else "."
sys.path[:0] = [ROOT + "/apps", ROOT + "/lib", ROOT + "/tests"]

import audiocore  # noqa: E402
import hmilink  # noqa: E402
import lvgl as lv  # noqa: E402
from hmilink import local  # noqa: E402

import _headless  # noqa: E402
from backline import box as boxmod  # noqa: E402
from backline import floor  # noqa: E402


def save_png(path, frame, w, h):
    from PIL import Image

    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        row = 2 * y * w
        for x in range(w):
            v = frame[row + 2 * x] | (frame[row + 2 * x + 1] << 8)
            px[x, y] = (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)
    img.save(path)


def main(argv):
    out = argv[0]
    opts = {"--size": "480x320", "--song": "rock", "--kit": None, "--at": "6.5", "--press": None}
    flags = set()
    i = 1
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            flags.add(argv[i])
            i += 1
    w, h = [int(n) for n in opts["--size"].lower().split("x")]
    frame = _headless.display(w, h)
    scr = lv.obj(None)
    lv.screen_load(scr)
    frames = [0]
    ms = [0]
    box = boxmod.Box(lambda: frames[0], song=opts["--song"], kit=opts["--kit"], now_ms=lambda: ms[0])
    panel = hmilink.Panel(local.connect(box.device.add(local.serve())))
    box.poll()
    panel.poll()
    view = floor.Floor(scr, (w, h), panel)
    e = box.engine
    spb = 48000 * 60.0 / e.project["tempo"]

    def run(beats):
        end = frames[0] + int(beats * spb)
        while frames[0] < end:
            box.service()
            audiocore.get_buffer(box.bus.output)
            frames[0] += 256
            ms[0] = frames[0] * 1000 // 48000

    e.gesture(0, "tap")
    at = float(opts["--at"])
    if "--tap-fill" in flags:
        run(at - 1.5)
        e.gesture(0, "tap")
        run(1.5)
    else:
        run(at)
    if opts["--press"]:
        e.press("AB".index(opts["--press"].upper()))
        run(0.01)
    box.device._telemetry()
    view.poll()
    _headless.advance(30)
    _headless.refresh()
    save_png(out, frame, w, h)
    print("%s: %dx%d, %s, art %d KB" % (out, w, h, e.telemetry()["part"], view.bytes() // 1024))
    box.close()


if __name__ == "__main__":
    main(sys.argv[1:])
