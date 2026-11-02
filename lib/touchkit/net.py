# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit.net -- Wi-Fi for the board's apps: when it's on is the set's call.

A desktop has no ``wifi`` or ``network`` module and is on its network
already: :func:`up` is then True once the computer has an address, and
:func:`ip` and :func:`hostname` are the computer's own.

The board joins a known network at boot (:func:`boot`) and stays joined
while apps come and go, like the display. An app that needs the network
calls :func:`up` from a timer until it says True. The hostname comes from
``settings.json`` (see ``touchkit.settings``).
"""

from . import settings

_started = False
_webrepl_on = False


def _host_ip():
    """This machine's IPv4 address on the route to the network, or None.
    For a host with no ``network`` module (a desktop), which is on its LAN
    already: a UDP socket "connected" to a documentation address (TEST-NET-1,
    RFC 5737) sends nothing and names the interface the OS would use."""
    import socket

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


def hostname():
    """The board's name on the network, without ``.local``, or None."""
    name = settings.get("hostname")
    if name:
        return name
    try:
        import network

        return network.hostname()
    except ImportError:  # a desktop: the computer's own name
        try:
            import socket

            return socket.gethostname()
        except Exception:
            return None
    except Exception:
        return None


def up():
    """True when the station is connected; starts a join (without waiting)
    when it isn't."""
    global _started
    try:
        import wifi
    except ImportError:
        # No wifi module: a desktop, which has joined its network already
        # (wifi.py is MicroPython's, and CPython can't import it).
        return _host_ip() is not None

    try:
        if wifi.radio.connected:
            start_webrepl()
            return True
    except Exception:
        pass
    if not _started:
        _started = True
        try:
            wifi.connect_from_secrets(wait=False, ntp=False)
        except Exception as e:
            print("touchkit: wifi:", e)
            _started = False
    return False


def start_webrepl():
    """WebREPL, once, when ``settings.json`` doesn't turn it off."""
    global _webrepl_on
    if _webrepl_on or not settings.get("webrepl", True):
        return
    try:
        import webrepl

        webrepl.start()
        _webrepl_on = True
    except Exception as e:
        print("touchkit: webrepl:", e)


def webrepl_on():
    return _webrepl_on


def boot():
    """Join a known network quietly (``secrets.py``'s or one wifi_manager
    remembered), then start WebREPL. With none in range, carry on offline
    and keep trying in the background; System's Wi-Fi setup asks for one.
    Call it on the main thread once the launcher has booted."""
    try:
        import wifi_manager

        kw = {"setup": False}
        if settings.get("hostname"):
            kw["hostname"] = settings.get("hostname")
        if wifi_manager.connect(**kw):
            start_webrepl()
            return
    except Exception as e:
        print("touchkit: wifi:", e)
    import lvgl as lv

    def poll(t):
        if up():
            t.delete()

    up()
    lv.timer_create(poll, 5000, None)


def setup_job():
    """The phone setup page until a network is joined: a job for the
    foreground loop (``scope.foreground(..., steps=False)``): it blocks."""
    try:
        import wifi_manager

        kw = {}
        if settings.get("hostname"):
            kw["hostname"] = settings.get("hostname")
        if wifi_manager.run(**kw):
            start_webrepl()
    except Exception as e:
        print("touchkit: wifi setup:", e)


def rssi():
    try:
        import network

        return network.WLAN(network.STA_IF).status("rssi")
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
        return _host_ip()
    except Exception:
        pass
    return None


def ntp(timeout=2):
    """Set the clock from NTP (a blocking call: run it on the worker)."""
    import ntptime

    ntptime.timeout = timeout
    ntptime.settime()
