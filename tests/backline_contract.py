# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's contract, on any interpreter: the pedal's gestures, the song's
plan, parts switching on the bar line, the ring following the meter, the
mixer's groups, the desk's song form and step taps, the starter songs, each
kind of kit sounding, a pedal pressed from an hmilink panel, a step
edited from one panel while the song plays, heard in the sound and seen by
another panel, and MIDI switches learned and played as pedals and actions.

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
from backline import midipedal  # noqa: E402
from backline import pedal as pedals  # noqa: E402
from songmodel import model  # noqa: E402

PLANTS = ("no-hold", "no-double", "switch-now", "no-return", "no-wrap", "outro-forever", "fill-ignores-main",
          "late-notes", "drop-pad", "no-choke", "deaf-panel", "song-without-outro", "four-steps", "deaf-mix",
          "form-out-of-order", "tap-sticks", "edit-resets-form", "edit-not-heard", "learn-on-release",
          "cc-no-release", "pc-as-pedal", "any-channel", "tempo-no-reset", "deaf-pedals")

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
    elif name == "four-steps":
        eng.meter = lambda project: (4, 1)
    elif name == "deaf-mix":
        eng.GROUP_OF.clear()
    elif name == "form-out-of-order":
        from backline import parts

        old = parts.blocks
        parts.blocks = lambda doc: sorted(old(doc), key=lambda b: b["role"])
    elif name == "tap-sticks":
        from backline import parts

        parts.LEVELS = (0, 96, 96, 96)
    elif name == "edit-resets-form":
        from backline import box

        old = box.Box.forward

        def forward(self, op):
            if "patterns" in op.get("path", ()):
                self.engine.form.__init__(self.model.doc)
                return
            old(self, op)
        box.Box.forward = forward
    elif name == "edit-not-heard":
        from backline import box

        old = eng.Engine.load

        def load(self, project):
            old(self, json.loads(json.dumps(project)))
        eng.Engine.load = load
    elif name == "learn-on-release":
        old = midipedal.MidiPedal.handle

        def handle(self, status, d1, d2):
            if self.learning is not None:
                msg, _press = midipedal.read(status, d1, d2)
                return self._learn(msg) if msg is not None else None
            return old(self, status, d1, d2)
        midipedal.MidiPedal.handle = handle
    elif name == "cc-no-release":
        old = midipedal.MidiPedal._act

        def act(self, i, slot, press):
            if press:
                old(self, i, slot, press)
        midipedal.MidiPedal._act = act
    elif name == "pc-as-pedal":
        midipedal.can_pedal = lambda msg: True
    elif name == "any-channel":
        old = midipedal.read

        def read(status, d1, d2):
            return old(status & 0xF0, d1, d2)
        midipedal.read = read
    elif name == "tempo-no-reset":
        old = midipedal.TapTempo.__init__

        def init(self, reset_ms=2000, keep=4, lo=40.0, hi=240.0):
            old(self, 1 << 29, keep, lo, hi)
        midipedal.TapTempo.__init__ = init
    elif name == "deaf-pedals":
        from backline import box

        box.Box._pedals_changed = lambda self: None
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


# -- the meter, the mixer, the desk's reading of a song -------------------------------


