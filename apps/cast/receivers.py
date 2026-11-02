# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The screens on the network that take a Miracast cast.

Three ways in, from quickest to slowest, and Cast lists what each finds as it
comes:

* **Remembered.** The receivers cast to before, kept in ``receivers.json``
  in the Cast app's data folder.
* **Announced.** A receiver that announces itself on mDNS as
  ``_display._tcp`` (Rokus do, and most smart TVs); about two seconds.
* **Listening.** A Windows PC with its Wireless Display app open announces
  itself only over Wi-Fi Direct, which this board can't hear, but it listens
  on Miracast's port, 7250. ``sweep()`` knocks on that port at every address
  on the subnet, a few at a time (the firmware has ten sockets), and asks
  each one that answers for its NetBIOS name.

A receiver is a dict: ``name``, ``host`` (its IPv4 address) and ``kind``,
"roku" for a Roku (it answers Roku's control port, 8060, and wants MICE's
session request) and "windows" for anything else.
"""

import socket
import struct

from devkit.clock import sleep_ms
from multimer import ticks_diff, ticks_ms

REMEMBER = "receivers.json"
MICE = 7250
BATCH = 8  # sockets at once: ten in the firmware, one or two held by WebREPL and the rest
WAIT_MS = 800  # an absent address costs this; a PC on Wi-Fi answers in 20 to 300 ms


def remembered(folder):
    """The receivers remembered in *folder*, last cast to first."""
    try:
        import json

        with open(folder + "/" + REMEMBER) as f:
            return [r for r in json.load(f).get("receivers", []) if r.get("host")]
    except (OSError, ValueError):
        return []


def remember(folder, receiver):
    """Put *receiver* first in *folder*'s ``receivers.json``. Call it before
    the cast starts: a flash write during one stalls the stream."""
    import json

    keep = [r for r in remembered(folder) if r["host"] != receiver["host"]]
    keep.insert(0, {k: receiver[k] for k in ("name", "host", "kind")})
    try:
        with open(folder + "/" + REMEMBER, "w") as f:
            json.dump({"receivers": keep[:6]}, f)
    except OSError as e:
        print("cast: couldn't remember %s: %s" % (receiver["host"], e))


def _is_roku(host):
    from devkit import ecp

    try:
        return ecp.device_info(host) is not None
    except OSError:
        return False


def announced():
    """The receivers that answer an mDNS browse for ``_display._tcp``."""
    import mdns
    import network

    # One mdns.Server may be live at a time (CircuitPython's rule), so give
    # it back before the next scan.
    server = mdns.Server(network.WLAN(network.STA_IF))
    try:
        found = server.find(service_type="_display", protocol="_tcp", timeout=2)
    finally:
        server.deinit()
    out = []
    for s in found:
        if s.ipv4_address:
            host = str(s.ipv4_address)
            out.append({"name": s.instance_name, "host": host, "kind": "roku" if _is_roku(host) else "windows"})
    return out


def netbios_name(host, ms=1200, tries=2):
    """A Windows PC's own name, from a NetBIOS node-status query sent to it
    (Windows answers one sent directly, not a broadcast), or None."""
    q = struct.pack(">HHHHHH", 0x4242, 0, 1, 0, 0, 0) + b"\x20CK" + b"A" * 30 + b"\x00" + struct.pack(">HH", 0x21, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(ms / 1000)
        d = None
        for _ in range(tries):  # UDP on Wi-Fi: one may go missing
            s.sendto(q, socket.getaddrinfo(host, 137)[0][-1])
            try:
                d = s.recv(1024)
                break
            except OSError:
                pass
        if d is None:
            return None
        at = 12 + 34 + 10  # header, the name asked about, its type, class, TTL and length
        for i in range(d[at]):
            e = d[at + 1 + i * 18 : at + 19 + i * 18]
            if e[15] == 0 and not e[16] & 0x80:  # the workstation name, not a group
                return bytes(e[:15]).decode().strip()
    except (OSError, IndexError, ValueError):
        pass
    finally:
        s.close()
    return None


def _listening(hosts):
    """``(those of *hosts* that accept a connection on 7250, how many were
    tried)``: fewer than asked when the firmware runs out of sockets."""
    import errno
    import select

    poll = select.poll()
    socks = {}
    tried = 0
    for h in hosts:
        try:
            s = socket.socket()
        except OSError:
            break  # out of sockets: the rest wait for the next batch
        s.setblocking(False)
        try:
            s.connect(socket.getaddrinfo(h, MICE)[0][-1])
        except OSError:
            pass  # EINPROGRESS: the answer comes through poll
        poll.register(s, select.POLLOUT)
        socks[id(s)] = (s, h)
        tried += 1
    found = []
    start = ticks_ms()
    try:
        while socks:
            left = WAIT_MS - ticks_diff(ticks_ms(), start)
            if left <= 0:
                break
            for obj, _ in poll.poll(left):
                s, h = socks.pop(id(obj), (None, None))
                if s is None:
                    continue
                poll.unregister(s)
                # Refused shows as writable too; a live connection has
                # nothing to read yet, a refused one is reset.
                try:
                    s.recv(1)
                    found.append(h)
                except OSError as e:
                    if e.args and e.args[0] == errno.EAGAIN:
                        found.append(h)
                s.close()
    finally:
        for s, _ in socks.values():
            s.close()
    return found, tried


def subnet_hosts(skip=()):
    """Every other address on this board's /24, in order."""
    import network

    me = network.WLAN(network.STA_IF).ifconfig()[0]
    base = me.rsplit(".", 1)[0]
    return [h for h in ("%s.%d" % (base, i) for i in range(1, 255)) if h != me and h not in skip]


def sweep(hosts):
    """Receivers among *hosts* that listen on Miracast's port, named."""
    out = []
    i = 0
    while i < len(hosts):
        found, tried = _listening(hosts[i : i + BATCH])
        if not tried:  # every socket busy: give them a moment, then go on regardless
            sleep_ms(300)
            found, tried = _listening(hosts[i : i + 1])
            tried = max(tried, 1)
        i += tried
        for h in found:
            roku = _is_roku(h)
            name = None if roku else netbios_name(h)
            out.append({"name": name or ("Roku at " if roku else "Computer at ") + h, "host": h,
                        "kind": "roku" if roku else "windows"})
    return out
