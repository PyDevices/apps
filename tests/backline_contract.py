# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's contract, on any interpreter: the pedal's gestures, the song's
plan, parts switching on the bar line, the starter songs, each kind of kit
sounding, and a pedal pressed from an hmilink panel.

    python tests/backline_contract.py [--plant=NAME] [--tmp FOLDER]
    micropython -X heapsize=64M tests/backline_contract.py

The pedal, the plan, the engine and the songs need nothing but the
interpreter: a stand-in kit counts what it is given. The kits need
audioinstruments and audiodsp on the path, and the panel check hmilink;
without them those checks say they skipped. The SoundFont kit needs a
``.sf2`` (``$SOUNDFONT``, or one in ``~/soundfonts``) and skips, saying so,
without one.

``--plant=NAME`` breaks Backline in one known way first (``PLANTS``), and a
check must then fail: ``tests/test_backline.py`` runs every plant. It ends
with ``N passed, M failed`` and exits non-zero on a failure.
"""

import json
import math
import os
import sys

try:
    _here = __file__
except NameError:  # pragma: no cover
    _here = sys.argv[0]
_sep = "\\" if "\\" in _here else "/"
_dir = _here.rsplit(_sep, 1)[0] if _sep in _here else "."
sys.path[:0] = [_sep.join((_dir, "..", "apps")), _sep.join((_dir, "..", "lib"))]

from backline import engine as eng  # noqa: E402
from backline import pedal as pedals  # noqa: E402
from songmodel import model  # noqa: E402

PLANTS = ("no-hold", "no-double", "switch-now", "no-return", "no-wrap", "outro-forever", "fill-ignores-main",
          "late-notes", "drop-pad", "no-choke", "deaf-panel", "song-without-outro")

RESULTS = [0, 0]
SKIPS = []
RATE = 48000


def check(name, ok, detail=""):
    if ok:
        RESULTS[0] += 1
        print("ok   " + name)
    else:
        RESULTS[1] += 1
        print("FAIL " + name + (": " + detail if detail else ""))


def skip(name, why):
    SKIPS.append(name)
    print("skip " + name + ": " + why)


def args():
    plant = None
    tmp = "/tmp"
    argv = sys.argv[1:]
    while argv:
        a = argv.pop(0)
        if a.startswith("--plant="):
            plant = a[len("--plant="):]
        elif a == "--tmp":
            tmp = argv.pop(0)
    return plant, tmp


def songs_dir():
    return _sep.join((_dir, "..", "apps", "backline", "songs"))


def load(name):
    with open(songs_dir() + "/" + name + ".json") as f:
        return json.load(f)


class FakeKit:
    """Counts what it's given: (frame it was handed at, pitch, velocity, delay)."""

    name = "fake"
    spec = "fake"
    timed = False

    def __init__(self, clock):
        self.clock = clock
        self.notes = []

    def note_on(self, pitch, velocity, delay=0):
        self.notes.append((self.clock() + delay, pitch, velocity, delay))


# -- plants ------------------------------------------------------------------


