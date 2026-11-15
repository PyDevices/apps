# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Vamp's front panel on a touch screen: an 800x480 layout on LVGL.

`View` draws a `vamp.panel.Front` and passes it every press::

    front = Front(lambda: join(host))
    view = View(front)
    while True:
        view.step()                  # the link, then whatever changed
        ...                          # LVGL's own loop

Along the top are Play, Rec, the tempo, the swing and the song's name. Down the
left is a row per track: a press selects it, M and S mute and solo it, and the
slider is its volume. The rest is the selected track's pattern, one bar of
sixteenths at a time: a press puts a note on a step or takes it away, and a
column lights where the box is playing.

The sizes are worked out from the display, for 800x480; a larger display gets
the same layout with bigger steps. Runs on MicroPython and CPython.
"""

import lvgl as lv

from vamp import panel

BG = 0x101318
BAR = 0x1B1F27
KEY = 0x2A3040
KEY_DOWN = 0x3A4258
ROW = 0x171A21
ROW_ON = 0x252B3A
CELL = 0x20242D
CELL_BEAT = 0x2A2F3B
CELL_BLACK = 0x181B22
CELL_BLACK_BEAT = 0x20242D
NOTE = 0xF0A030
NOTE_HELD = 0x8A5A1C
PLAY = 0x3FB950
REC = 0xE5484D
MUTE = 0xF0A030
SOLO = 0x4AA3FF
TEXT = 0xE6E6E6
DIM = 0x8A8F99
INK = 0x101318

TOP = 56            # the transport bar
LEFT = 208          # the tracks
HEAD = 44           # the bar and octave buttons over the grid
LABELS = 56         # the row names beside the grid
TRACK_H = 84        # a track's row, when they all fit
TRACK_MIN = 68


def _font(*sizes):
    for size in sizes:
        font = getattr(lv, "font_montserrat_%d" % size, None)
        if font is not None:
            return font
    return lv.font_get_default()


SMALL = _font(14, 12, 16)
FONT = _font(16, 18, 14)
BIG = _font(24, 22, 20, 28, 16)


def _plain(obj, x, y, w, h, color=None):
    obj.remove_style_all()
    obj.remove_flag(lv.obj.FLAG.SCROLLABLE)
    obj.remove_flag(lv.obj.FLAG.CLICKABLE)
    obj.set_pos(x, y)
    obj.set_size(w, h)
    if color is not None:
        obj.set_style_bg_color(lv.color_hex(color), 0)
        obj.set_style_bg_opa(lv.OPA.COVER, 0)
    return obj


def _label(parent, text, font, color, x=None, y=None, w=None):
    lbl = lv.label(parent)
    lbl.set_text(text)
    lbl.set_style_text_font(font, 0)
    lbl.set_style_text_color(lv.color_hex(color), 0)
    if w is not None:
        lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
        lbl.set_width(w)
    if x is not None:
        lbl.set_pos(x, y)
    return lbl


class _Key:
    """A button with a word on it, which can be lit."""

    def __init__(self, parent, text, x, y, w, h, press, font=None):
        self.obj = b = _plain(lv.obj(parent), x, y, w, h, KEY)
        b.add_flag(lv.obj.FLAG.CLICKABLE)
        b.set_style_radius(8, 0)
        b.set_style_bg_color(lv.color_hex(KEY_DOWN), lv.STATE.PRESSED)
        self.text = _label(b, text, font or FONT, TEXT)
        self.text.center()
        b.add_event_cb(lambda e: press(), lv.EVENT.CLICKED, None)

    def lamp(self, color):
        """Light the button in ``color``, or put it out with None."""
        self.obj.set_style_bg_color(lv.color_hex(color if color is not None else KEY), 0)
        self.text.set_style_text_color(lv.color_hex(INK if color is not None else TEXT), 0)


class _Row:
    """One track's widgets."""


def _show(obj, shown):
    if shown:
        obj.remove_flag(lv.obj.FLAG.HIDDEN)
    else:
        obj.add_flag(lv.obj.FLAG.HIDDEN)


def center(obj):
    """The middle of a widget on the screen, for a test's finger."""
    obj = getattr(obj, "obj", obj)
    a = lv.area_t()
    obj.get_coords(a)
    return (a.x1 + a.x2) // 2, (a.y1 + a.y2) // 2


