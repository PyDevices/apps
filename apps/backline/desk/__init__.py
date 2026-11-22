# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's desk view: perform and edit a song from a bigger screen.

Two tabs under one header. Perform (`perform.Perform`) is the floor view's
face, larger, with the song's form, the songs, the tempo and the kit.
Edit (`editor.Editor`) is the step grid of a part, the song library, the
kits and a mixer, every change landing while the song plays. The header
shows the part, the bar and beat, and what comes next, on both tabs.

Like the floor view, the desk holds nothing but an ``hmilink.Panel``, so
the same view runs on the box's own screen through ``hmilink.local``, or on
another computer or board through ``hmilink.tcp`` (`desk_main`). It is laid
out for 800x480 and larger, from the ``size`` it is given.

    desk = Desk(screen, (800, 480), panel)
    while True:
        desk.poll()
"""

import lvgl as lv

from . import look
from .. import art
from .editor import Editor
from .perform import Perform

TABS = (("perform", "PERFORM", "queue_music"), ("edit", "EDIT", "grid_on"))


class _Proxy:
    """What the floor view inside the desk sees as its panel: the desk's
    panel's document, and commands sent through the desk."""

    def __init__(self, desk):
        self.desk = desk
        self.on_doc = None
        self.on_tele = None

    @property
    def doc(self):
        return self.desk.panel.doc if self.desk.panel is not None else None

    @property
    def desc(self):
        return self.desk.panel.desc if self.desk.panel is not None else None

    def command(self, name, **args):
        self.desk.command(name, **args)

    def poll(self):
        pass


