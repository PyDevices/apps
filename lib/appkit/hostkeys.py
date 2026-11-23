# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Type on a USB keyboard plugged into the board's host port.

A keyboard on the host port types into whatever text field has the focus,
the same as the keyboard on the screen, and the on-screen keyboard closes
the moment it does. The Shell starts this for you on a board whose host
port it registers (`appkit.connections.usb_host`); a script can too::

    import endpointkit
    from usb.host import endpoints
    from appkit.hostkeys import HostKeys

    endpoints.register()
    typing = HostKeys(endpointkit.registry, look_ms=1000)

The keyboards it reads are the ones in use for endpointkit's ``keys`` kind:
the ones chosen in the picker, or, while none is chosen, every keyboard
plugged in. It follows `usb.host.endpoints` as keyboards come and go, and
reads only while a keyboard is in use, so a board with none plugged in
spends nothing on it.
"""

import errno

import lvgl as lv
import usb.core
from usb.host import endpoints as usb_endpoints
from usb.host import hid

from . import keys

#: How often an open keyboard is read, in ms.
READ_MS = 20

_ENODEV = getattr(errno, "ENODEV", 19)


class HostKeys:
    """Sends what the keyboards in use type to `appkit.keys`.

    Args:
        registry (endpointkit.Registry): where `usb.host.endpoints` registered
            its providers.
        read_ms (int): how often an open keyboard is read.
        look_ms (int or None): how often to poll *registry* for keyboards
            plugged in or pulled out. None when something else polls it
            already, as the status bar does once a second.

    Raises:
        ValueError: a keyboard in use has no interface ``usb.host.hid`` can read.
        usb.core.USBError: a keyboard in use refused to start.
    """

    def __init__(self, registry, read_ms=READ_MS, look_ms=None):
        self.registry = registry
        self.read_ms = read_ms
        #: endpoint id -> the open ``usb.host.hid.Device``
        self.open = {}
        # endpoint id -> the usb.core.Device that went away under it. It stays
        # listed until the next poll, and isn't opened again until then.
        self._gone = {}
        self._timer = None
        self._look = None
        # Kept: endpointkit unsubscribes by identity.
        self._listening = registry.subscribe("keys", self._changed)
        if look_ms:
            self._look = lv.timer_create(lambda t: registry.poll(), look_ms, None)
        self.update()

    def in_use(self):
        """The ``keys`` endpoints on the host port to read: the chosen ones,
        or every one plugged in while nothing is chosen."""
        reg = self.registry
        found = reg.selected("keys") if reg.selection("keys") else reg.endpoints("keys")
        return [ep for ep in found if usb_endpoints.device(ep) is not None]

    def update(self):
        """Open the keyboards that came into use and close the ones that left."""
        want = {}
        for ep in self.in_use():
            want[ep.id] = ep
        self._forget_gone(want)
        for ep_id in list(self.open):
            ep = want.get(ep_id)
            # A device of its own, until the host lists it again after a replug or a restart.
            if ep is None or usb_endpoints.device(ep) is not self.open[ep_id].dev:
                self._close(ep_id)
        for ep_id, ep in want.items():
            if ep_id in self.open or ep_id in self._gone:
                continue
            dev = usb_endpoints.device(ep)
            try:
                self.open[ep_id] = hid.Device(dev, hid.KEYBOARD, interface=usb_endpoints.interface(ep))
            except usb.core.USBError as e:
                if e.errno != _ENODEV:
                    raise
                self._gone[ep_id] = dev   # pulled out as it was opened
        self._fit_timer()

    def _forget_gone(self, want):
        """Let a keyboard that went away be opened again once the host has
        listed it again, as a new device, or dropped it."""
        for ep_id in list(self._gone):
            ep = want.get(ep_id)
            if ep is None or usb_endpoints.device(ep) is not self._gone[ep_id]:
                del self._gone[ep_id]

    def _fit_timer(self):
        busy = self.open or self._gone
        if busy and self._timer is None:
            self._timer = lv.timer_create(lambda t: self.read(), self.read_ms, None)
        elif not busy and self._timer is not None:
            self._timer.delete()
            self._timer = None

    def _changed(self, event, kind):
        self.update()

    def read(self):
        """Type what each open keyboard sent since the last read.

        A keyboard pulled out is closed. One that fails another way is closed
        too, and the error is raised.
        """
        if self._gone:
            self.update()
        for ep_id in list(self.open):
            dev = self.open[ep_id]
            try:
                while True:
                    ev = dev.read(-1)   # what has come in, without waiting
                    if ev is None:
                        break
                    if ev[0] == hid.KEY_DOWN:
                        keys.hid_key(ev[1], ev[2])
            except usb.core.USBError as e:
                self._gone[ep_id] = dev.dev
                self._close(ep_id)
                if e.errno != _ENODEV:
                    raise

    def _close(self, ep_id):
        dev = self.open.pop(ep_id)
        try:
            dev.close()
        except usb.core.USBError as e:
            if e.errno != _ENODEV:  # a keyboard pulled out has nothing to release
                raise
        finally:
            self._fit_timer()

    def close(self):
        """Stop reading: close every keyboard and stop following ``keys``."""
        self.registry.unsubscribe(self._listening)
        self._gone.clear()
        for ep_id in list(self.open):
            self._close(ep_id)
        for t in (self._timer, self._look):
            if t is not None:
                t.delete()
        self._timer = self._look = None
