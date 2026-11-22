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
"""

import socket
import sys

import hmilink
import lvgl as lv
from hmilink import tcp

from .desk import Desk
from . import remote

STEP_MS = 30
RETRY_MS = 3000
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


class Remote:
    """A `Desk` on ``screen`` that keeps a link to the box at ``(host, port)``."""

    def __init__(self, screen, size, host, port, connect=join):
        self.host, self.port = host, port
        self.connect = connect
        self.desk = Desk(screen, size, None)
        self.waited = RETRY_MS
        self._try()

    def _try(self):
        try:
            panel = self.connect(self.host, self.port)
        except OSError as e:
            self.desk._error({"msg": "no box at %s:%d (%s)" % (self.host, self.port, e)})
            return
        self.desk.attach(panel)

    def step(self, ms=STEP_MS):
        """One pass of the UI loop: the link, and a new try when it's gone."""
        panel = self.desk.panel
        if panel is not None and not panel.closed:
            self.desk.poll()
            self.waited = 0
            return
        if panel is not None:
            self.desk.panel = None
            self.desk._error({"msg": "the box went away"})
        self.waited += ms
        if self.waited >= RETRY_MS:
            self.waited = 0
            self._try()

    def close(self):
        if self.desk.panel is not None:
            self.desk.panel.close()


def start(argv=()):
    """Open the desk on this computer's display and start it. Returns its
    `Remote`; LVGL's loop runs it from here."""
    host, port = remote.target(list(argv))
    from display_driver import app  # noqa: F401  (the display, on LVGL)

    disp = lv.display_get_default()
    size = (disp.get_horizontal_resolution(), disp.get_vertical_resolution())
    screen = lv.obj(None)
    lv.screen_load(screen)
    view = Remote(screen, size, host, port)
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
    print("desk: joining the box at %s:%d" % (host, port))
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
