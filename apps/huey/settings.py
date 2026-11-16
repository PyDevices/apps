# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The app's settings: which server Huey talks to, with which models and key.

They are one JSON file, ``settings.json`` in the app's data folder
(``/data/huey`` on a board). `load` reads it over `DEFAULTS`, so the file
holds only what differs, and no file at all means the defaults.
"""

import json

#: Every setting and its value when the file doesn't give one.
DEFAULTS = {
    # an OpenAI-compatible server: the address its /chat/completions is under
    "base_url": "https://api.deepinfra.com/v1/openai",
    # a file holding the API key on one line; "" for a server that asks for none
    "key_file": "/deepinfra.key",
    "stt_model": "openai/whisper-large-v3-turbo",
    "chat_model": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
    "tts_model": "inworld-ai/realtime-tts-1.5-mini",
    # a voice the speech model has, or "" for its own: Huey is a he, so a man's
    "voice": "Dennis",
    # the rate of speech that comes back as bare PCM; WAV carries its own
    "speech_rate": 24000,
    # how loud Huey speaks, 0 to 100
    "volume": 80,
    # the longest question, in seconds
    "listen_seconds": 12,
    # where Huey is when the app opens: coast, bench or desk
    "place": "desk",
}


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
    return settings


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
