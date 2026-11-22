# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Where Backline's screens find each other.

The box listens for desks on one port (`listen_port`): another computer or
board joins it there as a desk panel over TCP, and a browser opens the
desk page at ``http://<box>:<port>/``. A desk finds its box from the
command line or the ``BACKLINE_BOX`` setting (`target`).

These two functions are the one place that knows how; a device picker
that lists the boxes it can see takes their place when there is one.
"""

import os

PORT = 9300


def _getenv(name):
    getenv = getattr(os, "getenv", None)
    return getenv(name) if getenv is not None else None


def listen_port(prefs=None):
    """The port the box serves desks on, or None for none.

    ``prefs["desk_port"]`` sets it, else ``$BACKLINE_PORT``; 0 turns
    serving off.
    """
    if prefs is not None and "desk_port" in prefs:
        port = prefs["desk_port"]
    else:
        port = _getenv("BACKLINE_PORT") or PORT
    return int(port) if port and int(port) else None


def target(argv=(), env=None):
    """``(host, port)`` of the box a desk joins: the first argument
    (``HOST`` or ``HOST:PORT``), else ``$BACKLINE_BOX``, else this computer.

    Raises:
        ValueError: The port isn't a number.
    """
    spec = argv[0] if argv else None
    if spec is None:
        spec = env.get("BACKLINE_BOX") if env is not None else _getenv("BACKLINE_BOX")
    spec = spec or "127.0.0.1"
    if ":" in spec:
        host, port = spec.rsplit(":", 1)
        return host, int(port)
    return spec, PORT