def plant(name):
    if name is None:
        return
    print("PLANTED " + name)
    if name == "no-hold":
        pedals.Pedal.poll = lambda self, now: []
    elif name == "no-double":
        old = pedals.Pedal.__init__

        def init(self, hold_ms=pedals.HOLD_MS, double_ms=pedals.DOUBLE_MS):
            old(self, hold_ms, -1)
        pedals.Pedal.__init__ = init
    elif name == "switch-now":
        eng.bar_after = lambda tick: tick
    elif name == "no-return":
        old = eng.Form._cut

        def cut(self, tick, now, at, steps):
            old(self, tick, now, at, [s for s in steps if not (s[0] == "main" and steps[0][0] == "fill")])
        eng.Form._cut = cut
    elif name == "no-wrap":
        old = eng.Form.gesture

        def gesture(self, pedal, g, tick):
            now = self.sounding(tick)
            if g == "hold" and now is not None and now[0] == "main" and now[1] == len(self.mains) - 1:
                return None
            return old(self, pedal, g, tick)
        eng.Form.gesture = gesture
    elif name == "outro-forever":
        old = eng.Form.gesture

        def gesture(self, pedal, g, tick):
            did = old(self, pedal, g, tick)
            self.plan = [e for e in self.plan if e[0] != "end"] or self.plan
            return did
        eng.Form.gesture = gesture
    elif name == "fill-ignores-main":
        eng.Form.fill_for = lambda self, n: self.fills[0] if self.fills else None
    elif name == "late-notes":
        old = eng.Engine.sequence

        def sequence(self):
            self.lookahead = -3000
            old(self)
        eng.Engine.sequence = sequence
    elif name == "drop-pad":
        from backline import kits

        old = kits.DrumMachineKit.note_on
        olds = kits.SampleKit.note_on

        def note_on(self, pitch, velocity, delay=0):
            if pitch != 46:
                old(self, pitch, velocity, delay)

        def note_on_s(self, pitch, velocity, delay=0):
            if pitch != 46:
                olds(self, pitch, velocity, delay)
        kits.DrumMachineKit.note_on = note_on
        kits.SampleKit.note_on = note_on_s
    elif name == "no-choke":
        from backline import kits

        old = kits.SampleKit.__init__

        def init(self, folder, rate=kits.RATE, voices=kits.VOICES):
            old(self, folder, rate, voices)
            self.chokes = {}
        kits.SampleKit.__init__ = init
    elif name == "deaf-panel":
        from backline import box

        old = box.Box.command

        def command(self, name, a):
            if name == "pedal":
                return None
            return old(self, name, a)
        box.Box.command = command
    elif name == "song-without-outro":
        old = eng.Form.__init__

        def init(self, project):
            old(self, project)
            self.outro = None
        eng.Form.__init__ = init
    else:
        raise SystemExit("no such plant: %r" % name)


# -- the pedal ---------------------------------------------------------------


def check_pedal():
    p = pedals.Pedal()
    got = p.press(1000) + p.poll(1100) + p.release(1120)
    check("a short press is a tap, on its release", got == ["tap"], repr(got))
    got = p.press(2000) + p.poll(2399)
    held = p.poll(2400)
    check("held 400 ms is a hold, while still down", got == [] and held == ["hold"] and p.state == "held",
          repr((got, held, p.state)))
    check("a hold says nothing more when let go", p.release(3000) == [] and p.state == "up")
    p = pedals.Pedal()
    first = p.press(0) + p.release(80)
    second = p.press(300)
    rest = p.release(380)
    check("a second press within 350 ms of a tap is a double tap", first == ["tap"] and second == ["double"] and
          rest == [], repr((first, second, rest)))
    p = pedals.Pedal()
    p.press(0)
    p.release(80)
    late = p.press(600) + p.release(680)
    check("a press long after a tap is another tap", late == ["tap"], repr(late))
    p = pedals.Pedal()
    p.press(0)
    got = p.press(10) + p.release(450)
    check("an unpolled long press still holds, and a repeat is ignored", got == ["hold"], repr(got))


# -- the plan ------------------------------------------------------------------


