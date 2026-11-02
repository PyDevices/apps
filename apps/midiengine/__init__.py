# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""midiEngine: a General MIDI sound module in the shape of MIDIPLUS's
pocket miniEngine. Plug a USB MIDI keyboard into the board's hub, or a
sequencer into a desktop's MIDI port, and every one of the 16 channels
plays: SoundFont instruments on 1-9 and 11-16, a drum kit on 10. Or play
a folder of .mid files, and the keyboard on top of them.

The panel is the module's face, four cards on one screen. The top one
is what's playing: the piece's title, its composer, length and place in
the library, a progress bar, and the transport (previous, play or stop,
next, loop) with the Library button. Under it the mixer: sixteen strips,
one per channel, each with its program number and a meter that lights
with every note and falls away; tap a strip to select its channel. The
channel card shows the selected channel's number, instrument and program
(step it with the arrows) and its volume and pan (the faders follow the
channel, and a CC7 or CC10 arriving on it moves them). The master card
has the MASTER level (the output's volume, kept as a preference), reverb
and chorus for the whole module, and PANIC, which stops the player and
every sound.

The Library button swaps the lower cards for the browser: the genres
down the left, the pieces of one (or all of them) on the right, each
with its title, composer and length; tap a piece to play it. "Genre
only" keeps next, previous and the end of a piece within the current
genre; off, they walk the whole library. The library is a folder of
.mid files, on a desktop ``$MIDI_DIR``, else ``~/midi``
(``%USERPROFILE%\\midi`` on Windows); on a board ``/sd/midi``, the
card mounted read-only while the app is open, as the MP3 player does. A
``catalog.json`` at its root names each piece's title, composer, genre
and length; without one the folder is scanned, subfolders as genres,
the file's name as its title. With no folder or no files, the face says
where to put them. ``player.py`` is the player, ``umidiparser.py`` the
parser it reads files with.

The sound is audioinstruments' ``soundfont`` and ``soundfont_drums``,
reading one .sf2, mixed through audioeffects' Chorus and Reverb and out
of the 3.5 mm jack. The bank is ``$SOUNDFONT``, else a .sf2 in
``~/soundfonts`` on a desktop, ``/sd/soundfonts`` or ``/soundfonts`` on a
board; with more than one there, the app opens on a list of them, the
last one chosen lit, and the sound starts with the one tapped (``banks.py``
finds them). With none, the face says where to put one. The bank is opened when the sound
starts; a channel's instrument is made the first time it is played or given a program, and its
samples are read on its notes, a bounded number of them kept. A tap on a piece only starts the
player's clock: its first events go on the app's timer.
The MIDI it answers is the sound module's (studio's ``soundmodule.engine``).
"""

import lvgl as lv
from multimer import ticks_diff, ticks_ms

from touchkit import ui

from soundmodule import engine as gm  # the sound module's engine, from studio

from . import midiin

from . import banks, player

RATE = 48000
CHANNELS = 2
CODEC_VOLUME = 85
MIDI_MS = 4  # how often the file player is serviced, and the port read while no file plays
FILE_MIDI_EVERY = 3  # while a file plays, the port is read every third service (12 ms): a read waits
                     # a millisecond or more for the device, time the file's notes need
UI_MS = 40
DECAY = 8  # a strip's meter falls this much (of 127) per UI tick: about 0.6 s from full
SETUP_MS = 500  # how often to look for a keyboard until one is found
SEP = "  \u2022  "  # between the facts of a line: a bullet, which every LVGL font has
SD_MIDI = "/sd/midi"  # a board's MIDI files

state = None  # for the console


def pan_text(v):
    if v == 64:
        return "C"
    return ("L%d" % (64 - v)) if v < 64 else ("R%d" % (v - 64))


def _mount(scope):
    """The SD card at ``/sd``, read-only, for as long as the app is open:
    the MP3 player's way."""
    import os

    import board_peripherals as bp

    try:
        os.listdir("/sd")
        return  # someone else's mount: leave it
    except OSError:
        pass
    card = bp.sdcard()
    os.mount(card, "/sd", readonly=True)

    def unmount():
        try:
            os.umount("/sd")
        finally:
            card.deinit()

    scope.on_close(unmount)


def midi_folder(scope):
    """Where the .mid files are: ``$MIDI_DIR`` or ``~/midi`` on a desktop,
    ``/sd/midi`` on a board. Raises what mounting the card raised."""
    if banks.DESKTOP:
        return banks.getenv("MIDI_DIR") or banks.home() + "/midi"
    _mount(scope)
    return SD_MIDI


