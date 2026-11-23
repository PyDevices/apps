# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Asking Backline for a groove in words, against a stand-in server: a good
answer becomes a song, a bad one goes back once with what was wrong and
then fails saying so, a server that is off or refuses fails loudly, a
server that can't hold a reply to a schema is asked for plain JSON, and a
song that came back plays, is kept or is let go from any panel.

    python tests/backline_ask_contract.py [--plant=NAME] [--tmp FOLDER]
    micropython -X heapsize=64M tests/backline_ask_contract.py

No network: the stand-in answers the client's requests itself. The box's
checks need hmilink, audioinstruments and audiodsp on the path, and skip
without them. ``--plant=NAME`` breaks it one known way first (``PLANTS``),
and a check must then fail; ``tests/test_backline.py`` runs every plant.
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

import chatclient  # noqa: E402
from backline import ask  # noqa: E402
from backline import engine as eng  # noqa: E402
from songmodel import model  # noqa: E402

PLANTS = ("no-retry", "lax", "no-fallback", "no-borrow", "copy-told", "grid-shift", "lost-plan", "quiet-failure",
          "keep-nowhere", "whole-reply", "old-song-shown", "ble-refused", "lower-style", "form-bars")
NEEDS_BOX = ("quiet-failure", "keep-nowhere", "old-song-shown")
RESULTS = [0, 0]
SKIPS = []
RATE = 48000
KITS = ["rhythm808", "rhythm909", "rhythm606", "rhythm78", "electronic_drums5"]


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


def starters():
    found = []
    for name in sorted(os.listdir(songs_dir())):
        if name.endswith(".json"):
            with open(songs_dir() + "/" + name) as f:
                found.append((name[:-5], json.load(f)))
    return found


# -- the stand-in server ----------------------------------------------------------------


class Reply:
    def __init__(self, status, body):
        self.status = status
        self.headers = {"content-type": "application/json"}
        self._body = json.dumps(body).encode()

    def read_all(self, most):
        return self._body

    def close(self):
        pass


class Streamed:
    """The answer sent as a slow server sends it: server-sent events, a few characters each."""

    def __init__(self, text):
        self.status = 200
        self.headers = {"content-type": "text/event-stream"}
        events = [{"choices": [{"delta": {"role": "assistant", "content": ""}}]}]
        events += [{"choices": [{"delta": {"content": text[i:i + 7]}}]} for i in range(0, len(text), 7)]
        self._data = "".join("data: %s\n\n" % json.dumps(e) for e in events).encode() + b"data: [DONE]\n\n"
        self.reads = 0

    def read(self, most):
        piece, self._data = self._data[:most], self._data[most:]
        self.reads += 1
        return piece

    def read_all(self, most):
        piece, self._data = self._data, b""
        return piece

    def close(self):
        pass


class Server:
    """Answers ``chat/completions`` from a list of replies, keeping every request.

    Each reply is the model's text, or ``(status, message)`` for a refusal,
    or an exception to raise as the connection would.
    """

    def __init__(self, replies, refuse_formats=()):
        self.replies = list(replies)
        self.refuse_formats = refuse_formats
        self.requests = []

    def post(self, url, headers, pieces, timeout=30):
        body = json.loads(b"".join(bytes(p) for p in pieces).decode())
        self.requests.append((url, headers, body))
        kind = (body.get("response_format") or {}).get("type", "text")
        if kind in self.refuse_formats:
            return Reply(400, {"error": {"message": "response_format %s isn't supported" % kind}})
        if not self.replies:
            return Reply(500, {"error": {"message": "the stand-in has no more answers"}})
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, tuple):
            return Reply(r[0], {"error": {"message": r[1]}})
        if body.get("stream"):
            return Streamed(r)
        return Reply(200, {"choices": [{"message": {"role": "assistant", "content": r}}]})


