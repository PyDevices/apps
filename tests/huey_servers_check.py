# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Huey's servers as endpointkit's ``assistant`` kind, with no network.

    OMNIPYTHON_DIR=../omnipython python tests/huey_servers_check.py
    OMNIPYTHON_DIR=../omnipython micropython tests/huey_servers_check.py

endpointkit comes from ``$OMNIPYTHON_DIR`` (or an ``omnipython`` checkout
beside this repository), and the app needs what Huey's contract does (LVGL,
svgio). Exits 1 if a check fails, 2 if something it needs isn't there.
"""

import os
import sys


def _up(path):
    return path.rsplit("/", 1)[0] if "/" in path else "."


_HERE = _up(__file__)
_ROOT = _up(_HERE)
_OMNI = os.getenv("OMNIPYTHON_DIR") or _ROOT + "/../omnipython"
sys.path[:0] = [_ROOT, _OMNI + "/packages/endpointkit"]

try:
    import endpointkit
except ImportError as e:
    print("can't run the server checks:", e)
    sys.exit(2)

# Through the app's package, which needs LVGL and svgio as Huey's other checks do.
try:
    from apps.huey import servers, settings as settingsmod
except ImportError as e:
    print("can't run the server checks:", e)
    sys.exit(2)

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)
        print("FAILED:", what)


def raises(fn, *args):
    try:
        fn(*args)
    except ValueError as e:
        return str(e)
    return None


SCRATCH = os.getenv("HUEY_SCRATCH") or "/tmp"
PATH = SCRATCH + "/huey_servers_settings.json"


def settings_with(text):
    with open(PATH, "w") as f:
        f.write(text)
    return settingsmod.load(PATH)


# The settings take a list of servers, and refuse a malformed one.
base = settings_with('{"base_url": "http://192.168.1.20:5000/v1", "servers": ['
                     '{"name": "DeepInfra", "base_url": "https://api.deepinfra.com/v1/openai",'
                     ' "key_file": "/deepinfra.key", "chat_model": "big"},'
                     '{"name": "Desk box", "voice": "am_echo"}]}')
check(len(base["servers"]) == 2, "two servers load")
for bad, why in (
    ('{"servers": [{"base_url": "x"}]}', "a server with no name"),
    ('{"servers": [{"name": "A", "colour": "red"}]}', "a setting servers don't have"),
    ('{"servers": [{"name": "A", "volume": "loud"}]}', "a setting only Huey has"),
    ('{"servers": [{"name": "A", "speech_rate": "fast"}]}', "a number given as text"),
    ('{"servers": ["A"]}', "a server that isn't an object"),
):
    check(raises(settings_with, bad) is not None, "refused: " + why)

# Each server is an endpoint, the settings' own first, labelled by its host.
got = servers.entries(base)
check([e[0] for e in got] == ["settings", "deepinfra", "desk-box"], "the local ids: %r" % ([e[0] for e in got],))
check([e[1] for e in got] == ["192.168.1.20:5000", "DeepInfra", "Desk box"], "the labels: %r" % ([e[1] for e in got],))
check(got[1][2]["chat_model"] == "big" and got[1][2]["stt_model"] == base["stt_model"],
      "a server's caps are its own settings over Huey's")
check(got[2][2]["base_url"] == base["base_url"] and got[2][2]["voice"] == "am_echo",
      "a server that gives no address uses Huey's")
twins = settings_with('{"servers": [{"name": "Box"}, {"name": "Box"}]}')
check([e[0] for e in servers.entries(twins)] == ["box", "box-2"], "two of a name get their own ids")
check(servers.entries(settings_with("{}")) == [], "no address and no servers is no endpoint")

# Choosing one in the device's picker changes what Huey talks to.
reg = endpointkit.Registry()
used = servers.use(base, reg)
check(used == base, "nothing chosen: the settings as they are")
check([ep.id for ep in reg.endpoints("assistant")] == ["huey:settings", "huey:deepinfra", "huey:desk-box"],
      "Huey's servers are in the picker")
reg.select("assistant", "huey:deepinfra")
used = servers.use(base, reg)
check(used["base_url"] == "https://api.deepinfra.com/v1/openai" and used["key_file"] == "/deepinfra.key"
      and used["chat_model"] == "big", "the chosen server's address, key and model")
check(used["volume"] == base["volume"] and used["place"] == base["place"], "Huey's own settings stay his")

# New settings reach the picker; registering twice doesn't happen.
fewer = settings_with('{"base_url": "http://192.168.1.20:5000/v1"}')
servers.use(fewer, reg)
check([ep.id for ep in reg.endpoints("assistant")] == ["huey:settings"], "a server taken out leaves the picker")
check(len(reg.providers("assistant")) == 1, "one provider however often Huey loads")
check(servers.use(fewer, reg) == fewer, "a chosen server that's gone: the settings as they are")

# Another app's assistant is followed too.
reg.register(endpointkit.Provider("assistant", "other"))
other = reg.providers("assistant")[-1]
other.scan = lambda: [other.endpoint("x", "Other", caps={"base_url": "http://other/v1", "chat_model": "m"})]
reg.refresh("assistant")
reg.select("assistant", "other:x")
used = servers.use(fewer, reg)
check(used["base_url"] == "http://other/v1" and used["chat_model"] == "m" and used["tts_model"] == fewer["tts_model"],
      "another provider's assistant gives what it has")

os.remove(PATH)
print("huey servers: %d failed" % len(failures))
sys.exit(1 if failures else 0)
