# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""deskkit.localtime: keep the board's clock right, and read it in local time.

A board with no battery-backed clock forgets the time when it loses power, so
it asks the network. It tries NTP first. Guest and office networks often block
NTP, so a web server's ``Date`` header is the fallback.

The clock reads in the chosen place's time once Weather has a place
(``deskkit.forecast``). Until then the board asks ipwho.is where its public IP
address is: the city, its coordinates, an IANA zone such as
``America/Chicago`` and that zone's offset from UTC right now. The zone sets
the clock, and the city becomes Weather's place until you choose one, so the
weather shows at once. ipwho.is is free and needs no key, and like any web
service it sees the board's public IP address. The answer is asked for again
with each daily resync, so a daylight saving change lands within a day. When
the lookup fails, the clock keeps what it had (UTC at first), Weather asks for
a ZIP code, and the board asks again a minute later, then at longer gaps up
to an hour: the first lookup after joining a network can fail while the link
settles, and the clock would otherwise stay on UTC for a day.

A browser page looks up its place the same way, from the visitor's public IP
address, so Weather opens on a forecast there too. The browser keeps the
time; the zone and the place come from the lookup, as on a board. ipwho.is
counts a page's lookups per site rather than per visitor, so when it refuses
one the page asks GeoJS (get.geojs.io, also free with no key), which names
the zone but not its offset: the first forecast brings that.
"""

import sys
import time

from appkit import net

# CircuitPython has no time.gmtime. It keeps no timezone, so its localtime()
# is UTC and does the same job.
gmtime = getattr(time, "gmtime", time.localtime)

# Where Python runs in a browser page: the browser keeps the clock, but
# nothing else says where the page is.
_BROWSERS = ("webassembly", "emscripten")
_FIRST_VALID_YEAR = 2025
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DATE_URL = "https://api.open-meteo.com/"
_IP_URL = (
    "https://ipwho.is/?fields=success,message,city,country_code,latitude,longitude,"
    "timezone.id,timezone.offset"
)
# A browser page's second source. ipwho.is counts a page's lookups per site,
# not per visitor (1,000 a day for everyone together), and refuses the rest.
_GEOJS_URL = "https://get.geojs.io/v1/ip/geo.json"
# Where the IP is in one of these, temperatures start in Fahrenheit.
_FAHRENHEIT = ("US", "PR", "GU", "VI", "AS", "MP", "LR", "KY", "BS", "BZ", "PW", "FM", "MH")
_RESYNC_S = 24 * 3600
# After a failed IP lookup: the first wait before the next try, and the longest.
_IP_RETRY_S = 60
_IP_RETRY_MAX_S = 3600

offset_s = None  # seconds east of UTC: the chosen place's (forecast sets it), or the IP's
zone = None  # the IANA zone the IP lookup found, while no place is chosen
_synced_at = None
_looked = False  # a resync has run since boot, so the IP lookup is done or failed
_ip_retry_at = None  # when a failed IP lookup is tried again
_ip_wait_s = 0  # the wait before that try


def is_set():
    """Return True once the clock holds a real date."""
    return gmtime()[0] >= _FIRST_VALID_YEAR


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
    resp = net.requests().get(_DATE_URL, timeout=10)
    try:
        for name, value in resp.headers.items():
            if name.lower() == "date":
                break
        else:
            raise ValueError("no Date header")
    finally:
        resp.close()
    net.set_clock(*parse_http_date(value))


def sync():
    """Set the clock from the network. It blocks: call it from a worker.

    Returns:
        bool: True when the clock was set, or the host keeps its own time.
    """
    global _synced_at
    if not net.sets_clock():
        _synced_at = time.time()  # so a browser looks its place up once a day
        return True
    try:
        net.ntp(3)
    except Exception as exc:
        print("deskkit: NTP failed (%r), asking a web server" % (exc,))
        try:
            _set_from_web()
        except Exception as exc2:
            print("deskkit: could not set the clock: %r" % (exc2,))
            return False
    _synced_at = time.time()
    keep_board_clock()
    return True


def keep_board_clock():
    """Copy the clock, now set from the network, to the board's own clock
    chip (its ``rtc`` role), which keeps time while the board is off. The
    board's config reads it back at the next start. Does nothing on a board
    without one."""
    board = sys.modules.get("board_config")
    if board is None or "rtc" not in getattr(board, "PERIPHERALS", ()):
        return
    try:
        t = gmtime()
        board.rtc.datetime((t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))
    except Exception as exc:
        print("deskkit: the board's clock chip wasn't set: %r" % (exc,))


def due():
    """Return True when the clock is unset, or this program hasn't set it in a day."""
    if not is_set() or _synced_at is None or time.time() - _synced_at >= _RESYNC_S:
        return True
    return _ip_retry_at is not None and time.time() >= _ip_retry_at


def finds_place():
    """Return True where the program looks up its place from its public IP
    address: on a board, and in a browser page. A desktop keeps its own
    timezone, and Weather asks it for a ZIP code."""
    return net.sets_clock() or sys.platform in _BROWSERS