def blues(**over):
    """A good answer: a 12-bar shuffle, 4 times through, the outro slowing."""
    spec = {
        "name": "Slow Twelve", "style": "blues", "tempo": 72, "meter": "4/4", "feel": "shuffle", "swing": 0,
        "kit": "rhythm808", "steps": 12,
        "form": [{"part": "intro", "bars": 1}, {"part": "main1", "bars": 12}, {"part": "outro", "bars": 2}],
        "patterns": {
            "intro": {"snare": "......xxXxxX", "kick": "X..........."},
            "main1": {"closed_hat": "x.ox.ox.ox.o", "snare": "...X.....X..", "kick": "X.....X..o..|X.....X....o"},
            "outro": {"closed_hat": "x.ox.ox.ox.o|............", "kick": "X.....X.....|X...........",
                      "crash": "............|X..........."},
        },
        "play": {"repeat": 4, "outro_tempo": 48},
    }
    spec.update(over)
    return spec


def asker(server, **settings):
    s = {"base_url": "http://stand-in/v1", "key_file": "", "chat_model": "song-model"}
    s.update(settings)
    return ask.Asker(s, KITS, starters(), server.post)


# -- plants ----------------------------------------------------------------------------------


def plant(name):
    if name is None:
        return
    print("PLANTED " + name)
    if name == "no-retry":
        ask.TRIES = 1
    elif name == "lax":
        ask.check = lambda spec, kits: []
    elif name == "no-fallback":
        chatclient.FORMATS = ("json_schema",)
    elif name == "no-borrow":
        ask.closest = lambda spec, songs: (None, None)
    elif name == "copy-told":
        old = ask.system_prompt
        ask.system_prompt = lambda kits: old(kits).replace("Never transcribe or reproduce", "Feel free to transcribe")
    elif name == "grid-shift":
        old = ask._pattern

        def pattern(bars, steps, drums):
            p = old(bars, steps, drums)
            for n in p["notes"]:
                n[0] += model.BAR // steps
            return p
        ask._pattern = pattern
    elif name == "lost-plan":
        old = ask.build

        def build(spec, songs, prompt=""):
            p, filled = old(spec, songs, prompt)
            p["repeat"] = 0
            p["tempo_map"] = []
            return p, filled
        ask.build = build
    elif name == "quiet-failure":
        from backline import box

        def asked(self, found, error):
            if error is None:
                old_asked(self, found, error)
        old_asked = box.Box._asked
        box.Box._asked = asked
    elif name == "keep-nowhere":
        from backline import box

        box.Box._save = lambda self, project: self.user_songs + "/nothing.json"
    elif name == "old-song-shown":
        from backline import box

        old_tele = box.Box.telemetry

        def telemetry(self):
            t = old_tele(self)
            t["song_index"] = self.song_index
            return t
        box.Box.telemetry = telemetry
    elif name == "lower-style":
        old_facts = ask.facts_text
        # the style left as the model wrote it, not starting with a capital
        ask.facts_text = lambda p, dot="-": old_facts(p, dot).replace(p["style"][:1].upper(), p["style"][:1], 1)
    elif name == "form-bars":
        old_build = ask.build

        def build(spec, songs, prompt=""):
            p, filled = old_build(spec, songs, prompt)
            p["form"] = [[e["part"], int(e["bars"])] for e in spec["form"]]
            return p, filled
        ask.build = build
    elif name == "ble-refused":
        ask.OTHERS = ()
    elif name == "whole-reply":
        old_json = chatclient.Client.chat_json

        def chat_json(self, messages, model, schema=None, name="answer", stream=False, **fields):
            return old_json(self, messages, model, schema, name, **fields)
        chatclient.Client.chat_json = chat_json
    else:
        raise SystemExit("no such plant: %r" % name)


# -- the checks ------------------------------------------------------------------------------


def check_spec():
    good = blues()
    check("a good spec has nothing wrong with it", ask.check(good, KITS) == [], repr(ask.check(good, KITS)))
    bad = blues(tempo=300, kit="cowbell_kit", steps=16)
    bad["patterns"] = {"main1": {"kick": "X..", "bongo": "x" * 12}}
    found = ask.check(bad, KITS)
    said = " | ".join(found)
    check("a bad spec is told every way it's wrong",
          "tempo" in said and "kit" in said and "steps should be 12" in said and "patterns.main1.kick" in said
          and "bongo isn't a drum" in said, said)
    check("a key the spec doesn't have is wrong too", ask.check(blues(lyrics="no"), KITS) != [])
    rule = ask.system_prompt(KITS)
    check("the model is told a named song is a style to borrow, never a drum part to copy",
          "take only its style, tempo and feel" in rule and "Never transcribe or reproduce" in rule)
    check("the fenced answer a chat model likes to give is read", ask.parse("```json\n{\"a\": 1}\n```") == {"a": 1})


