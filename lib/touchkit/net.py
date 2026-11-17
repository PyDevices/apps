# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit.net -- Wi-Fi for the board's apps: when it's on is the set's call.

A desktop has no ``wifi`` or ``network`` module and is on its network
already: `up` is then True once the computer has an address, and
`ip` and `hostname` are the computer's own. CircuitPython has no
``network`` module either: there `ip`, `rssi` and `hostname` read
``wifi.radio``.

The board joins a known network at boot (`boot`) and stays joined
while apps come and go, like the display. An app that needs the network
calls `up` from a timer until it says True. The hostname comes from
``settings.json`` (see ``touchkit.settings``).

Once the board is on a network its clock gets set (`keep_time`), and
again each day, so no app has to ask for it. That works on CircuitPython
too, through ``appkit.net``.
"""

import sys
import time

from . import settings

_CP = sys.implementation.name == "circuitpython"
_started = False
_webrepl_on = False
_clock_timer = None
_clock_asked = False
_CLOCK_CHECK_MS = 60_000
_CLOCK_JOB = "touchkit.clock"
_CP_JOIN_S = 5
# A join on CircuitPython holds the screen for 5 to 10 s whether it finds the
# network or not, and whatever its timeout. After one fails, `up` waits this
# long before the next, doubling up to _CP_RETRY_MAX_MS, so an offline board
# stays usable while apps poll.
_CP_RETRY_MS = 30_000
_CP_RETRY_MAX_MS = 300_000
_retry_ms = 0
_retry_at = None  # the `_now_ms` before which `up` doesn't try to join again


def _host_ip():
    """This machine's IPv4 address on the route to the network, or None.
    For a host with no ``network`` module (a desktop), which is on its LAN
    already: a UDP socket "connected" to a documentation address (TEST-NET-1,
    RFC 5737) sends nothing and names the interface the OS would use."""
    try:
        import socket
    except ImportError:  # CircuitPython names it socketpool
        return None

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(socket.getaddrinfo("192.0.2.1", 9)[0][-1])
        sa = s.getsockname()
        # CPython answers a tuple, MicroPython the packed sockaddr (the IPv4 address is bytes 4 to 8).
        ip = sa[0] if isinstance(sa, tuple) else ".".join(str(b) for b in sa[4:8])
        return None if ip.startswith("0.") else ip
    except OSError:
        return None
    finally:
        s.close()


def _radio():
    """CircuitPython's ``wifi.radio``, where there is no ``network`` module; else None."""
    try:
        import wifi

        return wifi.radio
    except (ImportError, AttributeError):
        return None


def hostname():
    """The board's name on the network, without ``.local``: ``boarddev.name()``."""
    import boarddev

    return boarddev.name()


def _station_state():
    """``"connected"`` when ``boot.py`` already joined the station, else None.
    A board set up with ``mcuctl wifi enable`` joins in ``boot.py``, before
    any app starts, and stays reachable through it. CircuitPython has no
    ``network`` module, so it is always None there: its radio and web
    workflow are the runtime's."""
    if _CP:
        return None
    try:
        import network

        if network.WLAN(network.STA_IF).isconnected():
            return "connected"
    except Exception:
        pass  # no network module (a desktop), or a port that can't say
    return None


def up():
    """True when the station is connected. When it isn't, starts a join: in
    the background on MicroPython. On CircuitPython a join holds the screen
    for seconds, so one is tried now and the next only after a wait that
    grows from 30 s to 5 minutes; an app can still poll this often."""
    global _started
    try:
        import wifi
    except ImportError:
        # No wifi module: a desktop, which has joined its network already
        # (wifi.py is MicroPython's, and CPython can't import it).
        return _host_ip() is not None

    try:
        joined = wifi.radio.connected
    except Exception:
        joined = False
    if joined:
        _joined()
        start_webrepl()
        keep_time()  # outside the try: a missing deskkit must be seen
        return True
    if _CP:
        # CircuitPython's join blocks while it tries; wifi_manager joins what
        # secrets.py or settings.toml hold.
        if _join_due():
            try:
                import wifi_manager

                ip = wifi_manager.connect(setup=False, timeout=_CP_JOIN_S)
            except Exception as e:
                print("touchkit: wifi:", e)
                ip = None
            if ip:
                _joined()
            else:
                _join_failed()
        return False
    if not _started:
        _started = True
        try:
            import wifi_manager

            wifi_manager.connect(setup=False, wait=False)
        except Exception as e:
            print("touchkit: wifi:", e)
            _started = False
    return False


def _needs_polling():
    """True on CircuitPython, where a network that drops is rejoined only by a
    call to `up`: the radio gives up retrying a few seconds after the access
    point goes, and stays off when it comes back."""
    try:
        import wifi
    except ImportError:
        return False
    return _CP and hasattr(wifi, "radio")


def _joined():
    global _retry_ms, _retry_at
    _retry_ms = 0
    _retry_at = None


def _join_failed():
    global _retry_ms, _retry_at
    _retry_ms = min(max(2 * _retry_ms, _CP_RETRY_MS), _CP_RETRY_MAX_MS)
    _retry_at = _now_ms() + _retry_ms


