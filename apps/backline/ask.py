# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Ask for a groove in words: a chat model writes a song spec, and Backline turns it into a song.

"A slow 12-bar blues groove at 72, 4 times through, slowing in the outro"
goes to any OpenAI-compatible ``chat/completions`` server (`chatclient`),
which must answer with a song spec: one JSON object, never code. `SCHEMA`
says what it holds, and `check` holds the answer to it strictly. An answer
that doesn't fit is sent back once with what was wrong; a second one that
doesn't fit fails with what was wrong, and so does a server that is off or
refuses. A song named in the prompt is a style, a tempo and a feel to
borrow, never a drum part to copy, and the model is told so.

`build` makes the songmodel project from a spec: the parts the spec writes
as step grids, the parts it leaves out (fills, the outro, an accent) taken
from the starter song closest in style, and the play plan as the song's
``repeat`` and ``tempo_map``. `preview` is what a screen shows before
anyone hears it.

The settings are the server's address, a key file and the model, in
``settings.json`` in the app's data folder (`load_settings`): the same
three Huey takes, so one lite-assistant or DeepInfra account serves both.

Imports on CPython and MicroPython with chatclient and songmodel; the
calls block, so the box makes them from a worker.
"""

import json

import chatclient
from songmodel import model

#: Every setting and its value when ``settings.json`` doesn't give one.
DEFAULTS = {
    # an OpenAI-compatible server: the address its /chat/completions is
    # under; "" until it is set, since only you know where your server runs
    "base_url": "",
    # a file holding the API key on one line; "" for a server that asks for none
    "key_file": "/lite-assistant.key",
    # the model that writes the song
    "chat_model": "gemma-4-E2B-it",
}

#: The parts a spec can write, in the order a song's patterns hold them.
PARTS = ("intro", "main1", "main2", "fill1", "fill2", "transition", "outro")
#: A spec's drum names and their General MIDI notes.
VOICES = (
    ("kick", 36), ("snare", 38), ("rim", 37), ("clap", 39), ("closed_hat", 42), ("pedal_hat", 44),
    ("open_hat", 46), ("crash", 49), ("ride", 51), ("ride_bell", 53), ("low_tom", 45), ("mid_tom", 47),
    ("high_tom", 48), ("floor_tom", 41), ("cowbell", 56), ("tambourine", 54),
)
NOTE = dict(VOICES)
#: What each step character plays at; "." is a rest, and "|" and spaces are only for reading.
VELOCITY = {"X": 118, "x": 96, "o": 70, "g": 42}
METERS = ("4/4", "12/8")
FEELS = ("straight", "swing", "shuffle")
#: What a kit sounds like, for the model choosing one.
KIT_NOTES = {
    "rhythm808": "deep electronic kit: hip hop, soul, slow jams",
    "rhythm909": "punchy electronic kit: rock, house, dance",
    "rhythm606": "light, bright electronic kit: country, latin, synth pop",
    "rhythm78": "vintage preset rhythm box: bossa, lounge, ballads",
    "electronic_drums5": "80s electronic kit with big toms: pop, new wave",
    "soundfont": "acoustic drum kit: blues, jazz, rock, anything played live",
}
TRIES = 2            # the first answer, and one more with what was wrong with it
#: How much of a bad answer goes back with what was wrong with it.
ECHO_MOST = 1500
MAX_TOKENS = 3000
#: Seconds the server may take to answer: a small model on a computer with no GPU writes a song in minutes.
TIMEOUT = 600


class AskError(Exception):
    """Asking for a song failed: the server, the key or the answer, and why."""


def load_settings(path):
    """The settings: `DEFAULTS`, with what the JSON file at *path* gives over them.

    Raises:
        ValueError: The file isn't a JSON object, or names a setting there
            isn't, or gives one that isn't text.
    """
    settings = dict(DEFAULTS)
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return settings
    try:
        given = json.loads(text)
    except ValueError:
        raise ValueError("%s isn't JSON" % path)
    if not isinstance(given, dict):
        raise ValueError("%s isn't a JSON object" % path)
    for name in given:
        if name not in DEFAULTS:
            raise ValueError("%s has no setting %r" % (path, name))
        if not isinstance(given[name], str):
            raise ValueError("%s: %r should be text" % (path, name))
        settings[name] = given[name]
    return settings


# -- the spec ----------------------------------------------------------------------


def _bars(steps):
    """A regular expression for one to four bars of *steps* steps, with "|" between them."""
    bar = "[Xxog.]{%d}" % steps
    return "%s(\\|%s){0,3}" % (bar, bar)


def schema(kits):
    """The JSON Schema a song spec follows, with *kits* the kit names to choose from.

    It is one of two shapes, a song of 12 steps a bar and a song of 16, so
    a server that holds the model to it holds every grid to the song's
    bar: one to four whole bars, which a small model can then neither
    miscount nor write forever.
    """
    return {"anyOf": [_song_schema(kits, 16), _song_schema(kits, 12)]}


def _song_schema(kits, steps):
    grid = {"type": "string", "pattern": "^%s$" % _bars(steps)}
    voices = {"type": "object", "properties": dict((name, grid) for name, _n in VOICES), "additionalProperties": False}
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "style": {"type": "string"},
            "tempo": {"type": "number", "minimum": 40, "maximum": 240},
            "meter": {"type": "string", "enum": list(METERS)},
            "feel": {"type": "string", "enum": list(FEELS)},
            "swing": {"type": "integer", "minimum": 0, "maximum": 60},
            "kit": {"type": "string", "enum": list(kits)},
            "steps": {"type": "integer", "enum": [steps]},
            "form": {"type": "array", "items": {
                "type": "object",
                "properties": {"part": {"type": "string", "enum": list(PARTS)},
                               "bars": {"type": "integer", "minimum": 1, "maximum": 16}},
                "required": ["part", "bars"], "additionalProperties": False}},
            "patterns": {"type": "object", "properties": dict((p, voices) for p in PARTS), "additionalProperties": False},
            "play": {"type": "object",
                     "properties": {"repeat": {"type": "integer", "minimum": 0, "maximum": 16},
                                    "outro_tempo": {"type": "number", "minimum": 0, "maximum": 240}},
                     "required": ["repeat", "outro_tempo"], "additionalProperties": False},
        },
        "required": ["name", "style", "tempo", "meter", "feel", "swing", "kit", "steps", "form", "patterns", "play"],
        "additionalProperties": False,
    }


EXAMPLE = {
    "name": "Straight Rock", "style": "rock", "tempo": 118, "meter": "4/4", "feel": "straight", "swing": 0,
    "kit": "rhythm909", "steps": 16,
    "form": [{"part": "intro", "bars": 1}, {"part": "main1", "bars": 8}, {"part": "fill1", "bars": 1},
             {"part": "outro", "bars": 2}],
    "patterns": {
        "intro": {"closed_hat": "x...x...x...x...", "snare": "........xxXXxxXX", "kick": "X..............."},
        "main1": {"closed_hat": "x.x.x.x.x.x.x.x.", "snare": "....X.......X...",
                  "kick": "X.......X.X.....|X.......X.X...x."},
        "fill1": {"snare": "x.x.x.x.XxXxXXXX", "kick": "X.......X......."},
        "outro": {"closed_hat": "x.x.x.x.x.x.x.x.|................", "snare": "....X.......XxXX|................",
                  "kick": "X.......X.X.....|X...............", "crash": "................|X..............."},
    },
    "play": {"repeat": 0, "outro_tempo": 0},
}


def system_prompt(kits):
    """What the model is told before the request: the spec, the rules and an example."""
    kit_lines = "\n".join("- %s: %s" % (k, KIT_NOTES.get(k, "a drum kit")) for k in kits)
    return (
        "You write drum grooves for Backline, a drum machine played with a footswitch. "
        "Answer with one JSON object and nothing else: no prose, no code fences, never code.\n\n"
        "The object has these keys, all required:\n"
        "- name: a short title of your own for the groove.\n"
        "- style: the style in a word or two (blues, rock, funk, bossa...).\n"
        "- tempo: beats per minute, 40 to 240. Use the tempo the person asks for exactly.\n"
        "- meter: \"4/4\", or \"12/8\" for a slow triplet ballad.\n"
        "- feel: \"straight\", \"swing\" (swung sixteenths) or \"shuffle\" (triplet feel).\n"
        "- swing: 0 to 60, how late the swung sixteenths are; 0 unless feel is swing.\n"
        "- kit: one of the kits below.\n"
        "- steps: steps in a bar: 12 for a shuffle or 12/8, else 16.\n"
        "- form: the parts in the order they play, each {\"part\": name, \"bars\": n}. Parts: intro, main1, "
        "main2, fill1, fill2, transition, outro. main1 is required. A 12-bar blues has main1 of 12 bars. "
        "fill1 is the fill played in main1, fill2 in main2, transition goes into main2.\n"
        "- patterns: for each part in form, its drums, each a step grid string: one character a step, "
        "X accent, x hit, o soft, g ghost note, . rest. A grid is one bar of exactly steps characters, or two "
        "to four such bars with \"|\" between them, and repeats to fill the part. Drums: %s.\n"
        "- play: {\"repeat\": n, \"outro_tempo\": bpm}. repeat is how many times the song goes through its "
        "main parts before the outro, and 0 loops until the player stops it: \"loop continuously\" is 0, "
        "\"4 times through\" is 4, and when the person doesn't say how many times, 0. outro_tempo is the "
        "tempo the outro slows to by its end: about two thirds of the tempo when the person asks for the end "
        "to slow, and 0, keeping the tempo, when they don't.\n\n"
        "Kits:\n%s\n\n"
        "When the person names a song or an artist, take only its style, tempo and feel, and write an original "
        "groove in that style. Never transcribe or reproduce the drum part of a real recording.\n\n"
        "An example answer:\n%s"
    ) % (", ".join(n for n, _p in VOICES), kit_lines, json.dumps(EXAMPLE, separators=(",", ":")))


def _grid(text):
    return text.replace("|", "").replace(" ", "")


def check(spec, kits):
    """What is wrong with *spec* as a song spec, as a list of sentences; empty when it fits.

    Args:
        spec: The parsed answer.
        kits (list): The kit names it may choose from.
    """
    errors = []
    if not isinstance(spec, dict):
        return ["the answer isn't a JSON object"]
    need = _song_schema(kits, 16)["required"]
    for key in need:
        if key not in spec:
            errors.append("%s is missing" % key)
    for key in spec:
        if key not in need:
            errors.append("%s isn't a key a song has" % key)
    if errors:
        return errors

    def text(key):
        v = spec[key]
        if not isinstance(v, str) or not v.strip() or len(v) > 60:
            errors.append("%s should be text of 1 to 60 characters" % key)

    def number(where, v, lo, hi, whole=False):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or (whole and v != int(v)) or not lo <= v <= hi:
            errors.append("%s should be %s from %d to %d, not %r" % (where, "a whole number" if whole else "a number",
                                                                     lo, hi, v))
            return False
        return True

    def one_of(key, choices):
        if spec[key] not in choices:
            errors.append("%s should be one of %s, not %r" % (key, ", ".join(str(c) for c in choices), spec[key]))
            return False
        return True

    text("name")
    text("style")
    number("tempo", spec["tempo"], 40, 240)
    meter_ok = one_of("meter", METERS)
    feel_ok = one_of("feel", FEELS)
    number("swing", spec["swing"], 0, 60, True)
    one_of("kit", kits)
    steps_ok = one_of("steps", (12, 16))
    if meter_ok and feel_ok and steps_ok:
        want = 12 if spec["meter"] == "12/8" or spec["feel"] == "shuffle" else 16
        if spec["steps"] != want:
            errors.append("steps should be %d for %s %s" % (want, spec["meter"], spec["feel"]))
    steps = spec["steps"] if steps_ok else 16

    bars = {}
    form = spec["form"]
    if not isinstance(form, list) or not form:
        errors.append("form should be a list of parts")
        form = []
    for i, entry in enumerate(form):
        where = "form[%d]" % i
        if not isinstance(entry, dict) or sorted(entry) != ["bars", "part"]:
            errors.append("%s should be {\"part\": name, \"bars\": n}" % where)
            continue
        if entry["part"] not in PARTS:
            errors.append("%s: part should be one of %s, not %r" % (where, ", ".join(PARTS), entry["part"]))
            continue
        if entry["part"] in bars:
            errors.append("%s: %s is in form twice" % (where, entry["part"]))
            continue
        if number(where + ".bars", entry["bars"], 1, 16, True):
            bars[entry["part"]] = int(entry["bars"])
    if form and "main1" not in bars:
        errors.append("form needs main1")
    if "fill2" in bars and "main2" not in bars:
        errors.append("form has fill2 but no main2")

    pats = spec["patterns"]
    if not isinstance(pats, dict):
        errors.append("patterns should be an object of parts")
        pats = {}
    for part in pats:
        if part not in PARTS:
            errors.append("patterns.%s isn't a part" % part)
            continue
        if part not in bars:
            errors.append("patterns.%s: %s isn't in form" % (part, part))
            continue
        drums = pats[part]
        if not isinstance(drums, dict) or not drums:
            errors.append("patterns.%s should be an object of drums" % part)
            continue
        hits = bad = 0
        for voice in drums:
            where = "patterns.%s.%s" % (part, voice)
            if voice not in NOTE:
                errors.append("%s: %s isn't a drum (drums: %s)" % (where, voice, ", ".join(n for n, _p in VOICES)))
                bad += 1
                continue
            g = drums[voice]
            if not isinstance(g, str):
                errors.append("%s should be a step grid string" % where)
                bad += 1
                continue
            g = _grid(g)
            wrong = [c for c in g if c not in VELOCITY and c != "."]
            if wrong:
                errors.append("%s has %r, which isn't a step (X x o g .)" % (where, wrong[0]))
                bad += 1
                continue
            n = len(g) // steps if g and len(g) % steps == 0 else 0
            if not n or n > bars[part] or bars[part] % n:
                fits = [str(k * steps) for k in range(1, bars[part] + 1) if bars[part] % k == 0]
                errors.append("%s has %d steps; for %d bar%s of %d steps it should have %s" % (
                    where, len(g), bars[part], "" if bars[part] == 1 else "s", steps, " or ".join(fits)))
                bad += 1
                continue
            hits += len(g) - g.count(".")
        if not hits and not bad and part == "main1":
            errors.append("patterns.main1 plays nothing")
    if "main1" in bars and "main1" not in pats:
        errors.append("patterns needs main1, which form lists")

    play = spec["play"]
    if not isinstance(play, dict) or sorted(play) != ["outro_tempo", "repeat"]:
        errors.append("play should be {\"repeat\": n, \"outro_tempo\": bpm}")
    else:
        number("play.repeat", play["repeat"], 0, 16, True)
        if number("play.outro_tempo", play["outro_tempo"], 0, 240) and 0 < play["outro_tempo"] < 30:
            errors.append("play.outro_tempo should be 0 or 30 to 240, not %r" % play["outro_tempo"])
    return errors


def parse(text):
    """The answer's JSON object: code fences around it are let go, nothing else.

    Raises:
        ValueError: It isn't JSON.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return json.loads(text)


