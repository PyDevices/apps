# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Where Backline's screens find each other.

The box listens for desks on one port (`listen_port`): another computer or
board joins it there as a desk panel over TCP, and a browser opens the
desk page at ``http://<box>:<port>/``. A desk finds its box from the
command line or the ``BACKLINE_BOX`` setting (`target`). The box can also
cast its desk view to a screen across the room (`cast_target`).

Over Bluetooth, a box with a radio takes desks too when it's given a name
to advertise (`ble_name`): a phone's or a computer's browser joins it with
Web Bluetooth. And a desk can wait for its box instead of finding it
(`desk_link`): a board advertises, or listens on its USB, and a browser
playing Backline connects to it.

These functions are the one place that knows how; a device picker that
lists the boxes and receivers it can see takes their place when there is
one.
"""

import json
import os

PORT = 9300
#: The name a board advertises when a desk spec says ``ble:`` and no more.
BLE_NAME = "Backline"
# What a cast can go to: Miracast to a Windows PC's Wireless Display app or
# a Roku's Screen mirroring, or frames to the PyDevices Companion channel
# on a Roku.
CAST_KINDS = ("windows", "roku", "companion")


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


def cast_target(prefs=None, spec=None):
    """The receiver the box casts its desk view to, or None for no cast.

    ``spec``, else ``prefs["cast"]``, else ``$BACKLINE_CAST``, as
    ``KIND:HOST``: ``windows:192.0.2.30`` (a PC with its Wireless Display
    app open), ``roku:192.0.2.40`` (a Roku with Screen mirroring on) or
    ``companion:192.0.2.40`` (a Roku running the Companion channel). An
    empty one is no cast.

    Returns:
        ``{"kind", "host", "name"}``, the shape a receiver list gives.

    Raises:
        ValueError: The kind isn't one of `CAST_KINDS`, or there's no host.
    """
    if spec is None and prefs is not None:
        spec = prefs.get("cast")
    if spec is None:
        spec = _getenv("BACKLINE_CAST")
    if not spec:
        return None
    kind, _, host = spec.partition(":")
    if kind not in CAST_KINDS or not host:
        raise ValueError("cast to KIND:HOST, KIND one of %s, not %r" % (", ".join(CAST_KINDS), spec))
    return {"kind": kind, "host": host, "name": "%s at %s" % (kind, host)}


def ble_name(prefs=None, folder=None):
    """The name the box advertises desks over Bluetooth with, or None for none.

    ``prefs["ble"]``, else ``$BACKLINE_BLE``, else ``"ble"`` in
    ``settings.json`` in ``folder`` (the app's data folder, ``/data/backline``
    on a board), so a board keeps it across a restart:
    ``{"ble": "Backline"}``. An empty name is none.
    """
    if prefs is not None and "ble" in prefs:
        return prefs["ble"] or None
    name = _getenv("BACKLINE_BLE")
    if name is None and folder:
        try:
            with open(folder + "/settings.json") as f:
                name = json.load(f).get("ble")
        except (OSError, ValueError):
            name = None
    return name or None


def desk_link(spec):
    """How a desk reaches its box, from ``spec``.

    ``HOST`` or ``HOST:PORT`` joins a box on the network over TCP;
    ``ble:NAME`` advertises over Bluetooth as NAME (`BLE_NAME` when it's
    left out) and waits for the box to connect, as a browser playing
    Backline does; ``usb`` listens on a second USB serial port of the board,
    which a browser on the computer it's plugged into opens with WebSerial.

    Returns:
        ``("tcp", (host, port))``, ``("ble", name)`` or ``("usb", None)``.

    Raises:
        ValueError: A TCP port isn't a number.
    """
    if spec.startswith("ble:") or spec == "ble":
        return "ble", spec[4:] or BLE_NAME
    if spec == "usb":
        return "usb", None
    return "tcp", target([spec])
