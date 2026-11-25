# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's contract, on any interpreter: the pedal's gestures, the song's
plan, parts switching on the bar line, the ring following the meter, the
mixer's groups, the desk's song form and step taps, the starter songs, each
kind of kit sounding, the SoundFont kit as the default and Backline's own
bank fetched and checked, a pedal pressed from an hmilink panel, a step
edited from one panel while the song plays, heard in the sound and seen by
another panel, and MIDI switches learned and played as pedals and actions.

    python tests/backline_contract.py [--plant=NAME] [--tmp FOLDER]
    micropython -X heapsize=64M tests/backline_contract.py

The pedal, the plan, the engine and the songs need nothing but the
interpreter: a stand-in kit counts what it is given. The kits need
audioinstruments and audiodsp on the path, and the panel check hmilink;
without them those checks say they skipped. The SoundFont kit plays a tiny
bank the test writes (``backline_bank.py``), never Backline's own or the
network.

``--plant=NAME`` breaks Backline in one known way first (``PLANTS``), and a
check must then fail: ``tests/test_backline.py`` runs every plant. It ends
with ``N passed, M failed`` and exits non-zero on a failure.
"""

import json
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
from backline import footswitch  # noqa: E402
from backline import kits as _kits  # noqa: E402
from backline import midipedal  # noqa: E402
from backline import pedal as pedals  # noqa: E402
from songmodel import model  # noqa: E402

PLANTS = ("no-hold", "no-double", "switch-now", "no-return", "no-wrap", "outro-forever", "fill-ignores-main",
          "late-notes", "drop-pad", "deaf-panel", "song-without-outro", "four-steps", "deaf-mix",
          "form-out-of-order", "tap-sticks", "edit-resets-form", "edit-not-heard", "learn-on-release",
          "cc-no-release", "pc-as-pedal", "any-channel", "tempo-no-reset", "deaf-pedals", "no-repeat", "no-ramp",
          "ramp-jumps", "fill-moves-form", "migrate-forgets", "switch-bounces", "switch-inverted",
          "switch-swapped", "machine-default", "lost-machine", "unchecked-fetch", "keep-partial", "no-fetch",
          "stale-url", "no-frozen")

# The kit lookup as the app has it: backline_bank.use() replaces it for
# the checks that play the test bank.
FIND_BANK = _kits.find_bank
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

        def note_on(self, pitch, velocity, delay=0):
            if pitch != 46:
                old(self, pitch, velocity, delay)
        kits.DrumMachineKit.note_on = note_on
    elif name == "machine-default":
        from backline import kits

        kits.DEFAULT = kits.MACHINES[0]
    elif name == "lost-machine":
        from backline import kits

        old = kits.available
        kits.available = lambda: [k for k in old() if k != "rhythm606"]
    elif name == "unchecked-fetch":
        from backline import kits

        kits._verify = lambda got, sha256, url: None
    elif name == "keep-partial":
        from backline import kits

        old_remove = kits.os.remove

        class _Os:
            def __getattr__(self, name):
                return getattr(old_os, name)

            def remove(self, path):
                if not path.endswith(".part"):
                    old_remove(path)
        old_os = kits.os
        kits.os = _Os()
    elif name == "no-fetch":
        from backline import box

        box.Box._fetch_default = lambda self: None
    elif name == "no-frozen":
        from backline import kits

        kits.frozen_bank = lambda: None
    elif name == "stale-url":
        from backline import kits

        kits.DEFAULT_URL = kits.DEFAULT_URL.replace("backline-drums-1", "backline-drums-0")
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
    elif name == "no-repeat":
        old = eng.Form.__init__

        def init(self, project):
            old(self, project)
            self.repeat = 0
        eng.Form.__init__ = init
    elif name == "no-ramp":
        model.ramp_to = lambda project, part: None
    elif name == "ramp-jumps":
        old = eng.Engine._ramp

        def ramp(self):
            old(self)
            if self.ramp is not None:
                self.ramp = (self.ramp[0], self.ramp[0] + 1, self.ramp[2])
        eng.Engine._ramp = ramp
    elif name == "fill-moves-form":
        def fill_in_plan(self, now, number, fill, tick):
            at = eng.bar_after(tick)
            self._cut(tick, now, at, [("fill", number, fill, at), ("main", number, self.mains[number],
                                                                   at + self.length(fill))])
            return "fill"
        eng.Form._fill_in_plan = fill_in_plan
    elif name == "migrate-forgets":
        old = model.migrate

        def migrate(project):
            old(project)
            project.pop("repeat", None)
            project.pop("tempo_map", None)
            return project
        model.migrate = migrate
    elif name == "switch-bounces":
        old = footswitch.Footswitch.__init__

        def init(self, pin, which=0, on_pedal=None, active_low=True, settle_ms=footswitch.SETTLE_MS):
            old(self, pin, which, on_pedal, active_low, 0)
        footswitch.Footswitch.__init__ = init
    elif name == "switch-inverted":
        footswitch.Footswitch._pressed = lambda self: bool(self.pin.value())
    elif name == "switch-swapped":
        footswitch.KEYS = (("switch", 1), ("switch_b", 0))
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


# -- the play plan: a repeat count and the outro slowing ---------------------------------


def planned_song(repeat, outro_tempo=None, tempo=120.0):
    """Intro, one main and its fill of a bar each, and a two-bar outro: a
    closed hat on every eighth throughout, so the onsets show the tempo."""
    hats = [[i * model.STEP * 2, 24, 42, 100] for i in range(8)]
    p = model.new_project()
    t = model.track("drums", "fake", "Drums")
    t["id"] = 1
    t["patterns"] = [{"bars": 1, "notes": hats}, {"bars": 4, "notes": [n[:] for n in hats * 1] +
                                                  [[n[0] + k * eng.BAR, 24, 42, 100] for k in (1, 2, 3) for n in hats]},
                     {"bars": 1, "notes": [[i * model.STEP, 24, 38, 90] for i in range(16)]},
                     {"bars": 2, "notes": hats + [[n[0] + eng.BAR, 24, 42, 100] for n in hats]}]
    p["tracks"] = [t]
    p["tempo"] = tempo
    p["parts"] = {"intro": 0, "mains": [1], "fills": [2], "outro": 3}
    p["repeat"] = repeat
    p["tempo_map"] = [{"part": "outro", "tempo": outro_tempo}] if outro_tempo else []
    return p


def check_plan():
    old = {"tempo": 100.0, "tracks": [model.track("drums", "fake")], "parts": {"mains": [0]}}
    model.migrate(old)
    check("an older song loads with no repeat count and no tempo map",
          old.get("repeat") == 0 and old.get("tempo_map") == [], repr(sorted(old)))
    song = planned_song(3)
    f = eng.Form(song)
    f.start(0)
    roles = [e[0] for e in f.plan]
    check("three times through: the intro, the main three times, the outro, the end",
          roles == ["intro", "main", "main", "main", "outro", "end"], repr(roles))
    e, kit, parts = run_engine(song, [(0, 0, "tap")], 30)
    names = [p[1] for p in parts]
    end = (1 + 3 * 4 + 2) * 4 * RATE * 60.0 / song["tempo"]
    stopped = parts[-1][0] if parts[-1][1] is None else -1
    check("a song with a repeat count plays itself through and stops after the outro",
          names == ["Intro", "Main 1", "Outro", None] and abs(stopped - end) < 512, "%r, stopped at %d of %d" %
          (names, stopped, end))
    loop = planned_song(0)
    e, kit, parts = run_engine(loop, [(0, 0, "tap")], 30)
    check("with no repeat count the main plays on until the pedal", [p[1] for p in parts] == ["Intro", "Main 1"],
          repr(parts))
    # A tap in a planned song: the fill takes the main's last bar, and the outro keeps its place.
    spb = RATE * 60.0 / song["tempo"]
    e, kit, parts = run_engine(song, [(0, 0, "tap"), (int(5.5 * spb), 0, "tap")], 30)
    names = [p[1] for p in parts]
    fill_at = [p[0] for p in parts if p[1] == "Fill 1"]
    outro_at = [p[0] for p in parts if p[1] == "Outro"]
    check("a tap in a planned song plays the fill over the main's last bar, and the form keeps its length",
          names[:5] == ["Intro", "Main 1", "Fill 1", "Main 1", "Outro"] and fill_at and
          abs(fill_at[0] - 4 * 4 * spb) < 512 and outro_at and abs(outro_at[0] - 13 * 4 * spb) < 512,
          "%r" % parts)


def onsets(e, pitch=42):
    return [n[0] for n in e.played if n[1] == pitch]


def check_ramp():
    song = planned_song(1, outro_tempo=60.0)
    e, kit, parts = run_engine(song, [(0, 0, "tap")], 16)
    spb = RATE * 60.0 / song["tempo"]
    hats = onsets(e)
    outro_at = [p[0] for p in parts if p[1] == "Outro"][0]
    before = [b - a for a, b in zip(hats, hats[1:]) if b <= outro_at]
    inside = [b - a for a, b in zip(hats, hats[1:]) if a >= outro_at]
    even = max(before) - min(before) <= 2
    check("before the outro the tempo holds", even, "gaps %d to %d frames" % (min(before), max(before)))
    widening = all(b > a for a, b in zip(inside, inside[1:]))
    smooth = inside and inside[0] < 1.12 * before[-1] and all(b < 1.15 * a for a, b in zip(inside, inside[1:]))
    check("across the outro the beats spread out smoothly", len(inside) == 15 and widening and smooth,
          "%r" % inside)
    # 120 to 60 over two bars: the last eighth is at nearly 62 BPM, almost twice as long as at 120.
    check("and the outro ends near its end tempo", inside and inside[-1] > 1.8 * before[-1],
          "last gap %d against %d" % (inside[-1] if inside else 0, before[-1]))
    t_mid = None
    frames = [0]
    e2 = eng.Engine(song, None, lambda: frames[0], RATE, now_ms=lambda: frames[0] * 1000 // RATE)
    e2.gesture(0, "tap")
    while e2.transport["playing"] and frames[0] < outro_at + int(4 * spb):
        e2.sequence()
        frames[0] += 256
    t_mid = e2.telemetry()["tempo"]
    check("the box tells the panels the tempo as it slows", 60.0 < t_mid < 110.0, "%r" % t_mid)
    # The outro reached by a double tap, in a song that loops: it slows the same way.
    loop = planned_song(0, outro_tempo=60.0)
    e, kit, parts = run_engine(loop, [(0, 0, "tap"), (int(6.5 * spb), 0, "double")], 20)
    hats = onsets(e)
    outro_at = [p[0] for p in parts if p[1] == "Outro"]
    inside = [b - a for a, b in zip(hats, hats[1:]) if outro_at and a >= outro_at[0]]
    check("a double tap's outro slows too", len(inside) == 15 and all(b > a for a, b in zip(inside, inside[1:])),
          "%r" % inside)


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
MACHINES = ("rhythm808", "rhythm909", "rhythm606", "rhythm78", "electronic_drums5")


def check_kits(tmp):
    try:
        from backline import kits
        import audiocore  # noqa: F401
        import audioinstruments  # noqa: F401
        import backline_bank
    except ImportError as e:
        skip("the kits", "no audio modules here (%s)" % e)
        return
    have = kits.available()
    check("the SoundFont kit comes first, and every drum machine is still a kit",
          have[0] == kits.SOUNDFONT and all(m in have for m in MACHINES), repr(have))
    for machine in kits.MACHINES:
        kit = kits.open_kit(machine)
        heard = [(p, sounds(kit, p)) for p in PADS]
        quiet = [p for p, v in heard if v < 500]
        check("%s sounds 36, 38, 42, 46 and 49" % machine, not quiet, repr(heard))
        kit.close()
    backline_bank.use(tmp)
    kit = kits.open_kit("soundfont")
    heard = [(p, sounds(kit, p)) for p in PADS]
    quiet = [p for p, v in heard if v < 500]
    check("the SoundFont kit sounds 36, 38, 42, 46 and 49", not quiet and kit.spec == "soundfont",
          repr((heard, kit.spec)))
    peaks(kit, RATE)
    kit.note_on(46, 120)
    peaks(kit, 1024)
    kit.note_on(42, 1)            # nearly silent, so what's left is the open hat's tail, or nothing
    peaks(kit, 2048)
    tail = peaks(kit, 1024)
    check("a closed hat stops the open one", tail < 300, "still %d" % tail)
    kit.close()


# -- Backline's own bank -------------------------------------------------------------


def _sha256(data):
    import hashlib

    return "".join("%02x" % b for b in hashlib.sha256(data).digest())


def _served(body, status=200):
    """A stand-in for the network: ``get(url, write)`` that answers ``body``."""
    asked = []

    def get(url, write):
        asked.append(url)
        if status == 200:
            for i in range(0, len(body), 1000):
                write(body[i:i + 1000])
        return status
    return get, asked


def _listing(folder):
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


def check_default_bank(tmp):
    from backline import kits

    check("the starter songs and a song naming no kit play the SoundFont kit",
          kits.DEFAULT == kits.SOUNDFONT and
          all(load(n[:-5])["tracks"][0].get("instrument") == kits.SOUNDFONT
              for n in os.listdir(songs_dir()) if n.endswith(".json")))
    folder = tmp + "/fetched"
    try:
        os.mkdir(folder)
    except OSError:
        pass
    body = b"RIFF" + bytes(range(256)) * 40
    get, asked = _served(body)
    path = kits.fetch_default(folder, sha256=_sha256(body), get=get)
    with open(path, "rb") as f:
        got = f.read()
    check("the bank is fetched from where the app says, whole, under its own name",
          got == body and path == folder + "/" + kits.DEFAULT_BANK and _listing(folder) == [kits.DEFAULT_BANK] and
          asked == [kits.DEFAULT_URL], repr((len(got), path, _listing(folder), asked)))
    os.remove(path)
    bad = body[:-1] + b"!"
    get, _asked = _served(bad)
    try:
        kits.fetch_default(folder, sha256=_sha256(body), get=get)
        refused = False
    except OSError:
        refused = True
    check("a download with the wrong bytes is refused and leaves nothing", refused and not _listing(folder),
          repr((refused, _listing(folder))))
    get, _asked = _served(b"", status=404)
    try:
        kits.fetch_default(folder, sha256=_sha256(body), get=get)
        refused = False
    except OSError:
        refused = True
    check("a missing bank is an error, and leaves nothing", refused and not _listing(folder),
          repr((refused, _listing(folder))))
    url = None
    try:
        with open(songs_dir() + "/../app.json") as f:
            url = json.load(f)["downloads"]["soundfonts/" + kits.DEFAULT_BANK]
    except (OSError, KeyError, ValueError):
        pass
    check("omip installs the bank from where the app fetches it, into the folder it looks in",
          url == kits.DEFAULT_URL and kits.default_folders()[0].endswith("backline/soundfonts"),
          repr((url, kits.DEFAULT_URL, kits.default_folders()[:1])))


def check_frozen_bank(tmp):
    """A firmware with Backline's bank frozen in plays it, and fetches nothing."""
    import backline_bank
    from backline import kits

    if kits.getenv("SOUNDFONT"):
        skip("the frozen bank", "$SOUNDFONT names another bank")
        return
    folder = tmp + "/frozen"
    try:
        os.mkdir(folder)
    except OSError:
        pass
    with open(backline_bank.write(folder + "/bank.sf2"), "rb") as f:
        data = f.read()
    with open(folder + "/" + kits.FROZEN_MODULE + ".py", "w") as f:
        f.write("BANK = %r\n" % data)
    old = (kits.find_bank, kits.default_bank)
    kits.find_bank = FIND_BANK
    kits.default_bank = lambda: None  # nothing downloaded on this machine
    sys.path.insert(0, folder)
    sys.modules.pop(kits.FROZEN_MODULE, None)
    try:
        if not kits.reads_from_memory():
            found = kits.find_bank()
            check("an audioinstruments that plays no bank from memory leaves a frozen bank for the download",
                  found is None, repr(type(found)))
        reads = kits.reads_from_memory
        kits.reads_from_memory = lambda: True
        try:
            found = kits.find_bank()
        finally:
            kits.reads_from_memory = reads
        check("a bank frozen into the firmware is the one the soundfont kit plays, before any download",
              found == data, repr(type(found)))
        if found != data:
            return
        try:
            import audioinstruments  # noqa: F401
            import audiocore  # noqa: F401
        except ImportError as e:
            skip("the frozen bank plays", "no audio modules here (%s)" % e)
            return
        if not kits.reads_from_memory():
            skip("the frozen bank plays", "this audioinstruments plays no bank from bytes")
            return
        kit = kits.open_kit(kits.SOUNDFONT)
        heard = kit.name == kits.DEFAULT_TITLE and kit.bank is found
        kit.close()
        check("the frozen bank opens as Backline Drums", heard, repr(kit.name))
        try:
            from backline import box as boxmod
            import hmilink  # noqa: F401
        except ImportError as e:
            skip("a box on the frozen bank", "no hmilink here (%s)" % e)
            return
        project = load("rock")
        del project["tracks"][0]["instrument"]
        worker = _Worker()
        b = boxmod.Box(lambda: 0, song=project, worker=worker, now_ms=lambda: 0)
        started = (b.kit_spec(), b.error, len(worker.jobs))
        b.close()
        check("a box on the frozen bank plays it at once and fetches nothing",
              started == (kits.SOUNDFONT, None, 0), repr(started))
    finally:
        sys.path.remove(folder)
        sys.modules.pop(kits.FROZEN_MODULE, None)
        kits.find_bank, kits.default_bank = old