def check_settings(tmp):
    path = tmp + "/backline-settings.json"
    with open(path, "w") as f:
        json.dump({"ble": "Backline", "base_url": "http://stand-in/v1", "key_file": ""}, f)
    try:
        found = ask.load_settings(path)
    except ValueError as e:
        found = {"refused": str(e)}
    os.remove(path)
    check("settings.json naming the box's Bluetooth name still gives the chat server",
          found.get("base_url") == "http://stand-in/v1" and found.get("key_file") == "" and "ble" not in found,
          repr(found))
    with open(path, "w") as f:
        json.dump({"base_url": "http://stand-in/v1", "chat_modle": "m"}, f)
    try:
        ask.load_settings(path)
        refused = ""
    except ValueError as e:
        refused = str(e)
    os.remove(path)
    check("a misspelt setting is still refused, naming it", "chat_modle" in refused, repr(refused))


def check_build():
    p, filled = ask.build(blues(), starters(), "a slow blues")
    pats = p["tracks"][0]["patterns"]
    parts = p["parts"]
    main = pats[parts["mains"][0]]
    step = model.BAR // 12
    kicks = sorted(n[0] for n in main["notes"] if n[2] == 36)
    want = []
    for bar in range(12):
        base = bar * model.BAR
        want += [base, base + 6 * step] + ([base + 9 * step] if bar % 2 == 0 else [base + 11 * step])
    check("the main's grid becomes notes on the steps it names, its two bars repeated through twelve",
          main["bars"] == 12 and kicks == sorted(want), "%r" % kicks[:8])
    check("the spec's play plan is the song's repeat count and the outro's tempo",
          p["repeat"] == 4 and model.ramp_to(p, "outro") == 48.0, "%r %r" % (p["repeat"], p["tempo_map"]))
    check("the fill the spec left out comes from the closest starter, the shuffle",
          parts.get("fills") and any(f.startswith("fill1 from Blues Shuffle") for f in filled), repr(filled))
    check("so every gesture has a part: an intro, a fill, an outro and an accent",
          all(k in parts for k in ("intro", "outro", "accent")) and len(parts["fills"]) == 1, repr(parts))
    view = ask.preview(p, filled)
    check("the preview shows the form the spec gave, in its order",
          [b["short"] for b in view["blocks"]] == ["INTRO", "MAIN 1", "OUTRO"] and view["blocks"][1]["bars"] == 12,
          repr(view["blocks"]))
    check("and says the plan in words", ask.plan_text(view) == "4 times through, the outro slowing to 48",
          ask.plan_text(view))
    view["kit_name"] = "Rhythm 808"
    check("and the song in a line, on every interpreter",
          ask.facts_text(view) == "Blues  - 72 BPM  - 4/4  - shuffle  - Rhythm 808", ask.facts_text(view))

    long_intro = blues()
    long_intro["form"][0]["bars"] = 4
    del long_intro["patterns"]["intro"]
    lp, _filled = ask.build(long_intro, starters(), "")
    shown = dict((b["short"], b["bars"]) for b in ask.preview(lp)["blocks"])
    plays = lp["tracks"][0]["patterns"][lp["parts"]["intro"]]["bars"]
    check("an intro the form names but the spec doesn't write shows the bars it plays",
          plays != 4 and shown.get("INTRO") == plays, "shown %r, plays %r" % (shown.get("INTRO"), plays))

    two = blues()
    two["form"] = two["form"][:2] + [{"part": "main2", "bars": 12}] + two["form"][2:]
    check("a main 2 the form names but the spec doesn't write is no error", ask.check(two, KITS) == [],
          repr(ask.check(two, KITS)))
    q, filled2 = ask.build(two, starters(), "a slow blues")
    pats2, parts2 = q["tracks"][0]["patterns"], q["parts"]
    first, second = pats2[parts2["mains"][0]], pats2[parts2["mains"][1]] if len(parts2["mains"]) > 1 else None
    check("it plays main 1's groove, and the sheet says so",
          second is not None and second["notes"] == first["notes"] and "main2 from main1" in filled2,
          "%r %r" % (parts2, filled2))
    return p