def check_meter():
    ballad = load("ballad_68")
    spb = RATE * 60.0 / ballad["tempo"]
    intro = eng.Form(ballad).length(ballad["parts"]["intro"])
    e, kit, parts = run_engine(ballad, [(0, 0, "tap")], 3)
    seen = []
    for k in range(12):
        tick = intro + eng.BAR + k * eng.BAR / 12.0 + 4
        e.transport["playing"] = True
        e.clock = (lambda f: lambda: f)(int(e.frame_at(tick)))
        t = e.telemetry()
        seen.append((t["step"], t["beat"]))
    want = [(k + 1, k // 3 + 1) for k in range(12)]
    check("12/8 lights twelve steps a bar, three to a beat", seen == want and e.telemetry()["steps"] == 12 and
          e.telemetry()["beats"] == 4, repr(seen))
    rock = load("rock")
    t = run_engine(rock, [(0, 0, "tap")], 1)[0].telemetry()
    check("4/4 lights four steps a bar, one a beat", t["steps"] == 4 and t["beats"] == 4, repr(t))


def check_mix():
    rock = load("rock")
    rock["tracks"][0]["mix"] = {"kick": 0, "snare": 50}
    e, kit, parts = run_engine(rock, [(0, 0, "tap")], 6)
    kicks = [n for n in kit.notes if n[1] in (35, 36)]
    pat = {}
    for p in rock["tracks"][0]["patterns"]:
        for n in p["notes"]:
            if n[2] == 38:
                pat[n[3]] = True
    snares = [n[2] for n in kit.notes if n[1] == 38]
    want = set(v * 50 // 100 for v in pat)
    check("the mixer's kick at 0 silences the kick, its snare at 50 halves it",
          not kicks and snares and set(snares) <= want, "%d kicks, snares %r" % (len(kicks), sorted(set(snares))))
    check("a song with no mix gets every group at 100", load_mixed("pop") == eng.MIX, repr(load_mixed("pop")))


def load_mixed(name):
    e = eng.Engine(load(name), None, lambda: 0, RATE)
    return e.track["mix"]


def check_desk_reading():
    from backline import parts

    rock = load("rock")
    roles = [(b["role"], b["number"]) for b in parts.blocks(rock)]
    want = [("intro", None), ("main", 0), ("fill", 0), ("transition", 1), ("main", 1), ("fill", 1), ("outro", None)]
    check("the song form reads intro, main 1, fill 1, transition, main 2, fill 2, outro", roles == want, repr(roles))
    check("a 4/4 grid has sixteen steps a bar, 12/8 twelve", parts.columns(rock) == (16, 24) and
          parts.columns(load("ballad_68")) == (12, 32), repr((parts.columns(rock), parts.columns(load("ballad_68")))))
    doc = json.loads(json.dumps(rock))
    index = doc["parts"]["mains"][0]
    seen = []
    for _ in range(4):
        op, path, value = parts.tap(doc, index, 39, 3, 24)
        keys = [int(k) if k.isdigit() else (-1 if k == "-" else k) for k in path.split("/")[1:]]
        if op == "add":
            model.apply(doc, {"op": "insert", "path": keys, "value": value})
        elif op == "remove":
            model.apply(doc, {"op": "remove", "path": keys})
        else:
            model.apply(doc, {"op": "set", "path": keys, "value": value})
        lv = parts.levels(doc["tracks"][0]["patterns"][index], [39], 24)
        seen.append(lv.get((39, 3), 0))
    check("taps walk a cell on, loud, soft and off", seen == [1, 2, 3, 0], repr(seen))


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


def check_live_edit():
    """Two panels on one box, the song playing: one adds a clap to the main
    groove and the other turns a hat down. The song plays on, the clap is
    heard on its step from the next pass, and both panels end with the box's
    song."""
    try:
        import hmilink
        from hmilink import local
        from backline import box as boxmod
        import audiocore
    except ImportError as e:
        skip("a live edit", "no hmilink or audio modules here (%s)" % e)
        return
    frames = [0]
    b = boxmod.Box(lambda: frames[0], song="rock", kit="rhythm808", now_ms=lambda: frames[0] * 1000 // RATE)
    b.device._tele_ms = 0
    listener = b.device.add(local.serve())
    a = hmilink.Panel(local.connect(listener))
    c = hmilink.Panel(local.connect(listener))
    b.poll()
    a.poll()
    c.poll()
    e = b.engine
    e.record = True
    spb = RATE * 60.0 / e.project["tempo"]

    def run(beats):
        end = frames[0] + int(beats * spb)
        while frames[0] < end:
            b.service()
            audiocore.get_buffer(b.bus.output)
            frames[0] += 256
            b.poll()
            a.poll()
            c.poll()

    e.gesture(0, "tap")
    run(10.2)                        # into main 1's first bar
    main = e.project["parts"]["mains"][0]
    before = len(e.played)
    a.send("add", "/tracks/0/patterns/%d/notes/-" % main, [48, 24, 39, 110])
    hats = [i for i, n in enumerate(e.project["tracks"][0]["patterns"][main]["notes"]) if n[2] == 42]
    c.send("replace", "/tracks/0/patterns/%d/notes/%d/3" % (main, hats[0]), 40)
    run(20)
    t = e.telemetry()
    check("the song plays on through an edit", t["playing"] and t["part"] == "Main 1", repr(t.get("part")))
    claps = [n for n in e.played[before:] if n[1] == 39]
    now = e.form.sounding(e.tick_at(frames[0]))
    start = now[3] if now is not None else 0
    length = e.form.length(main)
    on_step = [n for n in claps if now is not None and abs((e.tick_at(n[0]) - start) % length - 48) < 1]
    check("the clap added while it plays is heard, on its step", len(on_step) >= 2 and len(on_step) == len(claps),
          "%d claps, %d on the step" % (len(claps), len(on_step)))
    box_notes = b.model.doc["tracks"][0]["patterns"][main]["notes"]
    same = a.doc["tracks"][0]["patterns"][main]["notes"] == box_notes == c.doc["tracks"][0]["patterns"][main]["notes"]
    check("both panels end with the box's groove, the clap and the quieter hat in it",
          same and [48, 24, 39, 110] in box_notes and box_notes[hats[0]][3] == 40,
          "resyncs %d / %d" % (a.stats["resyncs"], c.stats["resyncs"]))
    b.close()


# -- MIDI switches ----------------------------------------------------------------


def cc(num, value, ch=0):
    return bytes((0xB0 | ch, num, value))


def check_midi_learn():
    got = []
    m = midipedal.MidiPedal(on_pedal=lambda w, d: got.append(("pedal", w, d)),
                            on_action=lambda a: got.append(("action", a)))
    check("the default map is pedal A, pedal B, tap tempo and stop, waiting to be learned",
          [s["bind"] for s in m.slots] == ["pedal_a", "pedal_b", "tap_tempo", "stop"] and
          all(s["msg"] is None for s in m.slots), repr(m.slots))
    m.learn(0)
    m.feed(cc(80, 0))                  # a foot coming up from before the slot was armed
    m.feed(cc(81, 127))
    check("an armed slot learns the next switch pressed, not a release",
          m.slots[0]["msg"] == ["cc", 0, 81] and m.learning is None and not got, repr((m.slots[0], got)))
    m.learn(1)
    m.feed(cc(81, 127))
    check("a switch learned again leaves the slot that had it", m.slots[1]["msg"] == ["cc", 0, 81] and
          m.slots[0]["msg"] is None and m.slots[1]["bind"] == "pedal_b", repr(m.slots[:2]))
    m2 = midipedal.MidiPedal(m.saved())
    check("the map saves as plain data and comes back the same", m2.saved() == m.saved() and
          repr(m.saved()) == repr(eval(repr(m.saved()))), repr(m2.saved()))


def run_midi(project, script, until_bars):
    """Play ``project`` from MIDI: ``script`` is [(ms, bytes)], fed to a
    `MidiPedal` whose switch 1 is learned as CC 80 on pedal A. Returns the
    parts, as `run_engine` does, and the gestures the pedal made."""
    frames = [0]
    kit = FakeKit(lambda: frames[0])
    e = eng.Engine(project, kit, lambda: frames[0], RATE, now_ms=lambda: frames[0] * 1000 // RATE)
    m = midipedal.MidiPedal(on_pedal=lambda w, d: e.press(w) if d else e.release(w))
    m.learn(0)
    m.handle(0xB0, 80, 127)
    gestures = []
    old = e.gesture

    def gesture(which, g):
        gestures.append(g)
        return old(which, g)
    e.gesture = gesture
    spb = RATE * 60.0 / project["tempo"]
    end = int(until_bars * 4 * spb)
    script = list(script)
    parts = []
    while frames[0] < end:
        ms = frames[0] * 1000 // RATE
        while script and script[0][0] <= ms:
            m.feed(script.pop(0)[1])
        e.poll()
        e.sequence()
        t = e.telemetry()
        name = t["part"] if t["playing"] else None
        if not parts or parts[-1][1] != name:
            parts.append((frames[0], name))
        frames[0] += 256
    return [p[1] for p in parts], gestures


def check_midi_pedal():
    rock = load("rock")
    beat = 60000.0 / rock["tempo"]
    t1 = int(9.5 * beat)                # main 1's first bar: hold
    t2 = int(30.5 * beat)               # main 2: tap, then tap again at once
    script = [(0, cc(80, 127)), (90, cc(80, 0)),
              (t1, cc(80, 127)), (t1 + 600, cc(80, 0)),
              (t2, cc(80, 127)), (t2 + 80, cc(80, 0)), (t2 + 250, cc(80, 127)), (t2 + 330, cc(80, 0))]
    names, gestures = run_midi(rock, script, 48)
    check("a momentary switch's CC 127 and 0 tap, hold and double-tap pedal A",
          gestures == ["tap", "hold", "tap", "double"], repr(gestures))
    want = [None, "Intro", "Main 1", "Transition 2", "Main 2", "Outro", None]
    check("from MIDI the tap starts the song, the hold moves to the next part and the double tap plays the outro",
          names == want, repr(names))
    # A note on and its note off are a pedal too, and a repeat isn't a second press.
    got = []
    m = midipedal.MidiPedal([{"msg": ["note", 9, 36], "bind": "pedal_b"}], on_pedal=lambda w, d: got.append((w, d)))
    m.feed(bytes((0x99, 36, 100, 0x99, 36, 100, 0x89, 36, 0, 0x99, 36, 90, 0x99, 36, 0)))
    check("a note on and its note off move the pedal once each", got == [(1, True), (1, False), (1, True), (1, False)],
          repr(got))


def check_midi_actions():
    got = []
    m = midipedal.MidiPedal(on_pedal=lambda w, d: got.append(("pedal", w, d)),
                            on_action=lambda a: got.append(("action", a)))
    m.learn(0)                          # bound to pedal A, but a program change can't be a pedal
    m.feed(bytes((0xC0, 3)))
    m.feed(bytes((0xC0, 3)))
    check("a program change learned for a pedal becomes an action, and does it on every press",
          m.slots[0]["bind"] == midipedal.ONE_SHOT and got == [("action", "fill")], repr((m.slots[0], got)))
    refused = False
    try:
        m.bind(0, "pedal_a")
    except ValueError:
        refused = True
    check("a program change can't be bound to a pedal", refused and m.slots[0]["bind"] == "fill", repr(m.slots[0]))
    m.bind(0, "outro")
    m.learn(3)
    m.feed(cc(64, 127, ch=1))
    del got[:]
    m.feed(bytes((0xC0, 3)) + cc(64, 127, ch=1) + cc(64, 0, ch=1))
    check("each press of an action switch does its action once", got == [("action", "outro"), ("action", "stop")],
          repr(got))
    del got[:]
    m.feed(bytes((0xC1, 3, 0xC0, 4, 0xB0, 64, 127, 0x90, 60, 100, 0x80, 60, 0, 0xF8, 0xFA,
                  0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7, 0xE0, 0, 64)))
    check("messages no switch holds are ignored: another channel, program or controller, notes, clock, SysEx",
          got == [], repr(got))
    tt = midipedal.TapTempo()
    bpm = [tt.tap(t) for t in (0, 500, 1000, 1500)]
    later = [tt.tap(t) for t in (6000, 6600)]
    check("tap tempo is the taps' pace, and a pause starts the count again",
          bpm == [None, 120.0, 120.0, 120.0] and later == [None, 100.0], repr((bpm, later)))


def check_midi_box():
    """A box reading a MIDI input: a desk learns switches and binds them
    through its panel, and sees the map; the switches start and stop the
    song and tap its tempo."""
    try:
        import hmilink
        from hmilink import local
        from backline import box as boxmod
        import audiocore  # noqa: F401
    except ImportError as e:
        skip("MIDI on the box", "no hmilink or audio modules here (%s)" % e)
        return

    class Port:
        def __init__(self):
            self.waiting = []

        def any(self):
            return len(self.waiting[0]) if self.waiting else 0

        def readinto(self, buf, nbytes=None):
            if not self.waiting:
                return None
            msg = self.waiting.pop(0)
            buf[:len(msg)] = msg
            return len(msg)

    frames = [0]
    ms = [0]
    b = boxmod.Box(lambda: frames[0], song="rock", kit="rhythm808", now_ms=lambda: ms[0])
    port = Port()
    b.midi_in = port
    panel = hmilink.Panel(local.connect(b.device.add(local.serve())))
    seen = []
    panel.on_event = seen.append
    b.poll()
    panel.poll()

    def step(*msgs):
        port.waiting.extend(msgs)
        b.service()
        b.poll()
        panel.poll()

    check("a panel is told the switches' map", (panel.desc or {}).get("pedals", {}).get("learning") == -1,
          repr((panel.desc or {}).get("pedals")))
    panel.command("pedals", learn=2)
    step()
    step(bytes((0xC0, 9)))
    last = [ev for ev in seen if ev.get("name") == "pedals"]
    check("a slot armed from a panel learns the switch, and the panel hears the map",
          len(last) >= 2 and last[-1]["slots"][2]["msg"] == ["pc", 0, 9] and last[-1]["learning"] == -1,
          repr(last[-1:]))
    panel.command("pedals", learn=0)
    step()
    step(cc(80, 127), cc(80, 0))
    step(cc(80, 127))
    ms[0] = 90
    step(cc(80, 0))
    check("the learned switch is pedal A: its tap starts the song", b.engine.transport["playing"] and
          b.engine.last == "start", repr(b.engine.last))
    tempo = b.engine.project["tempo"]
    for t in (1000, 1400, 1800):
        ms[0] = t
        step(bytes((0xC0, 9)))
    check("the tap tempo switch sets the song to its pace, and the panel's song follows",
          b.engine.project["tempo"] == 150.0 and (panel.doc or {}).get("tempo") == 150.0,
          "%r -> %r, panel %r" % (tempo, b.engine.project["tempo"], (panel.doc or {}).get("tempo")))
    panel.command("pedals", slot=2, bind="stop")
    step()
    step(bytes((0xC0, 9)))
    check("bound to stop from the panel, the switch stops the song", not b.engine.transport["playing"])
    b.close()


def main():
    p, tmp = args()
    plant(p)
    check_pedal()
    check_form()
    check_engine()
    check_meter()
    check_mix()
    check_desk_reading()
    check_songs()
    check_kits(tmp)
    check_panel()
    check_live_edit()
    check_midi_learn()
    check_midi_pedal()
    check_midi_actions()
    check_midi_box()
    print("on %s" % sys.implementation.name)
    print("%d passed, %d failed, %d skipped" % (RESULTS[0], RESULTS[1], len(SKIPS)))
    if RESULTS[1]:
        sys.exit(1)


main()
