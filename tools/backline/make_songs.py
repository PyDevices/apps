# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Write Backline's starter songs, apps/backline/songs/*.json, from the grooves below.

    python tools/backline/make_songs.py           # write every song
    python tools/backline/make_songs.py --check   # fail if one is out of date

Each part is a step grid per drum, General MIDI notes: 16 steps a bar for a
straight feel, 12 (triplet eighths) for a shuffle or a 12/8 ballad. A step
is ``X`` (accent), ``x`` (normal), ``o`` (soft), ``g`` (ghost) or ``.``
(rest); ``|`` and spaces are only for reading. Every song has an intro, two
mains, a fill for each, a transition, an outro and an accent.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SONGS = os.path.join(ROOT, "apps", "backline", "songs")
sys.path.insert(0, os.path.join(ROOT, "lib"))

from songmodel import model  # noqa: E402

VELOCITY = {"X": 118, "x": 96, "o": 70, "g": 42}
KICK, STICK, SNARE, CLAP, FLOOR, CHH, PHH, OHH, CRASH, RIDE, BELL = 36, 37, 38, 39, 41, 42, 44, 46, 49, 51, 53
TOM_LO, TOM_MID, TOM_HI, TOM_HIGH = 45, 47, 48, 50
COWBELL, TAMB, CRASH2 = 56, 54, 57
ROLES = ("intro", "main1", "main2", "fill1", "fill2", "transition", "outro", "accent")


def part(bars, grid, voices):
    """A songmodel pattern from step strings: ``voices`` maps note -> steps."""
    step = model.BAR // grid
    notes = []
    for pitch, steps in voices.items():
        steps = steps.replace("|", "").replace(" ", "")
        if len(steps) != bars * grid:
            raise ValueError("note %d has %d steps, not %d" % (pitch, len(steps), bars * grid))
        for i, ch in enumerate(steps):
            if ch in VELOCITY:
                notes.append([i * step, step, pitch, VELOCITY[ch]])
    notes.sort()
    return {"bars": bars, "notes": notes}


def song(name, tempo, kit, grid, parts, meter="4/4", style=""):
    """A project with one drum track holding ``parts`` in the order of ROLES."""
    p = model.new_project()
    p["name"] = name
    p["tempo"] = float(tempo)
    p["meter"] = meter
    p["style"] = style
    t = model.track("drums", kit, "Drums")
    t["id"] = 1
    t["patterns"] = [part(bars, grid, voices) for bars, voices in (parts[r] for r in ROLES)]
    p["tracks"] = [t]
    p["parts"] = {"intro": 0, "mains": [1, 2], "fills": [3, 4], "transitions": [5], "outro": 6, "accent": 7}
    return p


ACCENT16 = (1, {CRASH: "X...............", KICK: "X..............."})
ACCENT12 = (1, {CRASH: "X...........", KICK: "X..........."})

ROCK = song("Straight Rock", 118, "rhythm909", 16, {
    "intro": (2, {CHH: "x...x...x...x...|x.x.x.x.........",
                  SNARE: "................|........xxXXxxXX",
                  KICK: "X...............|X.......X......."}),
    "main1": (2, {CHH: "x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x.",
                  SNARE: "....X.......X...|....X.......X...",
                  KICK: "X.......X.X.....|X.......X.X...x.",
                  CRASH: "X...............|................"}),
    "main2": (2, {RIDE: "x.o.x.o.x.o.x.o.|x.o.x.o.x.o.x.o.",
                  SNARE: "....X.......X...|....X.......X..g",
                  KICK: "X.x.....X.x.....|X.x.....X.x...x.",
                  CRASH: "X...............|................"}),
    "fill1": (1, {SNARE: "x.x.x.x.XxXxXXXX", KICK: "X.......X......."}),
    "fill2": (1, {SNARE: "X.x.x...........", TOM_HI: "......xx........", TOM_MID: "........xx......",
                  FLOOR: "..........xxXX..", KICK: "X.......X.....X."}),
    "transition": (1, {SNARE: "x.x.x.x.xxxxXXXX", KICK: "X...X...X...X...", CHH: "x.x.x.x........."}),
    "outro": (2, {CHH: "x.x.x.x.x.x.x.x.|................",
                  SNARE: "....X.......XxXX|................",
                  KICK: "X.......X.X.....|X...............",
                  CRASH: "................|X..............."}),
    "accent": ACCENT16,
}, style="Rock")

