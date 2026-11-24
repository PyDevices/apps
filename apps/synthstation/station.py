# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The app: an instrument's control panel, opened straight away.

The last instrument played opens at the start, created at the output's rate
and playing through the board's audio out. The drop-down in the panel's title
bar picks another, and so do a keyboard's Stop and Play buttons; Rewind and
Fast Forward step through the patches. While the panel is up, MIDI from every
keyboard the program can reach plays it, and the line under the name shows
what rendering it costs. Pads on MIDI channel 10 play a drum kit one sound per
pad, and everything else plays its General MIDI notes.

MIDI channel 1 always has an instrument. The small drop-down beside the
instrument's picks another channel to show, and an instrument chosen while it
shows becomes that channel's own. A channel without one plays channel 1's.
"""

import sys

import lvgl as lv

from . import midi as _midi
from . import pads as _pads
from .catalog import DEFAULT, RENAMED, catalog, find
from .meters import TICK_MS as METER_MS
from .meters import Meters
from .parts import CHANNELS, Mix, Part

#: How often the keyboards are read, and the instrument told to take in
#: what was played, in milliseconds.
MIDI_MS = 4
FILL_MS = 10
#: Every so many fills the app checks what the pump's render costs.
GOVERN_EVERY = 5
#: The share of a block's time the voices may take before the app caps them.
BUDGET = 0.85
#: Reads to skip after changing the cap, while the stolen voices ring out.
SETTLE = 4
#: How often the load readout and the MIDI device names are refreshed.
STATUS_MS = 500
#: How often the load is printed to the console while an instrument
#: plays, for a log of a bench session; 0 prints nothing.
LOG_MS = 5000
#: How long a pad's note sounds when there's no keyboard.
PAD_NOTE_MS = 300
#: The controllers that move the first twelve macros: what a Donner DMK-25
#: PRO's four knobs send across its banks A, B and C.
KNOB_CCS = (30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41)
#: The controllers that also move the first eight macros: Sound Controllers
#: 1 to 8 in the MIDI spec, which many keyboards' knobs send. Any other
#: controller goes to the instrument itself.
SOUND_CCS = (70, 71, 72, 73, 74, 75, 76, 77)
#: Channel volume on MIDI channel 1 is the output's volume: slider S1 on a
#: DMK-25 PRO. Its other sliders send it on other channels.
VOLUME_CC = 7
#: A DMK-25 PRO's Rewind and Fast Forward buttons step through the patches,
#: and its Stop and Play buttons through the instruments.
PATCH_CCS = {16: -1, 17: 1}
INSTRUMENT_CCS = {18: -1, 19: 1}
#: MIDI channel 10, counted from 0: where a keyboard's pads send.
PAD_CHANNEL = 9
#: How long to wait for a USB keyboard before opening the first instrument,
#: whose pads play notes if there isn't one.
KEYBOARD_WAIT_MS = 10000
KEYBOARD_POLL_MS = 100

BG = 0x141518
PANEL = 0x24262B
TEXT = 0xE8E6E1
DIM = 0x8A8D93
ACCENT = 0xD8402F
MENU_W = 260
MENU_H = 36
#: The channel drop-down under the instrument's, on an 800 wide panel.
CHANNEL_W = 86
CHANNEL_H = 28
CHANNEL_INSET = 28
#: On a compact panel it takes this much of the instrument menu's width, and
#: shows the channel's number alone.
CHANNEL_COMPACT_W = 40
#: The instrument menu's first entry on any channel but the first.
FOLLOW = "Same as Ch 1"
#: The share of the panel's width up to the patch card's right edge, and where
#: the card starts on an 800 wide panel: controlpanel's own layout, kept in step
#: by the check.
PATCH_SHARE = 0.34
PATCH_INSET = 24
#: The space either side of the meters, on an 800 wide panel.
METER_GAP = 6

#: The running app, for a console or a bench script: ``current.adapter``
#: is the adapter of the instrument on the panel, ``current.parts`` has every
#: channel's, and ``current.parser.feed()`` plays MIDI bytes. None while the
#: app isn't open.
current = None


def _style(obj, bg=None, radius=0):
    obj.set_style_border_width(0, 0)
    obj.set_style_radius(radius, 0)
    obj.set_style_pad_all(0, 0)
    if bg is not None:
        obj.set_style_bg_color(lv.color_hex(bg), 0)
        obj.set_style_bg_opa(lv.OPA.COVER, 0)


def _label(parent, text, color=TEXT, font=None):
    label = lv.label(parent)
    label.set_text(text)
    label.set_style_text_color(lv.color_hex(color), 0)
    if font is not None:
        label.set_style_text_font(font, 0)
    return label


def _display_x(panel):
    """Where the panel's display starts: its window sits in a bezel on the header."""
    return panel.display.obj.get_parent().get_parent().get_x()


