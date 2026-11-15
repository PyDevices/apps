# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit.settings -- what one board has that another doesn't, kept in JSON.

Two kinds of file, both optional, both in appkit's data root (``/data`` on
the board):

``/data/settings.json``
    The whole set's: ``{"webrepl": false}`` keeps WebREPL off, say. The
    board's name isn't here: ``boarddev.name("my-panel")`` sets it, and
    `move_hostname` moves a ``"hostname"`` an older set saved here into it.

``/data/<app>/config.json``
    One app's: the Roku remote's ``{"prefer": "Living room"}`` picks the TV
    whose name holds that text when there are several, say. Each app's
    docstring lists its keys.

Code holds the defaults; a file holds only what differs.
"""

import json

from appkit import data

#: The set's defaults; ``settings.json`` overrides any of them.
DEFAULTS = {
    "webrepl": True,  # start WebREPL once Wi-Fi is up (its password is /webrepl_cfg.py's)
}

_settings = None


def _read(path):
    try:
        with open(path, "rb") as f:  # UTF-8 whatever the desktop's codepage
            d = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def get(key, default=None):
    """A set-wide setting: ``settings.json``'s, else the default."""
    global _settings
    if _settings is None:
        s = dict(DEFAULTS)
        s.update(_read(data.join(data.root(), "settings.json")))
        _settings = s
    return _settings.get(key, default)


def move_hostname():
    """Make an older set's ``"hostname"`` setting the board's name, once.

    The key comes out of ``settings.json`` either way. A name the board can't
    take (a space, say) is dropped, with the reason printed. Returns the name
    moved, or None.
    """
    global _settings
    path = data.join(data.root(), "settings.json")
    saved = _read(path)
    if "hostname" not in saved:
        return None
    name = saved.pop("hostname")
    import boarddev

    try:
        if name:
            boarddev.name(name)
    except ValueError as e:
        print("touchkit: settings.json's hostname isn't kept:", e)
        name = None
    with open(path, "wb") as f:
        f.write(json.dumps(saved).encode("utf-8"))
    _settings = None
    return name or None


def config(scope, defaults):
    """App *scope*'s settings: *defaults*, overridden by ``config.json`` in
    its ``data_dir``. A dict, read afresh each time the app opens."""
    c = dict(defaults)
    c.update(_read(data.join(scope.data_dir, "config.json")))
    return c