SHUFFLE = song("Blues Shuffle", 96, "rhythm808", 12, {
    "intro": (1, {CHH: "x..x..x..x..", SNARE: "......XxxXxX", KICK: "X..........."}),
    "main1": (2, {CHH: "x.ox.ox.ox.o|x.ox.ox.ox.o",
                  SNARE: "...X.....X..|...X.....X.g",
                  KICK: "X.....X..o..|X.....X....o",
                  CRASH: "X...........|............"}),
    "main2": (2, {RIDE: "x.ox.ox.ox.o|x.ox.ox.ox.o",
                  SNARE: "..gX.g..gX.g|..gX.g..gX.g",
                  KICK: "X..o..X..o..|X..o..X..o..",
                  PHH: "...x.....x..|...x.....x..",
                  CRASH: "X...........|............"}),
    "fill1": (1, {SNARE: "x.xx.xX.xXxX", KICK: "X.....X....."}),
    "fill2": (1, {SNARE: "X.x.........", TOM_HI: "...xx.......", TOM_MID: "......xx....", FLOOR: "........xXxX",
                  KICK: "X.....X....."}),
    "transition": (1, {SNARE: "x.xx.xxxxXXX", KICK: "X..X..X..X..", CRASH: "X..........."}),
    "outro": (2, {CHH: "x.ox.ox.ox.o|............",
                  SNARE: "...X.....XxX|............",
                  KICK: "X.....X.....|X...........",
                  CRASH: "............|X..........."}),
    "accent": ACCENT12,
}, style="Blues")

FUNK = song("Pocket Funk", 98, "rhythm909", 16, {
    "intro": (1, {CHH: "x.x.x.x.x.x.x.x.", SNARE: "............XxXX", KICK: "X......X........"}),
    "main1": (2, {CHH: "xoxoxoxoxoxoxoxo|xoxoxoxoxoxoxoxo",
                  SNARE: "....X..g.g..X..g|.g..X..g.g..X...",
                  KICK: "X.x....x..X.....|X.x....x..X..x..",
                  OHH: "................|..............o."}),
    "main2": (2, {CHH: "x.xox.xox.xox.xo|x.xox.xox.xox.xo",
                  OHH: "......o.......o.|......o.......o.",
                  SNARE: "g...X..g.g.gX..g|g...X..g.g.gX.gg",
                  KICK: "X..x..x...X..x..|X..x..x...X.x...",
                  CRASH: "X...............|................"}),
    "fill1": (1, {SNARE: "X..gX.gXg.XgXXgX", KICK: "X.....x...x....."}),
    "fill2": (1, {SNARE: "X.xx....X.......", TOM_HI: "....xx..........", TOM_MID: "..........xx....",
                  FLOOR: "............xxXX", KICK: "X.......x......."}),
    "transition": (1, {SNARE: "X.gX.gX.XgXgXXXX", KICK: "X..x..x...x.x...", OHH: "..............x."}),
    "outro": (2, {CHH: "xoxoxoxoxoxoxoxo|................",
                  SNARE: "....X..g.g..XxXX|................",
                  KICK: "X.x....x..X.....|X...............",
                  CRASH: "................|X..............."}),
    "accent": ACCENT16,
}, style="Funk")

