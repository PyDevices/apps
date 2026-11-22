# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Play a Backline song offline, pressing the pedal on a script, into a WAV file.

    python tools/backline/render.py SONG KIT OUT.wav [--log OUT.json]

SONG is a starter song's name (``rock``) or a song file, KIT a kit spec
(``rhythm909``, ``soundfont``, ``samples:/path/kit``). The script taps the
song in, taps for the first fill, holds for the transition to the second
main, taps for its fill and taps twice for the outro; the WAV runs on two
seconds past the stop. The presses go through the pedal's own timing, on a
clock made of the frames pulled, so the render is the same every time.

``--log`` writes when each part started, in seconds, and each gesture.
The path needs audioinstruments, audiodsp, hmilink and this repo's lib/
and apps/ folders, as the tests' wrapper sets it.
"""

import json
import sys

here = __file__.replace("\\", "/")
ROOT = here[: here.rfind("/tools/")] if "/tools/" in here else "."
sys.path[:0] = [ROOT + "/apps", ROOT + "/lib"]

import audiocore  # noqa: E402

from backline import box as boxmod  # noqa: E402
from backline import kits  # noqa: E402

RATE = kits.RATE

# (bar, beat, what): when to press, in the song's own bars from the start.
SCRIPT = (
    (0, 0, "tap"),        # the intro, then main 1
    (4, 2, "tap"),        # main 1's fill
    (7, 1, "hold"),       # the transition into main 2
    (11, 2, "tap"),       # main 2's fill
    (14, 1, "double"),    # the outro, then stop
)


def write_wav(path, data, rate=RATE, channels=2):
    import struct

    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * 2 * channels, 2 * channels, 16))
        f.write(b"data" + struct.pack("<I", len(data)))
        f.write(data)


def render(song, kit, tail_s=2.0, script=SCRIPT, limit_s=120):
    """Returns (pcm bytes, log)."""
    frames = [0]

    def clock():
        return frames[0]

    def now_ms():
        return frames[0] * 1000 // RATE

    project = None
    if song.endswith(".json"):
        project = boxmod.load_song(song)
        song = None
    box = boxmod.Box(clock, song=song if project is None else project, kit=kit, now_ms=now_ms)
    if box.error:
        raise SystemExit(box.error)
    e = box.engine
    spb = RATE * 60.0 / e.project["tempo"]
    actions = []
    for bar, beat, what in script:
        t = int((bar * 4 + beat) * spb)
        if what == "tap":
            actions += [(t, "press"), (t + RATE // 10, "release")]
        elif what == "hold":
            actions += [(t, "press"), (t + int(RATE * 0.6), "release")]
        elif what == "double":
            actions += [(t, "press"), (t + RATE // 12, "release"), (t + RATE // 5, "press"),
                        (t + RATE // 5 + RATE // 12, "release")]
    actions.sort()
    log = {"song": e.project["name"], "kit": e.kit.name, "tempo": e.project["tempo"], "parts": [], "gestures": []}
    out = bytearray()
    last = None
    stopped_at = None
    started = False
    while True:
        while actions and actions[0][0] <= frames[0]:
            _t, what = actions.pop(0)
            if what == "press":
                e.press(0)
            else:
                e.release(0)
        box.service()
        tele = e.telemetry()
        part = tele["part"] if tele["playing"] else None
        if tele["playing"]:
            started = True
        if part != last:
            log["parts"].append([round(frames[0] / RATE, 3), part])
            last = part
        if e.last and (not log["gestures"] or log["gestures"][-1][1] != e.last or log["gestures"][-1][2] != e.changes):
            log["gestures"].append([round(frames[0] / RATE, 3), e.last, e.changes])
        if started and not tele["playing"] and stopped_at is None:
            stopped_at = frames[0]
        _r, b = audiocore.get_buffer(box.bus.output)
        out.extend(bytes(b))
        frames[0] += len(b) // 4
        if stopped_at is not None and frames[0] - stopped_at > tail_s * RATE:
            break
        if frames[0] > limit_s * RATE:
            raise SystemExit("the song never stopped")
    box.close()
    return bytes(out), log


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    song, kit, path = argv[:3]
    data, log = render(song, kit)
    write_wav(path, data)
    if "--log" in argv:
        with open(argv[argv.index("--log") + 1], "w") as f:
            json.dump(log, f, indent=1)
    print("%s on %s: %.1f s, parts %s" % (log["song"], log["kit"], len(data) / 4 / RATE,
                                          " > ".join(p for _t, p in log["parts"] if p)))


if __name__ == "__main__":
    main(sys.argv[1:])
