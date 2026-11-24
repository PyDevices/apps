# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The desk's performance tab: the floor view's face, larger, with the
song's form under it and the songs, tempo and kit beside it.

The face is the floor view itself (`floor.Floor`), drawn at this tab's
size, so its lamps are pedals here too. The strip under it shows every part
of the song, the one playing lit with the playhead crossing it.
"""

import lvgl as lv

from . import look
from .. import parts as song
from .strip import Strip
from .. import floor as floormod


class Perform:
    """The tab in ``parent`` at ``(x, y)``, ``w`` by ``h``, for ``desk``."""

    def __init__(self, parent, x, y, w, h, desk):
        self.desk = desk
        s = desk.scale
        m = desk.m
        f = desk.fonts
        w, h = int(w), int(h)
        self.base = look.plain(lv.obj(parent))
        self.base.set_pos(int(x), int(y))
        self.base.set_size(w, h)
        rw = int(w * 0.3)
        lw = w - rw - 3 * m
        fh = int((h - 3 * m) * 0.72)
        face = look.plain(lv.obj(self.base))
        face.set_pos(m, m)
        face.set_size(lw, fh)
        face.set_style_radius(10, 0)
        face.set_style_clip_corner(True, 0)
        self.face = face
        self.floor = floormod.Floor(face, (lw, fh), desk.panel_proxy)

        sy = m + fh + m
        look.heading(self.base, "Song form", f["small"], m, sy, "form")
        hy = sy + f["small"].line_height + 2
        self.strip = Strip(self.base, m, hy, lw, h - hy - m, f["small"])

        rx = lw + 2 * m
        y = m
        look.heading(self.base, "Songs", f["small"], rx, y, "songs")
        y += f["small"].line_height + 4
        tempo_h = int(44 * s)
        kit_h = int(38 * s)
        list_h = h - y - 2 * m - tempo_h - kit_h - 2 * (f["small"].line_height + 4) - m
        self.songs = look.box(self.base, rx, y, rw, list_h, look.PANEL, 8, look.LINE)
        self.songs_w = rw
        self.songs.add_flag(lv.obj.FLAG.SCROLLABLE)
        self.songs.set_scroll_dir(lv.DIR.VER)
        self.song_buttons = []
        self.song_index = -1
        y += list_h + m
        look.heading(self.base, "Tempo", f["small"], rx, y)
        y += f["small"].line_height + 4
        bw = tempo_h
        look.button(self.base, rx, y, bw, tempo_h, icon="remove", on_click=lambda: self._tempo(-1))
        look.button(self.base, rx + rw - bw, y, bw, tempo_h, icon="add", on_click=lambda: self._tempo(1))
        well = look.box(self.base, rx + bw + 6, y, rw - 2 * bw - 12, tempo_h, 0x05070B, 8, look.LINE)
        self.tempo = look.text(well, "", f["value"], look.AMBER)
        self.tempo.align(lv.ALIGN.CENTER, -int(14 * s), 0)
        bpm = look.text(well, "BPM", f["small"], look.DIM)
        bpm.align(lv.ALIGN.RIGHT_MID, -8, 0)
        y += tempo_h + m
        look.heading(self.base, "Kit", f["small"], rx, y)
        y += f["small"].line_height + 4
        self.kits = look.dropdown(self.base, rx, y, rw, kit_h, f["body"], self._kit)
        self.kit_specs = []
        self.kits_listed = None    # the kit specs the list was set to
        self.titles = None         # the songs the buttons were made for

    # -- what it sends --

    def _tempo(self, step):
        panel = self.desk.panel
        if panel is None or panel.doc is None:
            return
        panel.set("/tempo", int(panel.doc.get("tempo", 120) + 0.5) + step)
        self.show_tempo(panel.doc)

    def _kit(self, index):
        if 0 <= index < len(self.kit_specs):
            self.desk.command("kit", spec=self.kit_specs[index])

    def _song(self, index):
        def on_click(_e):
            self.desk.command("song", index=index)

        return on_click

    # -- what it shows --

    def show_tempo(self, doc):
        self.tempo.set_text("%d" % int(doc.get("tempo", 120) + 0.5))

    def on_doc(self, doc, desc):
        self.floor._doc(doc, desc)
        self.strip.set_blocks(song.blocks(doc))
        self.show_tempo(doc)
        titles = desc.get("titles") or [doc.get("name", "")]
        if titles != self.titles:      # a song change keeps the list
            self.titles = titles
            f = self.desk.fonts
            s = self.desk.scale
            self.songs.clean()
            self.song_buttons = []
            bh = int(34 * s)
            w = self.songs_w - 14
            for i, name in enumerate(titles):
                b = look.button(self.songs, 6, 6 + i * (bh + 4), w, bh, name, fnt=f["body"], radius=6)
                b.get_child(0).align(lv.ALIGN.LEFT_MID, 10, 0)
                b.add_event_cb(self._song(i), lv.EVENT.CLICKED, None)
                self.song_buttons.append(b)
            self.song_index = -1
        kits = desc.get("kit_list") or []
        specs = [k["spec"] for k in kits]
        if specs != self.kits_listed:
            self.kits_listed = self.kit_specs = specs
            self.kits.set_options("\n".join(k["name"] for k in kits))
        self.show_kit(desc.get("kit"))

    def show_kit(self, spec):
        if spec in self.kit_specs and not self.kits.is_open():
            self.kits.set_selected(self.kit_specs.index(spec))

    def on_op(self, op):
        path = op.get("path", "")
        doc = self.desk.panel.doc
        if path == "/tempo":
            self.show_tempo(doc)
        elif path.startswith("/parts") or path.endswith("/bars"):
            self.strip.set_blocks(song.blocks(doc))

    def on_event(self, ev):
        if ev.get("name") == "kit":
            self.show_kit(ev.get("spec"))
        elif ev.get("name") == "song":
            self.show_kit(ev.get("kit"))

    def on_tele(self, t):
        self.floor._tele(t)
        self.strip.show(t)
        index = t.get("song_index", -1)
        if index != self.song_index:
            for i, b in enumerate(self.song_buttons):
                look.select(b, i == index)
            self.song_index = index
            if 0 <= index < len(self.song_buttons):
                self.song_buttons[index].scroll_to_view(False)