class _Worker:
    """Runs a job when told to, as the app's worker would on its thread."""

    def __init__(self):
        self.jobs = []

    def submit(self, work, done=None, key=None, owner=None, release=None):
        self.jobs.append((work, done))

    def run(self):
        while self.jobs:
            work, done = self.jobs.pop(0)
            try:
                value, error = work(), None
            except Exception as e:  # noqa: BLE001 - handed to done, as the worker does
                value, error = None, e
            if done is not None:
                done(value, error)


def check_first_start(tmp):
    """A box that starts with no bank fetches it, then plays it."""
    try:
        from backline import box as boxmod
        from backline import kits
        import audiocore  # noqa: F401
        import backline_bank
        import hmilink  # noqa: F401
    except ImportError as e:
        skip("the first start", "no hmilink or audio modules here (%s)" % e)
        return
    folder = tmp + "/first"
    try:
        os.mkdir(folder)
    except OSError:
        pass
    old = (kits.find_bank, kits.default_bank, kits.fetch_default)
    landed = []

    def fetch():
        landed.append(backline_bank.write(folder + "/" + kits.DEFAULT_BANK))
        return landed[-1]
    kits.find_bank = lambda: landed[-1] if landed else None
    kits.default_bank = kits.find_bank
    kits.fetch_default = fetch
    project = load("rock")
    del project["tracks"][0]["instrument"]
    worker = _Worker()
    try:
        b = boxmod.Box(lambda: 0, song=project, worker=worker, now_ms=lambda: 0)
        before = (b.kit_spec(), b.error or "")
        worker.run()
        after = (b.kit_spec(), b.error)
        b.close()
    finally:
        kits.find_bank, kits.default_bank, kits.fetch_default = old
    check("a box with no bank yet says it's fetching it, then plays it",
          before[0] is None and "fetching" in before[1] and after == (kits.SOUNDFONT, None), repr((before, after)))


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


