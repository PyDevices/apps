# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""deskkit.localtime: keep the board's clock right, and read it in local time.

A board with no battery-backed clock forgets the time when it loses power, so
it asks the network. It tries NTP first. Guest and office networks often block
NTP, so a web server's ``Date`` header is the fallback.
"""

import time

try:
    import machine
    import ntptime
except ImportError:  # a desktop: the host keeps the time
    machine = None
    ntptime = None

try:
    import requests
except ImportError:
    requests = None

_FIRST_VALID_YEAR = 2025
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DATE_URL = "https://api.open-meteo.com/"
_RESYNC_S = 24 * 3600

offset_s = None  # seconds east of UTC at the chosen place; forecast sets it
_synced_at = None


def is_set():
    """Return True once the clock holds a real date."""
    return time.gmtime()[0] >= _FIRST_VALID_YEAR


def parse_http_date(text):
    """Return ``(year, month, day, hour, minute, second)`` from a ``Date`` header.

    Args:
        text (str): A date such as ``Wed, 04 Nov 2026 02:36:50 GMT``.

    Raises:
        ValueError: The text isn't in that format.
    """
    parts = text.split()
    if len(parts) != 6 or parts[2] not in _MONTHS:
        raise ValueError("bad date: %s" % text)
    hour, minute, second = parts[4].split(":")
    return (
        int(parts[3]),
        _MONTHS.index(parts[2]) + 1,
        int(parts[1]),
        int(hour),
        int(minute),
        int(second),
    )


def _set_from_web():
    resp = requests.get(_DATE_URL, timeout=10)
    try:
        for name, value in resp.headers.items():
            if name.lower() == "date":
                break
        else:
            raise ValueError("no Date header")
    finally:
        resp.close()
    y, mo, d, h, mi, s = parse_http_date(value)
    weekday = time.gmtime(time.mktime((y, mo, d, 12, 0, 0, 0, 0, 0)))[6]
    machine.RTC().datetime((y, mo, d, weekday, h, mi, s, 0))


def sync():
    """Set the clock from the network. It blocks: call it from a worker.

    Returns:
        bool: True when the clock was set, or the host keeps its own time.
    """
    global _synced_at
    if machine is None:
        return True
    try:
        ntptime.timeout = 3
        ntptime.settime()
    except Exception as exc:
        print("deskkit: NTP failed (%r), asking a web server" % (exc,))
        try:
            _set_from_web()
        except Exception as exc2:
            print("deskkit: could not set the clock: %r" % (exc2,))
            return False
    _synced_at = time.time()
    return True


def resync_if_due():
    """Set the clock when it's unset or a day has passed. Call it from a worker."""
    if not is_set() or _synced_at is None or time.time() - _synced_at >= _RESYNC_S:
        sync()


def now():
    """Return the local time as a ``time.gmtime``-style tuple."""
    if offset_s is None:
        return time.localtime()
    return time.gmtime(time.time() + offset_s)


def clock_time():
    """Return the local ``(hour, minute, second)``."""
    t = now()
    return t[3], t[4], t[5]
