# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The song-form strip: a song's parts in a row, the one playing lit with
the playhead moving across it, and the one coming next outlined.

Each part is a block as wide as its bars, in its colour from the floor
view. With ``on_pick``, a tap on a block picks that part (the editor uses
it to choose the part to edit), and the picked one is underlined.
"""

import lvgl as lv

from . import look
from .. import parts as song
from .. import art


class Strip:
    """The strip in ``parent`` at ``(x, y)``, ``w`` by ``h``."""

    def __init__(self, parent, x, y, w, h, fnt, on_pick=None):
        self.w, self.h = int(w), int(h)
        self.fnt = fnt
        self.on_pick = on_pick
        self.base = look.plain(lv.obj(parent))
        self.base.set_pos(int(x), int(y))
        self.base.set_size(self.w, self.h)
        self.blocks = []
        self.objs = []
        self.lit = -1
        self.next = -1
        self.picked = -1
        self.head = None
        self.tag = None
        self.mark = None

    def set_blocks(self, blocks):
        """Lay out ``blocks`` (from `parts.blocks`)."""
        self.base.clean()
        self.blocks = blocks
        self.objs = []
        self.lit = self.next = -1
        n = len(blocks)
        if not n:
            self.head = self.tag = self.mark = None
            return
        gap = max(3, self.w // 160)
        tag_h = self.fnt.line_height
        top = tag_h + 2
        bh = self.h - top - max(4, self.h // 12)
        total = sum(b["bars"] for b in blocks)
        room = self.w - gap * (n - 1)
        # Every block at least wide enough for a short name, the rest by bars.
        least = min(room // n, max(30, room // (2 * n)))
        spare = room - least * n
        x = 0
        rail = look.box(self.base, 0, top + bh // 2 - 1, self.w, 2, look.LINE, 1, None)
        rail.set_style_bg_opa(160, 0)
        for i, b in enumerate(blocks):
            art.pause()
            bw = least + spare * b["bars"] // total if i < n - 1 else self.w - x
            color = look.ROLE_COLORS.get(b["role"], look.DIM)
            o = look.box(self.base, x, top, bw, bh, art.mix(color, look.BG, 0.8), 6, art.mix(color, look.BG, 0.45))
            lbl = look.text(o, b["short"], self.fnt, art.mix(color, look.TEXT, 0.35), bw - 6, lv.TEXT_ALIGN.CENTER)
            lbl.align(lv.ALIGN.CENTER, 0, 0)
            if self.on_pick is not None:
                o.add_flag(lv.obj.FLAG.CLICKABLE)
                o.add_event_cb(self._picker(i), lv.EVENT.CLICKED, None)
            self.objs.append((o, lbl, x, bw, color))
            x += bw + gap
        self.top, self.bh = top, bh
        head = look.box(self.base, 0, top - 2, max(2, self.w // 300), bh + 4, 0xFFFFFF, 1, None)
        head.add_flag(lv.obj.FLAG.HIDDEN)
        self.head = head
        tag = look.text(self.base, "NEXT", self.fnt, look.DIM)
        tag.set_style_text_letter_space(1, 0)
        tag.add_flag(lv.obj.FLAG.HIDDEN)
        self.tag = tag
        mark = look.box(self.base, 0, top + bh + 2, 10, max(3, self.h // 20), look.AMBER, 2, None)
        mark.add_flag(lv.obj.FLAG.HIDDEN)
        self.mark = mark
        if self.picked >= 0:
            p, self.picked = self.picked, -1
            self.pick(min(p, n - 1))

    def _picker(self, i):
        def on_event(_e):
            self.pick(i)
            self.on_pick(i)

        return on_event

    def pick(self, i):
        """Underline block ``i``, the part being edited."""
        if i == self.picked or self.mark is None:
            return
        self.picked = i
        _o, _l, x, bw, _c = self.objs[i]
        self.mark.set_pos(x + 4, self.top + self.bh + 2)
        self.mark.set_width(max(4, bw - 8))
        self.mark.remove_flag(lv.obj.FLAG.HIDDEN)

    def _style(self, i, how):
        if not 0 <= i < len(self.objs):
            return
        o, lbl, _x, _bw, color = self.objs[i]
        if how == "lit":
            o.set_style_bg_color(look.color(art.mix(color, look.BG, 0.35)), 0)
            o.set_style_border_color(look.color(color), 0)
            o.set_style_border_width(2, 0)
            lbl.set_style_text_color(look.color(0xFFFFFF), 0)
        elif how == "next":
            o.set_style_bg_color(look.color(art.mix(color, look.BG, 0.75)), 0)
            o.set_style_border_color(look.color(color), 0)
            o.set_style_border_width(2, 0)
            lbl.set_style_text_color(look.color(art.mix(color, look.TEXT, 0.2)), 0)
        else:
            o.set_style_bg_color(look.color(art.mix(color, look.BG, 0.8)), 0)
            o.set_style_border_color(look.color(art.mix(color, look.BG, 0.45)), 0)
            o.set_style_border_width(1, 0)
            lbl.set_style_text_color(look.color(art.mix(color, look.TEXT, 0.35)), 0)

    def show(self, tele):
        """Light the part ``tele`` says plays, and move the playhead."""
        if not self.objs:
            return
        playing = tele.get("playing")
        lit = song.find(self.blocks, tele.get("role"), tele.get("number")) if playing else -1
        nxt = song.find(self.blocks, tele.get("next_role"), tele.get("next_number")) if playing else -1
        if nxt == lit:
            nxt = -1
        if lit != self.lit or nxt != self.next:
            for i in (self.lit, self.next):
                self._style(i, "plain")
            self._style(nxt, "next")
            self._style(lit, "lit")
            self.lit, self.next = lit, nxt
            if nxt >= 0:
                _o, _l, x, bw, color = self.objs[nxt]
                self.tag.set_style_text_color(look.color(color), 0)
                self.tag.set_pos(x + 2, 0)
                self.tag.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                self.tag.add_flag(lv.obj.FLAG.HIDDEN)
        if lit < 0:
            self.head.add_flag(lv.obj.FLAG.HIDDEN)
            return
        _o, _l, x, bw, _c = self.objs[lit]
        length = self.blocks[lit]["bars"] * song.BAR
        frac = min(1.0, max(0.0, tele.get("at", 0) / float(length)))
        self.head.set_x(int(x + 2 + frac * (bw - 4)))
        self.head.remove_flag(lv.obj.FLAG.HIDDEN)

    def head_x(self):
        """Where the playhead is, or -1 when it's hidden (for a check)."""
        if self.head is None or self.head.has_flag(lv.obj.FLAG.HIDDEN):
            return -1
        return self.head.get_x()