def _join_due():
    return _retry_at is None or _now_ms() >= _retry_at


def _now_ms():
    # Only CircuitPython waits between joins, and it has time.monotonic.
    return int(time.monotonic() * 1000)


def start_webrepl():
    """WebREPL, once, when ``settings.json`` doesn't turn it off.

    Does nothing without a webrepl module (a desktop), when something already
    started it (``boot.py`` may have: starting it again would drop the listener
    it opened), and on CircuitPython, which has no WebREPL: its remote access is
    the web workflow that ``settings.toml`` turns on."""
    global _webrepl_on
    if _webrepl_on or not settings.get("webrepl", True):
        return
    if sys.implementation.name == "circuitpython" or webrepl_on():
        return
    try:
        import webrepl

        webrepl.start()
        _webrepl_on = True
    except ImportError:
        pass  # a desktop, or firmware without WebREPL: nothing to start
    except Exception as e:
        print("touchkit: webrepl:", e)


def webrepl_on():
    """True when WebREPL is listening, whoever started it."""
    if _webrepl_on:
        return True
    w = sys.modules.get("webrepl")  # main.py may have started it before the apps
    return w is not None and getattr(w, "listen_s", None) is not None


def boot():
    """Join a known network quietly (``secrets.py``'s or one wifi_manager
    remembered), then start WebREPL. With none in range, carry on offline
    and keep trying in the background; System's Wi-Fi setup asks for one.
    Call it on the main thread once the launcher has booted.

    A station that ``boot.py`` already joined is left alone: no rejoin, no
    second WebREPL, so a board set up with
    ``mcuctl wifi enable`` keeps its connection."""
    settings.move_hostname()
    if _station_state() == "connected":
        joined = True
    else:
        try:
            import wifi_manager

            joined = wifi_manager.connect(setup=False)
        except Exception as e:
            print("touchkit: wifi:", e)
            joined = False
    if joined:
        start_webrepl()
        keep_time()  # outside the try: a missing deskkit must be seen
        if not _needs_polling():
            return
    else:
        if _CP:
            _join_failed()  # where a join blocks, the next waits a while
        keep_time()
        up()
    import lvgl as lv

    def poll(t):
        # On CircuitPython the timer outlives the first join: it is what
        # notices a dropped access point and tries again.
        if up() and not _needs_polling():
            t.delete()

    lv.timer_create(poll, 5000, None)


def _set_clock_if_due(_timer=None):
    global _clock_asked
    try:
        import wifi
    except ImportError:
        return  # a desktop keeps its own time
    from appkit.worker import shared
    from deskkit import localtime  # ImportError when deskkit isn't installed

    try:
        joined = wifi.radio.connected
    except Exception:
        return
    worker = shared()
    if joined and localtime.due() and not worker.pending(_CLOCK_JOB):
        # NTP, or a web server's Date header where NTP is blocked: it blocks.
        _clock_asked = True
        worker.submit(localtime.resync_if_due, key=_CLOCK_JOB)


def keep_time():
    """Set the board's clock as soon as the station has joined, then check
    once a minute: a failed try is tried again, and the clock is set again
    each day. The setting runs on the shared worker (`appkit.worker`), so the
    screen keeps going. Call it on the main thread, as `boot` and `up` do;
    once it has asked, calling it again leaves the rest to the timer."""
    global _clock_timer
    if _clock_timer is None:
        import lvgl as lv

        if not lv.is_initialized():
            # An LVGL timer made before lv.init() crashes the interpreter.
            raise RuntimeError("touchkit.net keeps the clock with an LVGL timer: start the display first")
        _clock_timer = lv.timer_create(_set_clock_if_due, _CLOCK_CHECK_MS, None)
    if not _clock_asked:
        _set_clock_if_due()


def setup_job():
    """The phone setup page until a network is joined: a job for the
    foreground loop (``scope.foreground(..., steps=False)``): it blocks."""
    try:
        import wifi_manager

        joined = wifi_manager.run()
    except Exception as e:
        print("touchkit: wifi setup:", e)
        joined = False
    if joined:
        start_webrepl()
        keep_time()  # outside the try: a missing deskkit must be seen


def rssi():
    """The signal from the access point in dBm, or None off the network."""
    try:
        import network

        return network.WLAN(network.STA_IF).status("rssi")
    except ImportError:
        r = _radio()
        info = r.ap_info if r is not None else None
        return info.rssi if info is not None else None
    except Exception:
        return None


def ip():
    """This board's IPv4 address, or None off the network."""
    try:
        import network

        wl = network.WLAN(network.STA_IF)
        if wl.isconnected():
            return wl.ifconfig()[0]
    except ImportError:
        r = _radio()
        if r is None:
            return _host_ip()
        addr = r.ipv4_address
        return str(addr) if addr else None
    except Exception:
        pass
    return None


def ntp(timeout=2):
    """Set the clock from NTP (a blocking call: run it on the worker)."""
    from appkit import net as appnet

    appnet.ntp(timeout)
