# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's player: a song's parts, switched on the bar line by a footswitch.

A song is a songmodel project with one drum track. The track's patterns are
the parts, and the project's ``"parts"`` key says which pattern plays which
role::

    "parts": {"intro": 0, "mains": [1, 2], "fills": [3, 4],
              "transitions": [5], "outro": 6, "accent": 7}

``mains`` is the song's main grooves in order and ``fills`` holds one fill
for each. ``transitions`` holds one pattern, played going into any main, or
one for each main, played going into it. ``intro``, ``outro`` and ``accent``
are optional.

`Form` is the song's plan, with no sound: what plays from which tick, and
how each gesture changes it. Stopped, a tap starts the intro and then the
first main. Playing a main, a tap plays its fill at the next bar line and
comes back to it; a hold plays the transition and moves to the next main
(after the last, the first); a double tap plays the outro and stops. During
the outro, a double tap stops at once. The second pedal's tap plays the
accent over whatever is playing, and its hold stops at once.

A song with a ``"repeat"`` count plays itself: the intro, the mains in
order that many times, then the outro. A tap still plays a fill, in the
last bars of the main playing, so the form keeps its length; a hold or a
double tap takes over from the plan. A ``"tempo_map"`` entry for the outro
(``{"part": "outro", "tempo": 56}``) slows it smoothly from the song's
tempo to that one by its last beat, whichever way the outro was reached.

`Engine` plays the plan through a kit (see kits.py). The frame clock is
given, as Vamp's engine takes it: the frame the output renders next, from
``audiopump.now()`` or a count of what a test pulled. Each `Engine.sequence`
hands the kit every note due by now plus ``lookahead`` frames, the delay
until its frame passed along to a kit that can hold a note back. The plan
reaches the song's track as its ``current`` and ``next``, so
``songmodel.model.segments`` splits the time at each switch.

