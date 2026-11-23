# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A stand-in for castdisplay's browser mirror: one ``cast.target`` endpoint
that is unavailable without a password, connected with an address once
chosen, and "viewing" while `watch` says so. No server, no network."""

import endpointkit


class Mirror(endpointkit.Provider):
    kind = "cast.target"
    name = "mirror"
    remember = False

    def __init__(self, password="secret"):
        endpointkit.Provider.__init__(self)
        self.password = password
        self.running = False
        self.viewing = False
        self._said = None

    def _list(self):
        if not self.password:
            return [self.endpoint("browser", "Browser on this network", endpointkit.UNAVAILABLE,
                                  caps={"why": "Set a WebREPL password to mirror this screen"})]
        state = endpointkit.CONNECTED if self.running else endpointkit.AVAILABLE
        url = "http://192.0.2.7/" if self.running else None
        return [self.endpoint("browser", "Browser on this network", state,
                              caps={"url": url, "viewing": self.viewing and self.running})]

    def scan(self):
        self._said = (self.running, self.viewing, self.password)
        return self._list()

    def poll(self):
        now = (self.running, self.viewing, self.password)
        if now != self._said:
            self._said = now
            return self._list()
        return None

    def apply(self, endpoint, chosen):
        if chosen and not self.password:
            raise ValueError("Set a WebREPL password first: the mirror asks for it")
        self.running = chosen
        if not chosen:
            self.viewing = False

    def watch(self, on=True):
        self.viewing = on
