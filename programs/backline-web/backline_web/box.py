# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The browser as Backline's box: the songs, the drums and the floor view in a page.

The page runs Backline's own box (``backline.box``) in MicroPython's
WebAssembly build. Its sound goes to Web Audio, its floor view is drawn on a
canvas, and the pedals are the keyboard, two pads under the canvas and the
lamps on the floor view. A desk joins it on a port the page opened: a board
on USB through WebSerial, or one advertising over Bluetooth through Web
Bluetooth. The board runs the desk view as an hmilink panel; the page adds
the port to the box's device, so the board draws from the same song.

``page.js`` makes a `Page` and calls its `Page.tick` every few milliseconds.
Nothing waits: a tick renders the sound the output is about to need, reads
the desks, and every `UI_MS` redraws the floor view.
"""

import json

import _wasm_bridge
import audiocore
import hmilink
import js
from hmilink import local, stream, web
from time import ticks_diff, ticks_ms

from backline import box as boxmod
from backline import kits
from backline.floor import Floor

from .screen import Screen

#: How far ahead of what plays the page keeps the sound, in milliseconds. A
#: tick the browser runs late, while it lays out the page, eats into this
#: instead of into the sound.
LEAD_MS = 150
#: The frames rendered between two passes of the engine. A drum machine
#: plays a note the moment it's given one, so each pass hands it the notes
#: of the next chunk early, and the page gives each one to the kit at the
#: start of its own block. That keeps the timing to a block while the
#: engine runs once a chunk, which a browser's MicroPython can afford.
CHUNK = 512
UI_MS = 30
STATE_MS = 200
FORMAT = (kits.RATE, kits.CHANNELS, 16, True, False)
BYTES_PER_FRAME = 2 * kits.CHANNELS


class HeldKit:
    """A kit whose notes wait for the block they belong to.

    The engine gives it each note with its delay in frames; `release` passes
    on the ones due before a frame. Everything else is the kit's own.
    """

    timed = True

    def __init__(self, kit, clock):
        self.kit = kit
        self.clock = clock
        self.due = []

    def __getattr__(self, name):
        return getattr(self.kit, name)

    def note_on(self, pitch, velocity, delay=0):
        self.due.append((self.clock() + delay, pitch, velocity))

    def release(self, until):
        """Play every held note due before frame ``until``."""
        if not self.due:
            return
        keep = []
        for note in self.due:
            if note[0] < until:
                self.kit.note_on(note[1], note[2])
            else:
                keep.append(note)
        self.due = keep


class WebBox(boxmod.Box):
    """Backline's box, its clock the frames rendered so far."""

    def __init__(self, song=None, kit=None, plant=""):
        self.frames = 0
        self.block = 128
        self.plant = plant
        boxmod.Box.__init__(self, lambda: self.frames, song=song, kit=kit)

    def use_kit(self, spec):
        done = boxmod.Box.use_kit(self, spec)
        kit = self.engine.kit
        if kit is not None and not isinstance(kit, HeldKit):
            self.engine.kit = HeldKit(kit, self.engine.clock)
        self.engine.lookahead = CHUNK
        return done

    def command(self, name, args):
        if self.plant == "deaf-pedal" and name == "pedal":
            return None
        return boxmod.Box.command(self, name, args)

    def render(self, frames):
        """At least ``frames`` frames of the sound, as bytes."""
        out = bytearray()
        want = frames * BYTES_PER_FRAME
        while len(out) < want:
            if self.frames % CHUNK < self.block:
                self.service()
            self.engine.kit.release(self.frames + self.block)
            _r, buf = audiocore.get_buffer(self.bus.output)
            out.extend(buf)
            self.block = len(buf) // BYTES_PER_FRAME
            self.frames += self.block
        return out


class Page:
    """The box page: a `WebBox`, its floor view on canvas ``canvas`` of
    ``size``, and the desks that join it.

    ``plant`` is a fault for the page's own checks: ``"silent"`` (no sound
    reaches Web Audio), ``"deaf-pedal"`` (the box ignores pedals),
    ``"frozen-floor"`` (the floor view stops following) or ``"no-desks"``
    (a port the page opens never joins the box). With ``record``, the
    engine keeps every note it played, for `notes`.
    """

    def __init__(self, canvas="floor", size=(800, 480), song=None, kit=None, plant="", record=False):
        self.plant = plant
        self.box = WebBox(song=song, kit=kit, plant=plant)
        self.box.engine.record = record
        listener = self.box.device.add(local.serve())
        self.panel = hmilink.Panel(local.connect(listener))
        self.box.poll()
        self.panel.poll()
        self.screen = Screen(canvas, size[0], size[1])
        self.floor = Floor(self.screen.root, size, self.panel)
        self.ports = 0
        self.written = 0
        self.late = 0
        self.ui_at = self.state_at = ticks_ms()
        self.lead = kits.RATE * LEAD_MS // 1000

    def tick(self):
        """One pass: the sound, the desks and, every `UI_MS`, the screen."""
        self.pump()
        self._ports()
        self.box.poll()
        now = ticks_ms()
        if ticks_diff(now, self.ui_at) >= UI_MS:
            self.ui_at = now
            if self.plant != "frozen-floor":
                self.floor.poll()
            self.screen.step()
        if ticks_diff(now, self.state_at) >= STATE_MS:
            self.state_at = now
            js.backlineReport(json.dumps(self.state()))

    def pump(self):
        """Render what Web Audio will play next, keeping `LEAD_MS` queued.
        Until the page has had a click or a key, the browser keeps the sound
        off, and the song waits with it."""
        if not _wasm_bridge.audio_state(False):
            return
        queued = _wasm_bridge.audio_queued_size(False) // BYTES_PER_FRAME
        if queued == 0 and self.written and self.box.engine.transport["playing"]:
            self.late += 1
        while queued < self.lead:
            buf = self.box.render(CHUNK)
            if self.plant != "silent":
                if _wasm_bridge.audio_write(buf, *FORMAT) < 0:
                    return
            n = len(buf) // BYTES_PER_FRAME
            queued += n
            self.written += n

    def _ports(self):
        ports = js.backlinePorts
        while self.ports < ports.length:
            port = ports[self.ports]
            self.ports += 1
            if self.plant != "no-desks":
                self.box.device.add(stream.link(web.stream(port)))

    def pedal(self, which, down):
        """Pedal ``which`` (0 or 1) went down or up, from a key or a pad."""
        self.floor.pedal(which, bool(down))

    def notes(self):
        """The notes played so far, ``[[frame, pitch, velocity]]`` as JSON,
        when the page was made with ``record``."""
        return json.dumps([list(n) for n in self.box.engine.played])

    def state(self):
        """What the page shows around the canvas, and what its checks read."""
        t = self.box.telemetry()
        return {
            "role": "box",
            "playing": t["playing"],
            "part": t["part"],
            "bar": t["bar"],
            "beat": t["beat"],
            "song": t["song"],
            "tempo": t["tempo"],
            "kit": t["kit"],
            "error": t["error"],
            "desks": sum(1 for link in self.box.device.links if not isinstance(link, local.Link)),
            "frames": self.box.frames,
            "written": self.written,
            "late": self.late,
            "floor_part": self.floor.shown.get("part", ""),
            "floor_bar": self.floor.shown.get("bar", ""),
        }