def check_asking():
    server = Server([json.dumps(blues())])
    a = asker(server)
    project, view = a.ask("Let's play a slow 12-bar blues groove at 72, 4 times through, slowing in the outro")
    url, headers, body = server.requests[0]
    check("a good answer is a song at once", len(server.requests) == 1 and view["tries"] == 1 and project["tempo"] == 72)
    check("the request goes to chat/completions with the model, the rules and the schema",
          url == "http://stand-in/v1/chat/completions" and body["model"] == "song-model"
          and body["messages"][0]["role"] == "system" and body["response_format"]["type"] == "json_schema"
          and "Authorization" not in headers, json.dumps(body)[:200])
    check("the answer is read as it streams in, so a slow model only has to keep talking, not finish in time",
          body.get("stream") is True, json.dumps(body)[:200])

    # A bad answer goes back once with what was wrong.
    server = Server([json.dumps(blues(tempo=300)), json.dumps(blues())])
    a = asker(server)
    try:
        project, view = a.ask("a slow blues")
        got = view["tries"]
    except ask.AskError as e:
        got = str(e)
    last = server.requests[-1][2]["messages"][-1]["content"] if server.requests else ""
    check("a bad answer is sent back once with what was wrong, and the second is used",
          got == 2 and len(server.requests) == 2 and "tempo should be a number from 40 to 240" in last,
          "%r, %d requests, %r" % (got, len(server.requests), last[:120]))

    server = Server([json.dumps(blues(tempo=300)), "not json at all"])
    a = asker(server)
    try:
        a.ask("a slow blues")
        said = None
    except ask.AskError as e:
        said = str(e)
    check("two bad answers fail, saying what was wrong with the last",
          said is not None and "isn't JSON" in said and len(server.requests) == 2, repr(said))
    check("and every try is kept for whoever wants to see it", len(a.log) == 2 and a.log[0]["errors"])

    # A server that can't hold a reply to a schema is asked for any JSON object.
    server = Server([json.dumps(blues()), json.dumps(blues())], refuse_formats=("json_schema",))
    a = asker(server)
    try:
        a.ask("a slow blues")
        a.ask("a slow blues")
        kinds = [(r[2].get("response_format") or {}).get("type") for r in server.requests]
    except Exception as e:  # noqa: BLE001 - whatever it is, the check says so
        kinds = repr(e)
    check("a server that refuses a schema is asked for JSON, and only that from then on",
          kinds == ["json_schema", "json_object", "json_object"] and a.client.json_format == "json_object", repr(kinds))

    for what, server, want in (
            ("off", Server([OSError("connection refused")]), "can't reach"),
            ("refusing", Server([(401, "Incorrect API key provided.")]), "401"),
            ("out of answers", Server([]), "500")):
        try:
            asker(server).ask("a slow blues")
            said = None
        except ask.AskError as e:
            said = str(e)
        check("a server that is %s fails loudly, saying why" % what, said is not None and want in said, repr(said))
    try:
        asker(Server([]), base_url="").ask("a slow blues")
        said = None
    except ask.AskError as e:
        said = str(e)
    check("no server set up says where to set one", said is not None and "base_url" in said, repr(said))


class FakeKit:
    name = "fake"
    spec = "fake"
    timed = False

    def note_on(self, pitch, velocity, delay=0):
        pass


