# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""MP3 player: the songs in a folder, with the spectrum of what plays.

On a computer the songs are in ``$MP3_DIR``, else ``~/music``. On a board
they're in a ``music`` folder: ``/sd/music`` on the SD card, ``/music`` on
flash and ``/data/music``, all three in one list (`appkit.places`).

the archived pydevices-examples' mp3_from_sd, with buttons: play and stop, previous and
next, volume. A song that ends goes on to the next one. On a board the card is mounted
read-only (its writes are unreliable on this board) and only while the app
is open.
"""

import os

import lvgl as lv
from multimer import ticks_diff, ticks_ms

import spectrum
from appkit import data as appdata
from appkit import places
from touchkit import ui

MUSIC = "music"  # the folder name, on the card, flash and the data root
VOLUME = 80  # ES8311 steps of 0.5 dB: 80 is -10 dB
TOP = 132  # the spectrum's first row, in the app's area

state = None  # the open player's state, for the console


def _env(name):
    fn = getattr(os, "getenv", None)
    return fn(name) if fn is not None else None


def _home():
    return (_env("USERPROFILE") or _env("HOME") or "").replace("\\", "/")


def music_folder():
    """A computer's songs' folder: ``$MP3_DIR`` or ``~/music``."""
    return _env("MP3_DIR") or _home() + "/music"


def main(scope):
    try:
        import audiomp3
    except ImportError as e:
        ui.missing(scope, "missing: audiomp3", "The MP3 player needs audiomp3, the board's MP3 decoder, and an SD card: %s." % (e,))
        return
    import board_peripherals as bp
    from audiodev import AudioFormat

    scr = scope.root
    W, H = scope.size
    hdr = getattr(scope, "header", None) or scr
    status = ui.status(scope)
    if appdata.desktop():
        folder = music_folder()
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            names = []
        songs = [folder + "/" + n for n in names if n.lower().endswith(".mp3")]
    else:
        places.hold_card(scope)  # read-only, while the app is open
        folder = places.where_text(MUSIC)
        songs = places.files(MUSIC, (".mp3",))
    global state
    st = state = {"i": 0, "out": None, "file": None, "song": None, "meter": None, "fmt": None, "vol": VOLUME, "playing": False}

    title = ui.label(scr, "", ui.font, ui.WHITE)
    title.set_pos(16, 84)
    title.set_width(W - 32)
    title.set_long_mode(lv.label.LONG_MODE.DOTS)

    def release_song():
        if st["meter"] is not None:
            spectrum.stop(st["meter"])
            st["meter"] = None
        if st["out"] is not None:
            st["out"].stop()
        if st["file"] is not None:
            st["file"].close()
            st["file"] = None
        st["song"] = None

    def close():
        st["playing"] = False
        release_song()
        if st["out"] is not None:
            st["out"].detach()
            st["out"].close()
            st["out"] = None

    scope.on_close(close)

    def play(i=None):
        if not songs:
            return
        if i is not None:
            st["i"] = i % len(songs)
        release_song()
        path = songs[st["i"]]
        name = path.rsplit("/", 1)[-1]
        f = open(path, "rb")
        st["file"] = f
        song = audiomp3.MP3Decoder(f)
        st["song"] = song
        fmt = (song.sample_rate, song.channel_count)
        if st["out"] is not None and st["fmt"] != fmt:
            st["out"].detach()
            st["out"].close()
            st["out"] = None
        if st["out"] is None:
            fmt_out = AudioFormat(song.sample_rate, song.channel_count, 16)
            try:
                # A player can trade latency for fewer dropouts: a board
                # with a choice buffers more.
                st["out"] = bp.audio_out(fmt_out, latency="buffered")
            except TypeError:  # an audio_out that takes no latency
                st["out"] = bp.audio_out(fmt_out)
            # service() refills the decoder's file buffer from this thread
            # (the pump on the other core can't read the card): on the app's
            # timer, so it stops when the app closes.
            st["out"].attach(scope)
            st["fmt"] = fmt
        out = st["out"]
        out.set_volume(st["vol"])
        out.play(song)
        st["playing"] = True
        st["started"] = ticks_ms()
        title.set_text("%d/%d  %s  (%d Hz, %s)" % (st["i"] + 1, len(songs), name[:-4], song.sample_rate, "stereo" if song.channel_count == 2 else "mono"))
        play_lbl.set_text(lv.SYMBOL.STOP + "  Stop")
        if not getattr(out, "pumped", False):
            status.set_text("no spectrum: not on the audio pump")
            return
        try:
            from spectrum.analyzer import levels_for
        except ImportError as e:  # the spectrum draws with pygraphics
            status.set_text("no spectrum: %s" % (e,))
            return
        m = spectrum.meter(scope, levels_for(out), TOP)
        st["meter"] = m
        spectrum.start(m, scope, (hdr,))

    def stop():
        st["playing"] = False
        release_song()
        play_lbl.set_text(lv.SYMBOL.PLAY + "  Play")

    def toggle():
        if st["playing"]:
            stop()
        else:
            play()

    def volume(step):
        st["vol"] = max(0, min(100, st["vol"] + step))
        if st["out"] is not None:
            st["out"].set_volume(st["vol"])
        vol_lbl.set_text("%d%%" % st["vol"])

    y = 12
    b, _ = ui.button(scr, lv.SYMBOL.PREV, lambda: play(st["i"] - 1), w=90, h=60, font=ui.big)
    b.set_pos(16, y)
    b, play_lbl = ui.button(scr, lv.SYMBOL.PLAY + "  Play", toggle, w=180, h=60, font=ui.big)
    b.set_pos(118, y)
    b, _ = ui.button(scr, lv.SYMBOL.NEXT, lambda: play(st["i"] + 1), w=90, h=60, font=ui.big)
    b.set_pos(310, y)
    b, _ = ui.button(scr, lv.SYMBOL.VOLUME_MID, lambda: volume(-5), w=90, h=60, font=ui.big)
    b.set_pos(W - 16 - 90 - 100 - 90, y)
    vol_lbl = ui.label(scr, "%d%%" % st["vol"], ui.big, ui.WHITE)
    vol_lbl.set_pos(W - 16 - 90 - 92, y + 14)
    b, _ = ui.button(scr, lv.SYMBOL.VOLUME_MAX, lambda: volume(5), w=90, h=60, font=ui.big)
    b.set_pos(W - 16 - 90, y)

    if not songs:
        status.set_text("no songs")
        title.set_text("No songs. Put .mp3 files in %s." % folder)
        return

    def tick(t):
        out = st["out"]
        if (st["playing"] and out is not None and st["song"] is not None
                and ticks_diff(ticks_ms(), st["started"]) > 3000):
            # A song that has run out: the pump stops pulling it.
            from audiodev import pump

            h = pump.health() or {}
            if not h.get("running") and not out.paused:
                play(st["i"] + 1)
                return
        status.set_text("playing" if st["playing"] else "stopped")

    title.set_text("%d song%s in %s" % (len(songs), "" if len(songs) == 1 else "s", folder))
    scope.after(300, lambda t: play(0))
    scope.every(1000, tick)
