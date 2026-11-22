# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The step grid: a part's drums by steps, one bar at a time.

A row is a drum the kit has, a column a step of the bar, and a cell's
brightness is how hard it plays: dim on, bright loud, faint soft. A tap on
a cell sends the op that moves it to its next level (`parts.tap`), and the
column playing now is outlined while the part on show plays.
"""

import lvgl as lv

from . import look
from .. import parts as song
from .. import art

ON = (look.RAISED, art.mix(look.AMBER, look.RAISED, 0.25), look.AMBER, art.mix(look.AMBER, look.RAISED, 0.62))


class Grid:
    """The grid in ``parent`` at ``(x, y)``, ``w`` by ``h``. ``on_tap(pitch, step)``
    gets a tap, ``step`` counted from the part's first bar."""

    def __init__(self, parent, x, y, w, h, fnt, on_tap):
        self.w, self.h = int(w), int(h)
        self.fnt = fnt
        self.on_tap = on_tap
        self.base = look.plain(lv.obj(parent))
        self.base.set_pos(int(x), int(y))
        self.base.set_size(self.w, self.h)
        self.base.add_flag(lv.obj.FLAG.SCROLLABLE)
        self.base.set_scroll_dir(lv.DIR.VER)
        self.rows = []
        self.cols = 16
        self.beat = 4
        self.bar = 0
        self.cells = {}           # (pitch, column) -> [obj, level shown]
        self.head = None
        self.head_col = -1
        self.label_w = 0
        self.cell_w = self.cell_h = 0

    def build(self, rows, cols, beat):
        """Rows ``[(pitch, name)]``, ``cols`` steps a bar, ``beat`` steps a beat."""
        self.base.clean()
        self.rows, self.cols, self.beat = rows, cols, beat
        self.cells = {}
        gap = 3
        beat_gap = 5
        self.label_w = lw = max(64, self.w * 18 // 100)
        groups = cols // beat
        cw = (self.w - lw - gap * (cols - 1) - beat_gap * (groups - 1) - 2) // cols
        ch = max(22, min(cw + 6, (self.h - 2) // max(1, len(rows)) - gap))
        ch = min(ch, int(cw * 1.4))
        self.cell_w, self.cell_h = cw, ch
        self.xs = []
        x = lw
        for c in range(cols):
            if c and c % beat == 0:
                x += beat_gap
            self.xs.append(x)
            x += cw + gap
        for r, (pitch, name) in enumerate(rows):
            y = r * (ch + gap)
            lbl = look.text(self.base, name, self.fnt, look.DIM, lw - 8)
            lbl.set_pos(0, y + (ch - self.fnt.line_height) // 2)
            for c in range(cols):
                o = look.box(self.base, self.xs[c], y, cw, ch, self._off(c), 4, None)
                o.add_flag(lv.obj.FLAG.CLICKABLE)
                o.set_style_border_color(look.color(look.AMBER), lv.STATE.PRESSED)
                o.set_style_border_width(2, lv.STATE.PRESSED)
                o.add_event_cb(self._tapper(pitch, c), lv.EVENT.CLICKED, None)
                self.cells[(pitch, c)] = [o, 0]
        head = look.box(self.base, 0, 0, cw + 4, max(1, len(rows)) * (ch + gap) - gap + 4, 0xFFFFFF, 5, None)
        head.set_style_bg_opa(0, 0)
        head.set_style_border_color(look.color(0xFFFFFF), 0)
        head.set_style_border_width(2, 0)
        head.set_style_border_opa(200, 0)
        head.add_flag(lv.obj.FLAG.HIDDEN)
        self.head = head
        self.head_col = -1

    def _off(self, c):
        return art.mix(look.RAISED, 0xFFFFFF, 0.06) if c % self.beat == 0 else look.RAISED

    def _tapper(self, pitch, c):
        def on_event(_e):
            self.on_tap(pitch, self.bar * self.cols + c)

        return on_event

    def show(self, levels):
        """Light the cells: ``levels`` is `parts.levels` of the part on show.
        Only a cell whose level changed is restyled."""
        base = self.bar * self.cols
        for (pitch, c), slot in self.cells.items():
            lvl = levels.get((pitch, base + c), 0)
            if slot[1] == lvl:
                continue
            slot[1] = lvl
            o = slot[0]
            o.set_style_bg_color(look.color(ON[lvl] if lvl else self._off(c)), 0)

    def level(self, pitch, c):
        """The level a cell shows (for a check), or -1 when there's no such cell."""
        slot = self.cells.get((pitch, c))
        return -1 if slot is None else slot[1]

    def center(self, pitch, c):
        """A cell's centre on the screen, for a press."""
        o = self.cells[(pitch, c)][0]
        a = lv.area_t()
        o.get_coords(a)
        return (a.x1 + a.x2) // 2, (a.y1 + a.y2) // 2

    def playhead(self, column):
        """Outline ``column`` of the bar on show, or nothing when -1."""
        if self.head is None or column == self.head_col:
            return
        self.head_col = column
        if column < 0:
            self.head.add_flag(lv.obj.FLAG.HIDDEN)
            return
        self.head.set_pos(self.xs[column] - 2, -2)
        self.head.remove_flag(lv.obj.FLAG.HIDDEN)