class View:
    """The front panel's screen.

    Args:
        front: the `vamp.panel.Front` to draw and to press.
        screen: the LVGL screen to build on (default: the active one).
    """

    def __init__(self, front, screen=None):
        self.front = front
        scr = screen if screen is not None else lv.screen_active()
        disp = lv.display_get_default()
        self.w = w = disp.get_horizontal_resolution()
        self.h = h = disp.get_vertical_resolution()
        scr.remove_flag(lv.obj.FLAG.SCROLLABLE)
        scr.set_style_bg_color(lv.color_hex(BG), 0)
        scr.set_style_bg_opa(lv.OPA.COVER, 0)
        self.screen = scr
        self.rows = []
        self.cells = []
        self.painted = bytearray(0)
        self.row_labels = []
        self.grid_rows = 0
        self.shades = None
        self.head_step = None
        self._top_bar(scr, w)
        self._editor_bar(scr, w)
        self.tracks = _plain(lv.obj(scr), 0, TOP, LEFT, h - TOP, ROW)
        self.tracks.add_flag(lv.obj.FLAG.SCROLLABLE)
        self.tracks.set_scroll_dir(lv.DIR.VER)
        gx = LEFT + LABELS
        gy = TOP + HEAD + 4
        self.cell_w = (w - gx - 8) // panel.STEPS
        self.grid_h = h - gy - 8
        self.labels = _plain(lv.obj(scr), LEFT, gy, LABELS, self.grid_h)
        self.grid = _plain(lv.obj(scr), gx, gy, self.cell_w * panel.STEPS, self.grid_h)
        self.grid.add_flag(lv.obj.FLAG.CLICKABLE)
        self.grid.add_event_cb(self._grid_pressed, lv.EVENT.CLICKED, None)
        self.head = None
        self.message = _label(scr, "", BIG, DIM)
        self.message.align(lv.ALIGN.CENTER, 0, 0)
        self.refresh()

    # -- building --

    def _top_bar(self, scr, w):
        f = self.front
        bar = _plain(lv.obj(scr), 0, 0, w, TOP, BAR)
        self.play = _Key(bar, "Play", 8, 6, 112, 44, f.toggle_play)
        self.rec = _Key(bar, "Rec", 128, 6, 76, 44, f.toggle_armed)
        x = 220
        self.tempo_down = _Key(bar, "-", x, 6, 44, 44, lambda: f.tempo(-1), BIG)
        _label(bar, "Tempo", SMALL, DIM, x + 44, 4, 70).set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.tempo = _label(bar, "", BIG, TEXT, x + 44, 22, 70)
        self.tempo.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.tempo_up = _Key(bar, "+", x + 114, 6, 44, 44, lambda: f.tempo(1), BIG)
        x = 392
        self.swing_down = _Key(bar, "-", x, 6, 44, 44, lambda: f.swing(-5), BIG)
        _label(bar, "Swing", SMALL, DIM, x + 44, 4, 56).set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.swing = _label(bar, "", BIG, TEXT, x + 44, 22, 56)
        self.swing.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.swing_up = _Key(bar, "+", x + 100, 6, 44, 44, lambda: f.swing(5), BIG)
        x = 548
        self.name = _label(bar, "", FONT, TEXT, x, 8, w - x - 8)
        self.status = _label(bar, "", SMALL, DIM, x, 32, w - x - 8)

    def _editor_bar(self, scr, w):
        f = self.front
        bar = _plain(lv.obj(scr), LEFT, TOP, w - LEFT, HEAD, BG)
        self.editor_bar = bar
        self.bar_down = _Key(bar, "<", 8, 4, 44, 36, lambda: f.page(-1), BIG)
        self.bar_label = _label(bar, "", FONT, TEXT, 52, 12, 132)
        self.bar_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.bar_up = _Key(bar, ">", 184, 4, 44, 36, lambda: f.page(1), BIG)
        self.follow = _Key(bar, "Follow", 240, 4, 96, 36, f.toggle_follow)
        x = w - LEFT - 8 - 184
        self.octave_down = _Key(bar, "-", x, 4, 44, 36, lambda: f.octave(-1), BIG)
        self.octave_label = _label(bar, "", FONT, TEXT, x + 44, 12, 96)
        self.octave_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.octave_up = _Key(bar, "+", x + 140, 4, 44, 36, lambda: f.octave(1), BIG)

    def _build_tracks(self):
        f = self.front
        self.tracks.clean()
        self.rows = []
        doc = f.doc
        if doc is None:
            return
        count = len(doc["tracks"])
        height = max(TRACK_MIN, min(TRACK_H, (self.h - TOP) // max(1, count)))
        for i in range(count):
            row = _Row()
            row.obj = box = _plain(lv.obj(self.tracks), 0, i * height, LEFT, height - 2, ROW)
            box.add_flag(lv.obj.FLAG.CLICKABLE)
            box.add_event_cb(self._call(f.select, i), lv.EVENT.CLICKED, None)
            row.mark = _plain(lv.obj(box), 0, 0, 4, height - 2, NOTE)
            row.name = _label(box, "", FONT, TEXT, 12, 6, LEFT - 12 - 100)
            row.sub = _label(box, "", SMALL, DIM, 12, 28, LEFT - 12 - 100)
            row.mute = _Key(box, "M", LEFT - 98, 6, 44, 38, self._call(f.mute, i))
            row.solo = _Key(box, "S", LEFT - 50, 6, 44, 38, self._call(f.solo, i))
            s = lv.slider(box)
            s.remove_style_all()
            s.set_pos(16, height - 24)
            s.set_size(LEFT - 32, 8)
            s.set_range(0, 127)
            s.set_ext_click_area(12)
            s.set_style_radius(4, 0)
            s.set_style_bg_color(lv.color_hex(KEY), 0)
            s.set_style_bg_opa(lv.OPA.COVER, 0)
            s.set_style_radius(4, lv.PART.INDICATOR)
            s.set_style_bg_color(lv.color_hex(DIM), lv.PART.INDICATOR)
            s.set_style_bg_opa(lv.OPA.COVER, lv.PART.INDICATOR)
            s.set_style_radius(10, lv.PART.KNOB)
            s.set_style_pad_all(6, lv.PART.KNOB)
            s.set_style_bg_color(lv.color_hex(TEXT), lv.PART.KNOB)
            s.set_style_bg_opa(lv.OPA.COVER, lv.PART.KNOB)
            s.add_event_cb(self._volume(i, s, False), lv.EVENT.VALUE_CHANGED, None)
            s.add_event_cb(self._volume(i, s, True), lv.EVENT.RELEASED, None)
            row.volume = s
            self.rows.append(row)

    @staticmethod
    def _call(fn, arg):
        return lambda *e: fn(arg)

    def _volume(self, index, slider, last):
        return lambda e: self.front.volume(index, slider.get_value(), last)

    def _build_grid(self, rows):
        """The cells for this many rows: twelve for a melodic track, six for a kit."""
        self.grid.clean()
        self.labels.clean()
        self.cells = []
        self.row_labels = []
        self.grid_rows = rows
        self.painted = bytearray(rows * panel.STEPS)
        self.shades = None
        self.head = None
        if not rows:
            return
        cw = self.cell_w
        ch = self.cell_h = self.grid_h // rows
        for r in range(rows):
            lbl = _label(self.labels, "", SMALL, DIM, 0, r * ch + (ch - SMALL.get_line_height()) // 2, LABELS - 8)
            lbl.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
            self.row_labels.append(lbl)
            for c in range(panel.STEPS):
                cell = _plain(lv.obj(self.grid), c * cw + 1, r * ch + 1, cw - 2, ch - 2, CELL)
                cell.set_style_radius(3, 0)
                self.cells.append(cell)
        self.head = _plain(lv.obj(self.grid), 0, 0, cw, ch * rows, 0xFFFFFF)
        self.head.set_style_bg_opa(70, 0)
        self.head.add_flag(lv.obj.FLAG.HIDDEN)

    # -- presses --

    def _grid_pressed(self, e):
        indev = lv.indev_active()
        if indev is None or not self.grid_rows:
            return
        point = lv.point_t()
        indev.get_point(point)
        a = lv.area_t()
        self.grid.get_coords(a)
        self.front.toggle((point.y - a.y1) // self.cell_h, (point.x - a.x1) // self.cell_w)

    def cell_center(self, row, step):
        """Where a cell is on the screen, for a test's finger."""
        a = lv.area_t()
        self.grid.get_coords(a)
        return a.x1 + step * self.cell_w + self.cell_w // 2, a.y1 + row * self.cell_h + self.cell_h // 2

    # -- drawing what changed --

    def step(self):
        """Run the link and draw whatever it changed. Call it about 30 times a second."""
        self.front.poll()
        self.refresh()

    def refresh(self):
        f = self.front
        everything = f.take("all")
        if everything:
            self._build_tracks()
            self._show_message()
        if f.take("status") or everything:
            self.status.set_text(f.status)
        if f.take("top") or everything:
            self._draw_top()
        if f.take("tracks") or everything:
            self._draw_tracks()
        if f.take("grid") or everything:
            self._draw_grid()
            f.mark("head")
        if f.take("head"):
            self._draw_head()

    def _show_message(self):
        there = self.front.doc is not None
        for obj in (self.tracks, self.grid, self.labels, self.editor_bar):
            _show(obj, there)
        self.message.set_text("" if there else "Waiting for the box")

    def _draw_top(self):
        f = self.front
        doc = f.doc
        self.play.text.set_text("Stop" if f.playing else "Play")
        self.play.lamp(PLAY if f.playing else None)
        self.rec.lamp(REC if f.armed else None)
        self.name.set_text(doc.get("name", "") if doc is not None else "Vamp")
        self.tempo.set_text("%d" % round(doc["tempo"]) if doc is not None else "")
        self.swing.set_text("%d" % doc.get("swing", 0) if doc is not None else "")

    def _draw_tracks(self):
        f = self.front
        doc = f.doc
        if doc is None:
            return
        for i, row in enumerate(self.rows):
            t = doc["tracks"][i]
            on = i == f.selected
            row.obj.set_style_bg_color(lv.color_hex(ROW_ON if on else ROW), 0)
            _show(row.mark, on)
            row.name.set_text(t["name"])
            if t["kind"] == "drums":
                row.sub.set_text("Kit %d" % (t.get("patch", 0) + 1))
            elif t["instrument"].startswith("soundfont"):
                row.sub.set_text("Program %d" % (t.get("patch", 0) + 1))
            else:
                row.sub.set_text(t["instrument"])
            row.mute.lamp(MUTE if t.get("mute") else None)
            row.solo.lamp(SOLO if t.get("solo") else None)
            if not row.volume.has_state(lv.STATE.PRESSED):
                row.volume.set_value(t["volume"], False)

    def _draw_grid(self):
        f = self.front
        rows = f.rows()
        if len(rows) != self.grid_rows:
            self._build_grid(len(rows))
        if not rows:
            return
        index, pattern = f.pattern()
        self.bar_label.set_text("P%d  bar %d/%d" % (index + 1, f.bar + 1, pattern["bars"]))
        self.follow.lamp(PLAY if f.follow else None)
        melodic = f.track()["kind"] != "drums"
        for obj in (self.octave_down.obj, self.octave_label, self.octave_up.obj):
            _show(obj, melodic)
        if melodic:
            self.octave_label.set_text("%s-%s" % (rows[-1][1], rows[0][1]))
        shades = tuple(row[2] for row in rows)
        reshade = shades != self.shades
        self.shades = shades
        for r, row in enumerate(rows):
            self.row_labels[r].set_text(row[1])
        now = f.cells()
        was = self.painted
        steps = panel.STEPS
        for i in range(len(now)):
            state = now[i]
            if state == was[i] and not (reshade and state == panel.EMPTY):
                continue
            if state == panel.START:
                color = NOTE
            elif state == panel.HELD:
                color = NOTE_HELD
            else:
                beat = (i % steps) // 4 % 2 == 0
                if shades[i // steps]:
                    color = CELL_BLACK_BEAT if beat else CELL_BLACK
                else:
                    color = CELL_BEAT if beat else CELL
            self.cells[i].set_style_bg_color(lv.color_hex(color), 0)
        self.painted = now

    def _draw_head(self):
        f = self.front
        if self.head is None:
            return
        head = f.head
        if head is None or head // panel.STEPS != f.bar:
            self.head.add_flag(lv.obj.FLAG.HIDDEN)
            self.head_step = None
            return
        self.head_step = head % panel.STEPS
        self.head.set_x(self.head_step * self.cell_w)
        self.head.remove_flag(lv.obj.FLAG.HIDDEN)
