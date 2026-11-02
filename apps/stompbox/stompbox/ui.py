"""The screen: an LVGL panel over the engine. The same code draws on a board
with a display and in a desktop window.

Knobs are built from the effect adapter's parameter descriptions, so any
library's effect gets a panel without screen code of its own.
"""

import lvgl as lv

BG = 0x15171A
PANEL = 0x1F2226
LINE = 0x33373D
TEXT = 0xE8E6E1
MUTED = 0x8C9096
ACCENT = 0xF2A33A      # amber, like a pedal's LED
GOOD = 0x63C27A

KNOB = 92


def c(hex_):
    return lv.color_hex(hex_)


def label(parent, text, colour=TEXT, font=None):
    lb = lv.label(parent)
    lb.set_text(text)
    lb.set_style_text_color(c(colour), 0)
    if font is not None:
        lb.set_style_text_font(font, 0)
    return lb


def panel(parent, x, y, w, h):
    p = lv.obj(parent)
    p.set_pos(x, y)
    p.set_size(w, h)
    p.set_style_bg_color(c(PANEL), 0)
    p.set_style_border_width(0, 0)
    p.set_style_radius(10, 0)
    p.set_style_pad_all(14, 0)
    p.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return p


def button(parent, text, w, h, on_click, checkable=False):
    b = lv.button(parent)
    b.set_size(w, h)
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


def dropdown(parent, options, w, on_pick):
    dd = lv.dropdown(parent)
    dd.set_width(w)
    dd.set_options("\n".join(options))
    dd.set_style_bg_color(c(BG), 0)
    dd.set_style_text_color(c(TEXT), 0)
    dd.set_style_border_color(c(LINE), 0)
    lst = dd.get_list()
    lst.set_style_bg_color(c(BG), 0)
    lst.set_style_text_color(c(TEXT), 0)
    lst.set_style_max_height(360, 0)
    dd.add_event_cb(lambda e: on_pick(dd.get_selected()),
                    lv.EVENT.VALUE_CHANGED, None)
    return dd


