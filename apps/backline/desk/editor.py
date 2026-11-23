# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The desk's editor tab: change the song while it plays.

On the left, the song's form (tap a part to edit it), the part's step grid
and a pager for its bars. On the right, the song library, the kits of all
three kinds, and a mixer: the kit's volume and a fader for each group of
drums. Every change is an op or a command through the desk's panel, so it
reaches the sound at once and every other screen shows it.

While Follow is on, the grid shows whatever part plays and turns its bars
with it; picking a part turns Follow off.
"""

import lvgl as lv

try:
    from time import ticks_diff, ticks_ms
except ImportError:
    from multimer import ticks_diff, ticks_ms

from . import look
from .. import parts as song
from ..floor import text_width
from .grid import Grid
from .strip import Strip

SEND_MS = 60                  # a moving fader sends at most this often
FADERS = ("volume", "kick", "snare", "hats", "toms", "cymbals", "perc")
# The faders' names, longest first: the first set whose names all keep
# FADER_GAP pixels apart under their faders is the one shown.
FADER_NAMES = (("VOL", "KICK", "SNARE", "HATS", "TOMS", "CYM", "PERC"),
               ("VOL", "KCK", "SNR", "HAT", "TOM", "CYM", "PRC"),
               ("VOL", "BD", "SD", "HH", "TOM", "CY", "PRC"))
FADER_GAP = 6


def fader_names(slot, fnt):
    """The first of `FADER_NAMES` whose names, each centred in a ``slot``
    pixels wide, keep `FADER_GAP` apart in ``fnt``; else the shortest."""
    for names in FADER_NAMES:
        widths = [text_width(n, fnt) for n in names]
        if max(widths) <= slot and all(slot - (a + b) // 2 >= FADER_GAP for a, b in zip(widths, widths[1:])):
            return names
    return FADER_NAMES[-1]


class Editor:
    """The editor in ``parent`` at ``(x, y)``, ``w`` by ``h``, for ``desk``."""

    def __init__(self, parent, x, y, w, h, desk):
        self.desk = desk
        s = desk.scale
        m = desk.m
        self.base = look.plain(lv.obj(parent))
        self.base.set_pos(int(x), int(y))
        self.base.set_size(int(w), int(h))
        f = desk.fonts
        rw = int(w * 0.3)
        lw = int(w) - rw - 3 * m
        self.follow = True
        self.block = -1
        self.pattern = -1
        self.bar = 0
        self.bars = 1
        self.cols, self.ticks = 16, song.BAR // 16
        self.voices = []
        self.blocks = []
        self.sent = {}

        # -- left: the form, the toolbar, the grid --
        sh = int(56 * s)
        self.strip = Strip(self.base, m, m, lw, sh, f["small"], on_pick=self._pick)
        ty = m + sh + m
        th = int(36 * s)
        bar = look.box(self.base, m, ty, lw, th, look.PANEL, 8, look.LINE)
        self.part = look.text(bar, "", f["body"], look.AMBER, int(lw * 0.3))
        self.part.align(lv.ALIGN.LEFT_MID, 10, 0)
        self.info = look.text(bar, "", f["small"], look.DIM, int(lw * 0.22))
        self.info.align(lv.ALIGN.LEFT_MID, int(lw * 0.3) + 14, 0)
        bw = int(th * 1.1)
        fx = lw - int(84 * s) - 4
        self.follow_btn = look.button(bar, fx, 3, int(84 * s), th - 8, "FOLLOW", fnt=f["small"],
                                      on_click=self._toggle_follow, radius=6)
        look.select(self.follow_btn, True)
        nx = fx - 8 - bw
        self.next_btn = look.button(bar, nx, 3, bw, th - 8, icon="chevron_right", on_click=lambda: self._page(1),
                                    radius=6)
        self.page = look.text(bar, "", f["small"], look.TEXT, int(78 * s), lv.TEXT_ALIGN.CENTER)
        self.page.set_pos(nx - int(80 * s), (th - 2 - f["small"].line_height) // 2)
        self.prev_btn = look.button(bar, nx - int(82 * s) - bw, 3, bw, th - 8, icon="chevron_left",
                                    on_click=lambda: self._page(-1), radius=6)
        gy = ty + th + m
        self.grid = Grid(self.base, m, gy, lw, int(h) - gy - m, f["small"], self._tap)

        # -- right: songs, kits, mixer --
        rx = lw + 2 * m
        y = m
        look.heading(self.base, "Song", f["small"], rx, y, "songs")
        y += f["small"].line_height + 4
        dh = int(38 * s)
        self.songs = look.dropdown(self.base, rx, y, rw, dh, f["body"], self._song)
        y += dh + m
        look.heading(self.base, "Kit", f["small"], rx, y)
        y += f["small"].line_height + 4
        kh = int((int(h) - y) * 0.42)
        self.kits = look.box(self.base, rx, y, rw, kh, look.PANEL, 8, look.LINE)
        self.kits_w = rw
        self.kits.add_flag(lv.obj.FLAG.SCROLLABLE)
        self.kits.set_scroll_dir(lv.DIR.VER)
        self.kit_buttons = {}
        y += kh + m
        look.heading(self.base, "Mixer", f["small"], rx, y)
        y += f["small"].line_height + 4
        mh = int(h) - y - m
        mixer = look.box(self.base, rx, y, rw, mh, look.PANEL, 8, look.LINE)
        self.faders = {}
        self.fader_labels = []
        n = len(FADERS)
        slot = (rw - 8) // n
        self.fader_names = names = fader_names(slot, f["small"])
        track = int(12 * s)
        knob = track + 2 * max(2, track // 3)      # the knob stands out past the track
        top = knob // 2 + 6
        fh = mh - f["small"].line_height - 12 - knob // 2 - top
        for i, key in enumerate(FADERS):
            fx = 4 + i * slot + (slot - track) // 2
            lo, hi = (0, 127) if key == "volume" else (0, 100)
            fd = look.slider(mixer, fx, top, track, fh, lo, hi, self._fader(key))
            fd.add_event_cb(self._fader(key, True), lv.EVENT.RELEASED, None)
            lbl = look.text(mixer, names[i], f["small"], look.DIM, slot, lv.TEXT_ALIGN.CENTER)
            lbl.set_pos(4 + i * slot, mh - f["small"].line_height - 8)
            self.faders[key] = fd
            self.fader_labels.append(lbl)

    # -- what the editor sends --

    def _tap(self, pitch, step):
        panel = self.desk.panel
        if panel is None or panel.doc is None or self.pattern < 0:
            return
        op, path, value = song.tap(panel.doc, self.pattern, pitch, step, self.ticks)
        panel.send(op, path, value)
        self.show_cells()

    def _fader(self, key, final=False):
        path = "/tracks/0/volume" if key == "volume" else "/tracks/0/mix/" + key

        def on_change(value):
            panel = self.desk.panel
            if panel is None or panel.doc is None:
                return
            if not isinstance(value, int):
                value = self.faders[key].get_value()
            now = ticks_ms()
            if not final and ticks_diff(now, self.sent.get(key, now - SEND_MS)) < SEND_MS:
                return
            self.sent[key] = now
            panel.set(path, value)

        return on_change

    def _song(self, index):
        self.desk.command("song", index=index)

    def _kit(self, spec):
        def on_click(_e):
            self.desk.command("kit", spec=spec)

        return on_click

    def _pick(self, i):
        self.follow = False
        look.select(self.follow_btn, False)
        self.show_block(i, 0)

    def _toggle_follow(self):
        self.follow = not self.follow
        look.select(self.follow_btn, self.follow)

    def _page(self, step):
        self.follow = False
        look.select(self.follow_btn, False)
        self.bar = (self.bar + step) % max(1, self.bars)
        self.grid.bar = self.bar
        self.show_page()
        self.show_cells()

    # -- what it shows --

    def show_block(self, i, bar):
        if not 0 <= i < len(self.blocks):
            return
        b = self.blocks[i]
        self.block = i
        self.pattern = b["pattern"]
        self.bars = b["bars"]
        self.bar = bar % self.bars
        self.grid.bar = self.bar
        self.strip.pick(i)
        self.part.set_text(b["label"].upper())
        self.part.set_style_text_color(look.color(look.ROLE_COLORS.get(b["role"], look.AMBER)), 0)
        self.info.set_text("%d BAR%s" % (self.bars, "" if self.bars == 1 else "S"))
        self.show_page()
        self.show_cells()

    def show_page(self):
        self.page.set_text("BAR %d / %d" % (self.bar + 1, self.bars))

    def show_cells(self):
        doc = self.desk.panel.doc if self.desk.panel is not None else None
        if doc is None or self.pattern < 0:
            return
        pat = doc["tracks"][0]["patterns"][self.pattern]
        self.grid.show(song.levels(pat, [p for p, _n in self.grid.rows], self.ticks))

    def rebuild(self, doc, voices):
        """Lay the grid out again for the song's meter and the kit's drums."""
        self.voices = voices
        self.cols, self.ticks = song.columns(doc)
        rows = song.rows(voices, doc)
        self.grid.build(rows, self.cols, song.beat_columns(doc))
        self.grid.bar = self.bar
        self.show_cells()

    def on_doc(self, doc, desc):
        self.blocks = song.blocks(doc)
        self.strip.set_blocks(self.blocks)
        names = desc.get("titles") or [doc.get("name", "")]
        self.songs.set_options("\n".join(names))
        self.set_kits(desc.get("kit_list") or [], desc.get("kit"))
        self.rebuild(doc, desc.get("voices") or [])
        keep = self.block if 0 <= self.block < len(self.blocks) else 0
        self.show_block(keep, self.bar)
        self.show_mix(doc)

    def set_kits(self, kit_list, current):
        box = self.kits
        box.clean()
        self.kit_buttons = {}
        f = self.desk.fonts
        s = self.desk.scale
        w = self.kits_w - 14
        y = 6
        bh = int(30 * s)
        for source, title in (("machine", "Drum machines"), ("soundfont", "SoundFont"), ("samples", "Sample kits")):
            look.heading(box, title, f["small"], 6, y, "samples" if source == "samples" else None)
            y += f["small"].line_height + 4
            mine = [k for k in kit_list if k["source"] == source]
            if not mine:
                none = look.text(box, "none found" if source == "soundfont" else "no kit folders", f["small"], look.FAINT)
                none.set_pos(10, y)
                y += f["small"].line_height + 8
                continue
            for k in mine:
                b = look.button(box, 6, y, w, bh, k["name"], fnt=f["small"], radius=6)
                b.add_event_cb(self._kit(k["spec"]), lv.EVENT.CLICKED, None)
                self.kit_buttons[k["spec"]] = b
                y += bh + 4
            y += 4
        self.show_kit(current)

    def show_kit(self, spec):
        for k, b in self.kit_buttons.items():
            look.select(b, k == spec)

    def show_mix(self, doc):
        track = doc["tracks"][0]
        mix = track.get("mix") or {}
        for key, fd in self.faders.items():
            v = track.get("volume", 100) if key == "volume" else mix.get(key, 100)
            if fd.get_value() != v and not fd.has_state(lv.STATE.PRESSED):
                fd.set_value(int(v), False)

    def on_op(self, op):
        path = op.get("path", "")
        doc = self.desk.panel.doc
        if path.startswith("/tracks/0/patterns/%d/" % self.pattern):
            self.show_cells()
        if path.startswith("/tracks/0/mix") or path == "/tracks/0/volume":
            self.show_mix(doc)
        if path.startswith("/parts") or path.endswith("/bars"):
            self.blocks = song.blocks(doc)
            self.strip.set_blocks(self.blocks)
            self.show_block(min(self.block, len(self.blocks) - 1), self.bar)

    def on_event(self, ev):
        if ev.get("name") in ("kit", "song") and "voices" in ev:
            doc = self.desk.panel.doc
            self.show_kit(ev.get("spec", ev.get("kit")))
            if doc is not None:
                self.rebuild(doc, ev["voices"])

    def on_tele(self, t):
        self.strip.show(t)
        index = t.get("song_index")
        if index is not None and index != self.songs.get_selected() and not self.songs.is_open():
            self.songs.set_selected(index)
        playing = t.get("playing")
        if playing and self.follow:
            i = song.find(self.blocks, t.get("role"), t.get("number"))
            want_bar = t.get("at", 0) // song.BAR
            if i >= 0 and (i != self.block or want_bar != self.bar):
                self.show_block(i, want_bar)
        if playing and t.get("pattern") == self.pattern and t.get("at", 0) // song.BAR == self.bar:
            self.grid.playhead(int(t.get("at", 0) % song.BAR) // self.ticks)
        else:
            self.grid.playhead(-1)
