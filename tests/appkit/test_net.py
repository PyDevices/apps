# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit.net on CircuitPython, with its modules faked on CPython.

The socket pool, the HTTP session, the SNTP query and the clock each take
CircuitPython's path here; on a real board they are checked by hand.
"""

import importlib.util
import os
import struct
import sys
import time
import unittest
from unittest import mock

# By its file: the appkit package brings LVGL and icons, which this needs neither of.
_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib", "appkit", "net.py")
_spec = importlib.util.spec_from_file_location("appkit_net", _PATH)
net = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(net)

# 2026-11-14 12:34:56 UTC, as NTP counts it (from 1900).
WHEN = (2026, 11, 14, 12, 34, 56)
NTP_SECONDS = 1794659696 + 2208988800


class _Socket:
    def __init__(self, reply):
        self.reply = reply
        self.sent = []
        self.closed = False

    def settimeout(self, t):
        self.timeout = t

    def sendto(self, data, addr):
        self.sent.append((bytes(data), addr))

    def recvfrom_into(self, buf):
        buf[: len(self.reply)] = self.reply
        return len(self.reply), ("192.0.2.9", 123)

    def recv_into(self, buf):
        n = min(len(buf), len(self.reply))
        buf[:n] = self.reply[:n]
        self.reply = self.reply[n:]
        return n

    def close(self):
        self.closed = True


class _Pool:
    AF_INET = 2
    SOCK_STREAM = 1
    SOCK_DGRAM = 2

    def __init__(self, radio, reply=b""):
        self.radio = radio
        self.made = []
        self.reply = reply

    def getaddrinfo(self, host, port):
        return [(2, 2, 0, "", (host, port))]

    def socket(self, family=2, kind=1):
        s = _Socket(self.reply)
        self.made.append(s)
        return s


class CircuitPythonTest(unittest.TestCase):
    def setUp(self):
        self.rtc = mock.MagicMock()
        self.wifi = mock.MagicMock()
        self.socketpool = mock.MagicMock()
        reply = bytearray(48)
        reply[40:44] = struct.pack("!I", NTP_SECONDS)
        self.pool = _Pool(self.wifi.radio, bytes(reply))
        self.socketpool.SocketPool.return_value = self.pool
        fakes = {"rtc": self.rtc, "wifi": self.wifi, "socketpool": self.socketpool, "ssl": mock.MagicMock()}
        patches = [
            mock.patch.dict(sys.modules, fakes),
            mock.patch.object(net, "CIRCUITPYTHON", True),
            mock.patch.object(net, "_pool", None),
            mock.patch.object(net, "_session", None),
            # CircuitPython's struct_time is a tuple; CPython's won't take -1 days.
            mock.patch.object(time, "struct_time", tuple),
            # CircuitPython keeps no timezone: its localtime() is UTC.
            mock.patch.object(time, "localtime", time.gmtime),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_sockets_come_from_a_pool_on_the_radio(self):
        self.assertIs(net.sockets(), self.pool)
        self.assertIs(net.sockets(), self.pool)  # one pool, kept
        self.socketpool.SocketPool.assert_called_once_with(self.wifi.radio)

    def test_recv_reads_through_recv_into(self):
        s = _Socket(b"hello")
        self.assertEqual(net.recv(s, 3), b"hel")
        self.assertEqual(net.recv(s, 9), b"lo")
        self.assertEqual(net.recv(s, 9), b"")

    def test_ntp_sets_the_rtc_from_one_sntp_query(self):
        net.ntp(timeout=2)
        sock = self.pool.made[0]
        self.assertEqual(sock.sent[0][1], (net.NTP_HOST, 123))
        self.assertEqual(sock.sent[0][0][0], 0x1B)
        self.assertTrue(sock.closed)
        self.assertEqual(tuple(self.rtc.RTC.return_value.datetime[:6]), WHEN)

    def test_a_short_ntp_reply_is_refused(self):
        self.pool.reply = b"\x1c" * 12
        with self.assertRaisesRegex(OSError, "short"):
            net.ntp()

    def test_http_without_adafruit_requests_says_what_to_install(self):
        with mock.patch.dict(sys.modules, {"adafruit_requests": None}):
            with self.assertRaisesRegex(ImportError, 'omip.install\\("adafruit_requests"\\)'):
                net.requests()

    def test_http_is_one_session_on_the_pool(self):
        lib = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"adafruit_requests": lib}):
            session = net.requests()
            self.assertIs(net.requests(), session)
        lib.Session.assert_called_once()
        self.assertIs(lib.Session.call_args[0][0], self.pool)

    def test_the_board_keeps_the_clock(self):
        self.assertTrue(net.sets_clock())


class DesktopTest(unittest.TestCase):
    def test_a_desktop_keeps_its_own_clock(self):
        with mock.patch.object(net, "machine", None), mock.patch.object(net, "ntptime", None):
            self.assertFalse(net.sets_clock())
            with self.assertRaises(OSError):
                net.ntp()
            with self.assertRaises(OSError):
                net.set_clock(*WHEN)

    def test_sockets_are_the_socket_module(self):
        import socket

        self.assertIs(net.sockets(), socket)


if __name__ == "__main__":
    unittest.main()