class Desk:
    """The desk view on ``root``, ``size`` = (width, height), showing ``panel``.

    With ``on_switch``, a button in the header calls it: the app shows the
    floor view there instead.
    """

    def __init__(self, root, size, panel, on_switch=None):
        w, h = size
        self.size = size
        self.scale = s = min(w / 800.0, h / 480.0)
        self.m = m = max(6, int(8 * s))
        self.fonts = {"small": look.font(14 * s), "body": look.font(16 * s), "value": look.font(24 * s),
                      "title": look.font(24 * s)}
        self.panel = None
        self.panel_proxy = _Proxy(self)
        self.tele = {}
        self.shown = {}
        self.message = ""
        self.tab = None

        base = look.plain(lv.obj(root))
        base.set_pos(0, 0)
        base.set_size(w, h)
        base.set_style_bg_color(look.color(look.BG), 0)
        base.set_style_bg_opa(255, 0)
        self.base = base

        hh = int(52 * s)
        self.header_h = hh
        head = look.box(base, 0, 0, w, hh, look.PANEL, 0, None)
        look.box(base, 0, hh - 1, w, 1, look.LINE, 0, None)
        f = self.fonts
        title = look.text(head, "BACKLINE", f["body"], look.AMBER)
        title.set_style_text_letter_space(3, 0)
        title.align(lv.ALIGN.LEFT_MID, m * 2, 0)
        tx = m * 2 + int(118 * s)
        tw = int(124 * s)
        self.tab_buttons = {}
        for i, (key, name, icon) in enumerate(TABS):
            b = look.button(head, tx + i * (tw + m), m, tw, hh - 2 * m, name, fnt=f["small"],
                            on_click=self._tabber(key), radius=6)
            b.get_child(0).set_style_text_letter_space(2, 0)
            self.tab_buttons[key] = b
        rx = tx + 2 * (tw + m) + m
        # The readout: the part, the bar and beat, and what comes next.
        sw = int(30 * s) + m if on_switch is not None else 0
        self.readout_w = rw = w - rx - sw - 2 * m
        self.part = look.text(head, "", f["body"], look.DIM, int(rw * 0.34))
        self.part.set_pos(rx, (hh - f["body"].line_height) // 2)
        self.where = look.text(head, "", f["value"], look.TEXT, int(rw * 0.26), lv.TEXT_ALIGN.CENTER)
        self.where.set_pos(rx + int(rw * 0.34), (hh - f["value"].line_height) // 2)
        self.next = look.text(head, "", f["small"], look.DIM, int(rw * 0.40), lv.TEXT_ALIGN.RIGHT)
        self.next.set_pos(rx + int(rw * 0.60), (hh - f["small"].line_height) // 2)
        self.switch = None
        if on_switch is not None:
            bs = int(34 * s)
            self.switch = look.button(head, w - bs - m * 2, (hh - bs) // 2, bs, bs, icon="speed",
                                      on_click=on_switch, radius=6)

        body_h = h - hh
        self.perform = Perform(base, 0, hh, w, body_h, self)
        self.editor = Editor(base, 0, hh, w, body_h, self)
        self.show_tab("perform")
        self.attach(panel)

    # -- the panel --

    def attach(self, panel):
        """Draw from ``panel`` from now on (a new link after the old one went)."""
        self.panel = panel
        if panel is None:
            return
        panel.on_doc = self._doc
        panel.on_op = self._op
        panel.on_tele = self._tele
        panel.on_event = self._event
        panel.on_error = self._error
        if panel.doc is not None:
            self._doc(panel.doc, panel.desc)

    def poll(self):
        if self.panel is not None:
            self.panel.poll()

    def command(self, name, **args):
        if self.panel is not None and not self.panel.closed:
            self.panel.command(name, **args)

    def pedal(self, which, down):
        """Pedal ``which`` went down or up: tell the device."""
        self.command("pedal", pedal=which, down=down)

    # -- the tabs --

    def _tabber(self, key):
        def on_click():
            self.show_tab(key)

        return on_click

    def show_tab(self, key):
        """Show tab ``"perform"`` or ``"edit"``."""
        if key == self.tab:
            return
        self.tab = key
        for k, b in self.tab_buttons.items():
            look.select(b, k == key)
        if key == "perform":
            self.editor.base.add_flag(lv.obj.FLAG.HIDDEN)
            self.perform.base.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            self.perform.base.add_flag(lv.obj.FLAG.HIDDEN)
            self.editor.base.remove_flag(lv.obj.FLAG.HIDDEN)

    # -- what comes from the device --

    def _doc(self, doc, desc):
        self.perform.on_doc(doc, desc or {})
        self.editor.on_doc(doc, desc or {})

    def _op(self, op):
        self.perform.on_op(op)
        self.editor.on_op(op)

    def _event(self, ev):
        self.perform.on_event(ev)
        self.editor.on_event(ev)

    def _changed(self, key, value):
        if self.shown.get(key) == value:
            return False
        self.shown[key] = value
        return True

    def _error(self, msg):
        if msg.get("msg"):
            self.shown.pop("next", None)
            self.message = msg["msg"]
            self.next.set_text(self.message.upper())
            self.next.set_style_text_color(look.color(look.BAD), 0)

    def _tele(self, t):
        self.tele = t
        playing = t.get("playing")
        role = t.get("role", "stopped")
        color = look.ROLE_COLORS.get(role, look.DIM)
        if self._changed("part", (t.get("part"), color)):
            self.part.set_text((t.get("part") or "Ready").upper())
            self.part.set_style_text_color(look.color(color), 0)
        where = "%d . %d" % (t.get("bar", 1), t.get("beat", 1)) if playing else "- . -"
        if self._changed("where", where):
            self.where.set_text(where)
        if not (self.message and not playing):  # what the device refused stays until the song plays
            self.message = ""
            nxt = t.get("next") or ""
            if self._changed("next", (nxt, playing, t.get("next_role"))):
                self.next.set_text(("NEXT  " + nxt.upper()) if nxt else ("LOOPING" if playing else "TAP A TO START"))
                ncolor = look.ROLE_COLORS.get(t.get("next_role") or "", look.DIM) if nxt else look.DIM
                self.next.set_style_text_color(look.color(art.mix(ncolor, look.TEXT, 0.15)), 0)
        self.perform.on_tele(t)
        self.editor.on_tele(t)