class Knob:
    """Drag up or down to turn it (Shift-free fine control: drag slowly);
    double-click puts it back to the effect's default."""

    STEPS = 1000

    def __init__(self, parent, desc, on_change):
        self.desc = desc
        self.on_change = on_change
        self.root = lv.obj(parent)
        self.root.set_size(KNOB + 16, KNOB + 34)
        self.root.set_style_bg_opa(0, 0)
        self.root.set_style_border_width(0, 0)
        self.root.set_style_pad_all(0, 0)
        self.root.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.root.add_flag(lv.obj.FLAG.CLICKABLE)
        self.arc = lv.arc(self.root)
        self.arc.set_size(KNOB, KNOB)
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
        self.name.set_width(KNOB + 16)
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
    def __init__(self, app, width, height):
        self.app = app
        self.W = width
        self.H = height
        self.knobs = {}
        scr = lv.screen_active()
        scr.set_style_bg_color(c(BG), 0)
        scr.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.scr = scr
        self._header()
        self._source()
        self._effect()
        self._footer()

    # -- header ------------------------------------------------------------

    def _header(self):
        t = label(self.scr, "STOMPBOX", ACCENT, lv.font_montserrat_24)
        t.set_pos(20, 16)
        self.out_label = label(self.scr, "", MUTED)
        self.out_label.align(lv.ALIGN.TOP_RIGHT, -20, 22)

    # -- the clip and the transport -----------------------------------------

    def _source(self):
        p = panel(self.scr, 16, 60, self.W - 32, 76)
        self.src_panel = p
        self.clip_tag = lb = label(p, "CLIP", MUTED)
        lb.align(lv.ALIGN.LEFT_MID, 0, 0)
        names = self.app.clip_names() or ["(no clips found)"]
        self.clip_dd = dropdown(p, names, 380, self.app.pick_clip)
        self.clip_dd.align(lv.ALIGN.LEFT_MID, 50, 0)
        self.play_btn, self.play_text = button(p, lv.SYMBOL.PLAY + "  Play", 120, 44,
                               self.app.toggle_play)
        self.play_btn.align(lv.ALIGN.LEFT_MID, 450, 0)
        self.loop_btn, _ = button(p, lv.SYMBOL.LOOP + "  Loop", 110, 44,
                               lambda: self.app.set_loop(self.loop_btn.has_state(lv.STATE.CHECKED)),
                               checkable=True)
        self.loop_btn.align(lv.ALIGN.LEFT_MID, 584, 0)
        self.pos_label = label(p, "", MUTED)
        self.pos_label.align(lv.ALIGN.RIGHT_MID, 0, 0)

    def show_live(self, route, clock):
        """The source panel for a live input: where it comes from and goes,
        whether the two ends share a clock, and room for the latency."""
        for o in (self.clip_tag, self.clip_dd, self.play_btn, self.loop_btn, self.pos_label):
            o.add_flag(lv.obj.FLAG.HIDDEN)
        p = self.src_panel
        if getattr(self, "live_route", None) is None:
            tag = label(p, "LIVE", ACCENT)
            tag.align(lv.ALIGN.TOP_LEFT, 0, 0)
            self.live_route = label(p, "", TEXT)
            self.live_route.set_width(self.W - 32 - 28 - 50 - 350)
            self.live_route.set_long_mode(lv.label.LONG_MODE.DOTS)
            self.live_route.align(lv.ALIGN.TOP_LEFT, 50, 0)
            self.live_clock = label(p, "", MUTED)
            self.live_clock.set_width(self.W - 32 - 28 - 50 - 350)
            self.live_clock.set_long_mode(lv.label.LONG_MODE.DOTS)
            self.live_clock.align(lv.ALIGN.BOTTOM_LEFT, 50, 0)
            self.lat_value = label(p, "-- ms", ACCENT, lv.font_montserrat_24)
            self.lat_value.align(lv.ALIGN.TOP_RIGHT, 0, -4)
            self.lat_note = label(p, "", MUTED)
            self.lat_note.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        self.live_route.set_text(route)
        self.live_clock.set_text(clock)
        self._clock_text = clock

    def show_latency(self, total, held, periods, extra=""):
        """The latency figure: the software hold plus the device periods.
        What Windows' engine and the converters add beyond that isn't in it,
        and the note says so."""
        if getattr(self, "lat_value", None) is None:
            return
        self.lat_value.set_text("%.0f ms" % total)
        self.lat_value.align(lv.ALIGN.TOP_RIGHT, 0, -4)
        self.lat_note.set_text("held %.0f + device periods %.0f; Windows adds more"
                               % (held, periods))
        self.lat_note.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        if extra:
            self.live_clock.set_text(self._clock_text + extra)

    def show_playing(self, on):
        txt = (lv.SYMBOL.STOP + "  Stop") if on else (lv.SYMBOL.PLAY + "  Play")
        self.play_text.set_text(txt)
        if on:
            self.play_btn.add_state(lv.STATE.CHECKED)
        else:
            self.play_btn.remove_state(lv.STATE.CHECKED)

    def show_loop(self, on):
        if on:
            self.loop_btn.add_state(lv.STATE.CHECKED)
        else:
            self.loop_btn.remove_state(lv.STATE.CHECKED)

    def show_position(self, text):
        self.pos_label.set_text(text)

    # -- the effect slot ----------------------------------------------------

    def _effect(self):
        p = panel(self.scr, 16, 148, self.W - 32, self.H - 148 - 92)
        self.fx_panel = p
        self.lib_label = label(p, "", MUTED)
        self.lib_label.set_pos(0, 10)
        self.fx_dd = dropdown(p, self.app.effect_names(), 300, self.app.pick_effect)
        self.fx_dd.set_pos(110, 0)
        self.defaults_btn, _ = button(p, "Defaults", 100, 40, self.reset_knobs)
        self.defaults_btn.set_pos(424, 0)
        self.all_btn, _ = button(
            p, "Show all", 110, 40,
            lambda: self.app.set_show_all(self.all_btn.has_state(lv.STATE.CHECKED)),
            checkable=True)
        self.all_btn.set_pos(536, 0)
        self.fx_note = label(p, "", MUTED)
        self.fx_note.align(lv.ALIGN.TOP_RIGHT, 0, 10)
        grid = lv.obj(p)
        grid.set_pos(0, 56)
        grid.set_size(self.W - 32 - 28, self.H - 148 - 92 - 28 - 56)
        grid.set_style_bg_opa(0, 0)
        grid.set_style_border_width(0, 0)
        grid.set_style_pad_all(0, 0)
        grid.set_style_pad_column(14, 0)
        grid.set_style_pad_row(10, 0)
        grid.set_flex_flow(lv.FLEX_FLOW.ROW_WRAP)
        self.grid = grid

    def show_effect(self, effect, index):
        self.lib_label.set_text(effect.library.upper())
        self.fx_dd.set_selected(index)
        self.grid.clean()
        self.knobs = {}
        params = effect.parameters()
        for d in params:
            k = Knob(self.grid, d, self.app.turn)
            k.show(effect.get(d["key"]))
            self.knobs[d["key"]] = k
        self.fx_note.set_text("%d knobs" % len(params) if params
                              else "no knobs")

    def show_effect_list(self, names, index, show_all):
        self.fx_dd.set_options("\n".join(names))
        self.fx_dd.set_selected(index)
        if show_all:
            self.all_btn.add_state(lv.STATE.CHECKED)
        else:
            self.all_btn.remove_state(lv.STATE.CHECKED)

    def reset_knobs(self):
        for k in self.knobs.values():
            k.reset()

    # -- master -------------------------------------------------------------

    def _footer(self):
        p = panel(self.scr, 16, self.H - 80, self.W - 32, 64)
        lb = label(p, "MASTER", MUTED)
        lb.align(lv.ALIGN.LEFT_MID, 0, 0)
        s = lv.slider(p)
        s.set_width(360)
        s.set_range(0, 100)
        s.align(lv.ALIGN.LEFT_MID, 80, 0)
        s.set_style_bg_color(c(LINE), lv.PART.MAIN)
        s.set_style_bg_color(c(ACCENT), lv.PART.INDICATOR)
        s.set_style_bg_color(c(TEXT), lv.PART.KNOB)
        self.master = s
        self.master_label = label(p, "", TEXT)
        self.master_label.align(lv.ALIGN.LEFT_MID, 460, 0)
        s.add_event_cb(lambda e: self.app.set_master(s.get_value() / 100),
                       lv.EVENT.VALUE_CHANGED, None)
        self.status = label(p, "", MUTED)
        self.status.align(lv.ALIGN.RIGHT_MID, 0, 0)

    def show_master(self, level):
        self.master.set_value(int(round(level * 100)), False)
        self.master_label.set_text("%d%%" % int(round(level * 100)))

    def show_status(self, text, good=False):
        self.status.set_text(text)
        self.status.set_style_text_color(c(GOOD if good else MUTED), 0)
