# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Check that a window of some size gets a layout everything fits in.

    .venv/bin/python tools/layout_check.py --size 1280x720 --out runs/layout-1280x720
    .venv/bin/python tools/layout_check.py --size 844x390 --dpr 3 --out runs/layout-phone

Starts the app in a window of that size, opens a sketch, and looks at three
screens: the song, a drum grid and a piano roll. On each it asks the app
where its regions and controls are and checks that the regions are the
table ``app/ui/layout.py`` picks for the window, that every control lies
inside its region, and that controls in a row don't overlap. It saves a
screenshot of each screen in ``--out``: whether a name is cut short or two
labels touch is for your eyes.

On a phone's window it also opens the other pages (the track list, the
inspector and the keys) with their tabs, and checks that every button is at
least a fingertip (the table's ``touch``) across, and that a drag on a
knob turns it instead of scrolling the page. There the top bar and the
pages scroll, so a control only has to be inside its region across (the top
bar's, down; the editor's page scrolls both ways, so there it only has to
start inside it across, and below its top).
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

REGIONS = ("top", "tracks", "editor", "inspector", "keys", "tabs", "status")
SKETCH = ROOT / "songs" / "sketches" / "low_sun.json"


def inside(inner, outer):
    return (inner[0] >= outer[0] and inner[1] >= outer[1]
            and inner[0] + inner[2] <= outer[0] + outer[2] and inner[1] + inner[3] <= outer[1] + outer[3])


def overlap(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w > 0 and h > 0


def within(inner, outer, across, down):
    """``inner`` inside ``outer`` across, down, or both."""
    ok = True
    if across:
        ok &= inner[0] >= outer[0] and inner[0] + inner[2] <= outer[0] + outer[2]
    if down:
        ok &= inner[1] >= outer[1] and inner[1] + inner[3] <= outer[1] + outer[3]
    return ok


def look(g, name):
    """The checks on one screen's geometry: a list of (ok, line)."""
    out = []
    w, h = g["canvas"]
    dpr = g.get("dpr", 1)
    regions = g["regions"]
    table = layout.pick(w, h, dpr)
    want = {k: list(v) for k, v in table.items() if k in REGIONS}
    out.append((regions == want, "%s: the regions are layout.pick(%d, %d, %g)" % (name, w, h, dpr)))
    touch = table.get("touch", 0)
    page = g.get("page")
    groups = {
        "top": [g[k] for k in ("file", "play", "stop", "rec", "quant", "overdub", "tempo", "swing", "metronome", "song",
                               "undo", "redo")] + g["slots"],
        "tracks": g["tracks"] + g["mutes"] + g["pans"],
        "inspector": g["knob_rects"] + g["fx_moves"] + g["inst_steps"] + ([g["learn"]] if g.get("learn") else []),
        "keys": g["keys_shift"],
    }
    if g.get("song_shown") and g.get("scenes"):
        groups["editor"] = g["scenes"]["rows"]
    elif g.get("grid"):
        groups["editor"] = [g["grid"]["rect"]]
    elif g.get("roll"):
        groups["editor"] = [g["roll"]["rect"]]
    if touch:
        # One page is shown at a time: check the controls of the one that is.
        for region in table["pages"]:
            if region != page:
                groups.pop(region, None)
        groups["tabs"] = g["tabs"]
    for region, rects in groups.items():
        if touch:
            # The top bar scrolls across, the pages down, and the editor's page both ways: there a
            # control has to start inside its region across, and below its top.
            box = regions[region]
            if region == "editor":
                outside = [r for r in rects if not (box[0] <= r[0] < box[0] + box[2] and r[1] >= box[1])]
            else:
                outside = [r for r in rects if not within(r, box, region != "top", region == "top")]
        else:
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
    if touch:
        buttons = (groups["top"] + g["tabs"] + g["mutes"] + g["fx_moves"] + g["inst_steps"] + g["keys_shift"]
                   + ([g["learn"]] if g.get("learn") else []) + ([g["copy"]] + list(g["bars"].values()) if g.get("copy") else []))
        sc = g.get("scenes") if g.get("song_shown") else None
        if sc:
            buttons += sc["nums"] + sc["loops"] + sc["dups"] + [b for q in sc["moves"] + sc["letters"] for b in q]
        small = [r for r in buttons if r[2] < touch or r[3] < touch]
        out.append((not small, "%s: %d buttons are at least %d pixels across%s"
                    % (name, len(buttons), touch, ", but not %s" % small[:3] if small else "")))
    return out


def drag_up(s, r, name, key):
    """Drag ``r``'s control up on a scrolling page: it should turn, and the page stay put."""
    before, where = json.dumps(s.app.project()), s.app.geom()[key][0]
    x, y = r[0] + r[2] // 2, r[1] + r[3] // 2
    s.app.move(x, y)
    s.app.down()
    for k in range(1, 11):
        s.app.move(x, y - k * r[3] // 10)
        time.sleep(0.03)
    s.app.up()
    time.sleep(0.4)
    changed = json.dumps(s.app.project()) != before
    still = s.app.geom()[key][0] == where
    return [(changed and still, "%s: a drag up turns it%s%s" % (name, "" if changed else ", but nothing changed",
                                                           "" if still else ", and the page scrolled"))]


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
    g = s.app.geom()
    if g.get("page") is not None:
        # A phone: the other pages, each through its tab.
        for i, page in enumerate(("tracks", "inspector", "keys")):
            s.app.click_rect(g["tabs"][i + 1])
            time.sleep(0.5)
            here = s.app.geom()
            results.append((here["page"] == page, "the %s tab shows the %s page" % (page, page)))
            results += look(here, page)
            if out is not None:
                s.screenshot(str(out / ("%s.png" % page)))
            if page == "tracks":
                results += drag_up(s, here["pans"][0], "the first track's pan knob", "pans")
            elif page == "inspector":
                results += drag_up(s, here["knob_rects"][0], "the inspector's first knob", "knob_rects")
        s.app.click_rect(g["tabs"][0])
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
