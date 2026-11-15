# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Check that a window of some size gets a layout everything fits in.

    .venv/bin/python tools/layout_check.py --size 1280x720 --out runs/layout-1280x720

Starts the app in a window of that size, opens a sketch, and looks at three
screens: the song, a drum grid and a piano roll. On each it asks the app
where its regions and controls are and checks that the regions are the
table ``app/ui/layout.py`` picks for the window, that every control lies
inside its region, and that controls in a row don't overlap. It saves a
screenshot of each screen in ``--out``: whether a name is cut short or two
labels touch is for your eyes.
"""

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "app" / "ui"))

import layout  # noqa: E402
from checkkit import add_session_args, report, session  # noqa: E402

SKETCH = ROOT / "songs" / "sketches" / "low_sun.json"


def inside(inner, outer):
    return (inner[0] >= outer[0] and inner[1] >= outer[1]
            and inner[0] + inner[2] <= outer[0] + outer[2] and inner[1] + inner[3] <= outer[1] + outer[3])


def overlap(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w > 0 and h > 0


def look(g, name):
    """The checks on one screen's geometry: a list of (ok, line)."""
    out = []
    w, h = g["canvas"]
    regions = g["regions"]
    want = {k: list(v) for k, v in layout.pick(w, h).items() if k != "scale"}
    out.append((regions == want, "%s: the regions are layout.pick(%d, %d)" % (name, w, h)))
    groups = {
        "top": [g[k] for k in ("file", "play", "stop", "rec", "quant", "overdub", "tempo", "swing", "metronome", "song",
                               "undo", "redo")] + g["slots"],
        "tracks": g["tracks"] + g["mutes"] + g["pans"],
        "inspector": g["knob_rects"] + g["fx_moves"] + g["inst_steps"] + ([g["learn"]] if g.get("learn") else []),
        "keys": g["keys_shift"],
    }
    if g.get("grid"):
        groups["editor"] = [g["grid"]["rect"]]
    elif g.get("roll"):
        groups["editor"] = [g["roll"]["rect"]]
    elif g.get("scenes"):
        groups["editor"] = g["scenes"]["rows"]
    for region, rects in groups.items():
        outside = [r for r in rects if not inside(r, regions[region])]
        out.append((not outside, "%s: %d controls inside %s%s" % (name, len(rects), region,
                                                                  ", but not %s" % outside[:3] if outside else "")))
    # Side by side in the top bar, and the knobs in the inspector's grid.
    for what, rects in (("the top bar's buttons", groups["top"]), ("the inspector's knobs", g["knob_rects"]),
                        ("the track rows", g["tracks"])):
        clashes = [(a, b) for i, a in enumerate(rects) for b in rects[i + 1:] if overlap(a, b)]
        out.append((not clashes, "%s: %s don't overlap%s" % (name, what, ": %s" % clashes[:2] if clashes else "")))
    # A pan knob stays clear of its track's mute button.
    clashes = [(p, m) for p, m in zip(g["pans"], g["mutes"]) if overlap(p, m)]
    out.append((not clashes, "%s: each pan knob is clear of its mute button" % name))
    return out


def run(s, out=None):
    project = json.loads(SKETCH.read_text())
    results = []
    screens = (("song", True, None), ("drums", False, 0), ("roll", False, 3))
    for name, song_mode, track in screens:
        p = dict(project)
        p["song_mode"] = song_mode
        s.load(p)
        if track is not None:
            s.app.select(track)
        time.sleep(0.8)
        results += look(s.app.geom(), name)
        if out is not None:
            s.screenshot(str(out / ("%s.png" % name)))
    results.append((not s.log, "nothing went wrong on the page%s" % (": %s" % s.log[:2] if s.log else "")))
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_session_args(ap)
    ap.add_argument("--out", default=None, help="a folder for the three screenshots")
    a = ap.parse_args()
    out = pathlib.Path(a.out) if a.out else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
    with session(a) as s:
        ok = report("layout", run(s, out))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
