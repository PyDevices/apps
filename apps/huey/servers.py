# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Huey's servers in the device's picker, under Assistant.

The server in Huey's settings, and each one in their ``servers`` list, is an
endpoint of endpointkit's ``assistant`` kind. Choose one in the picker and
Huey talks to it from his next turn, with its models, voice and key. The
choice is the device's, so another app that talks to an assistant can
follow it too. Without endpointkit installed, Huey uses the server in his
settings, as before.
"""

try:
    import endpointkit
except ImportError:
    endpointkit = None

from .settings import SERVER_KEYS

#: The provider's name: the first half of each endpoint's id.
NAME = "huey"
#: The local id of the server the settings give at their top level.
OWN = "settings"
#: The endpoint caps that say where an assistant is; other providers' endpoints
#: of the kind give these too, so Huey can follow any of them.
CAPS = SERVER_KEYS


def _slug(name):
    out = ""
    for ch in name.lower():
        out += ch if ("a" <= ch <= "z" or "0" <= ch <= "9") else "-"
    return out.strip("-") or "server"


def _where(base_url):
    """The host of *base_url*: "api.deepinfra.com", "192.168.1.20:5000"."""
    rest = base_url.split("://", 1)[-1]
    return rest.split("/", 1)[0]


def entries(settings):
    """``(local_id, label, caps)`` for each server *settings* give: their own
    first, when it has an address, then each of ``servers``."""
    out = []
    if settings["base_url"]:
        caps = {k: settings[k] for k in CAPS}
        out.append((OWN, _where(settings["base_url"]), caps))
    taken = [OWN]
    for server in settings["servers"]:
        local = _slug(server["name"])
        n = 2
        while local in taken:
            local = "%s-%d" % (_slug(server["name"]), n)
            n += 1
        taken.append(local)
        caps = {k: settings[k] for k in CAPS}
        caps.update({k: v for k, v in server.items() if k != "name"})
        out.append((local, server["name"], caps))
    return out


if endpointkit is not None:

    class Servers(endpointkit.Provider):
        """The servers Huey's settings give, as endpoints of ``assistant``."""

        def __init__(self, settings):
            endpointkit.Provider.__init__(self, "assistant", NAME)
            self._settings = settings
            self._dirty = False

        def update(self, settings):
            """Take newly loaded *settings*; the list changes at the next poll."""
            if entries(settings) != entries(self._settings):
                self._dirty = True
            self._settings = settings

        def scan(self):
            return [self.endpoint(i, label, caps=caps) for i, label, caps in entries(self._settings)]

        def poll(self):
            if self._dirty:
                self._dirty = False
                return self.scan()
            return None


def use(settings, registry=None):
    """*settings* with the chosen assistant's over them.

    Registers Huey's servers with *registry* (the device's when None) the
    first time, and gives it the latest settings after. When the device has
    chosen an assistant that is found, its caps (an address, models, a key
    file) replace those settings; otherwise *settings* come back as they are.
    """
    if endpointkit is None:
        return settings
    reg = registry if registry is not None else endpointkit.registry
    mine = None
    for p in reg.providers("assistant"):
        if p.name == NAME:
            mine = p
    if mine is None:
        if "assistant" not in endpointkit.KINDS:
            # An endpointkit from before the kind was built in.
            endpointkit.add_kind("assistant", endpointkit.ONE)
        mine = Servers(settings)
        reg.register(mine)
    else:
        mine.update(settings)
        reg.poll()
    chosen = reg.selected("assistant")
    if not chosen:
        return settings
    out = dict(settings)
    for k in CAPS:
        if k in chosen[0].caps:
            out[k] = chosen[0].caps[k]
    return out