Imports on CPython and MicroPython with nothing but songmodel: the kit and
the clock are given, so a check runs it with numbers alone.
"""

import math

try:
    from time import ticks_ms
except ImportError:  # CPython
    import time

    def ticks_ms():
        return int(time.monotonic() * 1000)

from songmodel import model

from . import pedal as pedals

RATE = 48000
BAR = model.BAR
BEAT = model.PPQ
ACCENT = ((0, 49, 120), (0, 36, 115))    # crash and kick, when a song names no accent
LABELS = {"intro": "Intro", "main": "Main", "fill": "Fill", "transition": "Transition",
          "outro": "Outro", "end": "Stop"}


#: The mixer's voice groups: which GM drum notes each one turns up or down.
GROUPS = (
    ("kick", (35, 36)),
    ("snare", (37, 38, 39, 40)),
    ("hats", (42, 44, 46)),
    ("toms", (41, 43, 45, 47, 48, 50)),
    ("cymbals", (49, 51, 52, 53, 55, 57, 59)),
)
OTHER = "perc"                # every note no group names
GROUP_OF = {}
for _name, _notes in GROUPS:
    for _n in _notes:
        GROUP_OF[_n] = _name
MIX = dict((g, 100) for g in [n for n, _ in GROUPS] + [OTHER])


def meter(project):
    """``(steps, group)``: the segments a bar's ring shows, and how many of
    them make one beat. 12/8 is twelve eighths in four beats of three; 4/4 is
    four beats of one."""
    try:
        n, d = [int(x) for x in str(project.get("meter") or "4/4").split("/")]
    except ValueError:
        return 4, 1
    if n < 1:
        return 4, 1
    if d == 8 and n % 3 == 0 and n > 3:
        return n, 3
    return n, 1


def bar_after(tick):
    """The first bar line at or after ``tick``."""
    return int((tick + BAR - 1) // BAR) * BAR


def label(entry):
    """What a screen calls a plan entry: ``"Main 2"``, ``"Fill 1"``, ``"Outro"``."""
    if entry is None:
        return ""
    role, number = entry[0], entry[1]
    text = LABELS[role]
    return text if number is None else "%s %d" % (text, number + 1)


class Form:
    """A song's plan: entries ``(role, number, pattern, at)``, in tick order.

    ``number`` is which main a main or a fill belongs to (from 0), else None.
    The entry with the latest ``at`` not after a tick is what plays then, and
    a main plays on until the plan changes. An ``"end"`` entry stops the song.
    """

    def __init__(self, project):
        parts = project.get("parts") or {}
        patterns = project["tracks"][0]["patterns"]
        self.bars = [max(1, p.get("bars", 1)) for p in patterns]
        self.intro = parts.get("intro")
        self.mains = list(parts.get("mains") or [0])
        self.fills = list(parts.get("fills") or [])
        trans = parts.get("transitions")
        if trans is None:
            trans = parts.get("transition")
        self.transitions = list(trans) if isinstance(trans, list) else ([] if trans is None else [trans])
        self.outro = parts.get("outro")
        self.accent = parts.get("accent")
        self.repeat = max(0, int(project.get("repeat") or 0))
        self.plan = []
        self.before = None        # the entry advance() dropped last: still sounding while the kit runs ahead

    @property
    def playing(self):
        return bool(self.plan) and self.plan[0][0] != "end"

    def length(self, pattern):
        return self.bars[pattern] * BAR

    def fill_for(self, n):
        return self.fills[n] if n < len(self.fills) else None

    def transition_into(self, n):
        if not self.transitions:
            return None
        return self.transitions[n] if len(self.transitions) == len(self.mains) else self.transitions[0]

    def start(self, tick=0):
        """The plan from a standing start at ``tick``: the intro, then main 1.
        With a repeat count, the whole song: the mains in order that many
        times, then the outro and the end."""
        self.plan = []
        self.before = None
        at = tick
        if self.intro is not None:
            self.plan.append(("intro", None, self.intro, at))
            at += self.length(self.intro)
        if not self.repeat:
            self.plan.append(("main", 0, self.mains[0], at))
            return
        for k in range(self.repeat):
            for n, main in enumerate(self.mains):
                trans = self.transition_into(n) if len(self.mains) > 1 and (k or n) else None
                if trans is not None:
                    self.plan.append(("transition", n, trans, at))
                    at += self.length(trans)
                self.plan.append(("main", n, main, at))
                at += self.length(main)
        if self.outro is not None:
            self.plan.append(("outro", None, self.outro, at))
            at += self.length(self.outro)
        self.plan.append(("end", None, -1, at))

    def _fill_in_plan(self, now, number, fill, tick):
        """A tap while a planned song plays: the fill over the last bars of
        the main playing (or the next main, when those have begun), so
        what follows keeps its place."""
        earliest = bar_after(tick)
        for i, e in enumerate(self.plan):
            if e[0] != "main" or i + 1 >= len(self.plan) or self.plan[i + 1][0] == "fill":
                continue
            fill = self.fill_for(e[1])
            if fill is None:
                continue
            at = self.plan[i + 1][3] - self.length(fill)
            if at >= earliest and at >= e[3]:
                self.plan.insert(i + 1, ("fill", e[1], fill, at))
                return "fill"
        return None

    def stop(self):
        self.plan = []
        self.before = None

    def advance(self, tick):
        """Drop the entries that ended before ``tick``; returns what plays then."""
        while len(self.plan) > 1 and self.plan[1][3] <= tick:
            self.before = self.plan.pop(0)
        return self.plan[0] if self.plan else None

    def sounding(self, tick):
        """The entry playing at ``tick``, without dropping anything."""
        found = None
        if self.before is not None and self.before[3] <= tick:
            found = self.before
        for e in self.plan:
            if e[3] <= tick:
                found = e
        return found

    def following(self, tick):
        """The first entry starting after ``tick``, or None."""
        for e in self.plan:
            if e[3] > tick:
                return e
        return None

    def gesture(self, pedal, gesture, tick):
        """Change the plan for ``gesture`` on pedal ``pedal`` (0 or 1), made
        when ``tick`` is the earliest tick still to be played. Returns what
        it did: ``"start"``, ``"fill"``, ``"transition"``, ``"outro"``,
        ``"stop"``, ``"accent"`` or None for a gesture that means nothing now."""
        now = self.sounding(tick)
        if pedal == 1:
            if gesture == "tap":
                return "accent"
            if gesture == "hold" and self.playing:
                self.plan = [("end", None, -1, tick)]
                return "stop"
            return None
        if now is None or now[0] == "end":
            if gesture == "tap":
                self.start(tick)
                return "start"
            return None
        role, number = now[0], now[1]
        at = bar_after(tick)
        if role == "outro":
            if gesture == "double":
                self.plan = [("end", None, -1, tick)]
                return "stop"
            return None
        if gesture == "double":
            self._cut(tick, now, at, [("outro", None, self.outro, at)] if self.outro is not None else [])
            end = at + (self.length(self.outro) if self.outro is not None else 0)
            self.plan.append(("end", None, -1, end))
            return "outro"
        if role != "main":
            return None           # the intro, a fill or a transition: it finishes first
        if gesture == "tap":
            fill = self.fill_for(number)
            if fill is None:
                return None
            if self.repeat and self.following(tick) is not None:
                return self._fill_in_plan(now, number, fill, tick)
            self._cut(tick, now, at, [("fill", number, fill, at), ("main", number, self.mains[number],
                                                                   at + self.length(fill))])
            return "fill"
        if gesture == "hold":
            n = (number + 1) % len(self.mains)
            trans = self.transition_into(n)
            steps = []
            start = at
            if trans is not None:
                steps.append(("transition", n, trans, at))
                start += self.length(trans)
            steps.append(("main", n, self.mains[n], start))
            self._cut(tick, now, at, steps)
            return "transition"
        return None

    def _cut(self, tick, now, at, steps):
        """Keep what is playing, drop whatever was still to come, and add ``steps``."""
        self.plan = [now] + steps


class Engine:
    """A song played through a kit, two pedals steering it.

    ``kit`` has ``note_on(pitch, velocity, delay)`` (delay in frames) and
    ``name``; ``clock()`` is the frame the output renders next. ``lookahead``
    is how far ahead of the clock notes go to the kit: 0 for a kit that plays
    a note the moment it gets it.
    """

    def __init__(self, project, kit=None, clock=None, rate=RATE, lookahead=0, now_ms=ticks_ms):
        self.rate = rate
        self.kit = kit
        self.clock = clock or (lambda: 0)
        self.now_ms = now_ms
        self.lookahead = lookahead
        self.pedals = [pedals.Pedal(), pedals.Pedal()]
        self.hits = []            # (frame, pitch, velocity): accents not yet played
        self.played = []          # (frame, pitch, velocity), when ``record`` is set: what a check reads
        self.record = False
        self.changes = 0          # bumps when the plan changes, for a screen
        self.last = None          # the last thing a gesture did
        self.load(project)

    # -- the song --------------------------------------------------------------

    def load(self, project):
        model.migrate(project)
        self.project = project
        self.track = project["tracks"][0]
        self.form = Form(project)
        mix = self.track.get("mix")
        if not isinstance(mix, dict):
            mix = self.track["mix"] = {}
        for k, v in MIX.items():
            mix.setdefault(k, v)
        self.transport = {"playing": False, "anchor_frame": 0, "anchor_tick": 0.0}
        self.sequenced_to = None
        self._tempo = project.get("tempo", 120.0)
        self.ramp = None          # (from tick, to tick, to tempo): the outro slowing, once it's planned
        self.changes += 1

    def set_kit(self, kit):
        self.kit = kit

    def reform(self):
        """The song's parts or a pattern's length changed: plan with the new
        ones from here on, keeping what plays and what is queued."""
        old = self.form
        new = Form(self.project)
        new.plan = old.plan
        new.before = old.before
        self.form = new
        self._place()
        self.changes += 1

    # -- time -------------------------------------------------------------------

    def ticks_per_frame(self):
        return self.project["tempo"] * model.PPQ / (60.0 * self.rate)

    def tempo_at(self, tick):
        """The tempo at ``tick``: the song's, or on the way to the outro's
        end tempo across the outro (`ramp`)."""
        base = self.project["tempo"]
        r = self.ramp
        if r is None or tick <= r[0]:
            return base
        if tick >= r[1]:
            return r[2]
        return base + (r[2] - base) * (tick - r[0]) / (r[1] - r[0])

    def _seconds(self, tick):
        """Seconds from tick 0 to ``tick`` at the song's tempo, slowing
        across the ramp: the tempo changes evenly with the ticks there, so
        the time is a logarithm."""
        per = 60.0 / model.PPQ
        base = self.project["tempo"]
        r = self.ramp
        if r is None or tick <= r[0]:
            return tick * per / base
        t0, t1, end = r
        span = min(tick, t1) - t0
        if end == base:
            inside = span * per / base
        else:
            inside = per * (t1 - t0) / (end - base) * math.log((base + (end - base) * span / (t1 - t0)) / base)
        after = (tick - t1) * per / end if tick > t1 else 0.0
        return t0 * per / base + inside + after

    def _tick(self, seconds):
        """The tick `_seconds` puts at ``seconds``."""
        per = 60.0 / model.PPQ
        base = self.project["tempo"]
        r = self.ramp
        if r is None or seconds <= r[0] * per / base:
            return seconds * base / per
        t0, t1, end = r
        s0 = t0 * per / base
        s1 = self._seconds(t1)
        if seconds >= s1:
            return t1 + (seconds - s1) * end / per
        if end == base:
            return t0 + (seconds - s0) * base / per
        bpm = base * math.exp((seconds - s0) * (end - base) / (per * (t1 - t0)))
        return t0 + (bpm - base) * (t1 - t0) / (end - base)

    def tick_at(self, frame):
        tr = self.transport
        if self.ramp is None:
            return tr["anchor_tick"] + (frame - tr["anchor_frame"]) * self.ticks_per_frame()
        return self._tick(self._seconds(tr["anchor_tick"]) + (frame - tr["anchor_frame"]) / float(self.rate))

    def frame_at(self, tick):
        tr = self.transport
        if self.ramp is None:
            return tr["anchor_frame"] + (tick - tr["anchor_tick"]) / self.ticks_per_frame()
        return tr["anchor_frame"] + (self._seconds(tick) - self._seconds(tr["anchor_tick"])) * self.rate

    def retempo(self):
        """Keep the playhead where it is when the tempo changes; the project
        already holds the new tempo."""
        if self.transport["playing"]:
            now = self.clock()
            tr = self.transport
            tick = tr["anchor_tick"] + (now - tr["anchor_frame"]) * self._tempo * model.PPQ / (60.0 * self.rate)
            tr["anchor_frame"] = now
            tr["anchor_tick"] = tick
        self._tempo = self.project["tempo"]

    def edge(self):
        """The first tick not yet handed to the kit: where a change can still land."""
        if not self.transport["playing"]:
            return 0.0
        frame = self.sequenced_to if self.sequenced_to is not None else self.clock()
        return max(0.0, self.tick_at(frame))

    # -- the pedals -------------------------------------------------------------

    def press(self, which, now=None):
        self._gestures(which, self.pedals[which].press(self.now_ms() if now is None else now))

    def release(self, which, now=None):
        self._gestures(which, self.pedals[which].release(self.now_ms() if now is None else now))

    def poll(self, now=None):
        now = self.now_ms() if now is None else now
        for i, p in enumerate(self.pedals):
            self._gestures(i, p.poll(now))

    def _gestures(self, which, gestures):
        for g in gestures:
            self.gesture(which, g)

    def gesture(self, which, gesture):
        """Act on one gesture of pedal ``which``; returns what it did."""
        playing = self.transport["playing"]
        did = self.form.gesture(which, gesture, self.edge())
        if did == "start" and not playing:
            self.play()
        elif did == "accent":
            self.accent()
        if did is not None:
            self.last = did
            self.changes += 1
            self._place()
        return did

    def accent(self):
        """The accent pattern (or a crash and a kick) over what plays, from now."""
        now = self.clock()
        idx = self.form.accent
        notes = ACCENT
        if idx is not None and 0 <= idx < len(self.track["patterns"]):
            notes = [(n[0], n[2], n[3]) for n in self.track["patterns"][idx]["notes"]]
        tpf = self.ticks_per_frame()
        for start, pitch, vel in notes:
            self.hits.append((now + int(start / tpf), pitch, vel))
        self.hits.sort()

    # -- the transport ----------------------------------------------------------

    def play(self, at_frame=None):
        """Start the clock from tick 0 at ``at_frame`` (now when None)."""
        if not self.form.playing:
            self.form.start(0)
        self.transport = {"playing": True, "anchor_frame": self.clock() if at_frame is None else at_frame,
                          "anchor_tick": 0.0}
        self.sequenced_to = None
        self._place()

    def stop(self):
        self.transport["playing"] = False
        self.form.stop()
        self.sequenced_to = None
        self._place()

    def _place(self):
        """The plan as the track's ``current`` and ``next``, for songmodel,
        and the outro's ramp once the plan holds the outro."""
        t = self.track
        plan = self.form.plan
        self._ramp()
        if not plan:
            t["current"], t["current_at"], t["next"] = self.form.mains[0], 0, None
            return
        first = plan[0]
        t["current"] = first[2]
        t["current_at"] = int(first[3])
        t["next"] = {"pattern": plan[1][2], "at": int(plan[1][3])} if len(plan) > 1 else None

    def _ramp(self):
        if not self.transport["playing"]:
            self.ramp = None
            return
        end = model.ramp_to(self.project, "outro")
        if end is None or end <= 0:
            self.ramp = None
            return
        for e in ([self.form.before] if self.form.before else []) + self.form.plan:
            if e[0] == "outro":
                self.ramp = (e[3], e[3] + self.form.length(e[2]), end)
                return
        self.ramp = None

    # -- what plays -------------------------------------------------------------

    def sequence(self):
        """Hand the kit every note due by now plus the lookahead. One pass."""
        now = self.clock()
        until = now + self.lookahead + 1
        ons = []
        if self.hits:
            while self.hits and self.hits[0][0] < until:
                ons.append(self.hits.pop(0))
        if self.transport["playing"]:
            start = now if self.sequenced_to is None else max(self.sequenced_to, now - self.rate // 4)
            if until > start:
                ons.extend(self._schedule(start, until))
                self.sequenced_to = until
        if ons and self.kit is not None:
            kit = self.kit
            mix = self.track["mix"]
            for frame, pitch, vel in ons:
                vel = vel * mix.get(GROUP_OF.get(pitch, OTHER), 100) // 100
                if vel > 0:
                    kit.note_on(pitch, min(127, vel), max(0, frame - now))
            if self.record:
                self.played.extend(ons)

    def _schedule(self, f0, f1):
        """The notes whose frame falls in [f0, f1), moving the plan on as it goes."""
        t0, t1 = self.tick_at(f0), self.tick_at(f1)
        if t1 <= 0:
            return []
        t0 = max(t0, 0.0)
        found = []
        while t0 < t1:
            entry = self.form.advance(t0)
            self._place()
            if entry is None or entry[0] == "end":
                self.transport["playing"] = False
                self.form.stop()
                self._place()
                self.changes += 1
                break
            nxt = self.form.following(t0)
            stop = t1 if nxt is None else min(t1, nxt[3])
            found.extend(self._notes(t0, stop))
            if nxt is not None and stop >= nxt[3]:
                self.changes += 1
            t0 = stop
        return found

    def _notes(self, a, b):
        swing = self.project.get("swing", 0)
        found = []
        for s0, s1, base0, pats in model.segments(self.project, a, b):
            idx = pats.get(self.track["id"], -1)
            start_at = base0
            if isinstance(idx, tuple):
                idx, start_at = idx
            if not 0 <= idx < len(self.track["patterns"]):
                continue
            pat = self.track["patterns"][idx]
            length = pat["bars"] * BAR
            k0 = int((s0 - start_at) // length)
            k1 = int((s1 - start_at) // length)
            for k in range(k0, k1 + 1):
                base = start_at + k * length
                for start, _dur, pitch, vel in pat["notes"]:
                    tick = base + model.swung(start, swing)
                    if s0 <= tick < s1:
                        found.append((int(self.frame_at(tick)), pitch, vel))
        found.sort()
        return found

    # -- what a screen shows ------------------------------------------------------

    def telemetry(self):
        """Where the song is, for every panel: bar and beat within the part,
        the part and the next one, the pedals, the tempo and the kit."""
        playing = self.transport["playing"]
        tick = self.tick_at(self.clock()) if playing else 0.0
        now = self.form.sounding(tick) if playing else None
        nxt = self.form.following(tick) if playing else None
        if now is not None and now[0] == "end":
            playing = False           # stopped; the next pass says so to the transport too
            now = nxt = None
        bar = beat = step = 0
        bars = 1
        into = 0.0
        steps, group = meter(self.project)
        if now is not None and now[2] >= 0:
            bars = self.form.bars[now[2]]
            into = max(0.0, tick - now[3]) % (bars * BAR)
            bar = int(into // BAR) + 1
            step = min(steps, int((into % BAR) * steps // BAR) + 1)
            beat = (step - 1) // group + 1
        return {
            "playing": playing,
            "song": self.project.get("name", ""),
            "tempo": self.tempo_at(tick) if playing else self.project.get("tempo", 120.0),
            "meter": self.project.get("meter", "4/4"),
            "kit": getattr(self.kit, "name", "") if self.kit is not None else "",
            "role": now[0] if now else "stopped",
            "part": label(now) if now else "Ready",
            "next": label(nxt) if nxt else "",
            "next_role": nxt[0] if nxt else "",
            "bar": bar,
            "bars": bars,
            "beat": beat,
            "beats": steps // group,
            "step": step,
            "steps": steps,
            "number": now[1] if now else None,
            "next_number": nxt[1] if nxt else None,
            "pattern": now[2] if now else -1,
            "at": int(into),
            "pedals": [p.state for p in self.pedals],
            "gesture": self.last or "",
            "changes": self.changes,
        }
