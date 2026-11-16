# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Huey as someone to talk to: Perch's stage, with poses for a conversation.

`Actor` is Perch's `Stage` with four more things for the chameleon to do. He
turns to face you while he listens, his eyes wander while he thinks, his
mouth moves while he speaks, and then he settles back into the life he leads
in Perch. `perform` takes what a reply asked for: colours, a place, a season.
"""

import lvgl as lv

from ..perch import huey, huey_shift  # noqa: F401  (huey_shift adds the rest of the colours)
from ..perch.huey_props import ORDER as PROPS
from ..perch.stage import _BODY, _REACH, PLACES, Stage

MOODS = ("calm", "happy", "curious", "sleepy")
COLORS = ("leaf", "brand", "sunset", "board", "blossom", "snow", "night", "copper")
#: Each place a reply may ask for, and the seasons or times of day it has.
#: The workbench has none: there the colours are the only thing to change.
VARIANTS = {
    "coast": PLACES["coast"]["variants"],
    "bench": (),
    "desk": PLACES["desk"]["variants"],
}

_THINKS = (
    ((-0.4, -0.9), (0.8, -0.5), -8, 1.0),
    ((0.7, -0.8), (-0.6, -0.7), -10, 0.6),
)
_OPEN = (140, -110)  # inside his mouth: where the tongue rests while he speaks


class Actor(Stage):
    """Perch's stage, and the chameleon playing a part in a conversation.

    `listen`, `think`, `speak` and `settle` say what he is doing. While he
    speaks, set `mouth` to True and False as the sound rises and falls.
    """

    def __init__(self, root, size, place="desk", variant=None, view="wide", seed=7):
        #: "idle", "listen", "think", "speak" or "settle".
        self.part = "idle"
        #: True while his mouth is open, as he speaks.
        self.mouth = False
        self.mood = "calm"
        self.prop = None
        Stage.__init__(self, root, size, place, variant, view, seed)

    def shapes(self, doc, spec, scheme):
        kind = spec[0]
        if kind == "think":
            look, far, nod, curl = _THINKS[spec[1]]
            return huey.draw(doc, look=look, look_far=far, mood="curious", nod=nod, curl=curl, colors=scheme, perch=None), _REACH
        if kind == "talk":
            mood, is_open = spec[1], spec[2]
            if mood == "happy":
                return huey.draw(doc, look=(0.2, 0.0), mood="happy" if is_open else "calm", colors=scheme, perch=None), _BODY
            if is_open:
                eyes = "sleepy" if mood == "sleepy" else "calm"
                return huey.draw(doc, look=(0.2, 0.0), mood=eyes, tongue=1, target=_OPEN, colors=scheme, perch=None), _BODY
            return huey.draw(doc, look=(0.2, 0.0), mood=mood, colors=scheme, perch=None), _REACH
        return Stage.shapes(self, doc, spec, scheme)

    # -- the parts he plays ----------------------------------------------

    def _play(self, part):
        self.part = part
        self.mouth = False
        if self._loader is None:
            self._life = self._live()
            self._wait = 0
            self._quiet = False
            self.bug.add_flag(lv.obj.FLAG.HIDDEN)

    def listen(self):
        """He turns to face you, and keeps still."""
        self._play("listen")

    def think(self):
        """His eyes wander, each its own way, until there is something to say."""
        self._play("think")

    def speak(self, mood="calm", prop=None):
        """He speaks in *mood*, holding *prop* if one is named; `mouth` moves his mouth."""
        self.mood = mood
        self.prop = prop
        self._play("speak")

    def settle(self):
        """He holds his last look a moment, then goes back to his own life."""
        if self.part != "idle":
            self._play("settle")

    def rest(self):
        """Back to his own life at once."""
        self._play("idle")

    def _talking(self):
        """The two pictures he speaks with: mouth closed, mouth open."""
        if self.prop:
            return ("hold", self.prop, 0), ("hold", self.prop, 1)
        return ("talk", self.mood, 0), ("talk", self.mood, 1)

    def _live(self):
        if self.part == "idle":
            return Stage._live(self)
        return self._perform()

    def _perform(self):
        while self.part != "idle":
            part = self.part
            self._quiet = False
            if self._facing < 0:
                # the poses of a conversation are drawn facing right
                self._facing = 1
            if part == "listen":
                if not (yield from self._ready(("front", 0, 0), ("front", 0, 1))):
                    yield 1
                    continue
                beat = 0
                while self.part == "listen":
                    beat += 1
                    self._show(("front", 0, 1 if beat % 90 == 60 else 0))
                    yield 3 if beat % 90 == 60 else 1
            elif part == "think":
                first, second = ("think", 0), ("think", 1)
                if not (yield from self._ready(first)):
                    yield 1
                    continue
                self._show(first)
                self._wanted.insert(0, second)
                beat = 0
                while self.part == "think":
                    beat += 1
                    if beat % 28 == 0 and self._have(second):
                        self._show(second if self.pose == first else first)
                    yield 1
            elif part == "speak":
                shut, wide = self._talking()
                if not (yield from self._ready(shut, wide)):
                    yield 1
                    continue
                while self.part == "speak":
                    self._show(wide if self.mouth else shut)
                    yield 1
            elif part == "settle":
                last = ("happy",) if self.mood == "happy" and not self.prop else self._talking()[0]
                if (yield from self._ready(last)):
                    self._show(last)
                    for _ in range(40):
                        if self.part != "settle":
                            break
                        yield 1
                if self.part == "settle":
                    self.part = "idle"
        self._life = Stage._live(self)
        yield 1

    def _change(self, place, variant, view):
        yield from Stage._change(self, place, variant, view)
        # what a conversation opens with, drawn before it is wanted
        self._wanted[:0] = [("front", 0, 0), ("front", 0, 1), ("think", 0)]

    # -- what a reply asked for ------------------------------------------

    def perform(self, colors=None, place=None, variant=None):
        """Put on *colors*, go to *place*, change to *variant*: each only when given.

        A place or a season given without colours brings that place's own
        colours back. Nothing happens while an earlier change is being drawn.

        Returns:
            True when a change was begun.
        """
        if colors is None and place is None and variant is None:
            return False
        if self._loader is not None:
            return False
        if colors is not None:
            self.wears = colors
        else:
            self.wears = None
        place = place or self.place
        if variant is None and place == self.place:
            variant = self.variant
        if (place, variant or PLACES[place]["variants"][0]) == (self.place, self.variant) and (self.wears or self._own()) == self.scheme:
            return False
        return self.go(place, variant)

    def _own(self):
        schemes = PLACES[self.place]["schemes"]
        return schemes[self.variant] if schemes else self.variant
