# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The screen: an LVGL panel over the engine, laid out to whatever size the
app is given. The panels flow, the knobs scroll when they don't fit, and on a
small panel the whole screen does.

Knobs are built from the effect adapter's parameter descriptions, so any
library's effect gets a panel without screen code of its own.
"""

import lvgl as lv
from touchkit import ui as kit

BG = 0x15171A
PANEL = 0x1F2226
LINE = 0x33373D
TEXT = 0xE8E6E1
MUTED = 0x8C9096
ACCENT = 0xF2A33A      # amber, like a pedal's LED
GOOD = 0x63C27A

NARROW = 600           # below this width, the smaller knobs and buttons


def c(hex_):
    return lv.color_hex(hex_)


def label(parent, text, colour=TEXT, font=None):
    lb = lv.label(parent)
    lb.set_text(text)
    lb.set_style_text_color(c(colour), 0)
    lb.set_style_text_font(font or kit.small, 0)
    return lb


def flow(parent, wrap=True):
    """A row that wraps, its children centred on the line."""
    parent.set_flex_flow(lv.FLEX_FLOW.ROW_WRAP if wrap else lv.FLEX_FLOW.ROW)
    parent.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    parent.set_style_pad_column(10, 0)
    parent.set_style_pad_row(8, 0)


def panel(parent):
    p = lv.obj(parent)
    p.set_width(lv.pct(100))
    p.set_height(lv.SIZE_CONTENT)
    p.set_style_bg_color(c(PANEL), 0)
    p.set_style_border_width(0, 0)
    p.set_style_radius(10, 0)
    p.set_style_pad_all(10, 0)
    p.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return p


def button(parent, text, h, on_click, checkable=False):
    b = lv.button(parent)
    b.set_size(lv.SIZE_CONTENT, h)
    b.set_style_bg_color(c(LINE), 0)
    b.set_style_bg_color(c(ACCENT), lv.STATE.CHECKED)
    b.set_style_radius(8, 0)
    b.set_style_shadow_width(0, 0)
    if checkable:
        b.add_flag(lv.obj.FLAG.CHECKABLE)
    lb = label(b, text)
    lb.center()
    b.add_event_cb(lambda e: on_click(), lv.EVENT.CLICKED, None)
    return b, lb


def dropdown(parent, options, on_pick, list_height):
    dd = lv.dropdown(parent)
    dd.set_flex_grow(1)
    dd.set_style_min_width(140, 0)
    dd.set_options("\n".join(options))
    dd.set_style_bg_color(c(BG), 0)
    dd.set_style_text_color(c(TEXT), 0)
    dd.set_style_text_font(kit.small, 0)
    dd.set_style_border_color(c(LINE), 0)
    lst = dd.get_list()
    lst.set_style_bg_color(c(BG), 0)
    lst.set_style_text_color(c(TEXT), 0)
    lst.set_style_text_font(kit.small, 0)
    lst.set_style_max_height(list_height, 0)
    dd.add_event_cb(lambda e: on_pick(dd.get_selected()),
                    lv.EVENT.VALUE_CHANGED, None)
    return dd


def set_checked(obj, on):
    if on:
        obj.add_state(lv.STATE.CHECKED)
    else:
        obj.remove_state(lv.STATE.CHECKED)


def show(obj, on):
    if on:
        obj.remove_flag(lv.obj.FLAG.HIDDEN)
    else:
        obj.add_flag(lv.obj.FLAG.HIDDEN)


class Knob:
    """Drag up or down to turn it; double-click puts it back to the effect's
    default."""

    STEPS = 1000

    def __init__(self, parent, desc, size, on_change):
        self.desc = desc
        self.on_change = on_change
        self.root = lv.obj(parent)
        self.root.set_size(size + 16, size + 26)
        self.root.set_style_bg_opa(0, 0)
        self.root.set_style_border_width(0, 0)
        self.root.set_style_pad_all(0, 0)
        self.root.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.root.add_flag(lv.obj.FLAG.CLICKABLE)
        # A drag turns the knob; it doesn't scroll the grid behind it.
        self.root.remove_flag(lv.obj.FLAG.SCROLL_CHAIN_VER)
        self.arc = lv.arc(self.root)
        self.arc.set_size(size, size)
        self.arc.align(lv.ALIGN.TOP_MID, 0, 0)
        self.arc.set_range(0, self.STEPS)
        self.arc.set_bg_angles(135, 45)
        self.arc.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.arc.set_style_arc_width(7, lv.PART.MAIN)
        self.arc.set_style_arc_width(7, lv.PART.INDICATOR)
        self.arc.set_style_arc_color(c(LINE), lv.PART.MAIN)
        self.arc.set_style_arc_color(c(ACCENT), lv.PART.INDICATOR)
        self.arc.set_style_bg_color(c(TEXT), lv.PART.KNOB)
        self.arc.set_style_pad_all(3, lv.PART.KNOB)
        self.arc.set_style_pad_all(5, lv.PART.MAIN)
        self.value = label(self.arc, "", TEXT)
        self.value.center()
        self.name = label(self.root, desc["label"], MUTED)
        self.name.set_width(size + 16)
        self.name.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.name.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.name.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self._drag = None
        self.root.add_event_cb(lambda e: self._pressed(), lv.EVENT.PRESSED, None)
        self.root.add_event_cb(lambda e: self._pressing(), lv.EVENT.PRESSING, None)
        self.root.add_event_cb(lambda e: self._released(), lv.EVENT.RELEASED, None)
        self.root.add_event_cb(lambda e: self.reset(), lv.EVENT.DOUBLE_CLICKED, None)

    def _y(self):
        pt = lv.point_t()
        lv.indev_active().get_point(pt)
        return pt.y

    def _pressed(self):
        self._drag = (self._y(), self.arc.get_value())

    def _pressing(self):
        if self._drag is None:
            return
        y0, v0 = self._drag
        v = max(0, min(self.STEPS, v0 + (y0 - self._y()) * 4))
        if v != self.arc.get_value():
            self._apply(v)

    def _released(self):
        self._drag = None

    def _to_value(self, v):
        d = self.desc
        return d["min"] + (d["max"] - d["min"]) * v / self.STEPS

    def _to_steps(self, value):
        d = self.desc
        span = (d["max"] - d["min"]) or 1.0
        return int(round((value - d["min"]) * self.STEPS / span))

    def _apply(self, steps):
        self.show(self._to_value(steps))
        self.on_change(self.desc["key"], self._to_value(steps))

    def show(self, value):
        self.arc.set_value(self._to_steps(value))
        self.value.set_text("%.2f" % value)

    def turn(self, value):
        """Turn it as a hand would: the screen and the effect both follow."""
        self._apply(self._to_steps(value))

    def reset(self):
        self.turn(self.desc["default"])


class Screen:
    def __init__(self, app, scope):
        self.app = app
        W, H = scope.size
        narrow = W < NARROW
        self.knob_size = 64 if narrow else 84
        self.btn_h = 36 if narrow else 40
        self.list_h = H * 2 // 3
        self.knobs = {}
        self.status_label = kit.status(scope)
        scr = scope.root
        scr.set_style_bg_color(c(BG), 0)
        scr.set_style_bg_opa(255, 0)
        scr.set_style_pad_all(8, 0)
        scr.set_style_pad_row(8, 0)
        scr.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.scr = scr
        self._source()
        self._effect()
        self._footer()

    # -- the clip, or the live input ------------------------------------------

    def _source(self):
        p = panel(self.scr)
        flow(p)
        self.live_btn, _ = button(
            p, "Live", self.btn_h,
            lambda: self.app.set_live(self.live_btn.has_state(lv.STATE.CHECKED)),
            checkable=True)
        show(self.live_btn, self.app.can_go_live)
        names = self.app.clip_names() or ["(no clips found)"]
        self.clip_dd = dropdown(p, names, self.app.pick_clip, self.list_h)
        self.play_btn, self.play_text = button(p, lv.SYMBOL.PLAY + "  Play", self.btn_h,
                                               self.app.toggle_play)
        self.loop_btn, _ = button(p, lv.SYMBOL.LOOP + "  Loop", self.btn_h,
                                  lambda: self.app.set_loop(self.loop_btn.has_state(lv.STATE.CHECKED)),
                                  checkable=True)
        self.pos_label = label(p, "", MUTED)
        self.live_box = lv.obj(p)
        self.live_box.set_flex_grow(1)
        self.live_box.set_height(lv.SIZE_CONTENT)
        self.live_box.set_style_bg_opa(0, 0)
        self.live_box.set_style_border_width(0, 0)
        self.live_box.set_style_pad_all(0, 0)
        self.live_box.set_style_pad_row(2, 0)
        self.live_box.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.live_box.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.live_route = label(self.live_box, "", TEXT)
        self.live_clock = label(self.live_box, "", MUTED)
        self.lat_value = label(self.live_box, "", ACCENT, kit.font)
        self.lat_note = label(self.live_box, "", MUTED)
        for lb in (self.live_route, self.live_clock, self.lat_note):
            lb.set_width(lv.pct(100))
            lb.set_long_mode(lv.label.LONG_MODE.DOTS)
        show(self.live_box, False)

    def _clip_controls(self, on):
        for o in (self.clip_dd, self.play_btn, self.loop_btn, self.pos_label):
            show(o, on)
        show(self.live_box, not on)

    def show_live_button(self, on):
        set_checked(self.live_btn, on)

    def show_live(self, route, clock):
        """Where a live input comes from and goes, and whether the two ends
        share a clock."""
        self._clip_controls(False)
        self.show_live_button(True)
        self.live_route.set_text(route)
        self.live_clock.set_text(clock)
        self._clock_text = clock
        self.lat_value.set_text("")
        self.lat_note.set_text("")

    def show_clips(self):
        self._clip_controls(True)
        self.show_live_button(False)

    def show_latency(self, total, held, periods, extra=""):
        """The latency figure: the software hold plus the device periods.
        What the system's engine and the converters add beyond that isn't in
        it, and the note says so."""
        self.lat_value.set_text("%.0f ms" % total)
        self.lat_note.set_text("held %.0f + device periods %.0f; the system adds more"
                               % (held, periods))
        if extra:
            self.live_clock.set_text(self._clock_text + extra)

    def show_playing(self, on):
        txt = (lv.SYMBOL.STOP + "  Stop") if on else (lv.SYMBOL.PLAY + "  Play")
        self.play_text.set_text(txt)
        set_checked(self.play_btn, on)

    def show_loop(self, on):
        set_checked(self.loop_btn, on)

    def show_position(self, text):
        self.pos_label.set_text(text)

    # -- the effect slot ----------------------------------------------------

    def _effect(self):
        p = panel(self.scr)
        p.set_height(0)
        p.set_flex_grow(1)
        # On a small panel the screen scrolls instead of closing this up.
        p.set_style_min_height(self.btn_h + self.knob_size + 70, 0)
        p.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        p.set_style_pad_row(8, 0)
        head = lv.obj(p)
        head.set_width(lv.pct(100))
        head.set_height(lv.SIZE_CONTENT)
        head.set_style_bg_opa(0, 0)
        head.set_style_border_width(0, 0)
        head.set_style_pad_all(0, 0)
        head.remove_flag(lv.obj.FLAG.SCROLLABLE)
        flow(head)
        self.fx_dd = dropdown(head, self.app.effect_names(), self.app.pick_effect, self.list_h)
        self.defaults_btn, _ = button(head, "Defaults", self.btn_h, self.reset_knobs)
        self.all_btn, _ = button(
            head, "Show all", self.btn_h,
            lambda: self.app.set_show_all(self.all_btn.has_state(lv.STATE.CHECKED)),
            checkable=True)
        grid = lv.obj(p)
        grid.set_width(lv.pct(100))
        grid.set_height(0)
        grid.set_flex_grow(1)
        grid.set_style_bg_opa(0, 0)
        grid.set_style_border_width(0, 0)
        grid.set_style_pad_all(0, 0)
        grid.set_style_pad_column(10, 0)
        grid.set_style_pad_row(8, 0)
        grid.set_flex_flow(lv.FLEX_FLOW.ROW_WRAP)
        self.grid = grid

    def show_effect(self, effect, index):
        self.fx_dd.set_selected(index)
        self.grid.clean()
        self.knobs = {}
        for d in effect.parameters():
            k = Knob(self.grid, d, self.knob_size, self.app.turn)
            k.show(effect.get(d["key"]))
            self.knobs[d["key"]] = k

    def show_effect_list(self, names, index, show_all):
        self.fx_dd.set_options("\n".join(names))
        self.fx_dd.set_selected(index)
        set_checked(self.all_btn, show_all)

    def reset_knobs(self):
        for k in self.knobs.values():
            k.reset()

    # -- master -------------------------------------------------------------

    def _footer(self):
        p = panel(self.scr)
        flow(p)
        label(p, "MASTER", MUTED)
        s = lv.slider(p)
        s.set_flex_grow(1)
        s.set_style_min_width(100, 0)
        s.set_range(0, 100)
        s.set_style_bg_color(c(LINE), lv.PART.MAIN)
        s.set_style_bg_color(c(ACCENT), lv.PART.INDICATOR)
        s.set_style_bg_color(c(TEXT), lv.PART.KNOB)
        self.master = s
        self.master_label = label(p, "", TEXT)
        s.add_event_cb(lambda e: self.app.set_master(s.get_value() / 100),
                       lv.EVENT.VALUE_CHANGED, None)
        self.out_label = label(p, "", MUTED)

    def show_master(self, level):
        self.master.set_value(int(round(level * 100)), False)
        self.master_label.set_text("%d%%" % int(round(level * 100)))

    def show_status(self, text, good=False):
        self.status_label.set_text(text)
        self.status_label.set_style_text_color(c(GOOD if good else MUTED), 0)
