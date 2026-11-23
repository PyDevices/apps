# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""An LVGL screen on a page's canvas, with the canvas's pointer as its touch.

MicroPython's WebAssembly build paints a framebuffer registered with
``_wasm_bridge`` onto a canvas every animation frame, so LVGL renders
straight into that buffer. A click or a touch on the canvas is LVGL's
pointer, so a lamp on the floor view is a pedal on the page too.

    screen = Screen("floor", 480, 320)
    view = Floor(screen.root, screen.size, panel)
    # then, every 30 ms or so
    screen.step()
"""

import _wasm_bridge
import events
import lvgl as lv
from displaydev.wasmdisplay import WasmDevices
from time import ticks_diff, ticks_ms


class Screen:
    """A ``width`` x ``height`` LVGL display on the canvas with id ``canvas_id``.

    Raises:
        RuntimeError: The page has no such canvas.
    """

    def __init__(self, canvas_id, width, height):
        if not lv.is_initialized():
            lv.init()
        self.size = (width, height)
        self.frame = bytearray(width * height * 2)
        disp = lv.display_create(width, height)
        disp.set_color_format(lv.COLOR_FORMAT.RGB565)
        disp.set_flush_cb(self._flush)
        disp.set_buffers(self.frame, None, len(self.frame), lv.DISPLAY_RENDER_MODE.DIRECT)
        disp.set_default()
        self.display = disp
        if not _wasm_bridge.register_framebuffer(self.frame, width, height, canvas_id):
            raise RuntimeError("the page has no canvas %r" % canvas_id)
        self.devices = WasmDevices(canvas_id)
        self.pointer = [0, 0, False]
        indev = lv.indev_create()
        indev.set_type(lv.INDEV_TYPE.POINTER)
        indev.set_read_cb(self._read)
        indev.set_display(disp)
        self.indev = indev
        self.root = lv.obj(None)
        lv.screen_load(self.root)
        self.last = ticks_ms()

    def _flush(self, disp, area, pixels):
        disp.flush_ready()

    def _read(self, indev, data):
        data.point.x, data.point.y = self.pointer[0], self.pointer[1]
        data.state = lv.INDEV_STATE.PRESSED if self.pointer[2] else lv.INDEV_STATE.RELEASED

    def step(self):
        """Take the canvas's pointer events and run LVGL's timers once."""
        now = ticks_ms()
        for e in self.devices.read() or ():
            kind = e.type
            if kind in (events.MOUSEBUTTONDOWN, events.MOUSEBUTTONUP, events.MOUSEMOTION):
                self.pointer[0], self.pointer[1] = e.pos
                if kind != events.MOUSEMOTION:
                    self.pointer[2] = kind == events.MOUSEBUTTONDOWN
                    # Read it now: a click whose press and release arrive
                    # between two steps would otherwise never be seen down.
                    lv.tick_inc(max(0, ticks_diff(now, self.last)))
                    self.last = now
                    self.indev.read()
        lv.tick_inc(max(0, ticks_diff(now, self.last)))
        self.last = now
        lv.timer_handler()