def parse_ip_zone(reply):
    """Return ``(zone, offset_s)`` from an ipwho.is reply.

    Args:
        reply (dict): The decoded JSON.

    Returns:
        tuple: The IANA zone, and its offset from UTC now in seconds, or None
        when the reply doesn't say (`from_geojs`).

    Raises:
        ValueError: The reply says the lookup failed.
    """
    if not reply.get("success"):
        raise ValueError(reply.get("message") or "no timezone in the reply")
    tz = reply["timezone"]
    offset = tz.get("offset")
    return tz["id"], None if offset is None else int(offset)


def from_geojs(reply):
    """Return a GeoJS reply in the shape of an ipwho.is one.

    GeoJS names the zone but not its offset, so the offset is None; the first
    forecast brings it.

    Args:
        reply (dict): The decoded JSON of GeoJS's ``/v1/ip/geo.json``.
    """
    if not reply.get("timezone"):
        return {"success": False, "message": "no timezone in GeoJS's reply"}

    def number(key):
        value = reply.get(key)
        return None if value in (None, "") else float(value)

    return {
        "success": True,
        "city": reply.get("city"),
        "country_code": reply.get("country_code"),
        "latitude": number("latitude"),
        "longitude": number("longitude"),
        "timezone": {"id": reply["timezone"], "offset": None},
    }


def _get_json(url):
    resp = net.requests().get(url, timeout=10)
    try:
        return resp.json()
    finally:
        resp.close()


def _ask_where():
    """Return the IP lookup's reply, in ipwho.is's shape, and its zone and
    offset. A browser page asks GeoJS when ipwho.is fails."""
    try:
        reply = _get_json(_IP_URL)
        return (reply,) + parse_ip_zone(reply)
    except Exception as exc:
        if sys.platform not in _BROWSERS:
            raise
        print("deskkit: ipwho.is didn't answer (%r), asking GeoJS" % (exc,))
    reply = from_geojs(_get_json(_GEOJS_URL))
    return (reply,) + parse_ip_zone(reply)


def parse_ip_place(reply):
    """Return the place an ipwho.is reply points at, for Weather to start on.

    Args:
        reply (dict): The decoded JSON.

    Returns:
        dict: ``name``, ``lat``, ``lon``, ``units`` and ``from_ip`` (True), or
        None when the reply has no coordinates.
    """
    lat = reply.get("latitude")
    lon = reply.get("longitude")
    if lat is None or lon is None:
        return None
    return {
        "name": reply.get("city") or "Near you",
        "lat": lat,
        "lon": lon,
        "units": "F" if reply.get("country_code") in _FAHRENHEIT else "C",
        "from_ip": True,
    }


def follow_ip_zone():
    """Take the timezone, and Weather's place until one is chosen, from the
    board's public IP address, or in a browser the visitor's. Nothing changes
    once a place is chosen. It blocks: call it from a worker. A desktop keeps
    its own timezone (`finds_place`).

    Returns:
        bool: True when the offset now comes from the IP.
    """
    global offset_s, zone, _ip_retry_at, _ip_wait_s
    if not finds_place():
        return False
    from . import forecast  # here: forecast imports this module

    if forecast.place() is not None:
        zone = None
        _ip_retry_at = None
        return False  # a chosen place wins
    try:
        reply, found, offset = _ask_where()
    except Exception as exc:
        _ip_wait_s = min(max(2 * _ip_wait_s, _IP_RETRY_S), _IP_RETRY_MAX_S)
        _ip_retry_at = time.time() + _ip_wait_s
        print("deskkit: no place from the IP address, keeping %s, trying again in %d s: %r" % (zone or "UTC", _ip_wait_s, exc))
        return False
    _ip_retry_at = None
    _ip_wait_s = 0
    if forecast.place() is not None:
        return False  # chosen while the lookup ran
    zone = found
    if offset is not None:
        offset_s = offset
    here = parse_ip_place(reply)
    if here is not None:
        if forecast.ip_place is not None:
            here["units"] = forecast.ip_place["units"]  # keep a switch made since
        forecast.ip_place = here
    return True


def resync_if_due():
    """Set the clock, the timezone and the place from the IP when the clock
    is unset or a day has passed. Call it from a worker."""
    global _looked
    if due() and sync():
        follow_ip_zone()
    _looked = True


def network_moved():
    """Another network carries traffic now: the next `resync_if_due` sets
    the clock and looks up the IP's place again, and `finding` is True
    until it has."""
    global _synced_at, _looked, _ip_retry_at, _ip_wait_s
    _synced_at = None
    _looked = False
    _ip_retry_at = None
    _ip_wait_s = 0


def finding():
    """Return True while a board or a browser page hasn't yet tried to find
    where it is."""
    return finds_place() and not _looked


def now():
    """Return the local time as a ``time.gmtime``-style tuple."""
    if offset_s is None:
        return time.localtime()
    return gmtime(time.time() + offset_s)


def clock_time():
    """Return the local ``(hour, minute, second)``."""
    t = now()
    return t[3], t[4], t[5]


# The status bar's clock (appkit.bar) reads the same local time as Clock.
net.set_local_time(now)
