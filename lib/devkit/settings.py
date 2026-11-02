# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""devkit.settings -- what one DEV-KIT has that another doesn't, kept in JSON.

Two kinds of file, both optional, both in appkit's data root (``/data`` on
the board):

``/data/settings.json``
    The whole set's: ``{"hostname": "my-devkit"}`` names the board on the
    network (``my-devkit.local``). Without it the board keeps the name it
    has.

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
    "hostname": None,  # the board's mDNS name; None keeps the firmware's
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


def config(scope, defaults):
    """App *scope*'s settings: *defaults*, overridden by ``config.json`` in
    its ``data_dir``. A dict, read afresh each time the app opens."""
    c = dict(defaults)
    c.update(_read(data.join(scope.data_dir, "config.json")))
    return c
