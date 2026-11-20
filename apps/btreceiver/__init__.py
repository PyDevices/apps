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

The board is also the phone's hands-free unit, as a car kit is: the phone's
battery and signal show at the top right, and a call shows a card over the
player with the caller's number, to answer or decline. An answered call plays
through the board's speaker and sends its microphones to the phone, and the
music comes back when the call ends.

It needs a firmware with ``btclassic``. The audio goes out through the
board's ``audio_out`` on the audio pump, so a redraw never holds it up. On a
computer with no Bluetooth module the app plays a demo: a pretend phone that
pairs, plays a few tracks and follows the buttons.
"""

from multimer import ticks_diff, ticks_ms

from appkit import data as appdata
from touchkit import ui

from . import glyphs
from .screen import BANDS, Screen

UI_MS = 250  # how often the app reads the sink
BARS_MS = 66  # how often the spectrum moves
COVER_PX = 200  # AVRCP covers are 200 x 200; a larger one is halved to fit
COVER_JPEG = 96 * 1024  # room for the cover's JPEG
# A phone starting a stream sends about twice as fast for a second or two:
# this rides that out. Half of it is the delay to the speaker.
BUFFER_MS = 1000

state = None  # the open app's state, for the console
# What Android sends for a field it doesn't know, the title included when
# nothing is playing.
UNSAID = "Not Provided"
# A tap moves repeat on the way a phone's player does, and turns shuffle on
# or off. "group" (a sender's own mode) goes back to off.
NEXT_REPEAT = {"off": "all", "all": "single"}


def _said(text):
    """*text*, or "" when the sender says it doesn't know."""
    return "" if text == UNSAID else text


def _open_sink():
    """``(radio, sink, handsfree, bits, radio_was_on)``: btclassic's, or the
    demo's on a computer. None on a board without btclassic. *handsfree* is
    None on a firmware whose btclassic has no hands-free unit."""
    try:
        import btclassic
    except ImportError:
        if not appdata.desktop():
            return None
        from . import demo

        sink = demo.DemoSink()
        return demo.DemoRadio(), sink, demo.DemoHandsFree(sink), demo, True
    bt = btclassic.Bluetooth()
    was_on = bt.active()
    sink = btclassic.AudioSink(bt, buffer_ms=BUFFER_MS)
    make = getattr(btclassic, "HandsFree", None)
    if make is None:
        print("btreceiver: this btclassic has no HandsFree: no battery, signal or calls")
        return bt, sink, None, btclassic, was_on
    # Stereo frames, the shape the speaker plays. It follows the sink's phone.
    return bt, sink, make(bt, channels=2), btclassic, was_on


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
    bt, sink, hf, bits, was_on = opened
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
        hf.answer()

    def hangup():
        hf.hangup()

    def mute():
        st["muted"] = not st["muted"]
        if st["mic"] is not None:
            hf.uplink(None if st["muted"] else st["mic"])
        show_call()

    def route_audio():
        # The phone says when the audio has moved; the AUDIO bit follows.
        if hf.audio:
            hf.disconnect_audio()
        else:
            hf.connect_audio()

    on = {"play": toggle, "next": sink.next, "previous": sink.previous, "seek": sink.seek, "volume": volume,
          "repeat": repeat, "shuffle": shuffle, "answer": answer, "hangup": hangup, "mute": mute,
          "route": route_audio}
    scr = Screen(scope.root, scope.size, on)
    st = state = {"sink": sink, "hf": hf, "out": None, "rate": 0, "levels": None, "screen": scr, "t0": ticks_ms(),
                  "call_out": None, "mic": None, "muted": False, "talking": False, "answered": None}
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
        close_out()
        st["rate"] = rate
        if demo_mode:
            st["levels"] = _levels(None, True)
            return
        try:
            out = _speaker(rate)
            if out is None:
                status.set_text("no audio out")
                return
            out.play(sink)
            st["out"] = out
        except Exception as e:  # the screen still follows the sender
            print("btreceiver: no audio out:", e)
            status.set_text("no audio out")
            return
        st["levels"] = _levels(out, False)

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

    def route_call():
        # The phone moves a call's audio to the board and back; the speaker
        # follows it, and the microphones go with it. The music's output is
        # closed first: the speaker plays one stream at one rate.
        here = hf.audio
        if here and not st["talking"]:
            close_out()
            st["rate"] = 0
            st["talking"] = True
            if demo_mode:
                return
            rate = hf.sample_rate
            try:
                out = _speaker(rate)
                if out is None:
                    status.set_text("no audio out")
                    return
                out.play(hf)
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
                hf.uplink(mic)
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
            hf.uplink(None)
            mic.close()
        out = st["call_out"]
        st["call_out"] = None
        if out is not None:
            out.stop()
            out.close()
            print("btreceiver: call audio off the board; sent", hf.stats().get("sent"), "frames")

    def show_phone():
        if hf.connected:
            scr.show_phone(hf.battery, hf.signal, hf.service)
        else:
            scr.show_phone(None, None, None)

    def show_call():
        call = hf.call
        if call == "active":
            if st["answered"] is None:
                st["answered"] = ticks_ms()
        else:
            st["answered"] = None
        if call not in ("active", "held"):
            st["muted"] = False
        scr.show_call(call, hf.caller, sink.peer_name, hf.audio, st["muted"], demo_mode or st["mic"] is not None)
        show_time()

    def show_time():
        if st["answered"] is not None:
            scr.show_call_time(ticks_diff(ticks_ms(), st["answered"]))

    def follow_phone():
        changed = hf.changes()
        if changed & (bits.CONNECTION | bits.AUDIO | bits.CALL):
            route_call()
        if changed & (bits.CONNECTION | bits.PHONE):
            show_phone()
        if changed & (bits.CONNECTION | bits.CALL | bits.AUDIO):
            show_call()
        else:
            show_time()

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

    def follow(t):
        if hf is not None:
            follow_phone()
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
        if hf is not None:
            drop_call()
        close_out()
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
    if hf is not None:
        follow_phone()
        show_phone()
        show_call()
    scope.every(UI_MS, follow)
    scope.every(BARS_MS, bars)
    if not sink.connected:
        print("btreceiver: pair with %s and play" % name)


_SILENT = [0.0] * BANDS