def clock_text(ms):
    """``m:ss``, or ``h:mm:ss`` from an hour (a genre's total)."""
    if ms >= 3600000:
        return "%d:%02d:%02d" % (ms // 3600000, (ms // 60000) % 60, (ms // 1000) % 60)
    return "%d:%02d" % (ms // 60000, (ms // 1000) % 60)


def main(scope):
    global state
    scr = scope.root
    W, H = scope.size
    status = ui.status(scope)

    st = state = {
        "module": None, "out": None, "port": None, "host": None, "ch": 0, "level": [0] * 16,
        "seen": [0] * 16, "midi": None, "error": None, "shown": None, "bank": None, "bank_name": "",
        "merged": False, "midi_told": False, "ticks": 0,
        "since": ticks_ms(), "player": None, "player_shown": None, "browse": None, "marked": None, "widgets": {},
    }
    watch = midiin.Watch()  # names the hub's MIDI devices for the status line
    prefs = scope.store()
    prefs.setdefault("volume", gm.DEFAULT_MASTER)
    prefs.setdefault("ch", 0)
    prefs.setdefault("loop", False)
    prefs.setdefault("scope", player.ALL)
    st["ch"] = prefs["ch"]

    # -- the sound ------------------------------------------------------------------

    def find_banks():
        """The banks to choose from, ``[(path, bytes)]``, or None with the reason in ``st["error"]``."""
        try:
            # Dotted: on MicroPython, audioinstruments' lazy __getattr__ answers a
            # from-import of a submodule not yet loaded with AttributeError.
            import audioinstruments.soundfont  # noqa: F401  (the sampler gm.Module plays through)
        except (ImportError, AttributeError) as e:
            st["error"] = "no sampler in this firmware: %s" % (e,)
            return None
        desktop = banks.DESKTOP
        found = banks.candidates(banks.folders(desktop), banks.getenv("SOUNDFONT"))
        if not found:
            st["error"] = ("No SoundFont. Put a .sf2 in ~/soundfonts, or set SOUNDFONT to one." if desktop else
                           "No SoundFont. Put a .sf2 in %s or %s." % (banks.SD_SOUNDFONTS, banks.FLASH_SOUNDFONTS))
            return None
        return found

    def start_audio(bank):
        try:
            from audiodev import AudioFormat
            import board_peripherals as bp
            module = gm.Module(RATE, CHANNELS, bank=bank)
            module.prepare()  # the bank's presets read now, not in the first tap on a piece
            power = getattr(bp, "audio_power", None)
            if power is not None:
                power(True, volume=CODEC_VOLUME)
            out = bp.audio_out(AudioFormat(RATE, CHANNELS, 16))
            out.attach(scope)  # its service() on the app's timer: pumped here, stops with the app
            module.on_master = out.set_volume
            module.set_master(prefs["volume"])
            out.play(module.output)
        except Exception as e:
            st["error"] = "audio: %s" % (e,)
            return
        st["module"], st["out"], st["bank"] = module, out, bank
        st["bank_name"] = banks.name_of(bank)

    def stop_audio():
        out, module = st["out"], st["module"]
        st["out"] = st["module"] = None
        if out is not None:
            try:
                out.stop()
            except Exception:
                pass
            out.detach()
            out.close()
        if module is not None:
            module.close()  # after the output, so it never pulls a deinitialised node
        try:
            import board_peripherals as bp
            power = getattr(bp, "audio_power", None)
            if power is not None:
                power(False)
        except Exception:
            pass

    # -- MIDI in --------------------------------------------------------------------

    def open_midi():
        """Every USB MIDI device in the board's hub at once, merged (ones
        plugged in later are heard too), or a desktop's first MIDI port."""
        try:
            import usb.core
            from midiports import usb_host

            start = usb.core.start  # PyUSB on a desktop has no host to start
        except (ImportError, AttributeError):
            return open_desktop_midi()
        if not st["host"]:
            start(full_speed=True)  # the board's keyboard sits behind its hub
            st["host"] = True
        st["port"], _out = usb_host.all_ports()
        st["merged"] = True
        return True

    def open_desktop_midi():
        found = midiin.open_desktop()
        if found is None:
            return False
        st["port"], st["midi"] = found
        return True

    def midi(t):
        port = st["port"]
        if port is None:
            return
        try:
            if not port.any():
                return
            data = port.read()
        except Exception as e:
            st["port"] = None
            status.set_text("MIDI: %s" % (e,))
            return
        module = st["module"]
        if data and module is not None:
            module.feed(data)

    # -- the file player ------------------------------------------------------------

    def feed(data):
        """The player's sink: the same path as the port's bytes."""
        module = st["module"]
        if module is not None:
            module.feed(data)

    try:
        files = player.Player(midi_folder(scope), feed, loop=bool(prefs["loop"]), scope=prefs["scope"])
    except Exception as e:  # no card to mount: a player with nothing, and the reason
        files = player.Player(SD_MIDI, feed, loop=bool(prefs["loop"]), scope=prefs["scope"])
        files.message = "No SD card: %s. Put .mid files in %s on one." % (e, SD_MIDI)
    st["player"] = files

    def guarded(fn):
        """A transport action that reports a file the parser can't read, or
        a part that won't load, on the status line instead of dying in LVGL."""
        def run():
            try:
                fn()
            except Exception as e:
                files.stop()
                status.set_text("MIDI file: %s" % (e,))
        return run

    serve_player = guarded(files.service)

    # -- the face -------------------------------------------------------------------
    #
    # Four cards on an 8 px grid: what's playing (with the transport), the
    # mixer (sixteen strips), the selected channel and the master. The
    # LIBRARY button swaps the lower three for the library browser.

    M, G = 8, 8
    NOW_H, MIX_H = 96, 132
    LOW_Y = M + NOW_H + G + MIX_H + G  # the channel and master cards' top
    LOW_H = H - LOW_Y - M
    CW = W - 2 * M  # a full-width card
    CHAN_W = 470
    MAST_X = M + CHAN_W + G
    MAST_W = W - MAST_X - M
    PAD = 14  # inside a card

    def card(x, y, w, h):
        c = ui.box(scr, x, y, w, h, ui.PANEL)
        c.set_style_pad_all(0, 0)
        return c

    def one_line(lbl, font, w):
        """A label of one line, *w* wide, that ends in dots when the text is longer."""
        lbl.set_size(w, font.get_line_height())
        lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
        return lbl

    def eyebrow(parent, text, x, y, w=None, right=False):
        lbl = ui.label(parent, text, ui.tiny, ui.MUTED)
        lbl.set_style_text_letter_space(1, 0)
        lbl.set_pos(x, y)
        if w:
            one_line(lbl, ui.tiny, w)
        if right:
            lbl.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
        return lbl

    def key(parent, text, cb, w, h, font=None, color=None, checkable=False):
        b, lbl = ui.button(parent, text, cb, w=w, h=h, font=font, color=color or ui.KEY)
        b.set_style_radius(10, 0)
        b.set_style_shadow_width(0, 0)
        if checkable:
            b.add_flag(lv.obj.FLAG.CHECKABLE)
            b.set_style_bg_color(ui.ACCENT, lv.STATE.CHECKED)  # the one accent, not the theme's second colour
        return b, lbl

    def fader(parent, x, y, w, text, top, value, changed, accent=False):
        """A labelled horizontal slider: ``(slider, value label)``."""
        cap = eyebrow(parent, text, x, y)
        val = ui.label(parent, "", ui.small, ui.WHITE if accent else ui.MUTED)
        val.set_pos(x, y - 2)
        val.set_width(w)
        val.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
        s = lv.slider(parent)
        s.set_pos(x, y + 24)
        s.set_size(w, 8)
        s.set_range(0, top)
        s.set_value(value, False)
        s.set_style_bg_color(ui.BG, lv.PART.MAIN)
        s.set_style_bg_color(ui.ACCENT, lv.PART.INDICATOR)
        s.set_style_bg_color(ui.ACCENT if accent else ui.WHITE, lv.PART.KNOB)
        s.set_style_pad_all(4, lv.PART.KNOB)
        s.add_event_cb(lambda e: changed(s.get_value()), lv.EVENT.VALUE_CHANGED, None)
        return s, val, cap

    # -- now playing, with the transport --------------------------------------------

    now = card(M, M, CW, NOW_H)
    now_eyebrow = eyebrow(now, "", PAD, 10, CW - 2 * PAD - 380)
    TRANSPORT = 3 * 52 + 88 + 92 + 3 * G + 16  # prev, play, next, loop, a breath, library
    TEXT_W = CW - PAD - TRANSPORT - 10 - PAD
    title_lbl = one_line(ui.label(now, "", ui.big, ui.WHITE), ui.big, TEXT_W)
    title_lbl.set_pos(PAD, 28)
    meta_lbl = one_line(ui.label(now, "", ui.small, ui.MUTED), ui.small, TEXT_W)
    meta_lbl.set_pos(PAD, 60)
    progress = lv.bar(now)
    progress.set_pos(PAD, NOW_H - 12)
    progress.set_size(CW - 2 * PAD, 4)
    progress.set_range(0, 1000)
    progress.set_value(0, False)
    progress.set_style_bg_color(ui.BG, lv.PART.MAIN)
    progress.set_style_bg_color(ui.ACCENT, lv.PART.INDICATOR)

    def set_loop():
        files.loop = bool(loop_btn.has_state(lv.STATE.CHECKED))
        prefs["loop"] = files.loop

    def set_view():
        show_library(bool(library_btn.has_state(lv.STATE.CHECKED)))

    BY, BH = 14, 52
    bx = CW - PAD
    bx -= 92
    library_btn, _ = key(now, lv.SYMBOL.LIST + "  Library", set_view, 92, BH, checkable=True)
    library_btn.set_pos(bx, BY)
    bx -= 16 + 52
    loop_btn, _ = key(now, lv.SYMBOL.LOOP, set_loop, 52, BH, font=ui.font, checkable=True)
    loop_btn.set_pos(bx, BY)
    bx -= G + 52
    next_btn, _ = key(now, lv.SYMBOL.NEXT, guarded(files.next), 52, BH, font=ui.font)
    next_btn.set_pos(bx, BY)
    bx -= G + 88
    play_btn, play_lbl = key(now, lv.SYMBOL.PLAY, guarded(files.toggle), 88, BH, font=ui.big, color=ui.ACCENT)
    play_btn.set_pos(bx, BY)
    bx -= G + 52
    prev_btn, _ = key(now, lv.SYMBOL.PREV, guarded(files.prev), 52, BH, font=ui.font)
    prev_btn.set_pos(bx, BY)
    if files.loop:
        loop_btn.add_state(lv.STATE.CHECKED)

    def show_player():
        e = files.entry
        if files.message:
            shown = ("LIBRARY", "No MIDI files", files.message, 0, False)
        else:
            elapsed, length = files.elapsed_ms, files.length_ms
            if files.scope == player.GENRE and e["genre"]:
                siblings = files.indices(e["genre"])
                where = "%d/%d in %s" % (siblings.index(files.index) + 1, len(siblings), e["genre"])
            else:
                where = "%d/%d" % (files.index + 1, len(files.files))
                if e["genre"]:
                    where += SEP + e["genre"]
            if files.playing:
                when = "%s / %s" % (clock_text(elapsed), clock_text(length))
            else:
                when = clock_text(e["seconds"] * 1000) if e["seconds"] else ""
            meta = SEP.join(part for part in (e["composer"], when) if part)
            shown = (("NOW PLAYING" if files.playing else "STOPPED") + SEP + where, e["title"], meta,
                     (elapsed * 1000 // length) if length else 0, files.playing)
        if shown == st["player_shown"]:
            return
        st["player_shown"] = shown
        now_eyebrow.set_text(shown[0])
        title_lbl.set_text(shown[1])
        meta_lbl.set_text(shown[2])
        if files.message:  # the message wraps where the bar would be: nothing to progress
            meta_lbl.set_long_mode(lv.label.LONG_MODE.WRAP)
            meta_lbl.set_height(2 * ui.small.get_line_height())
            progress.add_flag(lv.obj.FLAG.HIDDEN)
        else:
            one_line(meta_lbl, ui.small, TEXT_W)
            progress.remove_flag(lv.obj.FLAG.HIDDEN)
        progress.set_value(shown[3], False)
        play_lbl.set_text(lv.SYMBOL.STOP if shown[4] else lv.SYMBOL.PLAY)
        mark_piece()

    # -- the mixer: sixteen strips --------------------------------------------------

    mix = card(M, M + NOW_H + G, CW, MIX_H)
    eyebrow(mix, "MIXER", PAD, 10)
    bank_lbl = eyebrow(mix, "", CW // 3, 10, CW - CW // 3 - PAD, right=True)
    SW, SG, SY, SH = 43, 4, 30, 96
    sx = PAD + (CW - 2 * PAD - 16 * SW - 15 * SG) // 2
    strips = []  # per channel: [strip, program label, meter, number label]

    def select_channel(ch):
        st["ch"] = ch
        prefs["ch"] = ch

    for ch in range(16):
        s = ui.box(mix, sx + ch * (SW + SG), SY, SW, SH, ui.BG)
        s.set_style_pad_all(0, 0)
        s.set_style_radius(6, 0)
        s.set_style_border_width(2, 0)
        s.set_style_border_color(ui.BG, 0)
        s.add_flag(lv.obj.FLAG.CLICKABLE)
        s.add_event_cb(lambda e, ch=ch: select_channel(ch), lv.EVENT.CLICKED, None)
        p = ui.label(s, "", ui.tiny, ui.MUTED)
        p.set_width(SW - 4)
        p.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        p.set_pos(0, 3)
        m = lv.bar(s)
        m.set_size(10, 50)
        m.set_pos((SW - 4 - 10) // 2, 21)
        m.set_range(0, 127)
        m.set_value(0, False)
        m.set_style_bg_color(ui.PANEL, lv.PART.MAIN)
        m.set_style_bg_color(ui.ACCENT, lv.PART.INDICATOR)
        m.set_style_radius(3, lv.PART.MAIN)
        m.set_style_radius(3, lv.PART.INDICATOR)
        m.remove_flag(lv.obj.FLAG.CLICKABLE)
        n = ui.label(s, "%d" % (ch + 1), ui.small, ui.MUTED)
        n.set_width(SW - 4)
        n.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        n.set_pos(0, SH - 4 - 22)
        strips.append([s, p, m, n])

    # -- the selected channel -------------------------------------------------------

    chan = card(M, LOW_Y, CHAN_W, LOW_H)
    eyebrow(chan, "CHANNEL", PAD, 10)
    ch_lbl = ui.label(chan, "", ui.huge, ui.ACCENT)
    ch_lbl.set_pos(PAD, 26)
    NAME_W = CHAN_W - PAD - 66 - 6 - 2 * 48 - 6 - PAD  # to the PROG buttons
    name_lbl = one_line(ui.label(chan, "", ui.big, ui.WHITE), ui.big, NAME_W)
    name_lbl.set_pos(PAD + 66, 28)
    part_lbl = one_line(ui.label(chan, "", ui.small, ui.MUTED), ui.small, NAME_W)
    part_lbl.set_pos(PAD + 66, 58)

    def step_program(d):
        module = st["module"]
        if module is None:
            return
        part = module.parts[st["ch"]]
        if part.drums:
            kits = module.kit_programs()
            i = max(i for i, p in enumerate(kits) if p <= part.program) if kits else 0
            program = kits[(i + d) % len(kits)] if kits else 0
        else:
            program = (part.program + d) % 128
        module.program(part, program)

    b, _ = key(chan, lv.SYMBOL.LEFT, lambda: step_program(-1), 48, 40, font=ui.font)
    b.set_pos(CHAN_W - PAD - 48 - 6 - 48, 24)
    b, _ = key(chan, lv.SYMBOL.RIGHT, lambda: step_program(1), 48, 40, font=ui.font)
    b.set_pos(CHAN_W - PAD - 48, 24)

    # The Volume and Pan faders are the selected channel's: the CC7 and
    # CC10 paths on its part. show() moves them when the channel or the
    # part's level changes, so the fader and MIDI take turns; last wins.
    def volume_changed(v):
        module = st["module"]
        if module is not None:
            module.set_volume(module.parts[st["ch"]], v)

    def pan_changed(v):
        module = st["module"]
        if module is not None:
            module.set_pan(module.parts[st["ch"]], v)

    def master_changed(v):
        prefs["volume"] = v
        module = st["module"]
        if module is not None:
            module.set_master(v)
        elif st["out"] is not None:
            st["out"].set_volume(v)

    def reverb_changed(v):
        if st["module"] is not None:
            st["module"].set_reverb(v)

    def chorus_changed(v):
        if st["module"] is not None:
            st["module"].set_chorus(v)

    FW = (CHAN_W - 2 * PAD - 24) // 2
    faders = {
        "Volume": fader(chan, PAD, 100, FW, "VOLUME", 127, gm.DEFAULT_VOLUME, volume_changed),
        "Pan": fader(chan, PAD + FW + 24, 100, FW, "PAN", 127, gm.DEFAULT_PAN, pan_changed),
    }

    # -- the master -----------------------------------------------------------------

    mast = card(MAST_X, LOW_Y, MAST_W, LOW_H)
    eyebrow(mast, "MASTER", PAD, 10)
    PW = 72
    MW = MAST_W - 2 * PAD - PW - 20
    faders["Master"] = fader(mast, PAD, 28, MW, "LEVEL", 100, prefs["volume"], master_changed, accent=True)
    faders["Reverb"] = fader(mast, PAD, 70, MW, "REVERB", 127, gm.DEFAULT_REVERB, reverb_changed)
    faders["Chorus"] = fader(mast, PAD, 112, MW, "CHORUS", 127, gm.DEFAULT_CHORUS, chorus_changed)

    def panic():
        """Every sound off: the player too, or its next event is a note."""
        files.stop()
        module = st["module"]
        if module is not None:
            module.panic()
        st["level"] = [0] * 16

    panic_btn, _ = key(mast, "PANIC", panic, PW, LOW_H - 28 - PAD, font=ui.small, color=ui.BG)
    panic_btn.set_pos(MAST_W - PAD - PW, 28)
    panic_btn.set_style_border_width(2, 0)
    panic_btn.set_style_border_color(ui.BAD, 0)
    panic_btn.set_style_text_color(ui.BAD, 0)

    # -- the library ----------------------------------------------------------------

    LIB_Y = M + NOW_H + G
    LIB_H = H - LIB_Y - M
    GENRE_W = 200
    lib = card(M, LIB_Y, CW, LIB_H)
    lib.add_flag(lv.obj.FLAG.HIDDEN)
    eyebrow(lib, "GENRES", PAD, 10)
    genre_lbl = eyebrow(lib, "", GENRE_W + PAD, 10, CW - GENRE_W - 2 * PAD - 180)
    rule = ui.box(lib, GENRE_W, PAD, 1, LIB_H - 2 * PAD, ui.BG)
    rule.set_style_radius(0, 0)

    def rows(x, y, w, h, parent=None):
        lst = lv.list(parent or lib)
        lst.set_pos(x, y)
        lst.set_size(w, h)
        lst.set_style_bg_opa(lv.OPA.TRANSP, 0)
        lst.set_style_border_width(0, 0)
        lst.set_style_pad_all(0, 0)
        lst.set_style_pad_row(2, 0)
        lst.set_style_radius(0, 0)
        return lst

    def row(lst, text, cb, detail=None):
        b = lst.add_button(None, text)
        b.set_height(44)
        b.set_style_bg_opa(lv.OPA.TRANSP, 0)
        b.set_style_border_width(0, 0)
        b.set_style_radius(8, 0)
        b.set_style_pad_hor(10, 0)
        b.set_style_text_font(ui.font, 0)
        b.set_style_text_color(ui.WHITE, 0)
        b.set_style_bg_color(ui.KEY, lv.STATE.PRESSED)
        b.set_style_bg_opa(lv.OPA.COVER, lv.STATE.PRESSED)
        b.get_child(0).set_long_mode(lv.label.LONG_MODE.DOTS)
        b.get_child(0).set_height(ui.font.get_line_height())
        if detail:
            ui.label(b, detail, ui.small, ui.MUTED)
        b.add_event_cb(lambda e: cb(), lv.EVENT.CLICKED, None)
        return b

    def mark(b, on):
        b.set_style_bg_color(ui.ACCENT, 0)
        b.set_style_bg_opa(lv.OPA._30 if on else lv.OPA.TRANSP, 0)
        b.set_style_text_color(ui.ACCENT if on else ui.WHITE, 0)

    genre_list = rows(PAD, 34, GENRE_W - 2 * PAD, LIB_H - 34 - PAD)
    piece_list = rows(GENRE_W + PAD, 48, CW - GENRE_W - 2 * PAD, LIB_H - 48 - PAD)
    genre_rows = []  # (genre or None, button)
    piece_rows = []  # (index, button)

    def set_scope():
        files.scope = player.GENRE if scope_btn.has_state(lv.STATE.CHECKED) else player.ALL
        prefs["scope"] = files.scope
        scope_lbl.set_text("Genre only" if files.scope == player.GENRE else "Whole library")
        st["player_shown"] = None

    scope_btn, scope_lbl = key(lib, "", set_scope, 160, 34, font=ui.small, checkable=True)
    scope_btn.set_pos(CW - PAD - 160, 6)
    if files.scope == player.GENRE:
        scope_btn.add_state(lv.STATE.CHECKED)
    set_scope()

    def browse(genre):
        """Fill the pieces column with one genre's pieces, or all of them."""
        st["browse"] = genre
        for g, b in genre_rows:
            mark(b, g == genre)
        indices = files.indices(genre)
        seconds = sum(files.entries[i]["seconds"] for i in indices)
        genre_lbl.set_text("%s%s%d piece%s%s" % (
            (genre or "Unsorted") if genre is not None else "ALL", SEP, len(indices), "" if len(indices) == 1 else "s",
            (SEP + clock_text(seconds * 1000)) if seconds else ""))
        piece_list.clean()
        del piece_rows[:]
        st["marked"] = None
        for i in indices:
            e = files.entries[i]
            text = e["title"] + ("  -  " + e["composer"] if e["composer"] else "")
            b = row(piece_list, text, guarded(lambda i=i: files.play(i)),
                    clock_text(e["seconds"] * 1000) if e["seconds"] else None)
            piece_rows.append((i, b))
        mark_piece(scroll=True)

    def mark_piece(scroll=False):
        """Light the current piece's row and scroll it into view: when asked,
        and whenever the current piece changes (PREV, NEXT, the end of a piece)."""
        current = files.index if files.files else None
        if st["marked"] != current:
            scroll = True
        if scroll:
            st["marked"] = current
            for i, b in piece_rows:
                mark(b, i == current)
                if i == current and scroll:
                    b.scroll_to_view(False)

    def fill_library():
        genre_list.clean()
        del genre_rows[:]
        genre_rows.append((None, row(genre_list, "All", lambda: browse(None), "%d" % len(files.files))))
        for g, count in files.genres():
            genre_rows.append((g, row(genre_list, g or "Unsorted", lambda g=g: browse(g), "%d" % count)))
        browse(files.genre if files.genre in [g for g, _ in genre_rows] else None)

    def show_library(on):
        if on:
            fill_library()
        for c in (mix, chan, mast):
            if on:
                c.add_flag(lv.obj.FLAG.HIDDEN)
            else:
                c.remove_flag(lv.obj.FLAG.HIDDEN)
        if on:
            lib.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            lib.add_flag(lv.obj.FLAG.HIDDEN)

    # -- the SoundFont picker -------------------------------------------------------
    #
    # Over the whole face, once, before the sound starts, when there is more
    # than one bank: one row per bank, its name and size; tap one and the
    # face comes back with the sound on that bank. No switching after.

    PICK_H = H - 2 * M
    pick = card(M, M, CW, PICK_H)
    pick.add_flag(lv.obj.FLAG.HIDDEN)
    eyebrow(pick, "SOUNDFONT", PAD, 10)
    one_line(ui.label(pick, "Choose a SoundFont", ui.big, ui.WHITE), ui.big, CW - 2 * PAD).set_pos(PAD, 28)
    pick_meta = one_line(ui.label(pick, "", ui.small, ui.MUTED), ui.small, CW - 2 * PAD)
    pick_meta.set_pos(PAD, 60)
    pick_list = rows(PAD, NOW_H, CW - 2 * PAD, PICK_H - NOW_H - PAD, parent=pick)
    pick_rows = []  # (path, button)
    face = (now, mix, chan, mast)

    def show_picker(found):
        where = []
        for path, _ in found:
            folder = path.rsplit("/", 1)[0]
            if folder not in where:
                where.append(folder)
        pick_meta.set_text("%d banks in %s%stap one to start the sound" % (len(found), " and ".join(where), SEP))
        last = prefs.get("bank")
        for path, size in found:
            detail = banks.mb_text(size)
            if len(where) > 1:  # the same name may be on the card and on flash
                detail = path.rsplit("/", 1)[0] + SEP + detail
            b = row(pick_list, banks.name_of(path), lambda path=path: picked(path), detail)
            mark(b, path == last)
            pick_rows.append((path, b))
        for c in face:
            c.add_flag(lv.obj.FLAG.HIDDEN)
        pick.remove_flag(lv.obj.FLAG.HIDDEN)
        for path, b in pick_rows:
            if path == last:
                b.scroll_to_view(False)

    def picked(path):
        if st["bank"] is not None:
            return  # chosen already: one bank per session
        st["bank"] = prefs["bank"] = path
        pick_meta.set_text("Loading %s ..." % banks.name_of(path))
        for p, b in pick_rows:
            mark(b, p == path)

        def load(t):  # after a frame, so the row and the message are drawn before a big bank opens
            start_audio(path)
            pick.add_flag(lv.obj.FLAG.HIDDEN)
            for c in face:
                c.remove_flag(lv.obj.FLAG.HIDDEN)
            st["shown"] = None

        scope.after(UI_MS * 2, load)

    st["widgets"] = {"title": title_lbl, "meta": meta_lbl, "progress": progress, "prev": prev_btn, "play": play_btn,
                     "play_label": play_lbl, "next": next_btn, "loop": loop_btn, "library": library_btn,
                     "scope": scope_btn, "panic": panic_btn, "faders": faders, "strips": strips,
                     "genres": genre_rows, "pieces": piece_rows, "now": now, "mix": mix, "chan": chan,
                     "mast": mast, "lib": lib, "pick": pick, "pick_rows": pick_rows}

    def show_fader(name, value, text):
        s, val, _ = faders[name]
        if not s.is_dragged():
            s.set_value(value, False)
        val.set_text(text)

    def show():
        module = st["module"]
        ch = st["ch"]
        if module is None:
            shown = (ch, st["error"])
            if shown != st["shown"]:
                st["shown"] = shown
                ch_lbl.set_text("%02d" % (ch + 1))
                # The reason on two lines, its first sentence in the name's
                # place, so a folder named in it isn't cut off.
                head, _, rest = (st["error"] or "").partition(". ")
                name_lbl.set_text(head if rest else "---")
                part_lbl.set_height(2 * ui.small.get_line_height())
                part_lbl.set_text(rest if rest else (st["error"] or ""))
                show_fader("Master", prefs["volume"], "%d" % prefs["volume"])
                for c, strip in enumerate(strips):
                    strip[0].set_style_border_color(ui.ACCENT if c == ch else ui.BG, 0)
                    strip[3].set_style_text_color(ui.WHITE if c == ch else ui.MUTED, 0)
            return
        part = module.parts[ch]
        loaded = sum(1 for p in module.parts if p.inst is not None)
        programs = tuple((p.program, p.inst is not None) for p in module.parts)
        shown = (ch, part.bank_msb, part.bank_lsb, part.volume, part.pan, part.bend, module.reverb_level,
                 module.chorus_level, module.master_level, loaded, programs)
        if shown == st["shown"]:
            return
        st["shown"] = shown
        ch_lbl.set_text("%02d" % (ch + 1))
        name_lbl.set_text(module.name(ch))
        part_lbl.set_height(ui.small.get_line_height())
        facts = ["PROG %03d" % (part.program + 1)]
        if part.bank_msb or part.bank_lsb:
            facts.append("bank %d:%d" % (part.bank_msb, part.bank_lsb))
        if part.bend != gm.BEND_CENTER:
            facts.append("bend %+d" % (part.bend - gm.BEND_CENTER))
        if part.inst is None:
            facts.append("not loaded")
        part_lbl.set_text(SEP.join(facts))
        show_fader("Volume", part.volume, "%d" % part.volume)
        show_fader("Pan", part.pan, pan_text(part.pan))
        show_fader("Master", module.master_level, "%d" % module.master_level)
        show_fader("Reverb", module.reverb_level, "%d" % module.reverb_level)
        show_fader("Chorus", module.chorus_level, "%d" % module.chorus_level)
        bank_lbl.set_text("%s%s%d of 16 parts loaded" % (st["bank_name"], SEP, loaded))
        for c, strip in enumerate(strips):
            p = module.parts[c]
            strip[0].set_style_border_color(ui.ACCENT if c == ch else ui.BG, 0)
            strip[1].set_text("KIT" if p.drums else "%03d" % (p.program + 1))
            strip[1].set_style_text_color(ui.WHITE if p.inst is not None else ui.MUTED, 0)
            strip[3].set_style_text_color(ui.WHITE if c == ch else ui.MUTED, 0)

    def tick(t):
        module = st["module"]
        level, seen = st["level"], st["seen"]
        for ch, strip in enumerate(strips):
            if module is not None:
                part = module.parts[ch]
                if part.notes != seen[ch]:
                    seen[ch] = part.notes
                    level[ch] = max(level[ch], part.last[1] if part.last else 100)
            level[ch] = max(0, level[ch] - DECAY)
            if level[ch] != strip[2].get_value():
                strip[2].set_value(level[ch], False)
        show()
        show_player()


    def setup(t):
        if st["port"] is None:
            try:
                open_midi()
            except Exception as e:
                status.set_text("MIDI: %s" % (e,))
                setup_timer.deinit()
                return
        if st["merged"]:
            # The hub's devices come and go: keep the status line current.
            if watch.changed(st["port"]):
                st["midi"] = watch.text
                st["midi_told"] = False
                if watch.text:
                    status.set_text(watch.text)
        elif st["port"] is not None:
            status.set_text(st["midi"])
            setup_timer.deinit()
            return
        if not st["midi"] and not st["midi_told"] and ticks_diff(ticks_ms(), st["since"]) > 8000:
            st["midi_told"] = True
            status.set_text("no MIDI in: plug a keyboard in")

    def close():
        port = st["port"]
        st["port"] = None
        files.stop()  # its notes off reach the parts before the output goes
        stop_audio()
        if port is not None:
            port.close()
        if st["host"]:
            import usb.core

            usb.core.stop()
            st["host"] = None

    scope.on_close(close)
    found = find_banks()
    if found is not None and len(found) == 1:
        start_audio(found[0][0])
    elif found:
        show_picker(found)
    setup_timer = scope.every(SETUP_MS, setup)
    def service(t):
        """The port and the player on one timer, the port first: a key
        played never waits behind a file's backlog."""
        st["ticks"] += 1
        with gm.deferred(st["module"]):  # what this tick plays leaves together
            if not files.playing or st["ticks"] % FILE_MIDI_EVERY == 0:
                midi(t)
            serve_player()

    scope.every(MIDI_MS, service)
    scope.every(UI_MS, tick)
    show()
    show_player()
