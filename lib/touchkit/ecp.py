# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit.ecp -- Roku's External Control Protocol, for the remote and Cast.

Every call blocks on the network, so run it on ``scope.worker``. Each
request opens a socket and closes it when done: nothing is left open when
an app closes. The TV must have "Control by mobile apps" on (it is by
default).
"""

import socket
from multimer import ticks_add, ticks_diff, ticks_ms

PORT = 8060


def _addr(host):
    return socket.getaddrinfo(host, PORT)[0][-1]


def request(host, method, path, timeout=3):
    """``(status, body)`` of one HTTP request to the Roku at *host*."""
    s = socket.socket()
    try:
        s.settimeout(timeout)
        s.connect(_addr(host))
        s.send(
            (
                "%s %s HTTP/1.1\r\nHost: %s:%d\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                % (method, path, host, PORT)
            ).encode()
        )
        data = b""
        while len(data) < 16384:
            chunk = s.recv(2048)
            if not chunk:
                break
            data += chunk
    finally:
        s.close()
    head, _, body = data.partition(b"\r\n\r\n")
    line = head.split(b"\r\n", 1)[0].split()
    code = int(line[1]) if len(line) > 1 else 0
    return code, body


#: A TV in standby takes about 5 s to answer a key, with 202.
KEY_TIMEOUT = 8


def keypress(host, key):
    """Press *key* (``"Select"``, ``"VolumeUp"``, ``"PowerOn"``...) on the Roku at *host*."""
    code, _ = request(host, "POST", "/keypress/" + key, timeout=KEY_TIMEOUT)
    if not 200 <= code < 300:  # 202 from a TV in standby
        raise OSError("the TV answered %d" % code)
    return code


def _tag(xml, tag):
    a = xml.find(b"<" + tag + b">")
    if a < 0:
        return None
    a += len(tag) + 2
    b = xml.find(b"</" + tag + b">", a)
    return xml[a:b].decode() if b > a else None


def device_info(host):
    """``{host, name, model, power}`` for the Roku at *host*, or None."""
    code, body = request(host, "GET", "/query/device-info")
    if code != 200:
        return None
    name = _tag(body, b"user-device-name") or _tag(body, b"friendly-device-name") or host
    model = _tag(body, b"friendly-model-name") or _tag(body, b"model-name") or ""
    power = _tag(body, b"power-mode") or ""
    return {"host": host, "name": name, "model": model, "power": power}


def discover(seconds=2.5):
    """``[{host, name, model, power}]`` for every Roku that answers SSDP."""
    msg = (
        b"M-SEARCH * HTTP/1.1\r\nHost: 239.255.255.250:1900\r\nMan: \"ssdp:discover\"\r\n"
        b"ST: roku:ecp\r\nMX: 2\r\n\r\n"
    )
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    hosts = []
    try:
        s.settimeout(0.3)
        dest = socket.getaddrinfo("239.255.255.250", 1900)[0][-1]
        for _ in range(2):
            s.sendto(msg, dest)
        end = ticks_add(ticks_ms(), int(seconds * 1000))
        while ticks_diff(end, ticks_ms()) > 0:
            try:
                data = s.recv(1024)
            except OSError:
                continue
            for line in data.split(b"\r\n"):
                if line[:9].lower() == b"location:":
                    url = line[9:].strip().decode()
                    host = url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
                    if host not in hosts:
                        hosts.append(host)
    finally:
        s.close()
    found = []
    for h in hosts:
        try:
            info = device_info(h)
        except OSError:
            info = None
        if info:
            found.append(info)
    return found


def pick(tvs, prefer=None, last=None):
    """The index in *tvs* to choose, or None when *prefer* matches none.

    *last* (a host) if it's there; else, with *prefer*, the first TV whose
    name holds it, then the first whose model does; else, with no *prefer*,
    0. A name is checked before any model because a short preference (say
    "65") can sit inside another TV's model number ("75R655"), and a remote
    that guesses sends its keys to the wrong set."""
    for i, t in enumerate(tvs):
        if last and t["host"] == last:
            return i
    if prefer:
        for key in ("name", "model"):
            for i, t in enumerate(tvs):
                if prefer in (t[key] or ""):
                    return i
        return None
    return 0
