# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Read what the chat model sent back: what Huey says, and how he acts it out.

The model is asked for one JSON object, ``{"say": "...", "mood": "happy",
"colors": "sunset", "prop": "mug", "place": "coast", "variant": "winter"}``,
where everything but ``say`` is optional. `read` takes whatever came back.
A model that wrote plain words is taken at its word, and a mood, a colour,
a prop or a place that Huey doesn't have is left out and noted.
"""

import json

from .actor import COLORS, MOODS, PROPS, VARIANTS

#: The most of a reply that is spoken and shown, in characters.
SAY_MOST = 280

PROMPT = (
    "You are Huey, a small, warm, curious chameleon (he, him) who lives on a little screen on someone's desk. "
    "They talk to you out loud and hear your answer spoken. Answer the way a friend would across a desk: "
    "one or two short sentences of plain spoken words, with no lists, no markdown and no emoji.\n"
    'Reply with one JSON object and nothing else. It always has "say", the words you speak. '
    "You are a chameleon on a stage, so when it suits what you say, act it out with any of these keys:\n"
    '"mood": %s\n'
    '"colors", the colours you turn: %s\n'
    '"prop", something to hold up: %s\n'
    '"place", somewhere to go: %s\n'
    '"variant", the season at the coast (%s) or the time of day at the desk (%s)\n'
    "Use a key only to change something, and leave the rest out. For example, asked which season you like best:\n"
    '{"say": "Autumn, easily. Watch, I turn the colour of the leaves.", "mood": "happy", "place": "coast", "variant": "autumn"}\n'
    "and asked what two and two make:\n"
    '{"say": "Four. I counted on my toes."}\n'
    "Just now you are at the %s%s, and your colours are %s."
)


def prompt(place, variant, colors):
    """The system message: who Huey is, the reply's format, and where he is now."""
    return PROMPT % (
        ", ".join(MOODS),
        ", ".join(COLORS),
        ", ".join(PROPS),
        ", ".join(sorted(VARIANTS)),
        ", ".join(VARIANTS["coast"]),
        ", ".join(VARIANTS["desk"]),
        place,
        " (%s)" % variant if VARIANTS[place] else "",
        colors,
    )


class Act:
    """One reply: `say`, and the `mood`, `colors`, `prop`, `place` and `variant` it chose, each None when it chose none.

    `ignored` lists what the model asked for that Huey doesn't have, as
    ``(key, value)`` pairs.
    """

    def __init__(self, say):
        self.say = say
        self.mood = self.colors = self.prop = self.place = self.variant = None
        self.ignored = []

    def record(self):
        """The reply as the model should have written it, for the history it is shown."""
        # "say" first, as the model is asked to write it: a dict's order isn't kept everywhere
        out = ['"say": ' + json.dumps(self.say)]
        for key in ("mood", "colors", "prop", "place", "variant"):
            if getattr(self, key) is not None:
                out.append('"%s": %s' % (key, json.dumps(getattr(self, key))))
        return "{" + ", ".join(out) + "}"


def _object(text):
    """The JSON object in *text*, or None: alone, in a code fence, or among other words."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        found = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def _plain(text):
    """Words written for the eye made fit to say: no fences, stars or quotes round them."""
    text = text.replace("```json", " ").replace("```", " ").replace("**", "").replace("*", "")
    text = " ".join(text.split())
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    return text


def _clip(text):
    if len(text) <= SAY_MOST:
        return text
    cut = text[:SAY_MOST]
    for stop in (". ", "! ", "? "):
        at = cut.rfind(stop)
        if at > SAY_MOST // 3:
            return cut[: at + 1]
    return cut.rsplit(" ", 1)[0] + "..."


def words(say):
    """The words Huey speaks for the model's *say*: what `read` gives as an act's ``say``."""
    return _clip(_plain(say))


def early(text):
    """The words of a reply still arriving, once its ``say`` is complete, or None until then.

    This is the reply as `read` would take it if *text* is the JSON object
    it was asked for, so speech can be asked for before the rest arrives.
    """
    start = text.lstrip()
    if start.startswith("```"):
        start = start[3:].lstrip("json \t\r\n")
    at = text.find('"say"')
    if at < 0 or start[:1] != "{":
        return None
    at += 5
    while at < len(text) and text[at] in " \t\r\n:":
        at += 1
    if at >= len(text) or text[at] != '"':
        return None
    end = at + 1
    while True:
        end = text.find('"', end)
        if end < 0:
            return None
        back = end - 1
        while text[back] == "\\":
            back -= 1
        if (end - 1 - back) % 2 == 0:
            break  # not escaped
        end += 1
    try:
        say = json.loads(text[at : end + 1])
    except ValueError:
        return None
    return words(say) or None


def read(text, place):
    """Make an `Act` of the model's reply *text*, given the *place* Huey is in.

    Raises:
        ValueError: The reply has nothing to say.
    """
    found = _object(text)
    if found is None:
        say = _plain(text)
        if say.startswith("{"):
            # an object cut short: its words are still worth having
            at = say.find('"say"')
            say = say[at + 5 :].lstrip(' :"').split('"')[0] if at >= 0 else ""
        found = {}
    else:
        say = found.get("say")
        say = _plain(say) if isinstance(say, str) else ""
    if not say:
        raise ValueError("the reply had nothing to say")
    act = Act(words(say))

    def choose(key, allowed):
        value = found.get(key)
        if value is None or value == "" or value == "none":
            return None
        if isinstance(value, str) and value.lower() in allowed:
            return value.lower()
        act.ignored.append((key, value))
        return None

    act.mood = choose("mood", MOODS)
    act.colors = choose("colors", COLORS)
    act.prop = choose("prop", PROPS)
    act.place = choose("place", VARIANTS)
    act.variant = choose("variant", VARIANTS[act.place or place])
    return act