# -- the song ----------------------------------------------------------------------


def _pattern(bars, steps, drums):
    step = model.BAR // steps
    notes = []
    for voice in drums:
        g = _grid(drums[voice])
        for k in range(bars * steps // len(g)):
            base = k * len(g)
            for i in range(len(g)):
                c = g[i]
                if c in VELOCITY:
                    notes.append([(base + i) * step, step, NOTE[voice], VELOCITY[c]])
    notes.sort()
    return {"bars": bars, "notes": notes}


def _grid_of(project):
    """12 for a starter whose notes fall on triplet steps, else 16."""
    for p in project["tracks"][0]["patterns"]:
        for n in p["notes"]:
            if n[0] % (model.BAR // 16):
                return 12
    return 16


def closest(spec, starters):
    """The starter song most like *spec*: its meter, then its grid, then its style, then its tempo.

    Args:
        starters (list): ``[(name, project)]``.
    """
    steps = spec["steps"]
    style = spec["style"].lower()
    best = None
    for name, p in starters:
        theirs = (p.get("style") or "").lower()
        score = (
            p.get("meter", "4/4") == spec["meter"],
            _grid_of(p) == steps,
            bool(theirs) and (theirs in style or style in theirs),
            -abs(p.get("tempo", 120) - spec["tempo"]),
        )
        if best is None or score > best[0]:
            best = (score, name, p)
    return (best[1], best[2]) if best else (None, None)


def build(spec, starters, prompt=""):
    """The songmodel project for a checked *spec*, and what came from a starter song.

    The parts the spec writes become patterns. A main 2 the form names but
    the spec doesn't write plays main 1's groove. Fills, a transition into
    main 2, the outro and the accent hit, where the spec leaves them out,
    are the closest starter's (`closest`), so every pedal gesture has a
    part to play.

    Args:
        spec (dict): A spec `check` found nothing wrong with.
        starters (list): ``[(name, project)]``, the starter songs.
        prompt (str): What was asked, kept in the song.

    Returns:
        ``(project, filled)``: *filled* names each part taken from a starter.
    """
    steps = spec["steps"]
    bars = dict((e["part"], int(e["bars"])) for e in spec["form"])
    _name, donor = closest(spec, starters)
    donor_parts = (donor or {}).get("parts") or {}
    donor_pats = donor["tracks"][0]["patterns"] if donor else []
    title = (donor or {}).get("name", "")
    patterns = []
    where = {}
    filled = []

    def take(part, pattern):
        where[part] = len(patterns)
        patterns.append(pattern)

    def borrow(part, index):
        if index is None or not 0 <= index < len(donor_pats):
            return
        take(part, json.loads(json.dumps(donor_pats[index])))
        filled.append("%s from %s" % (part, title))

    def donor_index(part):
        if part == "outro":
            return donor_parts.get("outro")
        if part in ("fill1", "fill2"):
            fills = donor_parts.get("fills") or []
            i = 0 if part == "fill1" else 1
            return fills[i] if i < len(fills) else (fills[0] if fills else None)
        if part == "transition":
            t = donor_parts.get("transitions", donor_parts.get("transition"))
            return (t[0] if t else None) if isinstance(t, list) else t
        return None

    for part in PARTS:
        drums = spec["patterns"].get(part)
        if drums:
            take(part, _pattern(bars[part], steps, drums))
        elif part == "main2" and part in bars:
            # a second main the spec names but doesn't write plays the first's groove
            mine = spec["patterns"]["main1"]
            if all(bars[part] % max(1, len(g.replace("|", "").replace(" ", "")) // steps) == 0 for g in mine.values()):
                take(part, _pattern(bars[part], steps, mine))
            else:
                take(part, json.loads(json.dumps(patterns[where["main1"]])))
            filled.append("main2 from main1")
        elif part in ("fill1", "outro") or (part in ("fill2", "transition") and "main2" in bars):
            borrow(part, donor_index(part))
        elif part in bars and part == "intro":
            borrow(part, donor_parts.get("intro"))
    accent = donor_parts.get("accent")
    if accent is not None and 0 <= accent < len(donor_pats):
        where["accent"] = len(patterns)
        patterns.append(json.loads(json.dumps(donor_pats[accent])))

    p = model.new_project()
    p["name"] = spec["name"].strip()[:40]
    p["style"] = spec["style"].strip()[:40]
    p["tempo"] = float(spec["tempo"])
    p["meter"] = spec["meter"]
    p["swing"] = int(spec["swing"]) if spec["feel"] == "swing" else 0
    p["feel"] = spec["feel"]
    t = model.track("drums", spec["kit"], "Drums")
    t["id"] = 1
    t["patterns"] = patterns
    p["tracks"] = [t]
    parts = {"mains": [where[m] for m in ("main1", "main2") if m in where]}
    parts["fills"] = [where[f] for f in ("fill1", "fill2") if f in where][:len(parts["mains"])]
    if "transition" in where and len(parts["mains"]) > 1:
        parts["transitions"] = [where["transition"]]
    for role in ("intro", "outro", "accent"):
        if role in where:
            parts[role] = where[role]
    p["parts"] = parts
    p["repeat"] = int(spec["play"]["repeat"])
    end = spec["play"]["outro_tempo"]
    p["tempo_map"] = [{"part": "outro", "tempo": float(end)}] if end and "outro" in where else []
    p["prompt"] = prompt
    p["form"] = [[e["part"], int(e["bars"])] for e in spec["form"]]
    return p, filled


LABELS = {"intro": "Intro", "main1": "Main 1", "main2": "Main 2", "fill1": "Fill 1", "fill2": "Fill 2",
          "transition": "Transition", "outro": "Outro"}
SHORT = {"intro": "INTRO", "main1": "MAIN 1", "main2": "MAIN 2", "fill1": "FILL 1", "fill2": "FILL 2",
         "transition": "TRANS", "outro": "OUTRO"}
ROLE = {"intro": ("intro", None), "main1": ("main", 0), "main2": ("main", 1), "fill1": ("fill", 0),
        "fill2": ("fill", 1), "transition": ("transition", 1), "outro": ("outro", None)}


def preview(project, filled=(), tries=1, kit_name=None):
    """What a screen shows of a made song before it plays: small, plain data.

    ``blocks`` is the song's form as the desk's strip draws it, the parts in
    the order the spec gave, with the outro on the end where a starter gave it.
    """
    patterns = project["tracks"][0]["patterns"]
    parts = project["parts"]
    form = [list(e) for e in project.get("form") or []]
    if "outro" in parts and not any(e[0] == "outro" for e in form):
        form.append(["outro", patterns[parts["outro"]]["bars"]])
    index = {"intro": parts.get("intro"), "outro": parts.get("outro")}
    for i, m in enumerate(parts.get("mains") or []):
        index["main%d" % (i + 1)] = m
    for i, f in enumerate(parts.get("fills") or []):
        index["fill%d" % (i + 1)] = f
    if parts.get("transitions"):
        index["transition"] = parts["transitions"][0]
    blocks = []
    for part, bars in form:
        if index.get(part) is None:
            continue
        role, number = ROLE[part]
        blocks.append({"role": role, "number": number, "pattern": index[part], "bars": bars,
                       "label": LABELS[part], "short": SHORT[part]})
    end = model.ramp_to(project, "outro")
    return {
        "name": project.get("name", ""),
        "style": project.get("style", ""),
        "tempo": project["tempo"],
        "meter": project.get("meter", "4/4"),
        "swing": project.get("swing", 0),
        "feel": project.get("feel", "straight"),
        "kit": project["tracks"][0]["instrument"],
        "kit_name": kit_name or project["tracks"][0]["instrument"],
        "repeat": project.get("repeat", 0),
        "outro_tempo": end or 0,
        "blocks": blocks,
        "filled": list(filled),
        "tries": tries,
        "prompt": project.get("prompt", ""),
    }


def plan_text(p):
    """The play plan in words, from a `preview`: "4 times through, the outro slowing to 48"."""
    if p.get("repeat"):
        text = "once through" if p["repeat"] == 1 else "%d times through" % p["repeat"]
    else:
        text = "loops until you stop it"
    if p.get("outro_tempo"):
        text += ", the outro slowing to %d" % int(p["outro_tempo"] + 0.5)
    return text


# -- asking ------------------------------------------------------------------------


class Asker:
    """Asks the server in the settings for songs.

    Args:
        settings (dict): ``base_url``, ``key_file`` and ``chat_model``.
        kits (list): The kit names a song may choose.
        starters (list): ``[(name, project)]``, for the parts a spec leaves out.
        post: What sends a request; `chatclient.web.post` unless a test gives its own.
    """

    def __init__(self, settings, kits, starters, post=None):
        self.settings = settings
        self.kits = list(kits)
        self.starters = starters
        self.post = post
        self.client = None
        #: Every try of the last `ask`: ``{"text", "errors"}``, the answer and what was wrong with it.
        self.log = []

    def _client(self):
        base = self.settings["base_url"]
        if not base:
            raise AskError("no server to ask: set base_url in Backline's settings.json")
        try:
            key = chatclient.read_key(self.settings["key_file"])
        except OSError as e:
            raise AskError("no API key: %s (key_file in settings.json, or \"\" for a server that needs none)" % (e,))
        if self.client is None or self.client.base != base.rstrip("/"):
            self.client = chatclient.Client(base, key, self.post, timeout=TIMEOUT)
        else:
            self.client._key = key
        return self.client

    def ask(self, prompt):
        """A song for *prompt*: ``(project, preview)``. Blocks; call it from a worker.

        Raises:
            AskError: No server or key, the server is off or refused, or the
                answer didn't fit the spec twice, with what was wrong.
        """
        client = self._client()
        messages = [{"role": "system", "content": system_prompt(self.kits)}, {"role": "user", "content": prompt}]
        self.log = []
        errors = []
        for attempt in range(TRIES):
            try:
                text = client.chat_json(messages, self.settings["chat_model"], schema(self.kits), "song", stream=True,
                                        max_tokens=MAX_TOKENS, temperature=0.6)
            except chatclient.ServerError as e:
                raise AskError("the server refused: %s" % (e,))
            except OSError as e:
                raise AskError("can't reach %s: %s" % (self.settings["base_url"], e))
            try:
                spec = parse(text)
            except ValueError as e:
                spec = None
                errors = ["the answer isn't JSON (%s)" % (e,)]
            else:
                errors = check(spec, self.kits)
            self.log.append({"text": text, "errors": errors})
            if not errors:
                project, filled = build(spec, self.starters, prompt)
                return project, preview(project, filled, attempt + 1)
            messages = messages + [
                {"role": "assistant", "content": text[:ECHO_MOST]},
                {"role": "user", "content": "That answer can't be used: %s. Send the whole song again as one JSON "
                                            "object, with those fixed." % "; ".join(errors[:12])},
            ]
        raise AskError("the model's song didn't fit, twice: %s" % "; ".join(errors[:6]))
