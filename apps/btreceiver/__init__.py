# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Bluetooth Receiver: the board plays what a phone or computer sends it.

Pair a phone with the board's name and play anything: music, a podcast, a
video's sound. The screen shows the cover large, then everything the sender
says about the track (title, artist, album, track number, genre, length and
where it's up to) and about the link (the sender's name, the codec and the
rate). The buttons drive the sender's player (hold a skip button to fast
forward or rewind), and the volume slider is the one on the phone. Shuffle
and repeat show the player's modes and change them, when the sender reports
them. A spectrum of what plays runs under the title.

With the "Phone calls and battery" switch in the header on (it's off until
you turn it on, and kept in ``config.json``), the board is also the phone's
hands-free unit, as a car kit is: the phone's battery and signal show at the
top right, and a call shows a card over the player with the caller's number,
to answer or decline. An answered call plays through the board's speaker and
sends its microphones to the phone, and the music comes back when the call
ends. On a board whose Bluetooth can't carry a
call's audio (``HandsFree.call_audio`` is False), the card answers and hangs
up, and you talk on the phone. A ringing call chimes softly every few
seconds.

A new text chimes once, over the music, whatever the calls setting (but not
over a call's audio on the board): the app
reads the phone's message service (MAP) for that, which the phone asks its
owner to allow the first time. ``"texts": false`` in ``config.json`` leaves
the phone's messages alone.

It needs a firmware with ``btclassic``. The audio goes out through the
board's ``audio_out`` on the audio pump, so a redraw never holds it up. On a
computer with no Bluetooth module the app plays a demo: a pretend phone that
pairs, plays a few tracks and follows the buttons.
"""

import json

from multimer import ticks_diff, ticks_ms

from appkit import data as appdata
from appkit.shell import is_round
from touchkit import settings, ui

from . import glyphs
from .chime import Chimes
from .screen import BANDS, Screen, calls_switch, switch_header

UI_MS = 250  # how often the app reads the sink
BARS_MS = 66  # how often the spectrum moves
COVER_PX = 200  # AVRCP covers are 200 x 200; a larger one is halved to fit
COVER_JPEG = 96 * 1024  # room for the cover's JPEG
# A phone starting a stream sends about twice as fast for a second or two:
# this rides that out. Half of it is the delay to the speaker.
BUFFER_MS = 1000
# Calling the phone's hands-free side when the setting is turned on: the
# first try waits this long after the unit starts, which a call made at once
# misses, and there are this many tries in all.
HF_RETRY_MS = 3000
HF_TRIES = 3
RING_MS = 4000  # how often a ringing call chimes
# The phone's message service, for the new-text chime: the first try waits
# this long after the music connects, which leaves the phone to set up its
# other links first. A try the phone hasn't answered in MAP_PENDING_MS is
# taken as failed.
MAP_WAIT_MS = 4000
MAP_TRIES = 3
MAP_PENDING_MS = 40000
MAP_BYTES = 4096  # the replies kept: only the phone's answer to notify()

state = None  # the open app's state, for the console
# What Android sends for a field it doesn't know, the title included when
# nothing is playing.
UNSAID = "Not Provided"
# A tap moves repeat on the way a phone's player does, and turns shuffle on
# or off. "group" (a sender's own mode) goes back to off.
NEXT_REPEAT = {"off": "all", "all": "single"}
#: The app's settings, kept in ``config.json`` in its data folder. ``calls``
#: makes the board the phone's hands-free unit: the phone's battery and
#: signal from that link, and a card for its calls. Off, the board is a
#: speaker only, and the battery is the one the player reports. ``texts``
#: chimes for each new text, from the phone's message service.
DEFAULTS = {"calls": False, "texts": True}


def _said(text):
    """*text*, or "" when the sender says it doesn't know."""
    return "" if text == UNSAID else text


def _open_sink():
    """``(radio, sink, bits, radio_was_on)``: btclassic's, or the demo's on a
    computer. None on a board without btclassic."""
    try:
        import btclassic
    except ImportError:
        if not appdata.desktop():
            return None
        from . import demo

        return demo.DemoRadio(), demo.DemoSink(), demo, True
    bt = btclassic.Bluetooth()
    was_on = bt.active()
    return bt, btclassic.AudioSink(bt, buffer_ms=BUFFER_MS), btclassic, was_on


def _open_handsfree(bt, sink, bits):
    """The phone's hands-free link, for the calls setting: btclassic's
    ``HandsFree``, or the demo's on a computer. None on a firmware whose
    btclassic has no hands-free unit."""
    demo_unit = getattr(bits, "DemoHandsFree", None)
    if demo_unit is not None:
        return demo_unit(sink)
    make = getattr(bits, "HandsFree", None)
    if make is None:
        print("btreceiver: this btclassic has no HandsFree: no battery, signal or calls")
        return None
    # Stereo frames, the shape the speaker plays. It follows the sink's phone.
    return make(bt, channels=2)


def _open_messages(bt, sink, bits):
    """The phone's message service, for the new-text chime: btclassic's
    ``Messages``, or the demo's on a computer. None on a firmware whose
    btclassic has no message client."""
    demo_msgs = getattr(bits, "DemoMessages", None)
    if demo_msgs is not None:
        return demo_msgs(sink)
    make = getattr(bits, "Messages", None)
    if make is None:
        print("btreceiver: this btclassic has no Messages: no chime for texts")
        return None
    return make(bt, max_bytes=MAP_BYTES)


def _load_config(scope):
    """The app's settings: DEFAULTS, overridden by its ``config.json``."""
    try:
        return settings.config(scope, DEFAULTS)
    except (ValueError, AttributeError):  # a scope with no data folder
        return dict(DEFAULTS)


def _save_config(scope, config):
    """Keep *config* in the app's ``config.json``: only what differs from
    DEFAULTS."""
    changed = {k: v for k, v in config.items() if DEFAULTS.get(k) != v}
    try:
        path = appdata.join(scope.data_dir, "config.json")
        with open(path, "w") as f:
            f.write(json.dumps(changed))
    except (OSError, ValueError, AttributeError) as e:
        print("btreceiver: couldn't save the settings:", e)


def _speaker(rate):
    """The board's ``audio_out`` at *rate*, or None where there's none."""
    try:
        import board_peripherals as bp
        from audiodev import AudioFormat
    except ImportError:
        return None
    make = getattr(bp, "audio_out", None)
    if make is None:
        return None
    return make(AudioFormat(rate, 2, 16))


def _microphone(rate):
    """The board's microphones, open, as one 16-bit channel at *rate*, for
    a call. None on a board with no ``pcm_in``."""
    try:
        import board_peripherals as bp
        from audiodev import AudioFormat
    except ImportError:
        return None
    make = getattr(bp, "pcm_in", None)
    if make is None:
        return None
    mic = make(AudioFormat(rate, 1, 16))
    mic.open()
    return mic


def _levels(out, demo_mode):
    """A source of BANDS levels, 0 to 1, for what *out* plays, or None."""
    try:
        if demo_mode:
            from spectrum.fake_music import FakeMusic

            return FakeMusic(BANDS)
        from spectrum.analyzer import levels_for

        return levels_for(out)(BANDS)
    except (ImportError, ValueError, AttributeError, OSError) as e:
        print("btreceiver: no spectrum:", e)
        return None


def main(scope):
    global state
    opened = _open_sink()
    if opened is None:
        ui.missing(scope, "missing: btclassic",
                   "Bluetooth Receiver needs a firmware with btclassic, the Bluetooth Classic module.")
        return
    bt, sink, bits, was_on = opened
    config = _load_config(scope)
    demo_mode = not hasattr(sink, "readinto")
    name = bt.config("name")
    try:
        pin = bt.config("pin")
    except (ValueError, OSError):  # a firmware that doesn't read it back
        pin = None
    status = ui.status(scope)
    status.set_text("demo" if demo_mode else "")

    def toggle():
        if sink.playing:
            sink.pause()
        else:
            sink.play()

    def volume(v):
        sink.volume = v

    def setting(name, value):
        # The sender answers with its new state, which the button then shows.
        try:
            sink.setting(name, value)
        except (OSError, ValueError) as e:
            print("btreceiver: %s:" % name, e)

    def repeat():
        setting("repeat", NEXT_REPEAT.get(getattr(sink, "repeat", None), "off"))

    def shuffle():
        setting("shuffle", "all" if getattr(sink, "shuffle", None) == "off" else "off")

    def answer():
        st["hf"].answer()

    def hangup():
        st["hf"].hangup()

    def mute():
        st["muted"] = not st["muted"]
        if st["mic"] is not None:
            st["hf"].uplink(None if st["muted"] else st["mic"])
        show_call()

    def route_audio():
        # The phone says when the audio has moved; the AUDIO bit follows.
        if st["hf"].audio:
            st["hf"].disconnect_audio()
        else:
            st["hf"].connect_audio()

    on = {"play": toggle, "next": sink.next, "previous": sink.previous, "seek": sink.seek, "volume": volume,
          "repeat": repeat, "shuffle": shuffle, "answer": answer, "hangup": hangup, "mute": mute,
          "route": route_audio}
    W, H = scope.size
    rect = getattr(scope, "rect", None) or (0, 0, W, H)
    round_ = W == H and tuple(rect[:2]) == (0, 0) and is_round()
    scr = Screen(scope.root, scope.size, on, switch=switch_header(scope) is None, round_=round_)
    st = state = {"sink": sink, "hf": None, "out": None, "rate": 0, "levels": None, "screen": scr, "t0": ticks_ms(),
                  "call_out": None, "mic": None, "muted": False, "talking": False, "answered": None,
                  "takes_audio": True, "config": config, "chimes": Chimes(), "rang": None, "msgs": None,
                  "map_tries": 0, "map_asked": ticks_ms(), "map_pending": False}
    jpeg = bytearray(COVER_JPEG)
    # Covers decode into two buffers made once, taking turns, so LVGL never
    # shows the one being written and a new cover makes no garbage.
    covers = [bytearray(COVER_PX * COVER_PX * 2) for _ in range(2)]

    def route():
        # Open the speaker at the stream's rate, and again if it changes. A
        # call's audio has the speaker until it ends.
        if st["talking"]:
            return
        rate = sink.sample_rate
        if not rate or rate == st["rate"]:
            return
        if demo_mode:  # the pretend phone has no audio: a chime's speaker stays
            st["rate"] = rate
            st["levels"] = _levels(None, True)
            return
        close_out()
        st["rate"] = rate
        if open_out(rate):
            st["levels"] = _levels(st["out"], False)

    def open_out(rate, music=True):
        # The speaker plays the music and the chimes through one mixer.
        # The demo's pretend phone has no audio: there it plays the chimes
        # alone.
        try:
            out = _speaker(rate)
            if out is None:
                if not demo_mode:
                    status.set_text("no audio out")
                return False
            out.play(st["chimes"].mix(rate, sink if music else None))
            st["out"] = out
        except Exception as e:  # the screen still follows the sender
            print("btreceiver: no audio out:", e)
            if not demo_mode:
                status.set_text("no audio out")
            return False
        return True

    def chime(kind):
        # On the board, the call's audio has the speaker, and only the call's
        # own chime goes over it while it rings. With no music yet, the
        # speaker opens for the chime at the phone's usual rate, and stays
        # open for the music to come.
        if st["talking"]:
            if kind == "call" and st["call_out"] is not None:
                print("btreceiver: chime for a call")
                st["chimes"].play(kind)
            return
        if st["out"] is None:
            rate = sink.sample_rate or 44100
            if not demo_mode:
                st["rate"] = rate
            open_out(rate, music=not demo_mode)
        print("btreceiver: chime for a %s" % kind)
        st["chimes"].play(kind)

    def close_out():
        src = st["levels"]
        st["levels"] = None
        if src is not None and hasattr(src, "close"):
            src.close()
        out = st["out"]
        st["out"] = None
        if out is not None:
            out.stop()
            out.close()
        st["chimes"].close()

    def route_call():
        # The phone moves a call's audio to the board and back; the speaker
        # follows it, and the microphones go with it. The music's output is
        # closed first: the speaker plays one stream at one rate.
        here = st["hf"].audio
        if here and not st["talking"]:
            close_out()
            st["rate"] = 0
            st["talking"] = True
            if demo_mode:
                return
            rate = st["hf"].sample_rate
            try:
                out = _speaker(rate)
                if out is None:
                    status.set_text("no audio out")
                    return
                # A phone may bring the call's audio up while it still rings,
                # and send nothing until it's answered: the chime goes over it.
                out.play(st["chimes"].mix(rate, st["hf"]))
                st["call_out"] = out
            except Exception as e:
                print("btreceiver: no call audio out:", e)
                status.set_text("no audio out")
                return
            try:
                mic = _microphone(rate)
            except Exception as e:  # the caller still plays; they can't hear us
                print("btreceiver: no microphone for the call:", e)
                mic = None
            st["mic"] = mic
            if mic is not None and not st["muted"]:
                st["hf"].uplink(mic)
            print("btreceiver: call audio on the board at %d Hz, microphone %s" % (rate, "on" if mic else "none"))
        elif not here and st["talking"]:
            drop_call()
            route()

    def drop_call():
        st["talking"] = False
        if demo_mode:
            return
        mic = st["mic"]
        st["mic"] = None
        if mic is not None:
            st["hf"].uplink(None)
            mic.close()
        out = st["call_out"]
        st["call_out"] = None
        if out is not None:
            out.stop()
            out.close()
            st["chimes"].close()
            print("btreceiver: call audio off the board; sent", st["hf"].stats().get("sent"), "frames")

    def show_phone():
        if st["hf"].connected:
            scr.show_phone(st["hf"].battery, st["hf"].signal, st["hf"].service)
        else:
            scr.show_phone(None, None, None)

    def show_call():
        call = st["hf"].call
        if call == "active":
            if st["answered"] is None:
                st["answered"] = ticks_ms()
        else:
            st["answered"] = None
        if call not in ("active", "held"):
            st["muted"] = False
        scr.show_call(call, st["hf"].caller, sink.peer_name, st["hf"].audio, st["muted"], demo_mode or st["mic"] is not None,
                      st["takes_audio"])
        show_time()

    def show_time():
        if st["answered"] is not None:
            scr.show_call_time(ticks_diff(ticks_ms(), st["answered"]))

    def call_phone():
        # The link follows the sink when the sink connects, but not to a
        # phone that was connected before the unit started: call that one
        # a few times, a while apart. A computer never answers.
        hf = st["hf"]
        if hf.connected or not sink.connected or not hasattr(hf, "connect"):
            st["hf_tries"] = 0
            st["hf_asked"] = ticks_ms()
            return
        if st["hf_tries"] >= HF_TRIES or ticks_diff(ticks_ms(), st["hf_asked"]) < HF_RETRY_MS:
            return
        st["hf_tries"] += 1
        st["hf_asked"] = ticks_ms()
        try:
            hf.connect()
        except OSError as e:
            print("btreceiver: the phone's hands-free link:", e)

    def follow_phone():
        call_phone()
        changed = st["hf"].changes()
        if changed & (bits.CONNECTION | bits.AUDIO | bits.CALL):
            route_call()
        if changed & (bits.CONNECTION | bits.PHONE):
            show_phone()
        if changed & (bits.CONNECTION | bits.CALL | bits.AUDIO):
            show_call()
        else:
            show_time()
        ring()

    def ring():
        # A ringing call chimes now and every RING_MS until it's answered or
        # gone, over the phone's own ringtone if it sends one: a phone that
        # rings in band can still send silence.
        hf = st["hf"]
        if hf.call != "incoming":
            st["rang"] = None
            return
        if st["rang"] is None or ticks_diff(ticks_ms(), st["rang"]) >= RING_MS:
            st["rang"] = ticks_ms()
            chime("call")

    def call_messages():
        # The message service follows the music's phone: asked for a few
        # seconds after it connects, and again, a few times, if that fails.
        # A computer has none, and is let be after MAP_TRIES.
        msgs = st["msgs"]
        now = ticks_ms()
        if msgs.connected or not sink.connected:
            st["map_tries"] = 0
            st["map_asked"] = now
            st["map_pending"] = False
            return
        if st["map_pending"] and ticks_diff(now, st["map_asked"]) < MAP_PENDING_MS:
            return
        if st["map_tries"] >= MAP_TRIES or ticks_diff(now, st["map_asked"]) < MAP_WAIT_MS:
            return
        st["map_tries"] += 1
        st["map_asked"] = now
        st["map_pending"] = True
        try:
            msgs.connect(timeout=0)
        except OSError as e:
            st["map_pending"] = False
            print("btreceiver: the phone's messages:", e)

    def follow_texts():
        msgs = st["msgs"]
        call_messages()
        changed = msgs.changes()
        if changed & bits.CONNECTION:
            st["map_pending"] = False
            if msgs.connected:
                try:
                    msgs.notify()
                    print("btreceiver: the phone reports new texts")
                except OSError as e:
                    print("btreceiver: the phone won't report new texts:", e)
        if not (changed & bits.NOTIFY or msgs.events):
            return
        new = False
        while True:
            ev = msgs.event()
            if ev is None:
                break
            # A text the phone sent shows up too, in "sent" or "outbox".
            if ev.get("type") == "NewMessage" and ev.get("folder", "inbox").endswith("inbox"):
                new = True
        if new:
            chime("text")

    def show_cover():
        try:
            n = sink.cover_into(jpeg)
        except ValueError as e:  # larger than COVER_JPEG
            print("btreceiver: cover:", e)
            n = 0
        if not n:
            scr.show_cover(None, 0, 0)
            return
        try:
            import jpegio

            dec = jpegio.JpegDecoder()
            w, h = dec.open(memoryview(jpeg)[:n])
            scale = 0
            while (w >> scale) > COVER_PX or (h >> scale) > COVER_PX:
                scale += 1
                if scale > 3:  # the decoder scales down to an eighth at most
                    raise ValueError("a %d x %d cover is too large" % (w, h))
            w, h = w >> scale, h >> scale
            covers.reverse()
            px = memoryview(covers[0])[: w * h * 2]
            dec.decode(px, scale)
        except Exception as e:
            print("btreceiver: cover:", e)
            scr.show_cover(None, 0, 0)
            return
        scr.show_cover(px, w, h)

    def show_link():
        # The sender's name heads the idle screen already. Its battery shows
        # whenever it's connected; the stream's details once the rate is known.
        playing = sink.connected and _said(sink.title)
        link = sink.link() if sink.connected else None
        if link is not None and not sink.sample_rate:
            link["sample_rate"] = 0
        scr.show_source(sink.peer_name if playing else "", link)

    def show_modes():
        # A firmware whose btclassic can't read them back has neither.
        scr.show_modes(getattr(sink, "repeat", None), getattr(sink, "shuffle", None))

    def show_all():
        if not sink.connected:
            scr.show_pairing(name, pin)
            return
        title = _said(sink.title)
        if title:
            scr.show_track(title, _said(sink.artist), _said(sink.album), sink.track_number, sink.track_count,
                           _said(sink.genre))
            scr.show_status(sink.status)
        else:
            scr.show_status(None)
            scr.show_idle(sink.peer_name)
        show_link()

    settings_bit = getattr(bits, "SETTINGS", 0)

    def open_phone():
        # The calls setting on: the phone's hands-free link, which brings its
        # battery, its signal and its calls.
        hf = _open_handsfree(bt, sink, bits)
        if hf is None:
            return
        st["hf"] = hf
        # A firmware older than HandsFree.call_audio always takes the call's audio.
        st["takes_audio"] = getattr(hf, "call_audio", True)
        st["hf_tries"] = 0
        st["hf_asked"] = ticks_ms()
        follow_phone()
        show_phone()
        show_call()

    def close_phone():
        # The calls setting off: the link goes, and with it the card and
        # the phone's own battery and signal. The player's battery stays.
        hf = st["hf"]
        if hf is None:
            return
        drop_call()
        st["hf"] = None
        hf.deinit()
        st["answered"] = None
        st["muted"] = False
        scr.show_phone(None, None, None)
        scr.show_call(None, "", "", False, False, False)
        route()

    def set_calls(on):
        config["calls"] = on
        _save_config(scope, config)
        if on:
            open_phone()
        else:
            close_phone()

    def follow(t):
        if st["hf"] is not None:
            follow_phone()
        if st["msgs"] is not None:
            follow_texts()
        changed = sink.changes()
        if changed:
            route()
        if changed & (bits.CONNECTION | bits.TRACK | bits.PLAYING):
            show_all()
        elif changed & (bits.PEER | bits.STREAM | bits.FORMAT):
            show_link()
        if changed & (bits.CONNECTION | bits.COVER):
            show_cover()
        if changed & bits.VOLUME:
            scr.show_volume(sink.volume)
        if changed & (bits.CONNECTION | settings_bit):
            show_modes()
        if sink.connected and _said(sink.title):
            scr.show_position(sink.position, sink.duration)

    def bars(t):
        src = st["levels"]
        if scr.call_state is not None:
            return  # under the card
        if src is None or not sink.playing:
            scr.show_levels(_SILENT)
            return
        scr.show_levels(src.levels(ticks_diff(ticks_ms(), st["t0"]) / 1000))

    def close():
        hf = st["hf"]
        if hf is not None:
            drop_call()
        close_out()
        msgs = st["msgs"]
        st["msgs"] = None
        if msgs is not None:
            msgs.deinit()
        # The phone is let go when the app closes, and called back when it
        # opens again. The radio goes back off if it was off.
        if hf is not None:
            hf.deinit()
        sink.deinit()
        if not was_on:
            bt.active(False)
        glyphs.forget()

    scope.on_close(close)
    show_all()
    show_cover()
    show_modes()
    scr.show_volume(sink.volume)
    route()
    st["switch"] = calls_switch(scope, config["calls"], set_calls, scr.lay)
    if config["calls"]:
        open_phone()
    if config["texts"]:
        try:
            st["msgs"] = _open_messages(bt, sink, bits)
        except OSError as e:  # the player and calls go on without it
            print("btreceiver: no chime for texts:", e)
    scope.every(UI_MS, follow)
    scope.every(BARS_MS, bars)
    if not sink.connected:
        print("btreceiver: pair with %s and play" % name)


_SILENT = [0.0] * BANDS