def check_form():
    rock = load("rock")
    f = eng.Form(rock)
    intro = f.length(f.intro)
    f.start(0)
    check("a start plays the intro, then main 1",
          [(e[0], e[1]) for e in f.plan] == [("intro", None), ("main", 0)] and f.plan[1][3] == intro, repr(f.plan))
    f.advance(intro)
    tick = intro + eng.BAR + 100          # mid-bar in main 1
    did = f.gesture(0, "tap", tick)
    fill_at = intro + 2 * eng.BAR
    ok = did == "fill" and f.plan[1][:3] == ("fill", 0, f.fills[0]) and f.plan[1][3] == fill_at
    check("a tap plays main 1's fill at the next bar line", ok, repr(f.plan))
    ok = len(f.plan) == 3 and f.plan[2][:3] == ("main", 0, f.mains[0]) and \
        f.plan[2][3] == fill_at + f.length(f.fills[0])
    check("after the fill, main 1 again", ok, repr(f.plan))
    did = f.gesture(0, "double", tick + 10)
    ok = did == "outro" and [e[0] for e in f.plan] == ["main", "outro", "end"] and f.plan[1][3] == fill_at
    check("a double tap before the fill starts replaces it with the outro", ok, repr(f.plan))
    f.start(0)
    f.advance(intro)
    f.gesture(0, "tap", intro + 5)
    f.advance(intro + eng.BAR)
    ignored = f.gesture(0, "tap", intro + eng.BAR + 5) is None and f.gesture(0, "hold", intro + eng.BAR + 6) is None
    check("taps and holds wait while a fill plays", ignored and f.plan[0][0] == "fill", repr(f.plan))
    f.start(0)
    f.advance(intro)
    did = f.gesture(0, "hold", intro + 30)
    at = intro + eng.BAR
    ok = did == "transition" and f.plan[1][:3] == ("transition", 1, f.transition_into(1)) and f.plan[1][3] == at \
        and f.plan[2][:3] == ("main", 1, f.mains[1]) and f.plan[2][3] == at + f.length(f.transition_into(1))
    check("a hold plays the transition, then main 2", ok, repr(f.plan))
    f.advance(f.plan[2][3])
    f.gesture(0, "tap", f.plan[0][3] + 7)
    check("main 2's tap plays main 2's own fill", f.plan[1][:3] == ("fill", 1, f.fills[1]), repr(f.plan))
    f.advance(f.plan[2][3])
    f.gesture(0, "hold", f.plan[0][3] + 7)
    check("a hold on the last main goes round to main 1", f.plan[-1][:2] == ("main", 0), repr(f.plan))
    f.advance(f.plan[-1][3])
    t = f.plan[0][3] + 7
    did = f.gesture(0, "double", t)
    ok = did == "outro" and f.plan[1][0] == "outro" and f.plan[-1][0] == "end" and \
        f.plan[-1][3] == eng.bar_after(t) + f.length(f.outro)
    check("a double tap plays the outro, then stops", ok, repr(f.plan))
    f.advance(f.plan[1][3])
    did = f.gesture(0, "double", f.plan[0][3] + 50)
    check("a double tap in the outro stops at once", did == "stop" and f.plan[0][0] == "end", repr(f.plan))
    f.start(0)
    did = f.gesture(1, "hold", 10)
    check("pedal B's hold stops at once", did == "stop" and f.plan == [("end", None, -1, 10)], repr(f.plan))
    check("pedal B's tap is the accent", f.gesture(1, "tap", 10) == "accent")


# -- the engine ------------------------------------------------------------------