POP = song("Bright Pop", 112, "electronic_drums5", 16, {
    "intro": (2, {CLAP: "....X.......X...|....X.......X...", KICK: "X...X...X...X...|X...X...X...X...",
                  SNARE: "................|............XXXX"}),
    "main1": (2, {CHH: "x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x.",
                  SNARE: "....X.......X...|....X.......X...",
                  CLAP: "....x.......x...|....x.......x...",
                  KICK: "X......x..X.....|X......x..X...x.",
                  CRASH: "X...............|................"}),
    "main2": (2, {OHH: "..x...x...x...x.|..x...x...x...x.",
                  CHH: "x...x...x...x...|x...x...x...x...",
                  SNARE: "....X.......X...|....X.......X...",
                  CLAP: "....x.......x...|....x.......x...",
                  KICK: "X...X...X...X...|X...X...X...X...",
                  CRASH: "X...............|................"}),
    "fill1": (1, {SNARE: "....x.x.xxxxXXXX", KICK: "X...X...X...X...", CLAP: "....X..........."}),
    "fill2": (1, {SNARE: "X...x.x.........", TOM_HI: "........xx......", TOM_LO: "..........xx....",
                  FLOOR: "............XXXX", KICK: "X...X...X...X..."}),
    "transition": (1, {SNARE: "x.x.x.x.xxxxXXXX", KICK: "X...X...X...X...", CRASH: "X..............."}),
    "outro": (2, {CHH: "x.x.x.x.x.x.x.x.|................",
                  SNARE: "....X.......X.XX|................",
                  KICK: "X......x..X.....|X...............",
                  CRASH: "................|X..............."}),
    "accent": ACCENT16,
}, style="Pop")

TRAIN = song("Country Train", 152, "rhythm606", 16, {
    "intro": (1, {SNARE: "o.o.X.o.o.o.X.o.", KICK: "X.......X......."}),
    "main1": (2, {SNARE: "gogoXogogogoXogo|gogoXogogogoXogo",
                  KICK: "X.......X.......|X.......X.......",
                  PHH: "....x.......x...|....x.......x..."}),
    "main2": (2, {SNARE: "gogoXogogogoXogo|gogoXogogogoXogo",
                  KICK: "X.......X.......|X.......X.......",
                  RIDE: "x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x.",
                  CRASH: "X...............|................"}),
    "fill1": (1, {SNARE: "gogoXogoxxxxXXXX", KICK: "X.......X......."}),
    "fill2": (1, {SNARE: "XoXoXoXo........", TOM_MID: "........xx..xx..", FLOOR: "..........xx..XX",
                  KICK: "X.......X......."}),
    "transition": (1, {SNARE: "gogoxogoXXXXXXXX", KICK: "X...X...X...X...", CRASH: "X..............."}),
    "outro": (2, {SNARE: "gogoXogogogoXoXX|................",
                  KICK: "X.......X.......|X...............",
                  CRASH: "................|X..............."}),
    "accent": ACCENT16,
}, style="Country")

BOSSA = song("Bossa Breeze", 132, "rhythm606", 16, {
    "intro": (2, {STICK: "x..x..x...x..x..|x..x..x...x..x..", CHH: "x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x."}),
    "main1": (2, {STICK: "x..x..x...x..x..|..x..x...x..x...",
                  KICK: "X..x....X..x....|X..x....X..x....",
                  CHH: "x.o.x.o.x.o.x.o.|x.o.x.o.x.o.x.o."}),
    "main2": (2, {STICK: "x..x..x...x..x..|..x..x...x..x...",
                  KICK: "X..x....X..x....|X..x....X..x....",
                  RIDE: "x.oox.oox.oox.oo|x.oox.oox.oox.oo",
                  PHH: "....x.......x...|....x.......x..."}),
    "fill1": (1, {STICK: "x..x..x.........", SNARE: "..........o.xoxx", KICK: "X..x....X..x...."}),
    "fill2": (1, {SNARE: "x.o.o...........", TOM_HI: "......o.o.......", TOM_LO: "..........o.o...",
                  FLOOR: "..............xx", KICK: "X..x....X..x...."}),
    "transition": (1, {SNARE: "o.o.o.o.x.x.xxXX", KICK: "X..x....X..x....", RIDE: "x...x...x...x..."}),
    "outro": (2, {STICK: "x..x..x...x..x..|................",
                  KICK: "X..x....X..x....|X...............",
                  CHH: "x.o.x.o.x.o.x.o.|................",
                  CRASH: "................|o..............."}),
    "accent": (1, {CRASH: "x...............", KICK: "X..............."}),
}, style="Latin")