def check_plays(project):
    """The made song plays itself 4 times through and slows across the outro."""
    frames = [0]
    e = eng.Engine(json.loads(json.dumps(project)), FakeKit(), lambda: frames[0], RATE,
                   now_ms=lambda: frames[0] * 1000 // RATE)
    e.record = True
    e.gesture(0, "tap")
    parts = []
    while e.transport["playing"] and frames[0] < RATE * 400:
        e.sequence()
        name = e.telemetry()["part"] if e.transport["playing"] else None
        if not parts or parts[-1][1] != name:
            parts.append((frames[0], name))
        frames[0] += 256
    names = [p[1] for p in parts]
    spb = RATE * 60.0 / 72
    outro_at = [p[0] for p in parts if p[1] == "Outro"]
    check("the song asked for plays the intro, its 12 bars 4 times and the outro, then stops",
          names == ["Intro", "Main 1", "Outro", None] and outro_at
          and abs(outro_at[0] - (1 + 48) * 4 * spb) < 512, "%r" % names)
    hats = [n[0] for n in e.played if n[1] == 42 and n[2] == ask.VELOCITY["x"]]   # one a beat
    before = [b - a for a, b in zip(hats, hats[1:]) if outro_at and b <= outro_at[0]]
    inside = [b - a for a, b in zip(hats, hats[1:]) if outro_at and a >= outro_at[0]]
    check("and its outro slows smoothly", inside and before and all(b > a for a, b in zip(inside, inside[1:]))
          and inside[-1] > 1.08 * before[-1], "%r" % inside)


def check_box(tmp):
    try:
        import hmilink  # noqa: F401
        from backline import box as boxmod
        from backline import kits

        kits.open_kit(kits.MACHINES[0], RATE).close()
    except Exception as e:  # noqa: BLE001 - a missing piece skips, saying which
        for name in NEEDS_BOX:
            skip("the box (%s)" % name, "%s" % (e,))
        return
    folder = tmp + "/backline-kept"
    for name in (os.listdir(folder) if _exists(folder) else []):
        os.remove(folder + "/" + name)
    server = Server([json.dumps(blues()), (500, "the model fell over")])
    frames = [0]
    b = boxmod.Box(lambda: frames[0], song="rock", ask_settings={"base_url": "http://stand-in/v1", "key_file": "",
                                                                    "chat_model": "song-model"},
                   user_songs=folder, post=server.post)
    heard = []
    b.device.event = lambda name, **data: heard.append((name, data))
    before = len(b.songs)
    b.command("ask", {"text": "a slow 12-bar blues at 72, 4 times through, slowing in the outro"})
    t = b.telemetry()
    check("a panel's ask comes back as a song every panel hears",
          t["ask"] == "ready" and heard and heard[-1][0] == "proposal" and heard[-1][1]["preview"]["name"] == "Slow Twelve"
          and b.model.describe()["proposal"]["tempo"] == 72, "%r %r" % (t["ask"], heard[-1:]))
    b.command("proposal", {"do": "play"})
    check("Play starts the song that came back", b.engine.transport["playing"] and b.model.doc["name"] == "Slow Twelve"
          and b.engine.form.repeat == 4)
    check("while it plays, no song in the list is shown as the one playing",
          b.telemetry()["song_index"] == -1 and b.telemetry()["song"] == "Slow Twelve", repr(b.telemetry()["song_index"]))
    b.command("proposal", {"do": "keep"})
    kept = [n for n in os.listdir(folder)] if _exists(folder) else []
    check("Keep saves it among the songs, and it is the song chosen",
          len(b.songs) == before + 1 and b.song_index == before and b.telemetry()["song_index"] == before
          and kept == ["slow_twelve.json"]
          and b.proposal is None, "%r %r" % (kept, b.songs[-1:]))
    b.command("ask", {"text": "something else"})
    t = b.telemetry()
    check("a server that fails is said on every panel",
          t["ask"] == "failed" and "fell over" in t["ask_error"] and heard[-1][1].get("error"), repr(t["ask_error"]))
    b.engine.stop()
    b.command("song", {"index": 0})
    first = b.model.doc["name"]
    b.ask_state = ""
    server.replies = [json.dumps(blues(name="Another One"))]
    b.command("ask", {"text": "a slow blues"})
    b.command("proposal", {"do": "play"})
    b.command("proposal", {"do": "discard"})
    check("Discard lets it go and brings back the song from before",
          b.model.doc["name"] == first and b.song_index == 0 and b.proposal is None and not b.engine.transport["playing"])
    b.close()


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def main():
    p, tmp = args()
    plant(p)
    check_spec()
    check_settings(tmp)
    project = check_build()
    check_asking()
    check_plays(project)
    check_box(tmp)
    print("on %s" % sys.implementation.name)
    print("%d passed, %d failed, %d skipped" % (RESULTS[0], RESULTS[1], len(SKIPS)))
    if RESULTS[1]:
        sys.exit(1)


main()