def run_engine(project, script, until_bars, lookahead=0, timed=False):
    """Play ``project``; ``script`` is [(frame, pedal, gesture)]. Returns
    (engine, kit, log of parts); ``engine.played`` has each note's own frame."""
    frames = [0]
    kit = FakeKit(lambda: frames[0])
    kit.timed = timed
    e = eng.Engine(project, kit, lambda: frames[0], RATE, lookahead=lookahead, now_ms=lambda: frames[0] * 1000 // RATE)
    e.record = True
    spb = RATE * 60.0 / project["tempo"]
    end = int(until_bars * 4 * spb)
    script = list(script)
    parts = []
    while frames[0] < end:
        while script and script[0][0] <= frames[0]:
            _f, which, g = script.pop(0)
            e.gesture(which, g)
        e.sequence()
        t = e.telemetry()
        name = t["part"] if t["playing"] else None
        if not parts or parts[-1][1] != name:
            parts.append((frames[0], name))
        frames[0] += 256
    return e, kit, parts


def check_engine():
    rock = load("rock")
    spb = RATE * 60.0 / rock["tempo"]
    # Start; tap for a fill in the middle of main 1's first bar; double tap later.
    script = [(0, 0, "tap"), (int(9.5 * spb), 0, "tap"), (int(20.5 * spb), 0, "double")]
    e, kit, parts = run_engine(rock, script, 40)
    names = [p[1] for p in parts]
    want = ["Intro", "Main 1", "Fill 1", "Main 1", "Outro", None]
    check("the parts play in order and the song stops", names == want, repr(names))
    f = eng.Form(rock)
    intro = f.length(f.intro)
    fill_tick = intro + eng.BAR       # the tap was in main 1's first bar
    f0 = int(e.frame_at(fill_tick))
    f1 = int(e.frame_at(fill_tick + eng.BAR))
    fill = rock["tracks"][0]["patterns"][f.fills[0]]
    after = [n for n in e.played if n[0] >= f0 - 1]
    ok = bool(after) and after[0][0] == f0 and after[0][1] == fill["notes"][0][2]
    check("the fill's first note lands on the bar line", ok, "%r, the bar line at %d" % (after[:2], f0))
    in_bar = [n for n in e.played if f0 <= n[0] < f1]
    check("the bar after the tap is the fill, note for note",
          sorted(n[1] for n in in_bar) == sorted(n[2] for n in fill["notes"]),
          "%r" % sorted(n[1] for n in in_bar))
    worst = 0
    early = 0
    for (frame, pitch, _v), (handed, kpitch, _kv, delay) in zip(e.played, kit.notes):
        worst = max(worst, handed - frame)
        if handed < frame:
            early += 1
    check("every note reaches the kit within a block of its frame, never early", worst <= 256 and not early and
          len(e.played) == len(kit.notes), "%d frames late at worst, %d early" % (worst, early))
    check("the song stops once the outro ends", parts[-1][1] is None and parts[-2][1] == "Outro", repr(parts[-2:]))
    # A kit that holds notes back is handed them early, each with its delay.
    e, kit, parts = run_engine(rock, [(0, 0, "tap")], 3, lookahead=512, timed=True)
    exact = all(handed == frame for (frame, _p, _v), (handed, _kp, _kv, _d) in zip(e.played, kit.notes))
    check("a timed kit gets every note ahead, its delay landing it on its frame",
          exact and len(e.played) == len(kit.notes) > 0 and max(n[3] for n in kit.notes) > 0,
          "%d notes" % len(kit.notes))


# -- the songs ---------------------------------------------------------------------


def check_songs():
    names = sorted(n[:-5] for n in os.listdir(songs_dir()) if n.endswith(".json"))
    check("eight starter songs", len(names) >= 8, repr(names))
    for name in names:
        p = load(name)
        model.migrate(p)
        parts = p.get("parts") or {}
        pats = p["tracks"][0]["patterns"] if p.get("tracks") else []
        f = eng.Form(p)
        idx = [parts.get("intro"), parts.get("outro")] + list(parts.get("mains") or []) + \
            list(parts.get("fills") or []) + list(parts.get("transitions") or [])
        ok = len(p["tracks"]) == 1 and p["tracks"][0]["kind"] == "drums" and \
            f.intro is not None and f.outro is not None and len(f.mains) >= 2 and \
            len(f.fills) == len(f.mains) and len(f.transitions) >= 1 and \
            all(i is not None and 0 <= i < len(pats) for i in idx)
        check("%s has an intro, mains, a fill per main, a transition and an outro" % name, ok, repr(parts))
        bad = []
        for i, pat in enumerate(pats):
            length = pat["bars"] * model.BAR
            if not pat["notes"]:
                bad.append("pattern %d is empty" % i)
            for n in pat["notes"]:
                if not (0 <= n[0] < length and 35 <= n[2] <= 81 and 1 <= n[3] <= 127):
                    bad.append("pattern %d: %r" % (i, n))
        check("%s's notes are General MIDI drums inside their bars" % name, not bad, repr(bad[:3]))


# -- the kits --------------------------------------------------------------------------


def peaks(kit, frames):
    """The loudest sample of ``kit`` over ``frames``."""
    import array
    import audiocore

    loud = 0
    got = 0
    while got < frames:
        kit.fill()
        _r, b = audiocore.get_buffer(kit.output)
        a = array.array("h", bytes(b))
        for v in a:
            if v > loud:
                loud = v
            elif -v > loud:
                loud = -v
        got += len(a) // 2
    return loud


def sounds(kit, pitch):
    peaks(kit, 4096)              # let what came before die away a little
    kit.note_on(pitch, 120)
    return peaks(kit, RATE // 8)


PADS = (36, 38, 42, 46, 49)


def write_kit(folder):
    """A sample kit of decaying tones, one per pad, and its kit.json."""
    from backline import kits

    try:
        os.mkdir(folder)
    except OSError:
        pass
    pads = {}
    for i, pitch in enumerate(PADS):
        n = RATE // 5
        data = bytearray(2 * n)
        hz = 80.0 + 140.0 * i
        for k in range(n):
            v = int(20000 * math.exp(-k / 2400.0) * math.sin(2 * math.pi * hz * k / RATE))
            data[2 * k] = v & 255
            data[2 * k + 1] = (v >> 8) & 255
        name = "pad%d.wav" % pitch
        kits.write_wav(folder + "/" + name, bytes(data), RATE)
        pads[str(pitch)] = name
    with open(folder + "/kit.json", "w") as f:
        json.dump({"name": "Test tones", "pads": pads, "choke": [[42, 46]]}, f)


def check_kits(tmp):
    try:
        from backline import kits
        import audiocore  # noqa: F401
        import audioinstruments  # noqa: F401
    except ImportError as e:
        skip("the kits", "no audio modules here (%s)" % e)
        return
    for machine in kits.MACHINES:
        kit = kits.open_kit(machine)
        heard = [(p, sounds(kit, p)) for p in PADS]
        quiet = [p for p, v in heard if v < 500]
        check("%s sounds 36, 38, 42, 46 and 49" % machine, not quiet, repr(heard))
        kit.close()
    bank = kits.find_bank()
    if bank is None:
        skip("the SoundFont kit", "no .sf2 here: set SOUNDFONT or put one in ~/soundfonts")
    else:
        kit = kits.open_kit("soundfont")
        heard = [(p, sounds(kit, p)) for p in PADS]
        quiet = [p for p, v in heard if v < 500]
        check("the SoundFont kit (%s) sounds 36, 38, 42, 46 and 49" % kit.name, not quiet, repr(heard))
        kit.close()
    folder = tmp + "/backline-kit"
    write_kit(folder)
    kit = kits.open_kit("samples:" + folder)
    heard = [(p, sounds(kit, p)) for p in PADS]
    quiet = [p for p, v in heard if v < 500]
    check("a sample kit sounds 36, 38, 42, 46 and 49", not quiet, repr(heard))
    peaks(kit, RATE)
    kit.note_on(46, 120)
    peaks(kit, 1024)
    kit.note_on(42, 1)            # nearly silent, so what's left is the open hat's tail, or nothing
    peaks(kit, 2048)
    tail = peaks(kit, 1024)
    check("a closed hat stops the open one", tail < 300, "still %d" % tail)
    kit.close()


# -- a pedal from a panel ---------------------------------------------------------------


def check_panel():
    try:
        import hmilink
        from hmilink import local
        from backline import box as boxmod
        import audiocore  # noqa: F401
    except ImportError as e:
        skip("the panel", "no hmilink or audio modules here (%s)" % e)
        return
    frames = [0]
    ms = [0]
    b = boxmod.Box(lambda: frames[0], song="rock", kit="rhythm808", now_ms=lambda: ms[0])
    b.device._tele_ms = 0         # telemetry on demand, below
    panel = hmilink.Panel(local.connect(b.device.add(local.serve())))
    seen = []
    panel.on_tele = seen.append
    b.poll()
    panel.poll()
    check("a panel gets the song", panel.doc is not None and panel.doc.get("name") == "Straight Rock" and
          panel.desc.get("kind") == "backline" and "parts" in panel.desc)
    panel.command("pedal", pedal=0, down=True)
    b.poll()
    ms[0] = 90
    panel.command("pedal", pedal=0, down=False)
    b.poll()
    for _ in range(40):
        b.service()
        frames[0] += 256
    b.device._telemetry()
    panel.poll()
    t = seen[-1] if seen else {}
    check("a tap from a panel starts the song, and its telemetry says so",
          t.get("playing") and t.get("part") == "Intro" and t.get("next") == "Main 1" and t.get("beat") == 1,
          repr(t))
    b.close()


def main():
    p, tmp = args()
    plant(p)
    check_pedal()
    check_form()
    check_engine()
    check_songs()
    check_kits(tmp)
    check_panel()
    print("on %s" % sys.implementation.name)
    print("%d passed, %d failed, %d skipped" % (RESULTS[0], RESULTS[1], len(SKIPS)))
    if RESULTS[1]:
        sys.exit(1)


main()
