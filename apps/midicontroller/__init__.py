# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""MIDI Controller: pads, knobs, faders and keys that play a synth or a DAW.

The tabs along the top switch between the views a hardware controller
would have side by side:

- Pads: sixteen pads in a 4 x 4 grid that play notes (a drum kit's from
  36, at the bottom left), with four banks, A to D, each sixteen notes up.
- Knobs: sixteen endless knobs, 4 x 4, or 8 x 2 on a wide, short screen,
  on CC 70 to 85 (a synth's sound controllers: 74 is the filter cutoff).
- Faders: sixteen faders in a row, on CC 102 to 117.
- Mixer: eight strips, each a volume fader (CC 7) with mute and solo,
  strip 1 on the channel and each next strip one channel up, so they are
  the volumes of a synth's first eight parts.
- XY: a pad that sends two CCs at once (16 across, 17 up), and the
  transport: rewind, forward, stop, play, record and loop (CC 20 to 25).
- Keys: two octaves of keys with octave shift, and a modulation wheel.
- Setup: where it sends, the channel, the velocity, and the mapping.

A touch panel reads no pressure, so a pad's velocity comes from where the
finger lands: nearer the top is harder. A key is harder nearer its front
edge. Setup can fix the velocity instead.

MIDI goes out over whichever way this board has: USB as a MIDI device
(``usb-device-midi``), a synth on the USB host port, Bluetooth LE MIDI
(bledev), or, on a computer or in a browser page, the MIDI outputs the
Connections picker lists. Setup picks one when there are several, and an
output picked there is the one Connections uses too. What comes back moves
the controls to match, so a DAW's automation turns the knobs, and a note
played into the board lights its pad.

Edit in Setup shows each control's note or CC in its place; tap one to
change it. The mapping and the settings are kept in ``config.json`` in
the app's data folder (``/data/midicontroller`` on a board), holding only
what differs from the defaults. Fits a screen of 480 x 320 or larger.
"""

import lvgl as lv
from controlkit import LampButton, PadGrid, Slider
from controlkit import encoder as _encoder
from controlkit.theme import BLACK
from multimer import ticks_diff, ticks_ms
from touchkit import settings, ui

from . import links
from .surface import (
    BANKS,
    CC,
    NOTE,
    TRANSPORT,
    Surface,
    family,
    index,
    is_button,
    note_name,
)

#: How often what comes in is read and the status line caught up, in ms.
TICK_MS = 20
#: How long after a change the settings are saved, in ms: one write for a
#: run of taps, never one in the middle of playing.
SAVE_MS = 1500
#: The tabs: key and label.
VIEWS = (("pads", "Pads"), ("knobs", "Knobs"), ("faders", "Faders"), ("mixer", "Mixer"),
         ("xy", "XY"), ("keys", "Keys"), ("setup", lv.SYMBOL.SETTINGS))
#: Each bank's colour, for the pads it lights.
BANK_COLORS = (0x26C6DA, 0xFFB300, 0xEC407A, 0x7CB342)
#: The velocities Setup steps through: 0 is from the touch.
VELOCITIES = (0, 32, 48, 64, 80, 96, 100, 112, 127)
#: The lamps of the transport buttons.
TRANSPORT_LAMPS = (0xFFB300, 0xFFB300, 0xC9CCD1, 0x3BA55C, 0xE53935, 0x26C6DA)
#: A key of the keyboard strip: white keys in an octave, and where each black one sits.
WHITE = (0, 2, 4, 5, 7, 9, 11)
BLACK_KEYS = ((1, 1), (3, 2), (6, 4), (8, 5), (10, 6))  # (semitone, after which white key)


def _margin(W):
    return max(6, W // 80)


def _point():
    p = lv.point_t()
    indev = lv.indev_active()
    if indev is None:
        return None
    indev.get_point(p)
    return p.x, p.y


def _area(obj):
    a = lv.area_t()
    obj.get_coords(a)
    return a


def _frac_up(obj):
    """How far up *obj* the finger is: 0 at its bottom edge, 1 at its top."""
    p = _point()
    if p is None:
        return None
    a = _area(obj)
    h = max(1, a.y2 - a.y1)
    return (a.y2 - p[1]) / h


def _frac_down(obj):
    f = _frac_up(obj)
    return None if f is None else 1 - f


def _button(parent, text, cb, x, y, w, h, font=None, color=None):
    b, lbl = ui.button(parent, text, cb, w=w, h=h, font=font or ui.small, color=color or ui.KEY)
    b.set_pos(x, y)
    b.set_style_radius(8, 0)
    b.set_style_pad_all(2, 0)
    return b, lbl


def _on_edges(obj, down, up):
    """``down()`` when a finger lands on *obj*, ``up()`` when it lifts or slides off."""
    obj.add_event_cb(lambda e: down(), lv.EVENT.PRESSED, None)
    obj.add_event_cb(lambda e: up(), lv.EVENT.RELEASED, None)
    obj.add_event_cb(lambda e: up(), lv.EVENT.PRESS_LOST, None)


class _KnobPanel:
    """What controlkit's encoders ask of the panel they sit on."""

    fine = False

    def __init__(self, app, scale):
        self.app = app
        self.travel = max(80, int(200 * scale))

    def default_value(self, i):
        return 0

    def _turned(self, enc, value):
        self.app.moved("knob%d" % enc.index, value)

    def _focused(self, enc):
        pass


def _name(cid):
    """A control's short name: ``Pad 1``, ``Vol 3``, ``Play``."""
    f, i = family(cid), index(cid)
    if f == "tr":
        return TRANSPORT[i]
    if cid in ("x", "y"):
        return "XY " + cid.upper()
    if cid == "mod":
        return "Mod"
    return "%s %d" % ({"pad": "Pad", "knob": "Knob", "fader": "Fader", "mix": "Vol", "mute": "Mute",
                       "solo": "Solo"}[f], i + 1)


class Controller:
    """The app on one screen: the tabs, the view under them, the link out."""

    def __init__(self, scope, link_opener=None):
        self.scope = scope
        self.root = scope.root
        self.W, self.H = scope.size
        self._open = link_opener or links.open_link
        try:
            config = settings.config(scope, {})
        except Exception:  # noqa: BLE001 - a scope with no data folder starts from the defaults
            config = {}
        self.surface = Surface(config)
        self.link = None
        self.link_error = None
        self.choices = links.choices()
        self.view = None
        self.edit = False
        self.editing = None  # the control the editor is open on
        self.widgets = {}  # control id -> fn(value) that shows a value without sending
        self.parts = {}  # control id -> the widget it is on this view
        self.shown = None
        self._changed_at = None
        self._buf = bytearray(64)

        W, H = self.W, self.H
        m = _margin(W)
        self.m = m
        self.status = ui.label(self.root, "", ui.small, ui.MUTED)
        self.status.set_long_mode(lv.label.LONG_MODE.DOTS)  # a long one ends in dots, inside the row
        self.status.set_size(W - 2 * m, ui.small.line_height)
        self.status.set_pos(m, 4)
        row = ui.small.line_height + 8
        tab_h = max(34, min(48, H // 9))
        gap = 4
        tab_w = (W - 2 * m - gap * (len(VIEWS) - 1)) // len(VIEWS)
        self.tabs = {}
        for i, (key, text) in enumerate(VIEWS):
            b, _ = _button(self.root, text, lambda key=key: self.show(key), m + i * (tab_w + gap), row, tab_w, tab_h)
            b.set_style_bg_color(ui.ACCENT, lv.STATE.CHECKED)
            self.tabs[key] = b
        top = row + tab_h + m
        self.body = ui.plain(lv.obj(self.root))
        self.body.set_pos(0, top)
        self.body.set_size(W, H - top)
        self.BW, self.BH = W, H - top - m

        self.choose(self.surface.settings["output"], save=False)
        scope.on_close(self.close)
        self.show(self.surface.settings["view"], save=False)
        self.tick()
        scope.every(TICK_MS, self.tick)

    # -- the link out ---------------------------------------------------------

    def choose(self, key, save=True):
        """Send through the way out named *key*, or the first this board has."""
        keys = [k for k, _ in self.choices]
        if key is not None and (key.startswith("pc:") or key.startswith("web:")):
            key = self._chosen_now(key[key.index(":") + 1:])  # saved before the picker chose
        # An output saved last time may not be listed yet (a browser lists
        # none until the person allows MIDI again, a synth not started yet):
        # it stays chosen, and plays once it's there.
        kept = key is not None and key.startswith("out:") and any(k.startswith("out:") for k in keys)
        if key not in keys and not kept:
            key = self._chosen_now() or (keys[0] if keys else None)
        if self.link is not None:
            self.link.close()
            self.link = None
        self.surface.out = None
        self.link_error = None
        if key is not None:
            try:
                self.link = self._open(key)
                self.surface.out = self.link
            except Exception as e:  # noqa: BLE001 - said on the status line; Setup can pick another
                print("midicontroller:", key, e)
                self.link_error = "%s: %s" % (dict(self.choices).get(key, key), e)
        if save:
            self.surface.set("output", key)
            self._changed_at = ticks_ms()

    def close(self):
        if self.link is not None:
            self.link.close()
            self.link = None
        self.save()

    def save(self):
        if not self.surface.changed:
            return
        import json

        from appkit import data

        self.surface.changed = False
        self._changed_at = None
        try:
            with open(data.join(self.scope.data_dir, "config.json"), "w") as f:
                json.dump(self.surface.config(), f)
        except (OSError, AttributeError, ValueError) as e:
            print("midicontroller: couldn't save the settings:", e)

    # -- each tick --------------------------------------------------------------

    def tick(self, _t=None):
        link = self.link
        now = ticks_ms()
        if link is not None:
            try:
                link.poll()
            except Exception as e:  # noqa: BLE001 - the link says what's wrong on its status
                print("midicontroller:", e)
            for _ in range(8):  # a burst at most this many reads a tick, so the screen keeps up
                n = link.read_into(self._buf)
                if not n:
                    break
                for cid, value in self.surface.feed(memoryview(self._buf)[:n], now, ticks_diff):
                    show = self.widgets.get(cid)
                    if show is not None:
                        show(value)
        if self.surface.changed:
            if self._changed_at is None:
                self._changed_at = now
            elif ticks_diff(now, self._changed_at) >= SAVE_MS:
                self.save()
        self._status()

    def _status(self):
        s = self.surface
        if self.link_error:
            where = self.link_error
        elif self.link is not None:
            where = self.link.status()
        elif not self.choices:
            where = "no MIDI out on this board"
        else:
            where = "not sending"
        text = "%s   ch %d" % (where, s.settings["channel"])
        if self.edit and self.view != "setup":
            text = "Editing: tap a control to change what it sends"
        elif s.error:
            text += "   " + s.error
        elif s.last is not None:
            text += "   " + describe(s.last)
        if text != self.shown:
            self.shown = text
            self.status.set_text(text)

    # -- what the controls call -------------------------------------------------

    def moved(self, cid, value):
        self.surface.move(cid, value, ticks_ms())

    # -- views --------------------------------------------------------------------

    def show(self, key, save=True):
        """Open the view *key*, from its tab."""
        if key not in self.tabs:
            key = "pads"
        for k, b in self.tabs.items():
            if k == key:
                b.add_state(lv.STATE.CHECKED)
            else:
                b.remove_state(lv.STATE.CHECKED)
        self.view = key
        self.editing = None
        if save and self.surface.settings["view"] != key:
            self.surface.set("view", key)
        self._build()

    def later(self, fn):
        """Run *fn* after this event: a button can't clean the view it's in."""
        self.body.add_flag(lv.obj.FLAG.HIDDEN)

        def run(_t=None):
            self.body.remove_flag(lv.obj.FLAG.HIDDEN)
            fn()

        self.scope.after(10, run)

    def _build(self):
        self.body.clean()
        self.widgets = {}
        self.parts = {}
        if self.editing is not None:
            self._editor(self.editing)
        elif self.view == "setup":
            self._setup()
        elif self.edit:
            self._map()
        else:
            getattr(self, "_" + self.view)()

    def _pads(self):
        W, BH, m = self.BW, self.BH, self.m
        bank_w = max(52, W // 12)
        s = min(BH, W - 3 * m - bank_w)
        x0 = (W - s - m - bank_w) // 2
        grid = PadGrid(self.body, x0, 0, s, s, BLACK, cols=4, rows=4, gap=max(4, s // 60),
                       on_down=self._pad_down, on_up=self._pad_up)
        self.grid = grid
        color = BANK_COLORS[self.surface.settings["bank"]]
        for g in range(16):
            cid = "pad%d" % self._pad_of(g)
            grid.set_label(g, self.surface.describe(cid))

            def show(value, g=g):
                grid.set_color(g, color if value else None)

            self.widgets[cid] = show
            if self.surface.values.get(cid):
                show(1)
        bh = (s - 3 * 6) // 4
        for i, name in enumerate(BANKS):
            b, _ = _button(self.body, name, lambda i=i: self._bank(i), x0 + s + m, i * (bh + 6), bank_w, bh,
                           font=ui.font)
            if i == self.surface.settings["bank"]:
                b.set_style_bg_color(lv.color_hex(BANK_COLORS[i]), 0)

    @staticmethod
    def _pad_of(g):
        """The pad number of grid cell *g*: pad 0 at the bottom left, as pads count."""
        row, col = divmod(g, 4)
        return (3 - row) * 4 + col

    def _pad_down(self, grid, g):
        self.surface.press("pad%d" % self._pad_of(g), _frac_up(grid.pad(g)))
        grid.set_color(g, BANK_COLORS[self.surface.settings["bank"]])

    def _pad_up(self, grid, g):
        self.surface.release("pad%d" % self._pad_of(g))
        grid.set_color(g, None)

    def _bank(self, i):
        self.surface.set("bank", i)
        self.later(self._build)

    def _knobs(self):
        W, BH, m = self.BW, self.BH, self.m
        # 4 x 4, or 8 x 2 where that makes each knob bigger.
        best = None
        for cols, rows in ((4, 4), (8, 2)):
            cw, ch = (W - 2 * m) // cols, BH // rows
            size = min(cw, ch - 16)
            if best is None or size > best[0]:
                best = (size, cols, rows, cw, ch)
        _, cols, rows, cw, ch = best
        scale = min(self.W / 800, self.H / 480)
        geom = _encoder.geometry(cw, ch, scale)
        panel = _KnobPanel(self, scale)
        x0 = (W - cols * cw) // 2
        for i in range(16):
            r, c = divmod(i, cols)
            cid = "knob%d" % i
            enc = _encoder.Encoder(panel, self.body, i, self.surface.describe(cid), x0 + c * cw, r * ch, cw, ch,
                                   geom, BLACK)
            enc.obj.remove_flag(lv.obj.FLAG.GESTURE_BUBBLE)
            enc.set_value(self.surface.values.get(cid, 0))
            self.widgets[cid] = enc.set_value
            self.parts[cid] = enc

    def _slider(self, cid, x, y, w, h, legend):
        def changed(s, value):
            self.moved(cid, value)

        sl = Slider(self.body, x, y, w, h, BLACK, legend=legend, value=self.surface.values.get(cid, 0),
                    on_change=changed)
        sl.obj.remove_flag(lv.obj.FLAG.GESTURE_BUBBLE)
        self.widgets[cid] = sl.set_value
        self.parts[cid] = sl
        return sl

    def _faders(self):
        W, BH, m = self.BW, self.BH, self.m
        cw = (W - 2 * m) // 16
        x0 = (W - 16 * cw) // 2
        for i in range(16):
            self._slider("fader%d" % i, x0 + i * cw + 1, 0, cw - 2, BH, str(i + 1))

    def _mixer(self):
        W, BH, m = self.BW, self.BH, self.m
        sw = (W - 2 * m) // 8
        x0 = (W - 8 * sw) // 2
        bh = max(18, min(34, BH // 10))
        lamp_h = bh + 16  # a lamp button's legend sits over its cap
        fader_h = BH - 2 * (lamp_h + 6)
        for i in range(8):
            x = x0 + i * sw
            self._slider("mix%d" % i, x + 2, 0, sw - 4, fader_h, str(i + 1))
            for j, (fam, lamp) in enumerate((("mute", 0xFFB300), ("solo", 0x3BA55C))):
                cid = "%s%d" % (fam, i)

                def pressed(b, on, cid=cid):
                    self.surface.press(cid)

                b = LampButton(self.body, x + 4, fader_h + 6 + j * (lamp_h + 6), sw - 8, bh, BLACK,
                               legend=fam, toggle=True, lamp=lamp, on_press=pressed)
                b.set_on(bool(self.surface.values.get(cid)))
                self.widgets[cid] = lambda v, b=b: b.set_on(v >= 64)
                self.parts[cid] = b

    def _xy(self):
        W, BH, m = self.BW, self.BH, self.m
        s = min(BH, (W - 3 * m) // 2)
        pad = ui.plain(lv.obj(self.body))
        pad.set_pos(m, 0)
        pad.set_size(s, s)
        pad.set_style_bg_color(ui.PANEL, 0)
        pad.set_style_bg_opa(lv.OPA.COVER, 0)
        pad.set_style_radius(12, 0)
        pad.add_flag(lv.obj.FLAG.CLICKABLE)
        pad.remove_flag(lv.obj.FLAG.GESTURE_BUBBLE)
        for w, h in ((s - 24, 1), (1, s - 24)):
            line = ui.plain(lv.obj(pad))
            line.set_size(w, h)
            line.set_style_bg_color(ui.KEY, 0)
            line.set_style_bg_opa(lv.OPA.COVER, 0)
            line.center()
        d = max(16, s // 10)
        dot = ui.plain(lv.obj(pad))
        dot.set_size(d, d)
        dot.set_style_radius(lv.RADIUS_CIRCLE, 0)
        dot.set_style_bg_color(ui.ACCENT, 0)
        dot.set_style_bg_opa(lv.OPA.COVER, 0)
        dot.remove_flag(lv.obj.FLAG.CLICKABLE)
        reach = s - d
        vals = self.surface.values

        def place():
            dot.set_pos(vals.get("x", 64) * reach // 127, reach - vals.get("y", 64) * reach // 127)

        def touched(e):
            p = _point()
            if p is None:
                return
            a = _area(pad)
            x = min(127, max(0, (p[0] - a.x1 - d // 2) * 127 // max(1, reach)))
            y = min(127, max(0, (a.y2 - p[1] - d // 2) * 127 // max(1, reach)))
            if x != vals.get("x"):
                self.moved("x", x)
            if y != vals.get("y"):
                self.moved("y", y)
            place()

        pad.add_event_cb(touched, lv.EVENT.PRESSED, None)
        pad.add_event_cb(touched, lv.EVENT.PRESSING, None)
        place()
        self.xy = pad
        self.widgets["x"] = self.widgets["y"] = lambda v: place()

        # The transport, three by two beside it.
        x0 = m + s + m
        cw = (W - x0 - m) // 3
        bh = max(24, min(56, (BH - 2 * 16 - m) // 2))
        y0 = (BH - 2 * (bh + 16) - m) // 2
        for i, name in enumerate(TRANSPORT):
            r, c = divmod(i, 3)
            cid = "tr%d" % i

            def pressed(b, on, cid=cid):
                self.surface.press(cid)
                self.surface.release(cid)

            self.parts[cid] = LampButton(self.body, x0 + c * cw + 3, y0 + r * (bh + 16 + m), cw - 6, bh, BLACK,
                                         legend=name, lamp=TRANSPORT_LAMPS[i], on_press=pressed)

    def _keys(self):
        W, BH, m = self.BW, self.BH, self.m
        mod_w = max(40, W // 16)
        self._slider("mod", m, 0, mod_w, BH, "Mod")
        x0 = m + mod_w + m
        row_h = max(30, min(44, BH // 6))
        kw_all = W - x0 - m
        oct_w = max(56, kw_all // 6)
        _button(self.body, lv.SYMBOL.LEFT + " Oct", lambda: self._octave(-1), x0, 0, oct_w, row_h)
        _button(self.body, "Oct " + lv.SYMBOL.RIGHT, lambda: self._octave(1), x0 + kw_all - oct_w, 0, oct_w, row_h)
        lo = self.surface.key_note(0)
        rng = ui.label(self.body, "%s to %s" % (note_name(max(0, lo)), note_name(min(127, lo + 23))), ui.small,
                       ui.MUTED)
        rng.align_to(self.body, lv.ALIGN.TOP_LEFT, x0 + kw_all // 2 - 40, (row_h - ui.small.line_height) // 2)
        rng.set_width(80)
        rng.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        top = row_h + m
        kh = BH - top
        whites = ui.plain(lv.obj(self.body))
        whites.set_pos(x0, top)
        whites.set_size(kw_all, kh)
        blacks = ui.plain(lv.obj(self.body))  # over the whites, in a layer of its own
        blacks.set_pos(x0, top)
        blacks.set_size(kw_all, kh * 3 // 5)
        blacks.remove_flag(lv.obj.FLAG.CLICKABLE)  # a touch between black keys reaches the white key under it
        ww = kw_all // 14
        self.keys = {}
        for octave in range(2):
            for j, semi in enumerate(WHITE):
                k = octave * 12 + semi
                key = self._key(whites, k, (octave * 7 + j) * ww + 1, 0, ww - 2, kh, ui.WHITE)
                if semi == 0:
                    lbl = ui.label(key, note_name(self.surface.key_note(k)) if lo + k <= 127 else "", ui.tiny,
                                   lv.color_hex(0x404040))
                    lbl.align(lv.ALIGN.BOTTOM_MID, 0, -4)
            for semi, after in BLACK_KEYS:
                k = octave * 12 + semi
                bw = ww * 3 // 5
                self._key(blacks, k, (octave * 7 + after) * ww - bw // 2, 0, bw, kh * 3 // 5, lv.color_hex(0x15171C))

    def _key(self, parent, k, x, y, w, h, color):
        key = ui.plain(lv.obj(parent))
        key.set_pos(x, y)
        key.set_size(w, h)
        key.set_style_bg_color(color, 0)
        key.set_style_bg_opa(lv.OPA.COVER, 0)
        key.set_style_bg_color(ui.ACCENT, lv.STATE.PRESSED)
        key.set_style_radius(4, 0)
        key.add_flag(lv.obj.FLAG.CLICKABLE)
        key.remove_flag(lv.obj.FLAG.GESTURE_BUBBLE)
        _on_edges(key, lambda: self.surface.key(k, True, _frac_down(key)), lambda: self.surface.key(k, False))
        self.keys[k] = key
        return key

    def _octave(self, step):
        self.surface.set("octave", self.surface.settings["octave"] + step)
        self.later(self._build)

    # -- setup, and editing the mapping ----------------------------------------------

    def _setup(self):
        W, BH, m = self.BW, self.BH, self.m
        s = self.surface
        rows = 4
        rh = min(52, (BH - (rows - 1) * m) // rows)
        name_w = max(96, W // 5)
        bw = max(44, rh)
        val_w = min(320, W - 2 * m - name_w - 2 * bw - 2 * m)

        def row(i, name, value, minus, plus):
            y = i * (rh + m)
            ui.label(self.body, name, ui.small, ui.MUTED).set_pos(m, y + (rh - ui.small.line_height) // 2)
            x = m + name_w
            _button(self.body, lv.SYMBOL.LEFT, minus, x, y, bw, rh, font=ui.font)
            v = ui.label(self.body, value, ui.small, ui.WHITE)
            v.set_long_mode(lv.label.LONG_MODE.DOTS)
            v.set_size(val_w, ui.small.line_height)
            v.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            v.set_pos(x + bw + m, y + (rh - ui.small.line_height) // 2)
            _button(self.body, lv.SYMBOL.RIGHT, plus, x + bw + 2 * m + val_w, y, bw, rh, font=ui.font)

        self.choices = links.choices()
        names = dict(self.choices)
        key = self.link.key if self.link is not None else s.settings["output"]
        row(0, "Send to", self._out_name(key) or names.get(key) or "nowhere", lambda: self._output(-1), lambda: self._output(1))
        row(1, "Channel", str(s.settings["channel"]), lambda: self._set("channel", -1),
            lambda: self._set("channel", 1))
        vel = s.settings["velocity"]
        row(2, "Velocity", "from the touch" if not vel else "always %d" % vel, lambda: self._set("velocity", -1),
            lambda: self._set("velocity", 1))
        y = 3 * (rh + m)
        n = 3
        w = (W - 2 * m - (n - 1) * m) // n
        b, _ = _button(self.body, "Edit mapping", self._toggle_edit, m, y, w, rh)
        if self.edit:
            b.set_style_bg_color(ui.ACCENT, 0)
        _button(self.body, "Reset mapping", self._reset_all, m + (w + m), y, w, rh)
        _button(self.body, "All notes off", s.panic, m + 2 * (w + m), y, w, rh)

    def _chosen_now(self, label=None):
        """The key of the output chosen in Connections now (or the listed one
        called *label*), when there is one, else None."""
        for key, name in self.choices:
            if key.startswith("out:") and (name == label if label is not None else self._is_chosen(key[4:])):
                return key
        return None

    @staticmethod
    def _is_chosen(ep_id):
        try:
            import endpointkit
        except ImportError:
            return False
        return ep_id in endpointkit.selection("midi.out")

    def _out_name(self, key):
        """What the controller plays when that's the Connections choice, or None."""
        names = getattr(self.link, "names", None)
        return names() if names is not None and key and key.startswith("out:") else None

    def _output(self, step):
        self.choices = links.choices()  # a browser lists its outputs once the person says yes
        keys = [k for k, _ in self.choices]
        if not keys:
            return
        cur = self.link.key if self.link is not None else self.surface.settings["output"]
        if cur not in keys or (cur.startswith("out:") and not self._is_chosen(cur[4:])):
            cur = self._chosen_now() or cur  # what Connections chose since
        i = keys.index(cur) if cur in keys else -step
        self.choose(keys[(i + step) % len(keys)])
        self.later(self._build)

    def _set(self, key, step):
        v = self.surface.settings[key]
        if key == "velocity":
            # Along the ladder, from where v sits on it.
            i = 0
            while i + 1 < len(VELOCITIES) and VELOCITIES[i + 1] <= v:
                i += 1
            v = VELOCITIES[min(len(VELOCITIES) - 1, max(0, i + step))]
        else:
            v += step
        self.surface.set(key, v)
        self.later(self._build)

    def _toggle_edit(self):
        self.edit = not self.edit
        self.later(self._build)

    def _reset_all(self):
        self.surface.reset()
        self.later(self._build)

    def _map(self):
        """The view's controls as buttons in their places, each with what it sends."""
        v = self.view
        if v == "pads":
            cids, cols = ["pad%d" % self._pad_of(g) for g in range(16)], 4
        elif v == "knobs":
            cids, cols = ["knob%d" % i for i in range(16)], 4
        elif v == "faders":
            cids, cols = ["fader%d" % i for i in range(16)], 4
        elif v == "mixer":
            cids, cols = ["%s%d" % (f, i) for f in ("mix", "mute", "solo") for i in range(8)], 8
        elif v == "xy":
            cids, cols = ["x", "y"] + ["tr%d" % i for i in range(len(TRANSPORT))], 4
        else:
            cids, cols = ["mod"], 1
        W, BH, m = self.BW, self.BH, self.m
        rows = (len(cids) + cols - 1) // cols
        cw = (W - 2 * m) // cols
        ch = min(72, BH // rows)
        font = ui.small if cw >= 96 else ui.tiny
        for i, cid in enumerate(cids):
            r, c = divmod(i, cols)
            b, lbl = _button(self.body, "%s\n%s" % (_name(cid), self.surface.describe(cid)),
                             lambda cid=cid: self._open_editor(cid), m + c * cw + 2, r * ch + 2, cw - 4, ch - 4,
                             font=font, color=ui.PANEL)
            lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            self.parts["map:" + cid] = b
        if v == "keys":
            hint = ui.label(self.body, "The keys play the channel; Oct moves them.", ui.small, ui.MUTED)
            hint.set_pos(m, ch + m)

    def _open_editor(self, cid):
        self.editing = cid
        self.later(self._build)

    def _editor(self, cid):
        W, BH, m = self.BW, self.BH, self.m
        s = self.surface
        kind, num = s.map[cid]
        title = ui.label(self.body, "%s sends %s" % (_name(cid), s.describe(cid)), ui.font, ui.WHITE)
        title.set_pos(m, 0)
        rh = min(52, (BH - ui.font.line_height - 3 * m) // 3)
        y = ui.font.line_height + m
        if is_button(cid):
            w = (W - 3 * m) // 2
            for i, (k, text) in enumerate(((NOTE, "Note"), (CC, "CC"))):
                b, _ = _button(self.body, text, lambda k=k: self._remap(cid, kind=k), m + i * (w + m), y, w, rh)
                if k == kind:
                    b.set_style_bg_color(ui.ACCENT, 0)
            y += rh + m
        steps = (-10, -1, 1, 10)
        val_w = max(80, W // 5)
        bw = (W - 2 * m - val_w - 4 * m) // 4
        x = m
        for i, step in enumerate(steps):
            _button(self.body, "%+d" % step, lambda step=step: self._remap(cid, number=num + step), x, y, bw, rh,
                    font=ui.font)
            x += bw + m
            if i == 1:
                v = ui.label(self.body, str(num), ui.big, ui.WHITE)
                v.set_width(val_w)
                v.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
                v.set_pos(x, y + (rh - ui.big.line_height) // 2)
                x += val_w + m
        y += rh + m
        w = (W - 3 * m) // 2
        _button(self.body, "Default", lambda: self._remap(cid, default=True), m, y, w, rh)
        _button(self.body, "Done", self._close_editor, 2 * m + w, y, w, rh, color=ui.ACCENT)

    def _remap(self, cid, kind=None, number=None, default=False):
        if default:
            self.surface.reset(cid)
        else:
            self.surface.remap(cid, kind=kind, number=number)
        self.later(self._build)

    def _close_editor(self):
        self.editing = None
        self.later(self._build)


def describe(msg):
    """A sent message for the status line: ``Note C1 100``, ``CC 74 = 64``."""
    status = msg[0] & 0xF0
    if status == 0x90 and msg[2]:
        return "Note %s %d" % (note_name(msg[1]), msg[2])
    if status in (0x80, 0x90):
        return "Note %s off" % note_name(msg[1])
    if status == 0xB0:
        return "CC %d = %d" % (msg[1], msg[2])
    return " ".join("%02X" % b for b in msg)


def main(scope):
    return Controller(scope)
