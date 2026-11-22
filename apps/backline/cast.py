# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's desk view on a screen across the room.

The box draws a desk view on a 1280x720 LVGL display of its own, in memory,
and hands each finished frame to a cast: a Windows PC's Wireless Display
app or a Roku's Screen mirroring over Miracast, or a Roku running the
PyDevices Companion channel. The desk there is a panel like any other, so
it follows the song as it plays and a change made anywhere shows on it.
The box's own screen, if it has one, carries on as before.

    target = remote.cast_target(prefs)          # {"kind", "host", "name"}
    cast = CastDesk(open_sink(target), box.device)
    while True:
        lv.timer_handler()
        cast.step()

The cast itself is ``castdisplay``'s (CPython with ffmpeg, or a board whose
firmware has castif). The sound stays where the box plays it.
"""

import lvgl as lv

try:
    from time import ticks_diff, ticks_ms
except ImportError:
    from multimer import ticks_diff, ticks_ms

import hmilink
from hmilink import local

from .desk import Desk

SIZE = (1280, 720)
FPS = 20             # frames a second a Miracast stream carries
COMPANION_FPS = 8    # the Companion channel fetches each frame as a PNG
BITRATE = 2_000_000
NAME = "Backline"


def open_sink(target, size=SIZE, name=NAME, log=None):
    """The cast for ``target`` (`remote.cast_target`), started: a display
    whose frames go to the receiver.

    Raises:
        ImportError: castdisplay isn't installed.
        ValueError: ``target`` names a kind there's no cast for.
    """
    kind = target["kind"]
    w, h = size
    if kind == "companion":
        from castdisplay.roku_companion import RokuDisplay

        return RokuDisplay(target["host"], w, h)
    if kind in ("windows", "roku"):
        from castdisplay.cast_display import CastDisplay

        return CastDisplay(target["host"], w, h, kind=kind, fps=FPS, bitrate=BITRATE, name=name, log=log)
    raise ValueError("no cast for %r" % (kind,))


class CastDesk:
    """A `Desk` on its own display, drawn into ``sink``'s frame buffer.

    ``sink`` is any display with ``framebuffers()``, ``show()`` and
    ``close()`` (a castdisplay display, or a stand-in in a test). ``device``
    is the box's ``hmilink.Device``: the desk joins it as a local panel.
    ``fps`` caps how often a changed frame is sent, on the clock
    ``now_ms`` (milliseconds, the real one by default).
    """

    def __init__(self, sink, device, size=SIZE, fps=None, now_ms=ticks_ms):
        if not lv.is_initialized():
            lv.init()
        self.sink = sink
        self.now_ms = now_ms
        self.size = w, h = size
        self.gap_ms = 1000 // (fps or FPS)
        self.sent = 0           # frames handed to the cast
        self.drawn = 0          # refreshes LVGL finished
        self.dirty = False
        self.last = None
        buf = sink.framebuffers()[0]
        self.disp = lv.display_create(w, h)
        self.disp.set_color_format(lv.COLOR_FORMAT.RGB565)
        # LVGL draws straight into the buffer the cast reads.
        self.disp.set_buffers(buf, None, len(buf), lv.DISPLAY_RENDER_MODE.DIRECT)
        self.disp.set_flush_cb(self._flush)
        prev = lv.display_get_default()
        self.disp.set_default()
        self.screen = lv.obj(None)
        if prev is not None:
            prev.set_default()   # the box's own screen stays where new screens go
        self.panel = hmilink.Panel(local.connect(device.add(local.serve())))
        self.desk = Desk(self.screen, size, self.panel)
        lv.screen_load(self.screen)

    def _flush(self, disp, area, px):
        if disp.flush_is_last():
            self.drawn += 1
            self.dirty = True
        disp.flush_ready()

    def step(self):
        """One pass: what the box sent, and a changed frame to the cast
        when the last one went long enough ago."""
        self.desk.poll()
        if not self.dirty:
            return
        now = self.now_ms()
        if self.last is not None and ticks_diff(now, self.last) < self.gap_ms:
            return
        self.last = now
        self.dirty = False
        self.sent += 1
        self.sink.show()

    def stats(self):
        """The cast's own counters, with the frames drawn and sent from here."""
        out = {}
        try:
            out.update(self.sink.stats())
        except Exception:  # noqa: BLE001 - a sink with no counters still casts
            pass
        out["drawn"] = self.drawn
        out["handed"] = self.sent
        return out

    def close(self):
        """Leave the box and end the cast."""
        self.panel.close()
        try:
            self.disp.delete()
        except Exception:  # noqa: BLE001 - the cast still ends
            pass
        self.sink.close()


def start(device, target, log=None):
    """Cast the desk of the box with ``device`` to ``target``. Returns the
    `CastDesk`; call its ``step()`` from the UI loop."""
    fps = COMPANION_FPS if target["kind"] == "companion" else FPS
    return CastDesk(open_sink(target, log=log), device, fps=fps)
