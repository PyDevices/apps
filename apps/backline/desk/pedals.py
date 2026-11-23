# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The editor's Pedals section: learn a MIDI foot controller's switches and
choose what each one does.

One row for each of the box's four switch slots. The button on the left
shows the message the switch sends; tap it, then press the switch, and the
slot learns it. The menu on the right binds the slot to pedal A or B (taps,
holds and double taps; the switch must send a release) or to one action. A
switch that sends a program change can only take an action: the box says so
if it's bound to a pedal.

Everything goes to the box as a ``pedals`` command, and the box's map comes
back to every desk (`box.Box`).
"""

from . import look

LEARNING = "PRESS NOW"


class Pedals:
    """The section in ``parent`` at ``(x, y)``, ``w`` by ``h``, for ``desk``."""

    def __init__(self, parent, x, y, w, h, desk):
        self.desk = desk
        f = desk.fonts
        self.base = look.box(parent, x, y, w, h, look.PANEL, 8, look.LINE)
        self.bindings = []
        self.map = None
        pad = 6
        foot = f["small"].line_height + 4
        rh = (int(h) - 2 * pad - foot) // 4
        bh = max(f["small"].line_height + 6, rh - 6)
        lw = int((w - 3 * pad) * 0.44)
        self.learn_buttons = []
        self.menus = []
        for i in range(4):
            ry = pad + i * rh + (rh - bh) // 2
            b = look.button(self.base, pad, ry, lw, bh, "%d  -" % (i + 1), fnt=f["small"],
                            on_click=self._learner(i), radius=6)
            self.learn_buttons.append(b)
            d = look.dropdown(self.base, 2 * pad + lw, ry, int(w) - 3 * pad - lw - 2, bh, f["small"], self._binder(i))
            self.menus.append(d)
        self.hint = look.text(self.base, "", f["small"], look.DIM, int(w) - 2 * pad)
        self.hint.set_pos(pad, int(h) - foot - 2)

    # -- what it sends --

    def _learner(self, i):
        def on_click():
            learning = self.map is not None and self.map.get("learning") == i
            self.desk.command("pedals", learn=-1 if learning else i)

        return on_click

    def _binder(self, i):
        def on_pick(index):
            if 0 <= index < len(self.bindings):
                self.desk.command("pedals", slot=i, bind=self.bindings[index][0])

        return on_pick

    # -- what it shows --

    def on_map(self, pedal_map):
        """The box's map (`midipedal.MidiPedal.describe`)."""
        if not pedal_map:
            return
        self.map = pedal_map
        names = [b[0] for b in pedal_map.get("bindings") or []]
        if names != [b[0] for b in self.bindings]:
            self.bindings = pedal_map["bindings"]
            options = "\n".join(label for _b, label in self.bindings)
            for d in self.menus:
                d.set_options(options)
        learning = pedal_map.get("learning", -1)
        for i, slot in enumerate(pedal_map.get("slots") or []):
            b = self.learn_buttons[i]
            label = LEARNING if i == learning else "%d  %s" % (i + 1, describe(slot.get("msg")))
            b.get_child(0).set_text(label)
            look.select(b, i == learning)
            if slot.get("bind") in names:
                k = names.index(slot["bind"])
                if self.menus[i].get_selected() != k and not self.menus[i].is_open():
                    self.menus[i].set_selected(k)
        if learning >= 0:
            self.hint.set_text("Press switch %d" % (learning + 1))
        elif any(s.get("msg") and s["msg"][0] == "pc" for s in pedal_map.get("slots") or []):
            self.hint.set_text("A PC switch takes an action only")
        else:
            last = pedal_map.get("last") or ""
            self.hint.set_text(("Last: " + last) if last else "Tap a switch's button to learn it")


def describe(msg):
    """``"CC 80 ch 1"`` for a slot's message, ``"-"`` for none."""
    if not msg:
        return "-"
    kind, ch, num = msg
    return "%s %d ch %d" % ({"cc": "CC", "note": "Note", "pc": "PC"}.get(kind, kind), num, ch + 1)
