# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Huey: hold the chameleon, ask him something out loud, and he answers.

While you hold Huey he turns to you and the board's microphone records.
Let go, and the question goes to an OpenAI-compatible server three times
over: for its words, for a reply, and for the reply as speech, which plays
through the board's speaker and shows in a speech bubble. The reply also
says how Huey acts it out: a mood, colours, something to hold, a place.

Which server, which models and which key file are in one settings file,
``settings.json`` in the app's data folder; see ``settings.py``.
"""

import lvgl as lv

from .settings import DEFAULTS
from .actor import Actor
from .turn import Turn
from ..perch.stage import TICK_MS

_GLASS = 0x0B2A4A
_LIME = 0xC4DC4C
_PAPER = 0xFFFDF4
_AMBER = 0xFFE9B0
_INK = 0x14283C
_BUBBLE_TICKS = 6000 // TICK_MS  # an answer stays this long after its last word
_NOTE_TICKS = 5000 // TICK_MS


def _font(size):
    """The Montserrat nearest *size* that this LVGL was built with."""
    for wanted in (size, 16, 14):
        font = getattr(lv, "font_montserrat_%d" % wanted, None)
        if font is not None:
            return font
    return lv.font_default()


class _Show:
    """The words over the picture: a speech bubble, a line of what is happening, a ring that hears."""

    def __init__(self, root, size, stage):
        w, h = size
        self.w, self.h = w, h
        self.stage = stage
        big = h >= 400
        self.ring_obj = lv.obj(root)
        self.ring_obj.remove_style_all()
        self.ring_obj.set_style_radius(lv.RADIUS_CIRCLE, 0)
        self.ring_obj.set_style_border_color(lv.color_hex(_LIME), 0)
        self.ring_obj.set_style_border_width(max(3, h // 100), 0)
        self.ring_obj.set_style_border_opa(200, 0)
        self.ring_obj.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.ring_obj.add_flag(lv.obj.FLAG.HIDDEN)
        self._ring = 0.0

        self.bubble = lv.obj(root)
        self.bubble.remove_style_all()
        self.bubble.set_style_radius(max(10, h // 24), 0)
        self.bubble.set_style_bg_color(lv.color_hex(_PAPER), 0)
        self.bubble.set_style_bg_opa(240, 0)
        self.bubble.set_style_pad_all(max(8, h // 34), 0)
        self.bubble.set_width(lv.SIZE_CONTENT)
        self.bubble.set_height(lv.SIZE_CONTENT)
        self.bubble.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.bubble.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.words = lv.label(self.bubble)
        self.words.set_style_text_font(_font(24 if big else 16), 0)
        self.words.set_style_text_color(lv.color_hex(_INK), 0)
        self.words.set_long_mode(lv.label.LONG_MODE.WRAP)
        self._words_most = w * 62 // 100
        self.tail = lv.obj(root)
        self.tail.remove_style_all()
        self.tail.set_style_bg_color(lv.color_hex(_PAPER), 0)
        self.tail.set_style_bg_opa(240, 0)
        self.tail.set_style_radius(lv.RADIUS_CIRCLE, 0)
        self.tail.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.bubble.add_flag(lv.obj.FLAG.HIDDEN)
        self.tail.add_flag(lv.obj.FLAG.HIDDEN)
        self._bubble_left = 0

        self.line = lv.obj(root)
        self.line.remove_style_all()
        self.line.set_style_radius(lv.RADIUS_CIRCLE, 0)
        self.line.set_style_bg_color(lv.color_hex(_GLASS), 0)
        self.line.set_style_bg_opa(190, 0)
        self.line.set_style_pad_hor(max(10, h // 28), 0)
        self.line.set_style_pad_ver(max(4, h // 80), 0)
        self.line.set_width(lv.SIZE_CONTENT)
        self.line.set_height(lv.SIZE_CONTENT)
        self.line.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.line.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.line_text = lv.label(self.line)
        self.line_text.set_style_text_font(_font(16 if big else 14), 0)
        self.line_text.set_style_text_color(lv.color_white(), 0)
        self.line_text.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.line.add_flag(lv.obj.FLAG.HIDDEN)
        self._note = ""
        self._heard = ""
        self._note_left = 0
        #: What the bubble and the line say now, for whoever is watching from outside.
        self.said = None
        self.noted = ""

    def _head(self):
        """Where Huey's head is on the screen, near enough."""
        if self.stage.place is None:
            # his first place is still being drawn
            return self.w // 2, self.h // 3
        ox, oy = self.stage._origin()
        k = self.stage._shown[0].header.h / 250 if self.stage._shown else self.h / 800
        return int(ox + 60 * k), int(oy - 150 * k)

    def _line(self):
        text = self._note or self._heard
        if self._note and self._heard:
            text = "%s   %s" % (self._heard, self._note)
        self.noted = text
        if not text:
            self.line.add_flag(lv.obj.FLAG.HIDDEN)
            return
        self.line_text.set_width(lv.SIZE_CONTENT)
        self.line_text.set_text(text)
        self.line_text.update_layout()
        most = self.w * 86 // 100
        if self.line_text.get_width() > most:
            self.line_text.set_width(most)
        self.line.remove_flag(lv.obj.FLAG.HIDDEN)
        self.line.align(lv.ALIGN.BOTTOM_MID, 0, -max(6, self.h // 40))

    def note(self, text):
        """What is happening now, on the line at the bottom; "" for nothing."""
        if text != self._note:
            self._note = text
            self._note_left = _NOTE_TICKS if text else 0
            self._line()

    def heard(self, text):
        """The question as it was understood, on the line whenever nothing is happening."""
        self._heard = '"%s"' % text if text else ""
        self._line()

    def say(self, text, trouble):
        """Put *text* in the speech bubble, in amber when it is *trouble*; None takes the bubble away."""
        self.said = text
        if text is None:
            self.bubble.add_flag(lv.obj.FLAG.HIDDEN)
            self.tail.add_flag(lv.obj.FLAG.HIDDEN)
            self._bubble_left = 0
            self.heard("")
            return
        color = lv.color_hex(_AMBER if trouble else _PAPER)
        self.bubble.set_style_bg_color(color, 0)
        self.tail.set_style_bg_color(color, 0)
        self.words.set_width(lv.SIZE_CONTENT)
        self.words.set_text(text)
        self.words.update_layout()
        if self.words.get_width() > self._words_most:
            self.words.set_width(self._words_most)
        self.bubble.remove_flag(lv.obj.FLAG.HIDDEN)
        self.bubble.update_layout()
        self._place_bubble()
        # an answer stays while it is spoken; trouble goes after a while by itself
        self._bubble_left = _BUBBLE_TICKS * 2 if trouble else -1

    def _place_bubble(self):
        hx, hy = self._head()
        bw, bh = self.bubble.get_width(), self.bubble.get_height()
        gap = max(6, self.h // 60)
        x = min(max(hx + self.w // 16, gap), self.w - bw - gap)
        y = min(max(hy - bh - self.h // 8, gap), self.h - bh - gap)
        self.bubble.set_pos(x, y)
        dot = max(8, self.h // 34)
        self.tail.set_size(dot, dot)
        self.tail.set_pos(x + bw // 8, y + bh + dot // 4)
        self.tail.remove_flag(lv.obj.FLAG.HIDDEN)

    def rest(self):
        """The answer has been spoken: its bubble stays a while longer, then goes."""
        if self._bubble_left < 0:
            self._bubble_left = _BUBBLE_TICKS

    def ring(self, level):
        """How loud the microphone hears, 0 to 1, as a ring round Huey's head; None takes it away."""
        if level is None:
            self.ring_obj.add_flag(lv.obj.FLAG.HIDDEN)
            self._ring = 0.0
            return
        # out fast, back slowly: a voice reads as a pulse
        self._ring = level if level > self._ring else self._ring * 0.8
        hx, hy = self._head()
        size = int(self.h * (0.2 + 0.22 * min(self._ring * 2.5, 1.0)))
        self.ring_obj.set_size(size, size)
        self.ring_obj.set_pos(hx - size // 2, hy - size // 2)
        self.ring_obj.remove_flag(lv.obj.FLAG.HIDDEN)

    def tick(self):
        if self._bubble_left > 0:
            self._bubble_left -= 1
            if self._bubble_left == 0:
                self.say(None, False)
        if self._note_left > 0 and self._note in ("Hold me to talk", "Hold me while you talk", "No speaker here: read my words"):
            self._note_left -= 1
            if self._note_left == 0:
                self.note("")


def start(scope, post=None, microphone=None, speaker=None):
    """Open the app on *scope*, as `main` does.

    Args:
        scope: The app's scope.
        post: What sends a request to the server, in place of the
            connection the app keeps open to it.
        microphone: What opens a microphone at a rate, in place of the board's.
        speaker: What opens a speaker at a rate and a count of channels, in place of the board's.
    """
    root = scope.root
    root.remove_flag(lv.obj.FLAG.SCROLLABLE)
    root.set_style_pad_all(0, 0)
    root.set_style_border_width(0, 0)
    root.set_style_bg_color(lv.color_hex(_GLASS), 0)
    root.set_style_bg_opa(255, 0)

    path = scope.data_dir + "/settings.json"
    stage = Actor(root, scope.size)
    show = _Show(root, scope.size, stage)
    turn = Turn(stage, show, scope.worker, path, post, microphone, speaker)
    why = turn.ready()
    place = turn.settings["place"] if turn.settings else DEFAULTS["place"]
    if place != stage.place:
        stage.go(place)
    if why:
        show.say(why, True)
    else:
        show.note("Hold me to talk")

    point = lv.point_t()
    held = [False]

    def pressed(_event):
        indev = lv.indev_active()
        if indev is None:
            return
        indev.get_point(point)
        if stage.hit(point.x, point.y):
            held[0] = True
            turn.press()
        elif turn.state == "idle":
            show.note("Hold me to talk")

    def released(_event):
        if held[0]:
            held[0] = False
            turn.release()

    root.add_flag(lv.obj.FLAG.CLICKABLE)
    root.add_event_cb(pressed, lv.EVENT.PRESSED, None)
    root.add_event_cb(released, lv.EVENT.RELEASED, None)
    root.add_event_cb(released, lv.EVENT.PRESS_LOST, None)

    was = [turn.state]

    def tick(_timer=None):
        if turn.astray():
            return
        stage.tick()
        turn.tick()
        if was[0] == "speak" and turn.state == "idle":
            show.rest()
        was[0] = turn.state
        show.tick()

    def close():
        turn.close()
        stage.close()

    scope.every(TICK_MS, tick)
    scope.on_close(close)
    # for whoever drives the app from outside: a test, a screenshot script
    scope.huey = (stage, show, turn)


def main(scope):
    start(scope)
