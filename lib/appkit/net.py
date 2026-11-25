# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit.net: sockets, HTTP and the clock, with the same calls on every Python.

CircuitPython reaches the network differently from MicroPython and a desktop.
It has no ``socket`` module: sockets come from a ``socketpool.SocketPool`` on
``wifi.radio``, which has the same ``socket()``, ``getaddrinfo()`` and
constants. Its core has no HTTP client: Adafruit's ``adafruit_requests``, from
the CircuitPython library bundle, gives a ``Session`` with the calls of
``requests``. And its clock is ``rtc.RTC()``, where MicroPython's is
``machine.RTC()`` and a desktop keeps its own.

An app or library that goes through these runs on all three::

    from appkit import net

    resp = net.requests().get("https://example.com/", timeout=10)
    sock = net.sockets().socket()

A missing piece raises ``ImportError`` saying what to install; nothing here
falls back quietly to something else.
"""

import struct
import sys
import time

CIRCUITPYTHON = sys.implementation.name == "circuitpython"

try:
    import machine
    import ntptime
except ImportError:  # a desktop keeps its own time; CircuitPython has neither
    machine = None
    ntptime = None

#: Where `ntp` asks on CircuitPython. MicroPython's ``ntptime`` has its own.
NTP_HOST = "pool.ntp.org"
# Seconds from NTP's epoch (1900) to the Unix one (1970).
_NTP_DELTA = 2208988800

_pool = None
_session = None
_local_time = time.localtime


def sockets():
    """Return what makes sockets: the ``socket`` module, or on CircuitPython a
    ``socketpool.SocketPool`` on ``wifi.radio``.

    Both have ``socket(family, type)``, ``getaddrinfo(host, port)`` and the
    ``AF_INET``, ``SOCK_STREAM`` and ``SOCK_DGRAM`` constants. Read with `recv`,
    since CircuitPython's sockets have ``recv_into`` but no ``recv``.
    """
    global _pool
    if not CIRCUITPYTHON:
        import socket

        return socket
    if _pool is None:
        import socketpool
        import wifi

        _pool = socketpool.SocketPool(wifi.radio)
    return _pool


def recv(sock, size):
    """Return up to *size* bytes from *sock*, ``b""`` when the other end has closed.

    Args:
        sock: A socket made through `sockets`, stream or datagram.
        size (int): The most to read.
    """
    if not CIRCUITPYTHON:
        return sock.recv(size)
    buf = bytearray(size)
    n = sock.recv_into(buf)
    return bytes(buf[:n])


def requests():
    """Return an HTTP client with the calls of ``requests``.

    That's the ``requests`` module on MicroPython and a desktop, and on
    CircuitPython one ``adafruit_requests.Session`` on `sockets` with TLS,
    kept for the program's life. Responses have ``json()``, ``content``,
    ``headers`` and ``close()`` everywhere.

    Raises:
        ImportError: The client isn't installed; the message says how to get it.
    """
    global _session
    if not CIRCUITPYTHON:
        try:
            import requests as client
        except ImportError:
            raise ImportError('HTTP needs requests: mip.install("requests"), or pip install requests on a computer')
        return client
    if _session is None:
        try:
            import adafruit_requests
        except ImportError:
            raise ImportError(
                'HTTP on CircuitPython needs adafruit_requests: omip.install("adafruit_requests") on the board, '
                "or circup install adafruit_requests from a computer"
            )
        import ssl

        _session = adafruit_requests.Session(sockets(), ssl.create_default_context())
    return _session


def sets_clock():
    """Return True where this program keeps the clock (a board), False where
    the computer does (a desktop)."""
    return CIRCUITPYTHON or machine is not None


def local_time():
    """Return the local time as a ``time.localtime``-style tuple.

    It comes from the source a library set with `set_local_time`, so the
    status bar and the apps read the same zone. With none set, it's
    ``time.localtime()``: on a board that's UTC, and on a desktop the
    computer's zone.
    """
    return _local_time()


def set_local_time(source):
    """Have `local_time` read from ``source``.

    A board keeps its clock in UTC and doesn't know its zone. A library that
    finds the zone (deskkit looks it up from the board's IP address, or the
    place chosen in Weather) sets itself here, and the status bar's clock
    follows it without depending on that library.

    Args:
        source: a function taking no arguments and returning a
            ``time.localtime``-style tuple.
    """
    global _local_time
    _local_time = source


def set_clock(year, month, day, hour, minute, second):
    """Set the board's clock to a UTC time.

    Raises:
        OSError: This is a desktop, whose clock is the computer's.
    """
    weekday = time.localtime(time.mktime((year, month, day, 12, 0, 0, 0, 0, 0)))[6]
    if CIRCUITPYTHON:
        import rtc

        rtc.RTC().datetime = time.struct_time((year, month, day, hour, minute, second, weekday, -1, -1))
    elif machine is not None:
        machine.RTC().datetime((year, month, day, weekday, hour, minute, second, 0))
    else:
        raise OSError("a desktop keeps its own clock")


def ntp(timeout=3):
    """Set the board's clock from NTP. It blocks: call it from a worker.

    MicroPython asks through its ``ntptime``; CircuitPython sends one SNTP
    query to `NTP_HOST` over `sockets`.

    Raises:
        OSError: No answer within *timeout* seconds, or this is a desktop.
    """
    if not CIRCUITPYTHON:
        if ntptime is None:
            raise OSError("a desktop keeps its own clock")
        ntptime.timeout = timeout
        ntptime.settime()
        return
    pool = sockets()
    addr = pool.getaddrinfo(NTP_HOST, 123)[0][-1]
    s = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
    try:
        s.settimeout(timeout)
        query = bytearray(48)
        query[0] = 0x1B  # version 3, client
        s.sendto(query, addr)
        reply = bytearray(48)
        n = s.recvfrom_into(reply)[0]
    finally:
        s.close()
    if n < 48:
        raise OSError("a short NTP reply (%d bytes)" % n)
    seconds = struct.unpack("!I", reply[40:44])[0] - _NTP_DELTA
    set_clock(*time.localtime(seconds)[:6])