class FakePin:
    """A pin whose level is set by the check: 1 is up (pulled up), 0 pressed."""

    def __init__(self):
        self.level = 1

    def value(self):
        return self.level


def run_switch(project, script, until_bars):
    """Play ``project`` from a switch on a pin: ``script`` is [(ms, level)],
    the pin's level from then on, as a stomp switch with its bounces gives
    it. Returns the parts, as `run_engine` does, the gestures, and the
    switch's own [(ms, down)]."""
    frames = [0]
    kit = FakeKit(lambda: frames[0])
    e = eng.Engine(project, kit, lambda: frames[0], RATE, now_ms=lambda: frames[0] * 1000 // RATE)
    moves = []

    def on_pedal(which, down):
        moves.append((e.now_ms(), down))
        if down:
            e.press(which)
        else:
            e.release(which)
    pin = FakePin()
    sw = footswitch.open_switches({"switch": "pin:4"}, on_pedal, opener=lambda spec: (pin, True))[0]
    gestures = []
    old = e.gesture

    def gesture(which, g):
        gestures.append(g)
        return old(which, g)
    e.gesture = gesture
    end_ms = int(until_bars * 4 * 60000.0 / project["tempo"])
    script = list(script)
    parts = []
    ms = 0
    while ms < end_ms:
        frames[0] = ms * RATE // 1000
        while script and script[0][0] <= ms:
            pin.level = script.pop(0)[1]
        sw.poll(ms)                 # as the box's service pass does, every few ms
        if ms % 4 == 0:
            e.poll()
            e.sequence()
            t = e.telemetry()
            name = t["part"] if t["playing"] else None
            if not parts or parts[-1][1] != name:
                parts.append((ms, name))
        ms += 1
    return [p[1] for p in parts], gestures, moves


def press(at, length, bounce=True):
    """A stomp switch pressed at ``at`` for ``length`` ms, chattering for
    3 ms each way when ``bounce``."""
    out = [(at, 0)]
    if bounce:
        out += [(at + 1, 1), (at + 2, 0), (at + 3, 1), (at + 4, 0)]
    up = at + length
    out.append((up, 1))
    if bounce:
        out += [(up + 1, 0), (up + 2, 1), (up + 3, 0), (up + 4, 1)]
    return out


def check_footswitch():
    """A switch on a pin plays the song as pedal A does: tap, hold, double tap."""
    rock = load("rock")
    beat = 60000.0 / rock["tempo"]
    t1 = int(9.5 * beat)
    t2 = int(30.5 * beat)
    script = press(10, 90) + press(t1, 600) + press(t2, 80) + press(t2 + 250, 80)
    names, gestures, moves = run_switch(rock, script, 48)
    check("a bouncing switch on a pin goes down and up once a press",
          [d for _t, d in moves] == [True, False] * 4, repr(moves))
    check("it is heard within a few ms of the contact settling", moves and 10 <= moves[0][0] <= 10 + 4 + 10,
          repr(moves[:1]))
    check("a switch on a pin taps, holds and double-taps pedal A", gestures == ["tap", "hold", "tap", "double"],
          repr(gestures))
    want = [None, "Intro", "Main 1", "Transition 2", "Main 2", "Outro", None]
    check("from the pin the tap starts the song, the hold moves to the next part and the double tap plays the outro",
          names == want, repr(names))
    # A switch that reads high when pressed, and the second setting is pedal B.
    pins = {}

    def opener(spec):
        pins[spec] = FakePin()
        pins[spec].level = 0
        return pins[spec], not spec.endswith(":high")
    got = []
    sws = footswitch.open_switches({"switch": "", "switch_b": "pin:5:high"}, lambda w, d: got.append((w, d)),
                                   opener=opener)
    sws[0].poll(0)
    pins["pin:5:high"].level = 1
    for t in range(1, 20):
        sws[0].poll(t)
    check("an empty setting is no switch; switch_b is pedal B; pin:N:high is pressed when high",
          len(sws) == 1 and got == [(1, True)], repr((len(sws), got)))
    try:
        footswitch.open_pin("gpio35")
        bad = None
    except ValueError as e:
        bad = str(e)
    check("a switch spec that isn't one of the forms says so", bad is not None and "pin:N" in bad, repr(bad))


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
    check_plan()
    check_ramp()
    check_meter()
    check_mix()
    check_desk_reading()
    check_songs()
    check_kits(tmp)
    check_default_bank(tmp)
    check_first_start(tmp)
    check_frozen_bank(tmp)
    check_panel()
    check_live_edit()
    check_midi_learn()
    check_midi_pedal()
    check_footswitch()
    check_midi_actions()
    check_midi_box()
    print("on %s" % sys.implementation.name)
    print("%d passed, %d failed, %d skipped" % (RESULTS[0], RESULTS[1], len(SKIPS)))
    if RESULTS[1]:
        sys.exit(1)


main()
