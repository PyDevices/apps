# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The app's settings: which server Huey talks to, with which models and key.

The defaults ask lite-assistant, a server for a computer on your own
network, whose address only you know: ``base_url`` has to be set.

They are one JSON file, ``settings.json`` in the app's data folder
(``/data/huey`` on a board). `load` reads it over `DEFAULTS`, so the file
holds only what differs, and no file at all means the defaults.
"""

import json

#: Every setting and its value when the file doesn't give one.
DEFAULTS = {
    # an OpenAI-compatible server: the address its /chat/completions is
    # under; "" until it is set, since only you know where your server runs
    "base_url": "",
    # a file holding the API key on one line; "" for a server that asks for none
    "key_file": "/lite-assistant.key",
    # what lite-assistant calls its models
    "stt_model": "moonshine",
    "chat_model": "gemma-4-E2B-it",
    "tts_model": "kokoro",
    # a voice the speech model has, or "" for its own: Huey is a he, so a man's
    "voice": "am_puck",
    # the rate of speech that comes back as bare PCM; WAV carries its own
    "speech_rate": 24000,
    # how loud Huey speaks, 0 to 100
    "volume": 80,
    # the longest question, in seconds
    "listen_seconds": 12,
    # where Huey is when the app opens: coast, bench or desk
    "place": "desk",
    # more servers to choose between in the device's picker, under
    # Assistant: each an object with a "name" and any of SERVER_KEYS
    "servers": [],
}

#: The settings a server in ``servers`` may give, over the ones above.
SERVER_KEYS = ("base_url", "key_file", "stt_model", "chat_model", "tts_model", "voice", "speech_rate")


def load(path):
    """The settings: `DEFAULTS`, with what the file at *path* gives over them.

    Raises:
        ValueError: The file isn't a JSON object, or names a setting there
            isn't, or gives one the wrong kind of value.
    """
    settings = dict(DEFAULTS)
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return settings
    try:
        given = json.loads(text)
    except ValueError:
        raise ValueError("%s isn't JSON" % path)
    if not isinstance(given, dict):
        raise ValueError("%s isn't a JSON object" % path)
    for name in given:
        if name not in DEFAULTS:
            raise ValueError("%s has no setting %r" % (path, name))
        if type(given[name]) is not type(DEFAULTS[name]):
            raise ValueError("%s: %r should be %s" % (path, name, "a number" if isinstance(DEFAULTS[name], int) else "text"))
        settings[name] = given[name]
    for server in settings["servers"]:
        _check_server(path, server)
    return settings


def _check_server(path, server):
    if not isinstance(server, dict) or not isinstance(server.get("name"), str) or not server["name"]:
        raise ValueError("%s: each of servers should be an object with a name" % path)
    for name in server:
        if name == "name":
            continue
        if name not in SERVER_KEYS:
            raise ValueError("%s: server %r has no setting %r" % (path, server["name"], name))
        if type(server[name]) is not type(DEFAULTS[name]):
            raise ValueError("%s: server %r: %r should be %s" % (
                path, server["name"], name, "a number" if isinstance(DEFAULTS[name], int) else "text"))


def read_key(settings):
    """The API key the settings name, or ``""`` when they name no file.

    Raises:
        OSError: The key file isn't there, or is empty.
    """
    path = settings["key_file"]
    if not path:
        return ""
    with open(path) as f:
        key = f.read().strip()
    if not key:
        raise OSError("%s is empty" % path)
    return key
