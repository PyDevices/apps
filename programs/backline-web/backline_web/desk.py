# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The browser as a Backline box's desk: the desk view on a canvas, joined to a box elsewhere.

The box is a board, or a computer, running Backline. The page opens a port
to it: Web Bluetooth to a box advertising its desk link, WebSerial to one on
USB, or a WebSocket to one on the network (its desk port, 9300). The desk
view is Backline's own (``backline.desk``), drawn by LVGL in MicroPython's
WebAssembly build, so it looks as it does on the box's screen. The space bar
is pedal A and B is pedal B, as on the box.

``page.js`` makes a `Page` and calls its `Page.tick` every few milliseconds.
"""

import json

import hmilink
import js
from hmilink import stream, web
from time import ticks_diff, ticks_ms

from backline.desk import Desk

from .screen import Screen

UI_MS = 30
STATE_MS = 200


class Page:
    """The desk page: a `Desk` on canvas ``canvas`` of ``size``, joined to
    whichever box the page opens a port to.

    ``plant`` is a fault for the page's own checks: ``"deaf-desk"`` (the
    pedals never leave the page) or ``"frozen-desk"`` (the view stops
    following the box).
    """

    def __init__(self, canvas="desk", size=(1024, 600), plant=""):
        self.plant = plant
        self.screen = Screen(canvas, size[0], size[1])
        self.desk = Desk(self.screen.root, size, None)
        self.desk._error({"msg": "choose a box to join"})
        self.ports = 0
        self.joined = 0
        self.waiting = False
        self.ui_at = self.state_at = ticks_ms()

    def tick(self):
        """One pass: a new port, the link, and every `UI_MS` the screen."""
        ports = js.backlinePorts
        if self.ports < ports.length:
            port = ports[ports.length - 1]
            self.ports = ports.length
            if self.desk.panel is not None:
                self.desk.panel.close()
            self.desk.attach(hmilink.Panel(stream.link(web.stream(port))))
            self.desk._error({"msg": "joining the box"})
            self.waiting = True
            self.joined += 1
        panel = self.desk.panel
        if panel is not None and panel.closed:
            self.desk.panel = None
            self.desk._error({"msg": "the box went away"})
        elif self.waiting and panel is not None and panel.ready:
            self.waiting = False
            self.desk.message = ""
            self.desk.shown.pop("next", None)
        now = ticks_ms()
        if ticks_diff(now, self.ui_at) >= UI_MS:
            self.ui_at = now
            if self.plant != "frozen-desk":
                self.desk.poll()
            self.screen.step()
        if ticks_diff(now, self.state_at) >= STATE_MS:
            self.state_at = now
            js.backlineReport(json.dumps(self.state()))

    def pedal(self, which, down):
        """Pedal ``which`` (0 or 1) went down or up, from a key or a pad."""
        if self.plant != "deaf-desk":
            self.desk.pedal(which, bool(down))

    def key(self, name):
        """A key typed on the page while the desk's prompt sheet is open: a
        character, ``"Backspace"`` or ``"Enter"`` (which asks)."""
        sheet = self.desk.prompt
        if not sheet.shown():
            return
        if name == "Enter":
            sheet.ask()
        elif name == "Backspace":
            sheet.field.delete_char()
        elif len(name) == 1:
            sheet.field.add_text(name)

    def state(self):
        """What the page shows around the canvas, and what its checks read."""
        t = self.desk.tele or {}
        panel = self.desk.panel
        part = self.desk.shown.get("part")
        return {
            "role": "desk",
            "joined": self.joined,
            "ready": bool(panel is not None and panel.ready),
            "song": (panel.doc or {}).get("name", "") if panel is not None else "",
            "playing": bool(t.get("playing")),
            "part": t.get("part", ""),
            "tempo": t.get("tempo", 0),
            "bar": t.get("bar", 0),
            "beat": t.get("beat", 0),
            "desk_part": part[0] if part else "",
            "desk_where": self.desk.shown.get("where", ""),
            "message": self.desk.message,
            "typing": self.desk.typing(),
        }
