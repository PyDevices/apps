# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The prompt sheet: ask for a groove in words, see the song that comes back, then play, keep or let it go.

The desk's header button opens it over the tabs. Type what you want ("a
slow 12-bar blues at 72, 4 times through, slowing in the outro") and Ask,
or Enter. The box asks its chat server (`ask`), and the sheet shows the song
before anyone hears it: its name and style, the tempo, meter and kit, the
play plan and its form as a strip. Play starts it, Keep puts it among the
songs, and Discard lets it go and brings back the song from before.

It holds nothing of its own: the request goes to the box as the ``ask``
command and the song comes back to every panel, so the same sheet works on
the box's screen and on a desk elsewhere.
"""

import lvgl as lv

from . import look
from .. import ask as askmod
from .. import glyphs
from .strip import Strip

try:
    from appkit import keys
except ImportError:  # a desk with no appkit: the field takes keys without an on-screen keyboard
    keys = None

HINT = "A slow 12-bar blues at 72, 4 times through, slowing in the outro"
IDLE = "Say a style, a tempo, a song to borrow the feel of, and how long to play."
ASKING = "Asking for the song... a model on a computer with no GPU can take a few minutes."


class PromptSheet:
    """The sheet in ``parent`` at ``(x, y)``, ``w`` by ``h``, for ``desk``; hidden until `show`."""

    def __init__(self, parent, x, y, w, h, desk):
        self.desk = desk
        s = desk.scale
        m = desk.m
        f = desk.fonts
        w, h = int(w), int(h)
        self.preview = None
        self.state = ""
        self.base = look.box(parent, x, y, w, h, look.BG, 0, None)
        self.base.add_flag(lv.obj.FLAG.CLICKABLE)     # taps stay on the sheet
        self.base.add_flag(lv.obj.FLAG.HIDDEN)
        pad = 2 * m
        look.heading(self.base, "Ask for a groove", f["small"], pad + 4, pad, "prompt")
        bs = int(34 * s)
        look.button(self.base, w - pad - bs, pad - 6, bs, bs, icon="close", on_click=desk.toggle_prompt, radius=6)

        fy = pad + f["small"].line_height + 2 * m
        fh = int(46 * s)
        aw = int(110 * s)
        field = lv.textarea(self.base)
        field.set_pos(pad, fy)
        field.set_size(w - 2 * pad - aw - m, fh)
        field.set_one_line(True)
        field.set_placeholder_text(HINT)
        field.set_style_text_font(f["body"], 0)
        field.set_style_bg_color(look.color(0x05070B), 0)
        field.set_style_bg_opa(255, 0)
        field.set_style_text_color(look.color(look.TEXT), 0)
        field.set_style_border_color(look.color(look.LINE), 0)
        field.set_style_border_color(look.color(look.AMBER), lv.STATE.FOCUSED)
        field.set_style_border_width(1, 0)
        field.set_style_radius(8, 0)
        field.set_style_pad_ver(max(2, (fh - f["body"].line_height) // 2 - 2), 0)
        hint = getattr(lv.PART, "TEXTAREA_PLACEHOLDER", None)   # not in every binding
        if hint is not None:
            field.set_style_text_color(look.color(look.FAINT), hint)
        if keys is not None:
            keys.attach(field)
        field.add_event_cb(lambda _e: self.ask(), lv.EVENT.READY, None)
        self.field = field
        self.ask_button = look.button(self.base, w - pad - aw, fy, aw, fh, "ASK", fnt=f["body"], on_click=self.ask)
        look.select(self.ask_button, True)

        sy = fy + fh + m
        self.status = look.text(self.base, IDLE, f["small"], look.DIM, w - 2 * pad)
        self.status.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status.set_height(2 * f["small"].line_height + 2)
        self.status.set_pos(pad, sy)

        # The song that came back.
        cy = sy + 2 * f["small"].line_height + 2 * m
        ch = h - cy - pad
        card = look.box(self.base, pad, cy, w - 2 * pad, ch, look.PANEL, 10, look.LINE)
        card.add_flag(lv.obj.FLAG.HIDDEN)
        self.card = card
        cw = w - 2 * pad
        ip = int(14 * s)
        self.title = look.text(card, "", f["title"], look.AMBER, cw - 2 * ip)
        self.title.set_pos(ip, ip)
        self.facts = look.text(card, "", f["body"], look.TEXT, cw - 2 * ip)
        self.facts.set_pos(ip, ip + f["title"].line_height + 6)
        self.plan = look.text(card, "", f["body"], look.DIM, cw - 2 * ip)
        self.plan.set_pos(ip, ip + f["title"].line_height + f["body"].line_height + 10)
        by = ip + f["title"].line_height + 2 * f["body"].line_height + 22
        bh2 = int(40 * s)
        buttons_y = ch - ip - bh2
        self.filled = look.text(card, "", f["small"], look.FAINT, cw - 2 * ip)
        self.filled.set_pos(ip, buttons_y - f["small"].line_height - m)
        look.heading(card, "Song form", f["small"], ip, by, "form")
        sy2 = by + f["small"].line_height + 2
        self.strip = Strip(card, ip, sy2, cw - 2 * ip, max(30, buttons_y - f["small"].line_height - 2 * m - sy2),
                           f["small"])
        bw = int(130 * s)
        self.buttons = {}
        for i, (key, name) in enumerate((("play", "PLAY"), ("keep", "KEEP"), ("discard", "DISCARD"))):
            b = look.button(card, ip + i * (bw + m), buttons_y, bw, bh2, name, fnt=f["body"],
                            on_click=self._doer(key), radius=6)
            self.buttons[key] = b
        look.select(self.buttons["play"], True, look.ROLE_COLORS.get("main", look.AMBER))

    # -- what it sends --

    def _doer(self, what):
        def on_click():
            self.desk.command("proposal", do=what)

        return on_click

    def ask(self):
        """Send what's in the field to the box."""
        text = self.field.get_text().strip()
        if not text or self.state == "asking":
            return
        if keys is not None:
            keys.hide()
        self.desk.command("ask", text=text)
        self.show_state("asking", "")

    # -- showing it --

    def shown(self):
        return not self.base.has_flag(lv.obj.FLAG.HIDDEN)

    def show(self):
        self.base.remove_flag(lv.obj.FLAG.HIDDEN)
        self.base.move_foreground()

    def hide(self):
        if keys is not None:
            keys.hide()
        self.base.add_flag(lv.obj.FLAG.HIDDEN)

    def toggle(self):
        if self.shown():
            self.hide()
        else:
            self.show()

    def show_state(self, state, error):
        if state == self.state and not error:
            return
        self.state = state
        if state == "asking":
            self.status.set_text(ASKING)
            self.status.set_style_text_color(look.color(look.DIM), 0)
        elif state == "failed":
            self.status.set_text(error or "the song didn't come")
            self.status.set_style_text_color(look.color(look.BAD), 0)
        elif state == "ready" and self.preview is not None:
            tries = self.preview.get("tries", 1)
            self.status.set_text("Here it is." + (" (The first answer didn't fit; the second did.)" if tries > 1 else ""))
            self.status.set_style_text_color(look.color(look.DIM), 0)
        else:
            self.status.set_text(IDLE)
            self.status.set_style_text_color(look.color(look.DIM), 0)

    def show_preview(self, p):
        """Show the song `ask.preview` describes, or none."""
        self.preview = p
        if p is None:
            self.card.add_flag(lv.obj.FLAG.HIDDEN)
            return
        self.title.set_text(p.get("name") or "Untitled")
        bits = [p.get("style", "").capitalize(), "%d BPM" % int(p.get("tempo", 0) + 0.5), p.get("meter", "4/4")]
        if p.get("swing"):
            bits.append("swing %d%%" % p["swing"])
        elif p.get("feel") not in (None, "straight"):
            bits.append(p["feel"])
        bits.append(p.get("kit_name") or p.get("kit", ""))
        self.facts.set_text("  ".join([bits[0]] + ["%s %s" % (glyphs.DOT, b) for b in bits[1:] if b]))
        plan = askmod.plan_text(p)
        self.plan.set_text(plan[0].upper() + plan[1:])
        self.strip.set_blocks(p.get("blocks") or [])
        filled = p.get("filled") or []
        self.filled.set_text(("Filled in: " + ", ".join(filled)) if filled else "")
        self.card.remove_flag(lv.obj.FLAG.HIDDEN)

    # -- what comes from the box --

    def on_doc(self, desc):
        self.show_preview(desc.get("proposal"))

    def on_event(self, ev):
        if ev.get("name") != "proposal":
            return
        if "preview" in ev:
            self.show_preview(ev["preview"])
            if ev.get("error"):
                self.show_state("failed", ev["error"])
        elif ev.get("did") in ("keep", "discard"):
            self.show_preview(None)
            self.show_state("", "")
            if ev.get("did") == "keep":
                self.field.set_text("")

    def on_tele(self, t):
        self.show_state(t.get("ask", ""), t.get("ask_error", ""))
        if self.preview is not None and t.get("song") == self.preview.get("name"):
            self.strip.show(t)       # the song that came back is the one playing