METAL = song("Iron Gallop", 168, "rhythm909", 16, {
    "intro": (2, {CRASH: "X...X...X...X...|X...X...X...X...", KICK: "X...X...X...X...|X...X...X...X...",
                  SNARE: "................|........XXXXXXXX"}),
    "main1": (2, {CHH: "x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x.",
                  SNARE: "....X.......X...|....X.......X...",
                  KICK: "X.xxX.xxX.xxX.xx|X.xxX.xxX.xxX.xx",
                  CRASH: "X...............|................"}),
    "main2": (2, {BELL: "x...x...x...x...|x...x...x...x...",
                  SNARE: "....X.......X...|....X.......X...",
                  KICK: "xxxxxxxxxxxxxxxx|xxxxxxxxxxxxxxxx",
                  CRASH: "X.......X.......|X.......X......."}),
    "fill1": (1, {SNARE: "XxXxXxXxXXXXXXXX", KICK: "X...X...X...X..."}),
    "fill2": (1, {TOM_HI: "XxXx............", TOM_MID: "....XxXx........", FLOOR: "........XxXxXXXX",
                  KICK: "xxxxxxxxxxxxxxxx"}),
    "transition": (1, {SNARE: "X..X..X.XXXXXXXX", KICK: "X..X..X.xxxxxxxx", CRASH: "X..X..X........."}),
    "outro": (2, {CRASH: "X...X...X...X...|X...............",
                  SNARE: "....X.......XXXX|................",
                  KICK: "X.xxX.xxX.xxXXXX|X..............."}),
    "accent": (1, {CRASH: "X...............", CRASH2: "X...............", KICK: "X..............."}),
}, style="Metal")

BALLAD = song("Slow Six", 62, "rhythm808", 12, {
    "intro": (1, {CHH: "x.ox.ox.ox.o", KICK: "X.....o.....", TOM_LO: "..........ox"}),
    "main1": (2, {CHH: "xooxooxooxoo|xooxooxooxoo",
                  STICK: "...X.....X..|...X.....X..",
                  KICK: "X.....X.....|X.....X..o.."}),
    "main2": (2, {RIDE: "xooxooxooxoo|xooxooxooxoo",
                  SNARE: "...X.....X..|...X.....X..",
                  KICK: "X....oX.....|X....oX..o..",
                  CRASH: "X...........|............"}),
    "fill1": (1, {SNARE: "...X..ooxxXX", KICK: "X.....X....."}),
    "fill2": (1, {SNARE: "...X........", TOM_HI: "......xx....", TOM_LO: "........xx..", FLOOR: "..........xX",
                  KICK: "X.....X....."}),
    "transition": (1, {SNARE: "...X..xoxxxX", KICK: "X.....X.....", CRASH: "X..........."}),
    "outro": (2, {RIDE: "xooxooxooxoo|............",
                  SNARE: "...X.....X.X|............",
                  KICK: "X.....X.....|X...........",
                  CRASH: "............|X..........."}),
    "accent": ACCENT12,
}, meter="12/8", style="6/8 ballad")

ALL = {"rock": ROCK, "shuffle": SHUFFLE, "funk": FUNK, "pop": POP, "country_train": TRAIN, "bossa": BOSSA,
       "metal": METAL, "ballad_68": BALLAD}


def text(project):
    return json.dumps(project, separators=(",", ":"), sort_keys=True) + "\n"


def main(argv):
    check = "--check" in argv
    stale = []
    for name, project in sorted(ALL.items()):
        path = os.path.join(SONGS, name + ".json")
        want = text(project)
        try:
            with open(path, encoding="utf-8") as f:
                have = f.read()
        except OSError:
            have = None
        if have == want:
            continue
        if check:
            stale.append(path)
        else:
            os.makedirs(SONGS, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(want)
            print("wrote", os.path.relpath(path, ROOT))
    if stale:
        sys.exit("out of date: %s\nRun python tools/backline/make_songs.py and commit the result." % ", ".join(stale))


if __name__ == "__main__":
    main(sys.argv[1:])