class Station:
    """The whole app on *scope*. ``main(scope)`` makes one."""

    def __init__(self, scope):
        self.scope = scope
        self.root = scope.root
        self.width, self.height = scope.size
        self.prefs = scope.store()
        self.inputs = None
        self.output = None
        self.adapter = None
        self.panel = None
        self.name = None
        #: The instruments, by MIDI channel counted from 0, and the channel
        #: the panel shows.
        self.parts = {}
        self.channel = 0
        self._playing = ()
        self._mix = None
        self._restored = False
        self._short = False
        self.loading = False
        self._filling = False
        self._fills = 0
        self._played = 0
        self._idle_us = None
        self._settle = 0
        #: The voices every playing instrument may sound between them, or
        #: None until the governor first reads the instruments' own.
        self._cap = None
        self._fitted = 0
        self._raised = False
        self._read = None
        self._refused = None
        self._timers = []
        self._meters = None
        self._volume = None
        self._held = {}
        self._patch_step = 0
        self._instrument_step = 0
        self._shown = None
        self._since_log = 0
        self._names = None
        self._panel_midi = False
        #: Whether the channel list ends with the Bluetooth MIDI switch.
        self._ble_ok = _midi.ble_available()
        #: Whether the remembered Bluetooth switch has been acted on.
        self._ble_started = False
        try:
            import audioinstruments as ai

            from .audio import Output

            self.ai = ai
            self.output = Output(scope)
        except ImportError as e:
            self._missing("Synth Station needs the audio libraries: %s." % (e,))
            return
        self.catalog = catalog(ai)
        name = RENAMED.get(self.prefs.get("name"), self.prefs.get("name"))
        if find(self.catalog, name)[0] is None:
            name = DEFAULT
        self.prefs["name"] = name
        self.instruments = [item for _, items in self.catalog for item in items]
        self.parser = _midi.Parser(self)
        scope.on_close(self.close)
        global current
        current = self
        self._build_splash()
        self._build_menu()
        self._status_timer = scope.every(STATUS_MS, self._status_tick)
        # Opening the keyboards can take a moment (a USB host starting), so
        # it happens once the splash is on the screen.
        scope.after(50, self._open_midi)
        follow = getattr(scope, "follow", None)
        if follow is not None and sys.platform in _midi.DESKTOPS:
            follow("midi.in", self._midi_moved)

    # ---- the splash and the menu -----------------------------------------------

    def _missing(self, text):
        _style(self.root, BG)
        label = _label(self.root, text)
        label.set_width(self.width - 40)
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        label.center()

    def _build_splash(self):
        w, h = self.width, self.height
        _style(self.root, BG)
        splash = lv.obj(self.root)
        _style(splash, BG)
        splash.set_size(w, h)
        splash.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.splash = splash
        title = _label(splash, "SYNTH STATION", TEXT, lv.font_montserrat_24)
        title.set_pos(16, 12)
        self.midi_label = _label(splash, "MIDI: looking...", DIM, lv.font_montserrat_16)
        self.midi_label.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.midi_label.set_width(w - 32)
        self.midi_label.set_pos(16, 46)
        self.notice = _label(splash, "", ACCENT, lv.font_montserrat_16)
        self.notice.set_pos(16, h - 26)
        self.notice.set_width(w - 32)
        self.notice.set_long_mode(lv.label.LONG_MODE.DOTS)

    def _build_menu(self):
        menu = lv.dropdown(self.root)
        menu.set_options("\n".join(display for _, display in self.instruments))
        menu.set_style_text_font(lv.font_montserrat_16, 0)
        menu.set_style_text_color(lv.color_hex(TEXT), 0)
        menu.set_style_bg_color(lv.color_hex(PANEL), 0)
        menu.set_style_border_width(0, 0)
        menu.get_list().set_style_text_font(lv.font_montserrat_16, 0)
        menu.add_event_cb(self._menu_changed, lv.EVENT.VALUE_CHANGED, None)
        self.menu = menu
        font = getattr(lv, "font_montserrat_14", lv.font_montserrat_16)
        channels = lv.dropdown(self.root)
        channels.set_style_text_font(font, 0)
        channels.set_style_text_color(lv.color_hex(TEXT), 0)
        channels.set_style_bg_color(lv.color_hex(PANEL), 0)
        channels.set_style_border_width(0, 0)
        channels.set_style_pad_ver(4, 0)
        channels.get_list().set_style_text_font(font, 0)
        channels.add_event_cb(self._channel_changed, lv.EVENT.VALUE_CHANGED, None)
        self.channels = channels
        self._fill_menus()
        self._place_menu()

    def _fill_menus(self):
        """What both drop-downs list and show, for the channel on the panel."""
        channel = self.channel
        names = [display for _, display in self.instruments]
        if channel:
            names.insert(0, FOLLOW)
        self.menu.set_options("\n".join(names))
        own = self.parts.get(channel)
        if own is not None:
            self._show_in_menu(own.name)
        elif not channel:
            self._show_in_menu(self.prefs["name"])
        self._fill_channels()

    def _fill_channels(self):
        """The channels, with a star on each that has an instrument of its own."""
        text = "%d%s" if self._short else "Ch %d%s"
        star = "*" if self._short else " *"
        options = [text % (c + 1, star if c and c in self.parts else "") for c in range(CHANNELS)]
        if self._ble_ok:
            # Last, so it's one more step for an encoder and one tap for a finger.
            on = self.inputs is not None and self.inputs.ble is not None
            options.append(("BT on" if on else "BT off") if self._short else
                           ("Bluetooth on" if on else "Bluetooth off"))
        self.channels.set_options("\n".join(options))
        self.channels.set_selected(self.channel)

    def _place_menu(self):
        """On the panel's name plate, or under the splash's title."""
        menu = self.menu
        channels = self.channels
        panel = self.panel
        short = self._short
        if panel is None:
            menu.set_size(MENU_W, MENU_H)
            menu.set_pos(16, 76)
            channels.set_size(CHANNEL_W, MENU_H)
            channels.set_pos(16 + MENU_W + 8, 76)
        else:
            plate = panel.title
            if plate.has_flag(lv.obj.FLAG.HIDDEN):  # a compact panel has no plate
                # The two share the room the menu had: the header has no more.
                short = True
                width = MENU_W // 2 - CHANNEL_COMPACT_W - 2
                menu.set_size(width, MENU_H)
                menu.set_pos(2, 2)
                channels.set_size(CHANNEL_COMPACT_W, MENU_H)
                channels.set_pos(2 + width + 2, 2)
            else:
                plate.add_flag(lv.obj.FLAG.HIDDEN)
                # The patch card's width, unless a bigger display leaves the
                # meters no room beside that.
                panel.root.update_layout()
                s = panel._s
                x = s(PATCH_INSET)
                room = _display_x(panel) - 2 * s(METER_GAP) - Meters.width(s)
                right = min(int(panel.width * PATCH_SHARE), room)
                y = max(2, plate.get_y() - 8)
                menu.set_size(max(right - x, MENU_W // 2), MENU_H)
                menu.set_pos(x, y)
                # Under it, right of the engine's light.
                below = y + MENU_H + 2
                channels.set_size(s(CHANNEL_W), min(CHANNEL_H, panel.header.get_height() - below - 2))
                channels.set_pos(x + s(CHANNEL_INSET), below)
        if short and not self._short:
            # Once: a display that's compact stays compact.
            self._short = True
            channels.set_symbol(None)
            # Their lists stay wide enough to read.
            menu.get_list().set_style_min_width(MENU_W // 2, 0)
            channels.get_list().set_style_min_width(CHANNEL_W, 0)
            self._fill_channels()
        menu.move_foreground()
        channels.move_foreground()

    def _build_meters(self):
        """In the header between the menu and the display, if they fit."""
        panel = self.panel
        s = panel._s
        menu = self.menu
        menu.update_layout()
        channels = self.channels
        channels.update_layout()
        left = max(menu.get_x() + menu.get_width(), channels.get_x() + channels.get_width()) + s(METER_GAP)
        room = _display_x(panel) - s(METER_GAP) - left
        width = Meters.width(s)
        if room >= width:
            pad = s(6)
            self._meters = Meters(panel.header, left + (room - width) // 2, pad, panel.header.get_height() - 2 * pad, s)

    def _meter_tick(self, _timer=None):
        left, right = self.output.levels()
        self._meters.tick(left, right)

    def _menu_changed(self, _event):
        at = self.menu.get_selected()
        if self.channel:
            if at == 0:
                self.follow()
                return
            at -= 1
        self.choose(self.instruments[at][0])

    def _channel_changed(self, _event):
        at = self.channels.get_selected()
        if at == CHANNELS:
            self.set_ble(self.inputs is None or self.inputs.ble is None)
            return
        self.show(at)

    def set_ble(self, on):
        """Turn Bluetooth MIDI on or off, and remember it for the next time
        the app opens. A failure to start is said where the MIDI status is."""
        inputs = self.inputs
        if inputs is None:
            return
        self.prefs["ble"] = bool(on)
        self._ble_started = True
        try:
            inputs.set_ble(on, self.parser)
        except Exception as e:  # said on the status line by ble_text()
            print("synthstation: Bluetooth MIDI didn't start:", e)
            self.prefs["ble"] = False
        self._fill_channels()
        self._shown = None
        self._status_tick()

    def _show_in_menu(self, name):
        for i, (module, _) in enumerate(self.instruments):
            if module == name:
                self.menu.set_selected(i + 1 if self.channel else i)
                return

    # ---- MIDI ------------------------------------------------------------------

    def _open_midi(self, _timer=None):
        self.inputs = _midi.Inputs().open()
        self._show_midi()
        self._first_instrument(KEYBOARD_WAIT_MS)

    def _midi_moved(self, endpoints):
        """Other MIDI inputs were chosen for the computer: read those, or
        every input again when none is."""
        if self.inputs is None:
            return  # not open yet, or reopening below
        self.inputs.close()
        self.inputs = None
        if any(ep.error for ep in endpoints):
            # This app held a port the choice wanted, and a port has one
            # reader at a time: now it's let go, ask for the choice again.
            import endpointkit

            endpointkit.select("midi.in", endpointkit.chosen("midi.in"))
        self.inputs = _midi.Inputs().open()
        self._show_midi()

    def _first_instrument(self, wait_ms):
        """Open the last instrument played, once a keyboard is seen or the wait is over."""
        if self.panel is not None or self.loading or self.inputs is None:
            return
        # A keyboard shows up as the port is read, and nothing else reads it yet.
        self.inputs.poll(self.parser)
        if wait_ms > 0 and self.inputs.kind == "usb" and not self.has_midi():
            self.scope.after(KEYBOARD_POLL_MS, lambda t: self._first_instrument(wait_ms - KEYBOARD_POLL_MS))
            return
        self._show_midi()
        self.pick(self.prefs["name"])

    def _midi_text(self):
        text = self._inputs_text()
        ble = self.inputs.ble_text() if self.inputs is not None else None
        if ble is not None and ble != "Bluetooth":  # while connected, it's one of the names
            text += " " + ble + "."
        return text

    def _inputs_text(self):
        inputs = self.inputs
        if inputs is None:
            return "MIDI: looking..."
        if inputs.kind is None and inputs.names():
            return "MIDI: " + " + ".join(inputs.names())
        if inputs.kind is None:
            if inputs.why == _midi.NO_INPUT:
                return "No MIDI keyboard: the pads play notes."
            return "No MIDI (%s): the pads play notes." % (inputs.why,)
        names = inputs.names()
        if not names:
            if inputs.kind == "usb":
                return "No MIDI keyboard: plug one into the USB host port, or play the pads."
            if inputs.kind == "web" and inputs.ports[0].why:
                return "No MIDI: the browser refused it. The pads play notes."
            return "No MIDI keyboard: the pads play notes."
        return "MIDI: " + " + ".join(names)

    def has_midi(self):
        inputs = self.inputs
        return inputs is not None and bool(inputs.names())

    def _show_midi(self):
        text = self._midi_text()
        if text != self._names:
            self._names = text
            self.midi_label.set_text(text)
            self.midi_label.set_style_text_color(lv.color_hex(TEXT if self.has_midi() else ACCENT), 0)

    # The parser's sink: a keyboard's messages land here.

    def _part(self, channel):
        """The part MIDI channel *channel* plays: its own, or channel 1's."""
        parts = self.parts
        return parts.get(channel) or parts.get(0)

    def note_on(self, note, velocity, channel=0):
        if self._meters is not None:
            self._meters.strike(velocity)
        part = self._part(channel)
        if part is None or self.loading:
            return
        if channel == PAD_CHANNEL and part.pad_notes is not None:
            pad = note - _pads.FIRST_PAD
            if not 0 <= pad < len(part.pad_notes):
                return  # a pad past the kit's last sound is silent
            # Kept for the release: a SoundFont's next kit lays out differently.
            part.struck[note] = note = part.pad_notes[pad]
        if self._mix is not None:
            self._mix.wake(part.adapter.instrument)
        part.adapter.note_on(note, velocity)
        self._played = 2

    def note_off(self, note, channel=0):
        part = self._part(channel)
        if part is None or self.loading:
            return
        if channel == PAD_CHANNEL and part.pad_notes is not None:
            note = part.struck.pop(note, None)
            if note is None:
                return
        part.adapter.note_off(note)

    def control(self, controller, value, channel=0):
        part = self._part(channel)
        if part is None or self.loading:
            return
        adapter = part.adapter
        if controller == VOLUME_CC and channel == 0:
            # Like the knobs: the codec is across I2C, so only the last value.
            self._volume = value
            return
        if controller in PATCH_CCS or controller in INSTRUMENT_CCS:
            # Once per press, whatever a button or a slider sends after it.
            pressed = value >= 64
            if pressed and not self._held.get(controller):
                if controller in PATCH_CCS:
                    self._patch_step += PATCH_CCS[controller]
                else:
                    self._instrument_step += INSTRUMENT_CCS[controller]
            self._held[controller] = pressed
            return
        if controller in KNOB_CCS:
            knob = KNOB_CCS.index(controller)
        elif controller in SOUND_CCS:
            knob = SOUND_CCS.index(controller)
        else:
            knob = -1
        if 0 <= knob < adapter.macro_count:
            # Only each knob's last value, applied once everything waiting
            # has been read: a macro change can take milliseconds, and a
            # fast sweep sends a hundred values a second.
            part.knobs[knob] = value
        else:
            adapter.instrument.control_change(controller, value)

    def bend(self, value, channel=0):
        part = self._part(channel)
        if part is not None and not self.loading:
            part.adapter.instrument.pitch_bend(value)

    def program(self, number, channel=0):
        part = self._part(channel)
        if part is not None:
            part.program = number

    def _lay_out_pads(self, part):
        """Read the pads' notes once per patch, as asking a SoundFont takes a moment."""
        adapter = part.adapter
        part.pad_patch = adapter.patch_index
        part.pad_notes = _pads.pad_notes(part.name, adapter.instrument)

    def _midi_tick(self, _timer=None):
        inputs = self.inputs
        if inputs is None or self.adapter is None or self.loading:
            return
        playing = self._playing
        for part in playing:
            if part.adapter.patch_index != part.pad_patch:
                self._lay_out_pads(part)
        inputs.poll(self.parser)
        for part in playing:
            adapter = part.adapter
            if part.knobs:
                knobs = part.knobs
                part.knobs = {}
                for knob, value in knobs.items():
                    adapter.note_cc(knob, value)
            if part.program is not None:
                number = part.program
                part.program = None
                # Only a program the instrument has: the others would be silence.
                if number in (adapter.instrument.patches or {}):
                    adapter.note_program(number)
        if self._volume is not None:
            self.output.set_volume(self._volume * 100 // 127)
            self._volume = None
        if self._patch_step:
            step = self._patch_step
            self._patch_step = 0
            self._step_patch(step)
        if self._instrument_step:
            step = self._instrument_step
            self._instrument_step = 0
            # Not from inside this timer: the change stops it.
            self.scope.after(1, lambda t: self._step_instrument(step))

    def _step_patch(self, step):
        adapter = self.adapter
        keys = sorted(adapter.instrument.patches or {})
        if len(keys) > 1:
            at = keys.index(adapter.patch_index) if adapter.patch_index in keys else 0
            adapter.note_program(keys[(at + step) % len(keys)])

    def _step_instrument(self, step):
        names = [module for module, _ in self.instruments]
        at = names.index(self.name) if self.name in names else 0
        self.choose(names[(at + step) % len(names)])

    # ---- the instrument ------------------------------------------------------

    def choose(self, name):
        """Give the channel on the panel instrument *name*, from the menu or
        a keyboard's buttons. On channel 1 that changes what every channel
        without an instrument of its own plays."""
        own = self.parts.get(self.channel)
        if self.loading or (own is not None and name == own.name and self.panel is not None):
            return
        self._close_panel()
        self._silence()
        self._drop(self.channel)
        self._remember()
        self.splash.remove_flag(lv.obj.FLAG.HIDDEN)
        self._place_menu()
        self.pick(name)

    def show(self, channel):
        """Put MIDI channel *channel*, 0 to 15, on the panel: its own
        instrument, or channel 1's while it has none. The sound carries on."""
        if self.loading or not 0 <= channel < CHANNELS:
            return
        self._close_panel()
        self.channel = channel
        self._fill_menus()
        if 0 in self.parts and (self.output.instrument is not None or self._play()):
            self._open_panel()

    def follow(self):
        """Take away the instrument of the channel on the panel, so that it
        plays channel 1's again."""
        channel = self.channel
        if self.loading or not channel or channel not in self.parts:
            return
        self._close_panel()
        self._silence()
        self._drop(channel)
        self._remember()
        self._fill_menus()
        if 0 in self.parts and self._play():
            self._open_panel()

    def _reopen(self):
        self._close_panel()
        self._open_panel()

    def _silence(self):
        """Stop the output and let go of the mix, before a part changes."""
        self.output.stop()
        mix = self._mix
        self._mix = None
        if mix is not None:
            mix.deinit()

    def _drop(self, channel):
        """Deinitialise a channel's own instrument. Nothing may be pulling it."""
        part = self.parts.pop(channel, None)
        self._playing = tuple(self.parts[c] for c in sorted(self.parts))
        if part is not None:
            part.forget()
            part.adapter.instrument.deinit()

    def _remember(self):
        """Keep which channels have which instruments for the next time the
        app opens, once the ones kept last time are back."""
        if self._restored:
            self.prefs["parts"] = {str(c + 1): part.name for c, part in self.parts.items() if c}

    def _patch_key(self, channel, name):
        return name if not channel else "%d:%s" % (channel + 1, name)

    def _play(self):
        """Send every part to the output: one as it is, several through a mix.

        Returns False, with the reason on the splash, when the output won't start.
        """
        self._silence()
        playing = self._playing = tuple(self.parts[c] for c in sorted(self.parts))
        output = self.output
        try:
            if len(playing) == 1:
                output.start(playing[0].adapter.instrument)
            else:
                self._mix = Mix([part.adapter.instrument for part in playing], output.rate, output.channels)
                output.start(self._mix)
        except Exception as e:
            self._silence()
            self.notice.set_text("No sound out: %s" % (e,))
            return False
        return True

    def pick(self, name):
        """Open instrument *name* on the panel."""
        if self.loading or self.panel is not None:
            return
        self.loading = True
        self._show_in_menu(name)
        self.notice.set_text("Loading %s..." % find(self.catalog, name)[1])
        # Give the screen a frame to show that before the work starts.
        self.scope.after(30, lambda t: self._load(name))

    def _create(self, name):
        import audioinstruments.panel

        adapter = audioinstruments.panel.create(name, self.output.rate, channel_count=self.output.channels)
        inst = adapter.instrument
        # Build the voices' tables now, not on the first key.
        note_map = getattr(self.ai.load(name), "NOTE_MAP", None)
        for note in ([n for n, _ in note_map] if note_map else (60,)):
            inst.note_on(note, 1)
        inst.fill()
        inst.all_notes_off()
        inst.fill()
        return adapter

    def _add(self, channel, name):
        """Create instrument *name* as *channel*'s part, on the patch it was left on."""
        adapter = self._create(name)
        inst = adapter.instrument
        patch = self.prefs.get("patches", {}).get(self._patch_key(channel, name))
        if patch and patch in (inst.patches or {}):
            adapter.set_patch(patch)
        # RELOAD builds the instrument again. Nothing is played or filled
        # while it does; then the output takes the new one and lets go of
        # the old, which is deinitialised once nothing pulls it.
        reload = adapter.request_reload

        def request_reload():
            self.loading = True
            try:
                return reload()
            finally:
                self.loading = False

        adapter.request_reload = request_reload
        adapter.on_reload(self._reloaded)
        part = self.parts[channel] = Part(name, adapter)
        # A drum machine's voices are its sounds, one circuit each: a cap would
        # silence the sounds past it, so it's never capped.
        part.most = 1 if name in _pads.KIT_PADS else inst.voices
        self._lay_out_pads(part)
        return part

    def _restore(self):
        """Bring back the other channels' instruments from the last time the app was open."""
        for key, name in sorted(self.prefs.get("parts", {}).items()):
            channel = int(key) - 1
            name = RENAMED.get(name, name)
            if not 0 < channel < CHANNELS or channel in self.parts or find(self.catalog, name)[0] is None:
                continue
            try:
                self._add(channel, name)
            except Exception as e:
                print("synthstation: channel %s's %s didn't load: %s" % (key, name, e))

    def _load(self, name):
        display = find(self.catalog, name)[1]
        channel = self.channel
        try:
            self._add(channel, name)
        except Exception as e:
            self.notice.set_text("%s didn't load: %s" % (display, e))
            self.loading = False
            return
        if not channel:
            self.prefs["name"] = name
        if not self._restored and 0 in self.parts:
            self._restored = True
            self._restore()
        self._remember()
        if 0 not in self.parts:
            self.notice.set_text("Choose an instrument for Ch 1 first.")
            self.loading = False
            return
        if not self._play():
            self.loading = False
            return
        self._fill_menus()
        self._open_panel()
        self.loading = False
        if self._ble_ok and self.prefs.get("ble") and not self._ble_started:
            # After the sound: on a board short of internal RAM, Bluetooth
            # failing to start is said on the status line, and the
            # instrument still plays.
            self._ble_started = True
            self.set_ble(True)
        self._status_tick()

    def _open_panel(self):
        """Build the panel for the channel being shown. Its part is already playing."""
        part = self._part(self.channel)
        adapter = part.adapter
        name = part.name
        self.name = name
        self._idle_us = None
        self._settle = 0
        self._cap = None
        self._fitted = 0
        self._raised = False
        self._read = None
        self._refused = None
        self.adapter = adapter
        self.notice.set_text("")
        self.splash.add_flag(lv.obj.FLAG.HIDDEN)
        shown = adapter
        if not self.has_midi():
            shown = _pads.NotePads(adapter, _pads.notes_for(self.ai.load(name)), self._pad_note)
        self._panel_midi = self.has_midi()
        self.panel = self._build_panel(shown, find(self.catalog, name)[1])
        self._place_menu()
        self._build_meters()
        self._shown = None
        self._since_log = 0
        self._timers = [
            self.scope.every(MIDI_MS, self._midi_tick),
            self.scope.every(FILL_MS, self._fill),
        ]
        if self._meters is not None:
            self._timers.append(self.scope.every(METER_MS, self._meter_tick))

    def _reloaded(self, new, old):
        # Every adapter already holds its newest instrument.
        self._play()
        old.deinit()

    def _build_panel(self, adapter, title):
        import sys

        import audioinstruments.panel_view as panel_view

        two_wheels = False
        if getattr(sys, "platform", "") in ("linux", "darwin", "win32"):
            # Only the display_driver that opened this window: importing it
            # here would open another.
            driver = sys.modules.get("display_driver")
            if driver is not None and hasattr(driver, "set_wheel_mapping"):
                driver.set_wheel_mapping(adjust_axis="h", adjust_sign=1, navigate=True, navigate_sign=-1)
                two_wheels = True
                self._wheels = driver
        return panel_view.build(
            adapter, screen=self.root, title=title, subtitle=None if self.has_midi() else "No MIDI",
            two_wheels=two_wheels)

    def _pad_note(self, note):
        adapter = self.adapter
        if adapter is None:
            return
        if self._mix is not None:
            self._mix.wake(adapter.instrument)
        adapter.note_on(note, 100)
        self.scope.after(PAD_NOTE_MS, lambda t: self.adapter is adapter and adapter.note_off(note))

    def _fill(self, _timer=None):
        """Let the instrument take in what was played. A tick can land
        between the bytecodes of whatever the app is doing, so one that
        arrives inside another fill, or while the instrument is being
        swapped, is dropped."""
        adapter = self.adapter
        if adapter is None or self._filling or self.loading:
            return
        playing = self._playing
        self._filling = True
        try:
            for part in playing:
                part.adapter.instrument.fill()
            if self._mix is not None:
                self._mix.tick(FILL_MS)
        finally:
            self._filling = False
        self._fills += 1
        # A new note is read again once its strike has rendered, rather than
        # waiting for the next scheduled look.
        if self._played:
            self._played -= 1
        if self._played == 1 or self._fills % GOVERN_EVERY == 0:
            self._govern()

    def _govern(self):
        """Cap the voices at what the pump can render in time.

        The pump renders on a core of its own, so a chord the core can't
        keep up with doesn't slow the app, it starves the speaker: the audio
        runs behind for as long as the keys are held. Each sounding voice
        costs about the same, so from the cost of the blocks just rendered
        this works out how many voices fit in `BUDGET` of a block's time.
        That count is one cap for every instrument playing, and `_share`
        hands it out between them. The extra notes steal instead of
        everything going quiet. The cap is set from the first sounding
        voice, before a chord needs it. That voice also wakes whatever the
        voices share, so it reads dearer than the voices after it: with
        every allowed voice sounding and room for one more, the cap goes up
        one, and a count that has fit stays allowed unless the blocks go
        over budget. A cap it just raised stays up until a chord has used it
        or the blocks go over budget: the keys already held can't take the
        new voice, so their reads say nothing about it. A count that went
        over budget isn't tried again until the keys are up, because each
        try steals a note.

        A drum machine's sounds are outside the cap, and what they cost
        counts against the other instruments' voices.
        """
        output = self.output
        cost = output.pull_us()
        parts = [part for part in self._playing if part.most > 1]
        if cost is None or not parts:
            return
        if self._settle:
            # The blocks right after a cap still carry the voices it stole.
            self._settle -= 1
            return
        counts = [part.adapter.instrument.voice_pool.sounding() for part in parts]
        sounding = sum(counts)
        voices = self._cap
        if voices is None:
            voices = self._cap = sum(part.adapter.instrument.voices for part in parts)
        if sounding == 0:
            self._idle_us = cost if self._idle_us is None else min(self._idle_us, cost)
            self._refused = None
            self._share(parts, counts)
            return
        idle = self._idle_us or 0
        budget = BUDGET * output.block_us()
        per_voice = (cost - idle) / sounding
        if per_voice <= 0:
            self._share(parts, counts)
            return
        # Every part that's sounding keeps a voice: the cap thins chords, it
        # never silences a keyboard.
        fit = max(len(counts) - counts.count(0), int((budget - idle) / per_voice + 0.5))
        # Just after a key the mean still holds blocks from before it.
        settled = self._played == 0
        if cost <= budget:
            if settled and sounding > self._fitted:
                self._fitted = sounding
            fit = max(fit, self._fitted)
        if fit < voices and (cost > budget or sounding >= voices or not self._raised):
            if cost > budget:
                self._refused = sounding
            self._cap = fit
            self._raised = False
            self._settle = SETTLE
        elif (
            settled
            and sounding >= voices
            and voices < sum(part.most for part in parts)
            and (self._refused is None or voices + 1 < self._refused)
        ):
            step = per_voice
            read = self._read
            if read is not None and read[0] < sounding and cost > read[1]:
                step = (cost - read[1]) / (sounding - read[0])
            if cost + step <= budget:
                self._cap = voices + 1
                self._raised = True
                self._settle = SETTLE
        if settled:
            self._read = (sounding, cost)
        if self._share(parts, counts):
            self._settle = SETTLE

    def _share(self, parts, counts):
        """Hand the cap out between *parts*, sounding *counts* voices now.

        The cap counts the voices of the parts that are sounding. Each gets
        what it's sounding and one spare, so its next key sounds without
        stealing and a growing chord shows in the next read. Over the cap,
        the spares go first, then voices from whichever is sounding the
        most: the biggest chord loses a note before a smaller part does,
        and none goes below one voice. Under it, the room left goes to the
        part with the fewest. A quiet part keeps an even split of the cap
        for its next chord, which the read after it trims if it has to.
        Returns True when that stole voices.
        """
        cap = self._cap
        even = max(1, cap // len(parts))
        shares = []
        total = 0
        for part, count in zip(parts, counts):
            share = min(part.most, count + 1 if count else even)
            shares.append(share)
            if count:
                total += share
        while total > cap:
            pick = best = None
            for i, share in enumerate(shares):
                if counts[i] and share > 1:
                    # A spare before a sounding voice, then the biggest share.
                    key = (share > counts[i], share)
                    if best is None or key > best:
                        pick, best = i, key
            if pick is None:
                break
            shares[pick] -= 1
            total -= 1
        while total < cap:
            pick = None
            for i, share in enumerate(shares):
                if counts[i] and share < parts[i].most and (pick is None or share < shares[pick]):
                    pick = i
            if pick is None:
                break
            shares[pick] += 1
            total += 1
        stole = False
        for part, share, count in zip(parts, shares, counts):
            inst = part.adapter.instrument
            if inst.voices != share:
                inst.voices = share
            if share < count:
                stole = True
        return stole

    def _close_panel(self):
        """Take the panel down. The instruments stay, and keep playing."""
        for timer in self._timers:
            timer.deinit()
        self._timers = []
        self._meters = None
        self.adapter = None
        patches = self.prefs.setdefault("patches", {})
        for channel, part in self.parts.items():
            patches[self._patch_key(channel, part.name)] = part.adapter.patch_index
            part.forget()
        panel = self.panel
        self.panel = None
        if panel is not None:
            panel.delete()
        driver = getattr(self, "_wheels", None)
        if driver is not None:
            self._wheels = None
            driver.set_wheel_mapping(adjust_axis="v", adjust_sign=1, navigate=False, navigate_sign=1)

    # ---- the readout -----------------------------------------------------------

    def _status_text(self):
        """The display's second line: render load and underruns."""
        load, worst, underruns = self.output.load()
        text = "LOAD --" if load is None else "LOAD %d%% U%d" % (load, underruns)
        inputs = self.inputs
        if inputs is not None and inputs.ble is not None:
            text += " BT" if inputs.ble.state == "connected" else " BT..."
        elif inputs is not None and inputs.ble_why:
            text += " BT!"
        return text

    def _status_tick(self, _timer=None):
        if self.inputs is not None and self.panel is None:
            self._show_midi()
        panel = self.panel
        if panel is None or self.loading:
            return
        if self.has_midi() and not self._panel_midi:
            # A keyboard arrived: its panel has patches where the note pads were.
            self._reopen()
            return
        text = self._status_text()
        if text != self._shown:
            self._shown = text
            panel.set_status(text)
        if LOG_MS:
            self._since_log += STATUS_MS
            if self._since_log >= LOG_MS:
                self._since_log = 0
                output = self.output
                print("synthstation: %s load %s%% peak %s%% underruns %d starved %d ms" % (
                    self.name, output.load_pct, output.worst_pct, output.underruns, output.starved_ms()))

    def close(self):
        global current
        if current is self:
            current = None
        self._close_panel()
        if self.output is not None:
            # Before the instruments go, so nothing pulls a deinitialised one.
            self._silence()
            for channel in list(self.parts):
                self._drop(channel)
            self.output.close()
        if self.inputs is not None:
            self.inputs.close()
            self.inputs = None
