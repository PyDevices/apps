# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's desk on its own: a screen that joins a box somewhere else.

On a computer, with this repository's ``apps/`` and ``lib/`` and hmilink on
the path, and omnipython-desktop for the window::

    OMNIPYTHON_WIDTH=1280 OMNIPYTHON_HEIGHT=720 python -m backline.desk_main HOST[:9300]

The box is a running Backline. With no address, it looks on this computer,
or at ``$BACKLINE_BOX``. The space bar is pedal A and B is pedal B, as on
the box. When the box goes away, the desk says so and joins it again when
it's back.

A board can also wait for its box, when the box is a browser playing
Backline (a browser can connect, but can't be found): ``ble:NAME``
advertises over Bluetooth as NAME, and ``usb`` listens on a second USB
serial port (`remote.desk_link`). From the board's REPL, with the app in
``/apps/backline``::

    from backline import desk_main
    desk_main.main(["ble:Backline"])
"""

import socket
import sys

import hmilink
import lvgl as lv
from hmilink import stream, tcp

from .desk import Desk
from . import remote

STEP_MS = 30
RETRY_MS = 3000
SILENT_MS = 3000     # a box sends telemetry many times a second: this long without any, it has gone
JOIN_S = 3
K_SPACE, K_B = 32, 98


def join(host, port, seconds=JOIN_S):
    """A panel on the box at ``host``:``port``, giving up after ``seconds``.

    Raises:
        OSError: The box didn't answer.
    """
    s = socket.socket()
    s.settimeout(seconds)
    try:
        s.connect(socket.getaddrinfo(host, port)[0][-1])
    except OSError:
        s.close()
        raise
    link = tcp.Link(s)
    link._decided(False)          # a panel speaks lines from the start
    return hmilink.Panel(link)


def usb_serial():
    """A second USB serial port on this board, beside the REPL's, for a
    browser's WebSerial. Needs micropython-lib's ``usb-device-cdc``.

    A board with one USB port can't be a USB device while it's a USB host,
    and Home starts the host for keyboards. Stop it first with
    ``usb.core.stop()``, and plug that port into the computer."""
    import usb.device
    from usb.device.cdc import CDCInterface

    cdc = CDCInterface(timeout=0)
    usb.device.get().init(cdc, builtin_driver=True)
    return cdc


def opener(spec, usb=usb_serial, adapter=None):
    """``(where, connect)`` for a desk spec (`remote.desk_link`): what the
    desk calls its box, and ``connect(host, port)`` for `Remote`, which makes
    a panel on it. ``usb`` makes the USB port, once; ``adapter`` is the
    Bluetooth radio (the board's own when it's left out).

    Raises:
        ValueError: A TCP port isn't a number.
    """
    kind, arg = remote.desk_link(spec)
    if kind == "ble":
        from hmilink import ble

        return "Bluetooth, as %s" % arg, lambda _h, _p: hmilink.Panel(ble.advertise(arg, adapter=adapter))
    if kind == "usb":
        port = []

        def on_usb(_h, _p):
            if not port:
                port.append(usb())
            return hmilink.Panel(stream.link(port[0]))

        return "USB", on_usb
    return "%s:%d" % arg, lambda _h, _p: join(arg[0], arg[1])


class Remote:
    """A `Desk` on ``screen`` that keeps a link to the box at ``(host, port)``.

    ``connect(host, port)`` makes the panel; ``where`` is what the desk
    calls the box (``host:port`` when it's left out).
    """

    def __init__(self, screen, size, host, port, connect=join, where=None):
        self.host, self.port = host, port
        self.where = where or "%s:%s" % (host, port)
        self.connect = connect
        self.desk = Desk(screen, size, None)
        self.waited = RETRY_MS
        self.waiting = False
        self.quiet = 0           # ms since the box last said anything
        self._heard = None
        self._try()

    def _try(self):
        try:
            panel = self.connect(self.host, self.port)
        except OSError as e:
            self.desk._error({"msg": "no box at %s (%s)" % (self.where, e)})
            return
        self.desk.attach(panel)
        if not panel.ready:
            self.waiting = True
            self.desk._error({"msg": "waiting for the box: %s" % self.where})

    def step(self, ms=STEP_MS):
        """One pass of the UI loop: the link, and a new try when it's gone."""
        panel = self.desk.panel
        if panel is not None and not panel.closed:
            self.desk.poll()
            self._listen(panel, ms)
            if self.waiting and panel.ready:
                self.waiting = False
                self.desk.message = ""
                self.desk.shown.pop("next", None)
            self.waited = 0
            return
        if panel is not None:
            self.desk.panel = None
            self.desk._error({"msg": "the box went away"})
        self.waited += ms
        if self.waited >= RETRY_MS:
            self.waited = 0
            self._try()

    def _listen(self, panel, ms):
        """Close a link the box has gone quiet on. A box that resets leaves
        the desk's socket open with nothing behind it, and the box sends
        telemetry many times a second, so `SILENT_MS` of nothing means it
        has gone; the next pass says so and joins it again."""
        heard = panel.stats["tele"] + panel.stats["ops_in"]
        if heard != self._heard:
            self._heard = heard
            self.quiet = 0
            return
        self.quiet += ms
        if self.quiet >= SILENT_MS:
            self.quiet = 0
            self._heard = None
            panel.close()

    def close(self):
        if self.desk.panel is not None:
            self.desk.panel.close()


def start(argv=()):
    """Open the desk on this computer's display and start it. Returns its
    `Remote`; LVGL's loop runs it from here."""
    argv = list(argv)
    spec = argv[0] if argv else "%s:%d" % remote.target()
    where, connect = opener(spec)
    from display_driver import app  # noqa: F401  (the display, on LVGL)

    disp = lv.display_get_default()
    size = (disp.get_horizontal_resolution(), disp.get_vertical_resolution())
    screen = lv.obj(None)
    lv.screen_load(screen)
    view = Remote(screen, size, spec, None, connect, where)
    view.timer = lv.timer_create(lambda t: view.step(), STEP_MS, None)
    held = set()

    def key(down):
        def on_key(e):
            k = getattr(e, "key", None)
            if down == (k in held):
                return
            (held.add if down else held.discard)(k)
            if k in (K_SPACE, K_B):
                view.desk.pedal(0 if k == K_SPACE else 1, down)

        return on_key

    try:
        import events

        app.on(events.KEYDOWN, key(True))
        app.on(events.KEYUP, key(False))
    except (ImportError, AttributeError):
        pass
    print("desk: joining the box at %s" % where)
    return view


def main(argv=None):
    """Run the desk until the window closes or Ctrl-C."""
    view = start(sys.argv[1:] if argv is None else argv)
    from display_driver import app

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        view.timer.delete()
        view.close()
    return view


if __name__ == "__main__":
    main()
