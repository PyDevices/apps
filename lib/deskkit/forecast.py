# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""deskkit.forecast: the place you've chosen and its weather, from Open-Meteo.

Open-Meteo needs no account or key, and is free for non-commercial use. Its
reply also carries the place's UTC offset, which is how the clock follows the
place's timezone and daylight saving. A chosen place wins over the timezone
``deskkit.localtime`` finds from the board's IP address.

The forecast lives here rather than in an app, so it stays while apps open and
close. It's kept in RAM: writing flash every half hour would wear it for
something a boot gets back in seconds. Only the place is saved.
"""

import json
import time

import requests
import wifi_manager
from appkit import data

from . import localtime

try:
    import network
except ImportError:  # a desktop
    network = None

MAX_AGE_S = 30 * 60
RETRY_S = 5 * 60

_GEO_URL = (
    "https://geocoding-api.open-meteo.com/v1/search"
    "?name=%s&count=1&language=en&format=json&countryCode=US"
)
_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
    "&current=temperature_2m,apparent_temperature,weather_code,is_day"
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    "&temperature_unit=fahrenheit&timezone=auto&forecast_days=5"
)
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

latest = None  # what parse() made from the last good reply
last_error = None
_tried_at = None
_got_at = None
_place = None


def _place_file():
    return data.join(data.app_dir("deskkit"), "place.json")


def place():
    """Return the saved place as a dict, or None before one is chosen."""
    global _place
    if _place is None:
        try:
            with open(_place_file()) as f:
                _place = json.load(f)
        except (OSError, ValueError):
            return None
        localtime.offset_s = _place.get("utc_offset")
        localtime.zone = None
    return _place


def _save():
    with open(_place_file(), "w") as f:
        json.dump(_place, f)


def choose(zip_code):
    """Look up *zip_code* and make it the place. It blocks: call it from a worker.

    Args:
        zip_code (str): A US ZIP code.

    Returns:
        dict: The place.

    Raises:
        ValueError: Open-Meteo knows no place with that code.
    """
    global _place, latest, _got_at
    resp = requests.get(_GEO_URL % zip_code, timeout=15)
    try:
        results = resp.json().get("results")
    finally:
        resp.close()
    if not results:
        raise ValueError("no place for " + zip_code)
    found = results[0]
    units = _place.get("units", "F") if _place else "F"
    _place = {
        "zip": zip_code,
        "name": found["name"],
        "lat": found["latitude"],
        "lon": found["longitude"],
        "units": units,
    }
    _save()
    latest = None
    _got_at = None
    fetch()
    return _place


def set_units(units):
    """Show temperatures in *units*, ``"F"`` or ``"C"``, from now on."""
    if _place is not None:
        _place["units"] = units
        _save()


def degrees(fahrenheit):
    """Return a Fahrenheit reading as whole degrees in the chosen units."""
    if _place is not None and _place.get("units") == "C":
        return round((fahrenheit - 32) * 5 / 9)
    return round(fahrenheit)


def _weekday(date):
    y, m, d = date.split("-")
    return _DAYS[localtime.gmtime(time.mktime((int(y), int(m), int(d), 12, 0, 0, 0, 0, 0)))[6]]


def parse(reply):
    """Turn an Open-Meteo reply into the plain dict the apps show.

    Args:
        reply (dict): The decoded JSON.

    Returns:
        dict: ``temp``, ``feels``, ``code``, ``is_day``, ``hi``, ``lo``, ``as_of``
        (``"HH:MM"`` at the place), ``utc_offset`` and ``days``, a list of
        ``(weekday, code, hi, lo, chance_of_rain)``.
    """
    now = reply["current"]
    daily = reply["daily"]
    days = []
    for i, date in enumerate(daily["time"]):
        days.append(
            (
                _weekday(date),
                daily["weather_code"][i],
                daily["temperature_2m_max"][i],
                daily["temperature_2m_min"][i],
                daily["precipitation_probability_max"][i],
            )
        )
    return {
        "temp": now["temperature_2m"],
        "feels": now["apparent_temperature"],
        "code": now["weather_code"],
        "is_day": bool(now["is_day"]),
        "hi": daily["temperature_2m_max"][0],
        "lo": daily["temperature_2m_min"][0],
        "as_of": now["time"].split("T")[1],
        "utc_offset": reply["utc_offset_seconds"],
        "days": days,
    }


def _rejoin():
    if network is not None and not network.WLAN(network.STA_IF).isconnected():
        wifi_manager.connect(setup=False)


def fetch():
    """Get the forecast now, and keep the clock right. It blocks: call it from a worker.

    A failure keeps the last forecast, so the app can say how old it is.

    Returns:
        bool: True when the forecast is new.
    """
    global latest, last_error, _tried_at, _got_at
    _tried_at = time.time()
    try:
        _rejoin()
        localtime.resync_if_due()
        resp = requests.get(_URL % (_place["lat"], _place["lon"]), timeout=15)
        try:
            latest = parse(resp.json())
        finally:
            resp.close()
    except Exception as exc:
        last_error = exc
        print("deskkit: no forecast: %r" % (exc,))
        return False
    last_error = None
    _got_at = time.time()
    localtime.offset_s = latest["utc_offset"]
    localtime.zone = None
    if _place.get("utc_offset") != latest["utc_offset"]:
        _place["utc_offset"] = latest["utc_offset"]
        _save()  # rare: the first time, and at each daylight saving change
    return True


def is_stale():
    """Return True when a fetch is due: the data is old and no try was recent."""
    if _got_at is not None and time.time() - _got_at < MAX_AGE_S:
        return False
    return _tried_at is None or time.time() - _tried_at >= RETRY_S


def keep_fresh(scope, on_update=None):
    """Fetch whenever the forecast goes stale, for as long as *scope* is open.

    Args:
        scope (AppScope): The app that wants it.
        on_update (callable): Called with no arguments on the main thread after
            each fetch, good or bad, while the app is open.
    """

    def done(_value, _error):
        if on_update is not None:
            on_update()

    def check(_timer=None):
        if place() is not None and is_stale():
            scope.worker.submit(fetch, done, key="forecast")

    scope.every(60_000, check)
    check()
