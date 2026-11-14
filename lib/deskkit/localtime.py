# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""deskkit.localtime: keep the board's clock right, and read it in local time.

A board with no battery-backed clock forgets the time when it loses power, so
it asks the network. It tries NTP first. Guest and office networks often block
NTP, so a web server's ``Date`` header is the fallback.

The clock reads in the chosen place's time once Weather has a place
(``deskkit.forecast``). Until then the board asks ipwho.is which timezone its
public IP address is in: an IANA zone such as ``America/Chicago`` and that
zone's offset from UTC right now. ipwho.is is free and needs no key, and like
any web service it sees the board's public IP address. The answer is asked for
again with each daily resync, so a daylight saving change lands within a day.
When the lookup fails, the clock keeps what it had (UTC at first) and the board
asks again at the next resync.
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
_ZONE_URL = "https://ipwho.is/?fields=success,message,timezone.id,timezone.offset"
_RESYNC_S = 24 * 3600

offset_s = None  # seconds east of UTC: the chosen place's (forecast sets it), or the IP's
zone = None  # the IANA zone the IP lookup found, while no place is chosen
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


def due():
    """Return True when the clock is unset, or this program hasn't set it in a day."""
    return not is_set() or _synced_at is None or time.time() - _synced_at >= _RESYNC_S


def parse_ip_zone(reply):
    """Return ``(zone, offset_s)`` from an ipwho.is reply.

    Args:
        reply (dict): The decoded JSON.

    Raises:
        ValueError: The reply says the lookup failed.
    """
    if not reply.get("success"):
        raise ValueError(reply.get("message") or "no timezone in the reply")
    tz = reply["timezone"]
    return tz["id"], int(tz["offset"])


def follow_ip_zone():
    """Take the timezone from the board's public IP address, unless a place is
    chosen. It blocks: call it from a worker. A desktop keeps its own timezone.

    Returns:
        bool: True when the offset now comes from the IP.
    """
    global offset_s, zone
    if machine is None:
        return False
    from . import forecast  # here: forecast imports this module

    if forecast.place() is not None:
        zone = None
        return False  # a chosen place wins
    try:
        resp = requests.get(_ZONE_URL, timeout=10)
        try:
            found, offset = parse_ip_zone(resp.json())
        finally:
            resp.close()
    except Exception as exc:
        print("deskkit: no timezone from the IP address, keeping %s: %r" % (zone or "UTC", exc))
        return False
    if forecast.place() is not None:
        return False  # chosen while the lookup ran
    zone = found
    offset_s = offset
    return True


def resync_if_due():
    """Set the clock and the timezone when the clock is unset or a day has
    passed. Call it from a worker."""
    if due() and sync():
        follow_ip_zone()


def now():
    """Return the local time as a ``time.gmtime``-style tuple."""
    if offset_s is None:
        return time.localtime()
    return time.gmtime(time.time() + offset_s)


def clock_time():
    """Return the local ``(hour, minute, second)``."""
    t = now()
    return t[3], t[4], t[5]
