# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Bluetooth Receiver: the board plays what a phone or computer sends it.

Pair a phone with the board's name and play anything: music, a podcast, a
video's sound. The screen shows the cover large, then everything the sender
says about the track (title, artist, album, track number, genre, length and
where it's up to) and about the link (the sender's name, the codec and the
rate). The buttons drive the sender's player (hold a skip button to fast
forward or rewind), and the volume slider is the one on the phone. A spectrum of what plays runs under the title.

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

    on = {"play": toggle, "next": sink.next, "previous": sink.previous, "seek": sink.seek, "volume": volume}
    scr = Screen(scope.root, scope.size, on)
    st = state = {"sink": sink, "out": None, "rate": 0, "levels": None, "screen": scr, "t0": ticks_ms()}
    jpeg = bytearray(COVER_JPEG)
    # Covers decode into two buffers made once, taking turns, so LVGL never
    # shows the one being written and a new cover makes no garbage.
    covers = [bytearray(COVER_PX * COVER_PX * 2) for _ in range(2)]

    def route():
        # Open the speaker at the stream's rate, and again if it changes.
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
        # The sender's name heads the idle screen already; the stream's
        # details stay while it's paused, once its rate is known.
        playing = sink.connected and sink.title
        scr.show_source(sink.peer_name if playing else "", sink.link() if playing and sink.sample_rate else None)

    def show_all():
        if not sink.connected:
            scr.show_pairing(name, pin)
            return
        if sink.title:
            scr.show_track(sink.title, sink.artist, sink.album, sink.track_number, sink.track_count, sink.genre)
            scr.show_status(sink.status)
        else:
            scr.show_status(None)
            scr.show_idle(sink.peer_name)
        show_link()

    def follow(t):
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
        if sink.connected and sink.title:
            scr.show_position(sink.position, sink.duration)

    def bars(t):
        src = st["levels"]
        if src is None or not sink.playing:
            scr.show_levels(_SILENT)
            return
        scr.show_levels(src.levels(ticks_diff(ticks_ms(), st["t0"]) / 1000))

    def close():
        close_out()
        # The phone is let go when the app closes, and called back when it
        # opens again. The radio goes back off if it was off.
        sink.deinit()
        if not was_on:
            bt.active(False)
        glyphs.forget()

    scope.on_close(close)
    show_all()
    show_cover()
    scr.show_volume(sink.volume)
    route()
    scope.every(UI_MS, follow)
    scope.every(BARS_MS, bars)
    if not sink.connected:
        print("btreceiver: pair with %s and play" % name)


_SILENT = [0.0] * BANDS
