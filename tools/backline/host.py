# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Run a Backline box with no screen, in real time, for desks to join.

    python tools/backline/host.py [--port 9300] [--song rock] [--kit rhythm909]
        [--seconds 60] [--wav OUT.wav] [--log OUT.json] [--play]
        [--cast KIND:HOST] [--stamp]

The box plays at the pace of the wall clock and serves desks on PORT: a
browser opens ``http://localhost:PORT/``, and ``python -m backline.desk_main
localhost:PORT`` joins as a desk. What it plays is pulled as an output
would pull it, and with ``--wav`` written to a file, so an edit made from a
desk can be heard, and looked at, where it landed. ``--log`` writes every op
the box took, with the second of the recording it landed at. ``--play``
taps pedal A at the start. The path needs audioinstruments, audiodsp,
hmilink and this repo's ``lib/`` and ``apps/`` folders.

``--cast`` also shows the desk view on a screen across the room, drawn at
1280x720 and cast with castdisplay (and ffmpeg): ``windows:HOST`` for a
PC's Wireless Display app, ``roku:HOST`` for a Roku's Screen mirroring,
``companion:HOST`` for the Companion channel on a Roku
(`backline.remote.cast_target`; ``$BACKLINE_CAST`` works too). A Windows
PC won't take a cast from itself: cast to it from another computer. The
cast's counters print every five seconds. ``--stamp`` puts the
wall clock's seconds (modulo 1000) in the cast's corner, so a screenshot
of the receiver taken at a known time shows how far behind it is.
"""

import json
import sys
import time

here = __file__.replace("\\", "/")
ROOT = here[: here.rfind("/tools/")] if "/tools/" in here else "."
sys.path[:0] = [ROOT + "/apps", ROOT + "/lib", ROOT + "/tools/backline"]

import audiocore  # noqa: E402
from hmilink import tcp  # noqa: E402

from backline import box as boxmod  # noqa: E402
from backline import kits  # noqa: E402
from backline import page_data  # noqa: E402
from backline import remote  # noqa: E402
from render import write_wav  # noqa: E402

RATE = kits.RATE
UI_MS = 30


def open_cast(box, spec, stamp):
    """The desk cast to ``spec`` (or ``$BACKLINE_CAST``), or None for none."""
    target = remote.cast_target(spec=spec)
    if target is None:
        return None, None
    import lvgl as lv

    from backline import cast

    view = cast.start(box.device, target, log=lambda *a: print("cast:", *a, flush=True))
    label = None
    if stamp:
        label = lv.label(view.screen)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        label.set_style_bg_color(lv.color_hex(0x000000), 0)
        label.set_style_bg_opa(255, 0)
        label.set_style_text_font(lv.font_montserrat_24, 0)
        label.align(lv.ALIGN.BOTTOM_RIGHT, -8, -4)
    print("backline host: casting the desk to %s" % target["name"], flush=True)
    return view, label


def main(argv):
    opts = {"--port": "9300", "--song": "rock", "--kit": None, "--seconds": "60", "--wav": None, "--log": None,
            "--cast": None}
    flags = set()
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            flags.add(argv[i])
            i += 1
    frames = [0]
    start = time.monotonic()

    def now_ms():
        return int((time.monotonic() - start) * 1000)

    box = boxmod.Box(lambda: frames[0], song=opts["--song"], kit=opts["--kit"], now_ms=now_ms)
    ops = []
    forward = box.forward

    def logged(op):
        ops.append({"s": round(frames[0] / RATE, 3), "op": op.get("op"), "path": op.get("path"),
                    "value": op.get("value")})
        forward(op)

    box.model.forward = logged
    port = int(opts["--port"])
    box.device.add(tcp.serve(port, page=page_data.page()))
    print("backline host: %s on %s, desks at http://localhost:%d/" % (box.engine.project["name"],
                                                                        box.engine.kit.name, port), flush=True)
    view, stamp = open_cast(box, opts["--cast"], "--stamp" in flags)
    if view is not None:
        import lvgl as lv
    ui_last = time.monotonic()
    said = ui_last
    if "--play" in flags:
        box.engine.gesture(0, "tap")
    out = bytearray() if opts["--wav"] else None
    seconds = float(opts["--seconds"])
    late = 0
    try:
        while time.monotonic() - start < seconds:
            due = int((time.monotonic() - start) * RATE)
            while frames[0] < due:
                box.service()
                _r, b = audiocore.get_buffer(box.bus.output)
                if out is not None:
                    out.extend(bytes(b))
                frames[0] += len(b) // 4
            if due - frames[0] > RATE // 10:
                late += 1
            box.poll()
            now = time.monotonic()
            if view is not None and now - ui_last >= UI_MS / 1000:
                if stamp is not None:
                    stamp.set_text("%.2f" % (time.time() % 1000))
                lv.tick_inc(int((now - ui_last) * 1000))
                ui_last = now
                lv.timer_handler()
                view.step()
                if now - said >= 5:
                    said = now
                    t = box.telemetry()
                    print("cast %.1f s: bar %d beat %d %s | %s" % (now - start, t["bar"], t["beat"], t["part"],
                                                                 view.stats()), flush=True)
            time.sleep(0.002)
    except KeyboardInterrupt:
        pass
    if out is not None:
        write_wav(opts["--wav"], bytes(out))
    if opts["--log"]:
        with open(opts["--log"], "w") as f:
            json.dump({"ops": ops, "tempo": box.engine.project["tempo"], "late": late}, f, indent=1)
    print("backline host: %.1f s played, %d ops, %d late passes" % (frames[0] / RATE, len(ops), late), flush=True)
    if view is not None:
        print("backline host: cast %s" % (view.stats(),), flush=True)
        view.close()
    box.close()


if __name__ == "__main__":
    main(sys.argv[1:])
