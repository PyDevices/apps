# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Spotify: the board is a Spotify Connect speaker (earful), and the screen
is its remote (say-so, Spotify's Web API).

Where the firmware has earful, the board is a speaker as well as the
remote; without it, the app is the remote alone, for whatever device
Spotify is playing on. That's decided when the app opens.

The screen shows what's playing (on this board or wherever Spotify is
playing) with play/pause, previous, next and volume, and "Play here" moves
playback to the board. Every Web API call runs on ``scope.worker``, so a
slow answer never freezes the screen.

Its data folder (``/data/spotify`` on the board) holds:

``sayso.local.json`` and ``tokens.json``
    say-so's Spotify app credentials and the account's tokens, made once
    with say-so's own login on a computer. The tokens are read and
    refreshed here, whatever path ``sayso.local.json`` names.
``earful.credentials``
    The speaker's pairing, written here after a phone first plays to it.
    Until a phone has picked the speaker once (Spotify's devices button),
    Spotify refuses to start it from the Web API.
``config.json`` (optional)
    ``{"name": "Kitchen", "volume": 60}``: the speaker's name, and its
    volume when it starts.

On close it stops the speaker (its threads, the pairing server and mDNS),
the audio pump stream and say-so's sockets; the worker drops what it had
queued. Wi-Fi stays joined: it's shared, like the display.
"""

import sys

import lvgl as lv
from appkit import data as appdata
from multimer import ticks_diff, ticks_ms

import spectrum
from touchkit import net, settings, ui
from touchkit.clock import sleep_ms

# A desktop's speaker has a name of its own, so it never takes the board's place in Spotify's devices.
DEFAULTS = {"name": "PyDevices desktop" if appdata.desktop() else "PyDevices", "volume": 70}
CRED_FILE = "earful.credentials"
CONFIG = "sayso.local.json"
TOKENS = "tokens.json"
PUMP_MS = 10
POLL_MS = 5000
# While the board plays, the screen follows earful itself and Spotify is asked
# far less often: the worker's request and JSON parse share the interpreter
# with the screen and the spectrum, and stalled them on every poll.
POLL_HERE_MS = 20000
RING_SECONDS = 4
SILENCE = bytes(4 * 44100 * PUMP_MS // 1000)  # 10 ms of 44.1 kHz stereo 16-bit
ART = 150  # the cover, decoded at half Spotify's 300 px one
# The spectrum: under the buttons, centred.
METER_BANDS = 8
METER_W = 400
METER_H = 120

state = None  # the open app's state, for the console


class _PumpPCM:
    """earful's view of an audiodev pump stream: earful calls write, space,
    service and set_volume as real methods."""

    def __init__(self, stream, transport):
        self._stream = stream
        self._transport = transport

    def write(self, buf):
        return self._stream.write(buf)

    def space(self):
        return self._stream.space()

    def queued_size(self):
        return self._stream.level()

    def service(self):
        pass

    def clear(self):
        # earful calls this when it clears its own ring (pause, skip, seek):
        # without it the pump plays out what it holds, seconds of it.
        ring = self._stream.ring
        if ring is not None:
            ring.clear()

    def set_volume(self, volume):
        self._transport.set_volume(volume)

    def open(self):
        pass

    def close(self):
        self._stream.deinit()


def _pump_pcm(fmt):
    from audiodev import pump
    from boarddev import pcm_out

    out = transport = pcm_out(fmt)
    while transport is not None and getattr(transport, "wire", None) is None:
        transport = getattr(transport, "_inner", None)
    if transport is None:
        # No I2S wire to pump: a desktop, whose audio out earful writes to itself.
        out.open()
        return out
    driver = pump.BusioDriver(
        transport.wire, fmt, power=getattr(transport, "audio_power", None), volume=transport.volume, transport=transport
    )
    frames = 256
    stream = pump.attach_stream(fmt, driver=driver, frames=frames, capacity=max(2, fmt.rate * RING_SECONDS // frames))
    return _PumpPCM(stream, transport)


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _client(folder, dev):
    """say-so's Web API client from the data folder's files. Never starts a
    browser login: with no usable token it raises.

    Joined with this board's speaker when there is one (say-so's local
    device): a command with no device_id goes straight to it instead of
    through Spotify, so pass the other device's id when playback is
    elsewhere."""
    from sayso import auth as sa
    from sayso.client import SpotifyClient

    config = sa.load_config(folder + "/" + CONFIG)
    client_id, client_secret = sa.credentials_from_config(config)
    cache = sa.TokenCache(folder + "/" + TOKENS)
    cached = cache.load()
    refresh = cached.get("refresh_token")
    if not refresh:
        raise sa.SpotifyConfigError("no refresh token in %s/%s: log in with say-so on a computer first" % (folder, TOKENS))
    auth = sa.AuthorizationCodeAuth(
        client_id,
        client_secret,
        sa.redirect_uri_from_config(config, cached),
        scope=sa.scopes_from_config(config, cached),
        refresh_token=refresh,
        token_cache=cache,
    )
    if dev is None:
        return SpotifyClient(auth=auth)
    return SpotifyClient(auth=auth, local_device=dev)


def _speaker_available():
    try:
        import earful
    except ImportError:
        return False
    return bool(earful.available())


def main(scope):
    global state
    conf = settings.config(scope, DEFAULTS)
    NAME = conf["name"]
    folder = scope.data_dir
    cred_path = folder + "/" + CRED_FILE
    root = scope.root
    W, H = scope.size
    status = ui.status(scope)
    speaker = _speaker_available()
    st = state = {
        "phase": "wifi", "dev": None, "pcm": None, "client": None, "pb": None, "my_id": None,
        "saved": _read(cred_path) if speaker else None, "err": None, "vol": conf["volume"], "ticks": 0,
        "events": None, "active": False,
        # what Spotify last said: playing, and (progress_ms, ticks_ms) to count on from
        "playing": False, "base": None, "art_url": None, "meter": None, "speaker": speaker,
        "host_audio": False,
    }  # fmt: skip
    keep = {}  # the cover's pixels, while LVGL shows them
    w = scope.worker

    TEXT_W = W - 48 - ART - 16  # beside the cover
    art = lv.image(root)
    art.set_pos(W - 24 - ART, 14)
    art.set_size(ART, ART)
    track = ui.label(root, "", ui.big, ui.WHITE)
    track.set_pos(24, 20)
    track.set_width(TEXT_W)
    track.set_long_mode(lv.label.LONG_MODE.DOTS)
    artist = ui.label(root, "", ui.font, ui.ACCENT)
    artist.set_pos(24, 62)
    artist.set_width(TEXT_W)
    artist.set_long_mode(lv.label.LONG_MODE.DOTS)
    where = ui.label(root, "", ui.small, ui.MUTED)
    where.set_pos(24, 94)
    where.set_width(TEXT_W)
    bar = lv.bar(root)
    bar.set_size(TEXT_W, 12)
    bar.set_pos(24, 122)
    bar.set_range(0, 1000)
    times = ui.label(root, "", ui.small, ui.MUTED)
    times.set_pos(24, 140)

    # -- the speaker (earful) ----------------------------------------------------

    def start_speaker():
        import earful
        from audiodev import AudioFormat

        pcm = _pump_pcm(AudioFormat(44100, 2, 16))
        st["pcm"] = pcm
        st["host_audio"] = not isinstance(pcm, _PumpPCM)
        if st["saved"]:
            earful.set_credentials(st["saved"])
        dev = earful.Device(name=NAME, bitrate=160)
        dev.volume = st["vol"]
        dev.start()
        dev.attach(pcm)
        st["dev"] = dev
        # earful's state events, where this firmware has them; without, the
        # app polls Spotify as before.
        st["events"] = getattr(dev, "events", None)

    def pump(t):
        dev = st["dev"]
        if dev is None:
            return
        dev.service()
        if st["host_audio"]:
            # A host's queued sink stalls without a keepalive until playback starts.
            pcm = st["pcm"]
            if not dev.playing and pcm.queued_size() < 4 * len(SILENCE):
                pcm.write(SILENCE)
            pcm.service()
        events = st["events"]
        if events is not None:
            batch = events()  # an empty tuple, without allocating, when nothing changed
            if batch:
                follow(batch)
        st["ticks"] += 1
        if st["ticks"] % 100 == 0:
            save_creds()

    def save_creds():
        # earful pairs in RAM; the app keeps it in its data folder. Rewritten
        # only when it changed (a new pairing), so the flash sees one write.
        import earful

        if not earful.has_credentials():
            return
        blob = earful.credentials()
        if blob and blob != st["saved"]:
            try:
                with open(cred_path, "wb") as f:
                    f.write(blob)
                st["saved"] = blob
                print("spotify: pairing saved")
            except OSError as e:
                print("spotify: pairing not saved:", e)

    # -- the remote (say-so) ---------------------------------------------------------

    def api(work, done=None, key=None):
        def finished(value, error):
            if error is not None:
                st["err"] = error
                status.set_text("Web API: %s" % (str(error)[:60],))
            if done is not None:
                done(value, error)

        w.submit(work, finished, key=key)

    def follow(batch):
        # What earful told Spotify, at once: no poll needed to see a pause or a skip.
        for kind, value in batch:
            if kind == "active":
                st["here"] = st["active"] = bool(value)
                if not value:
                    poll()  # moved elsewhere: ask Spotify where
        show()

    def poll(t=None):
        if st["client"] is None or w.pending("poll"):
            return
        if t is not None and st["active"]:
            return  # this board is Spotify's active device and earful tells us what changes
        if t is not None and playing_here():
            now = ticks_ms()
            if ticks_diff(now, st.get("polled", 0)) < POLL_HERE_MS:
                return
        st["polled"] = ticks_ms()
        c = st["client"]
        look_for_me = speaker and st["my_id"] is None

        def work():
            pb = c.current_playback()
            if not look_for_me:
                return pb, None  # each call is 1-2 s from the board: skip what we know
            my = None
            try:
                for d in c.devices():
                    if d.name == NAME and d.id:  # say-so lists the joined speaker too, without an id
                        my = d.id
            except Exception:
                pass
            return pb, my

        def done(value, error):
            if error is None:
                pb, my = value
                st["pb"] = pb
                d = getattr(pb, "device", None)
                if d is not None and d.name != NAME and st.get("here"):
                    st["here"] = False  # moved elsewhere (a phone, say)
                    status.set_text("")
                st["playing"] = bool(pb is not None and pb.is_playing)
                st["base"] = ((pb.progress_ms or 0) if pb is not None else 0, ticks_ms())
                if my:
                    st["my_id"] = my
                show()

        api(work, done, key="poll")

    def shown_ms(dur):
        # Between polls the clock counts on by itself.
        base = st["base"]
        if base is None:
            return 0
        pos, at = base
        if st["playing"]:
            pos += ticks_diff(ticks_ms(), at)
        return min(pos, dur) if dur else pos

    def target():
        # None reaches this board's speaker directly; elsewhere, name the device.
        if playing_here():
            return None
        d = getattr(st["pb"], "device", None)
        return d.id if d is not None else None

    # -- the cover ------------------------------------------------------------------

    def art_url():
        dev = st["dev"]
        if playing_here() and dev.art:
            # earful has the 640 px cover; the 300 px one is the same image
            return dev.art.replace("ab67616d0000b273", "ab67616d00001e02")
        album = getattr(getattr(st["pb"], "item", None), "album", None)
        best = None
        for im in getattr(album, "images", None) or ():
            if best is None or abs((im.width or 0) - 300) < abs((best.width or 0) - 300):
                best = im
        return getattr(best, "url", None)

    def want_art():
        # Fetched afresh for every track, on the worker; nothing is cached.
        url = art_url()
        if url == st["art_url"]:
            return
        st["art_url"] = url
        if not url:
            art.add_flag(lv.obj.FLAG.HIDDEN)
            return

        def work():
            import requests

            r = requests.get(url)
            try:
                data = r.content
            finally:
                r.close()
            return (url,) + ui.decode_jpeg(data, ART * 3 // 2, 10000)

        def done(value, error):
            if error is not None:
                print("spotify: cover:", error)
                return
            u, pixels, aw, ah = value
            if u != st["art_url"]:
                return  # a later track's cover is on its way
            ui.rgb565_image(art, pixels, aw, ah, keep)
            art.remove_flag(lv.obj.FLAG.HIDDEN)

        w.submit(work, done, key="art")

    def show():
        # Spotify's word on what plays where, also when it plays here: the
        # speaker's own playing and position don't follow audio the pump plays.
        pb = st["pb"]
        dev = st["dev"]
        playing = st["playing"]
        if playing_here() and dev.title:
            # earful knows the track, the position and whether it plays the
            # moment they change; Spotify's answer comes a poll later.
            track.set_text(dev.title or "")
            artist.set_text(dev.artist or "")
            dur = dev.duration or 0
            pos = min(dev.position or 0, dur) if dur else (dev.position or 0)
            playing = st["playing"] = bool(dev.playing)
            on = NAME + " (this board)"
        elif pb is not None and getattr(pb, "item", None) is not None:
            item = pb.item
            track.set_text(item.name or "")
            artists = getattr(item, "artists", None) or ()
            artist.set_text(", ".join(a.name for a in artists))
            dur = getattr(item, "duration_ms", 0) or 0
            pos = shown_ms(dur)
            d = getattr(pb, "device", None)
            on = (d.name or "?") if d is not None else "?"
            if speaker and on == NAME:
                on += " (this board)"
        elif dev is not None and dev.track:
            track.set_text(dev.title or "")
            artist.set_text(dev.artist or "")
            dur = dev.duration or 0
            pos = shown_ms(dur)
            on = NAME + " (this board)"
        else:
            track.set_text("Nothing playing")
            artist.set_text("")
            pos = dur = 0
            playing = False
            on = None
        where.set_text(("%s on %s" % ("Playing" if playing else "Paused", on)) if on else "")
        bar.set_value(int(pos * 1000 // dur) if dur else 0, 0)
        times.set_text(
            "%d:%02d / %d:%02d" % (pos // 60000, pos // 1000 % 60, dur // 60000, dur // 1000 % 60) if dur else ""
        )
        play_lbl.set_text(lv.SYMBOL.PAUSE if playing else lv.SYMBOL.PLAY)
        want_art()
        vol_lbl.set_text("%d%%" % st["vol"])

    def playing_here():
        dev = st["dev"]
        if dev is None or not dev.track:
            return False
        if st.get("here"):  # moved here, Spotify's next answer not in yet
            return True
        return st["pb"] is not None and getattr(getattr(st["pb"], "device", None), "name", None) == NAME

    def toggle():
        c = st["client"]
        if c is None:
            return
        playing = st["playing"]
        dur = getattr(getattr(st["pb"], "item", None), "duration_ms", 0) or 0
        st["base"] = (shown_ms(dur), ticks_ms())
        st["playing"] = not playing  # at once; the next poll corrects it
        show()
        dev_id = target()
        api((lambda: c.pause(dev_id)) if playing else (lambda: c.play(dev_id)), lambda v, e: poll(), key="toggle")

    def skip(forward):
        c = st["client"]
        if c is not None:
            dev_id = target()
            api(
                (lambda: c.next_track(dev_id)) if forward else (lambda: c.previous_track(dev_id)),
                lambda v, e: poll(),
                key="skip",
            )

    def volume(step):
        st["vol"] = max(0, min(100, st["vol"] + step))
        vol_lbl.set_text("%d%%" % st["vol"])
        c = st["client"]
        dev = st["dev"]
        if dev is not None and playing_here():
            dev.volume = st["vol"]  # the board's own: no round trip
        elif c is not None:
            v = st["vol"]
            dev_id = target()
            api(lambda: c.volume(v, dev_id), key="volume")

    def play_here():
        c = st["client"]
        if c is None or st["dev"] is None:
            return
        status.set_text("moving playback here...")

        def work():
            my = st["my_id"]
            if my is None:
                for d in c.devices():
                    if d.name == NAME and d.id:  # say-so lists the joined speaker too, without an id
                        my = d.id
            if my is None:
                raise OSError("Spotify doesn't list %s yet: pick it once on your phone" % NAME)
            # Just after the speaker comes up the Web API answers 404 for a
            # few seconds, though Spotify already has it.
            for attempt in range(3):
                try:
                    c.transfer_playback([my], play=True)
                    break
                except Exception as e:
                    if attempt == 2 or "404" not in str(e):
                        raise
                    sleep_ms(1500)
            return my

        def done(value, error):
            if error is None:
                st["my_id"] = value
                st["here"] = True
                status.set_text("playing on %s" % NAME)
                if st["dev"] is not None:
                    st["dev"].volume = st["vol"]  # a transfer brings the phone's volume
                poll()

        api(work, done, key="here")

    y = 180
    b, _ = ui.button(root, lv.SYMBOL.PREV, lambda: skip(False), w=96, h=72, font=ui.big)
    b.set_pos(24, y)
    b, play_lbl = ui.button(root, lv.SYMBOL.PLAY, toggle, w=120, h=72, font=ui.big, color=ui.GOOD)
    b.set_pos(132, y)
    b, _ = ui.button(root, lv.SYMBOL.NEXT, lambda: skip(True), w=96, h=72, font=ui.big)
    b.set_pos(264, y)
    b, _ = ui.button(root, lv.SYMBOL.VOLUME_MID, lambda: volume(-5), w=80, h=72, font=ui.big)
    b.set_pos(392, y)
    vol_lbl = ui.label(root, "%d%%" % st["vol"], ui.big, ui.WHITE)
    vol_lbl.set_pos(484, y + 22)
    b, _ = ui.button(root, lv.SYMBOL.VOLUME_MAX, lambda: volume(5), w=80, h=72, font=ui.big)
    b.set_pos(566, y)
    if speaker:
        b, _ = ui.button(root, "Play\nhere", play_here, w=120, h=72, font=ui.font, color=ui.WARN)
        b.set_pos(W - 24 - 120 + 4, y)

    # -- start up, one step per tick --------------------------------------------------

    def connect_client():
        st["phase"] = "client"
        dev = st["dev"]

        def done(value, error):
            st["phase"] = "ready"
            if error is None:
                st["client"] = value
                poll()
            else:
                status.set_text("no remote: %s" % (str(error)[:40],))

        api(lambda: _client(folder, dev), done, key="client")

    def setup(t):
        phase = st["phase"]
        if phase == "wifi":
            if net.up():
                rssi = net.rssi()
                status.set_text("Wi-Fi %s dBm" % rssi if rssi else "Wi-Fi up")
                if speaker:
                    # The speaker stamps what it tells Spotify with the clock.
                    if appdata.desktop():
                        st["phase"] = "speaker"  # the computer's clock is right already
                    else:
                        st["phase"] = "ntp"
                        api(net.ntp, lambda v, e: st.__setitem__("phase", "speaker"), key="ntp")
                else:
                    status.set_text("remote only: this firmware has no speaker")
                    connect_client()
            else:
                status.set_text("joining Wi-Fi...")
            return
        if phase == "speaker":
            try:
                start_speaker()
            except Exception as e:
                status.set_text("speaker failed: %s" % (e,))
                sys.print_exception(e)
                st["phase"] = "failed"
                return
            status.set_text("speaker %s up" % NAME)
            scope.every(PUMP_MS, pump)
            try:
                m = spectrum.meter(
                    scope, spectrum.pump_tap(44100, 2), 264, x=(W - METER_W) // 2,
                    width=METER_W, height=METER_H, bands=METER_BANDS,
                )  # fmt: skip
                spectrum.start(m, scope)
                st["meter"] = m
            except Exception as e:
                print("spotify: no spectrum:", e)
            connect_client()
            return
        if phase in ("ready", "failed"):
            t.deinit()
        # "ntp" and "client" wait for the worker

    def close():
        spectrum.stop(st["meter"])
        st["meter"] = None
        dev = st["dev"]
        st["dev"] = None
        if dev is not None:
            try:
                save_creds()
            except Exception:
                pass
            dev.stop()  # its threads, the pairing server, mDNS
        pcm = st["pcm"]
        st["pcm"] = None
        if pcm is not None:
            pcm.close()  # the last pump client: the pump stops and the codec powers down
        st["client"] = None
        dev = pcm = None
        w.cancel()
        try:
            from sayso import transport

            # say-so's kept-alive TLS sockets, unless the worker is mid-request
            # (a request in flight finishes on its own and is dropped)
            if not w.busy:
                transport.close_connections()
        except Exception as e:
            print("spotify: sockets:", e)

    scope.on_close(close)
    show()
    scope.every(300, setup)
    scope.every(POLL_MS, poll)

    def clock(t):
        dev = st["dev"]
        if dev is not None and dev.track != st.get("track"):
            st["track"] = dev.track
            if playing_here():
                st["base"] = (0, ticks_ms())  # a new track starts from 0:00
            show()
        elif st["playing"] or playing_here():
            show()

    scope.every(500, clock)
