# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The app: an instrument's control panel, opened straight away.

The last instrument played opens at the start, created at the output's rate
and playing through the board's audio out. The drop-down in the panel's title
bar picks another, and so do a keyboard's Stop and Play buttons; Rewind and
Fast Forward step through the patches. While the panel is up, MIDI from every
keyboard the program can reach plays it, and the line under the name shows
what rendering it costs.
"""

import lvgl as lv

from . import midi as _midi
from .catalog import DEFAULT, RENAMED, catalog, find

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
#: How long to wait for a keyboard before opening the first instrument, whose
#: pads play notes if there isn't one.
KEYBOARD_WAIT_MS = 3000
KEYBOARD_POLL_MS = 100

BG = 0x141518
PANEL = 0x24262B
TEXT = 0xE8E6E1
DIM = 0x8A8D93
ACCENT = 0xD8402F
MENU_W = 260
MENU_H = 36

#: The running app, for a console or a bench script: ``current.adapter``
#: is the instrument's adapter, ``current.parser.feed()`` plays MIDI bytes.
#: None while the app isn't open.
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
        self.loading = False
        self._filling = False
        self._fills = 0
        self._played = 0
        self._idle_us = None
        self._settle = 0
        self._most_voices = 0
        self._fitted = 0
        self._raised = False
        self._read = None
        self._refused = None
        self._timers = []
        self._knobs = {}
        self._volume = None
        self._program = None
        self._held = {}
        self._patch_step = 0
        self._instrument_step = 0
        self._shown = None
        self._since_log = 0
        self._names = None
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
        self._place_menu()

    def _place_menu(self):
        """On the panel's name plate, or under the splash's title."""
        menu = self.menu
        panel = self.panel
        if panel is None:
            menu.set_size(MENU_W, MENU_H)
            menu.set_pos(16, 76)
        else:
            plate = panel.title
            if plate.has_flag(lv.obj.FLAG.HIDDEN):  # a compact panel has no plate
                menu.set_size(MENU_W // 2, MENU_H)
                menu.set_pos(2, 2)
            else:
                plate.add_flag(lv.obj.FLAG.HIDDEN)
                menu.set_size(max(plate.get_width(), MENU_W // 2), MENU_H)
                menu.set_pos(plate.get_x(), max(2, plate.get_y() - 8))
        menu.move_foreground()

    def _menu_changed(self, _event):
        self.choose(self.instruments[self.menu.get_selected()][0])

    def _show_in_menu(self, name):
        for i, (module, _) in enumerate(self.instruments):
            if module == name:
                self.menu.set_selected(i)
                return

    # ---- MIDI ------------------------------------------------------------------

    def _open_midi(self, _timer=None):
        self.inputs = _midi.Inputs().open()
        self._show_midi()
        self._first_instrument(KEYBOARD_WAIT_MS)

    def _first_instrument(self, wait_ms):
        """Open the last instrument played, once a keyboard is seen or the wait is over."""
        if self.panel is not None or self.loading or self.inputs is None:
            return
        if wait_ms > 0 and self.inputs.kind is not None and not self.has_midi():
            self.scope.after(KEYBOARD_POLL_MS, lambda t: self._first_instrument(wait_ms - KEYBOARD_POLL_MS))
            return
        self._show_midi()
        self.pick(self.prefs["name"])

    def _midi_text(self):
        inputs = self.inputs
        if inputs is None:
            return "MIDI: looking..."
        if inputs.kind is None:
            if inputs.why == _midi.NO_INPUT:
                return "No MIDI keyboard: the pads play notes."
            return "No MIDI (%s): the pads play notes." % (inputs.why,)
        names = inputs.names()
        if not names:
            if inputs.kind == "usb":
                return "No MIDI keyboard: plug one into the USB host port, or play the pads."
            return "No MIDI keyboard: the pads play notes."
        return "MIDI: " + " + ".join(names)

    def has_midi(self):
        inputs = self.inputs
        return inputs is not None and inputs.kind is not None and bool(inputs.names())

    def _show_midi(self):
        text = self._midi_text()
        if text != self._names:
            self._names = text
            self.midi_label.set_text(text)
            self.midi_label.set_style_text_color(lv.color_hex(TEXT if self.has_midi() else ACCENT), 0)

    # The parser's sink: a keyboard's messages land here.

    def note_on(self, note, velocity):
        adapter = self.adapter
        if adapter is not None and not self.loading:
            adapter.note_on(note, velocity)
            self._played = 2

    def note_off(self, note):
        adapter = self.adapter
        if adapter is not None and not self.loading:
            adapter.note_off(note)

    def control(self, controller, value, channel=0):
        adapter = self.adapter
        if adapter is None or self.loading:
            return
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
            self._knobs[knob] = value
        else:
            adapter.instrument.control_change(controller, value)

    def bend(self, value):
        adapter = self.adapter
        if adapter is not None and not self.loading:
            adapter.instrument.pitch_bend(value)

    def program(self, number):
        self._program = number

    def _midi_tick(self, _timer=None):
        inputs = self.inputs
        if inputs is None or self.adapter is None or self.loading:
            return
        inputs.poll(self.parser)
        adapter = self.adapter
        if self._knobs:
            knobs = self._knobs
            self._knobs = {}
            for knob, value in knobs.items():
                adapter.note_cc(knob, value)
        if self._volume is not None:
            self.output.set_volume(self._volume * 100 // 127)
            self._volume = None
        if self._program is not None:
            number = self._program
            self._program = None
            # Only a program the instrument has: the others would be silence.
            if number in (adapter.instrument.patches or {}):
                adapter.note_program(number)
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
        """Change to instrument *name*, from the menu or a keyboard's buttons."""
        if self.loading or (name == self.name and self.panel is not None):
            return
        self._stop_instrument()
        self.splash.remove_flag(lv.obj.FLAG.HIDDEN)
        self._place_menu()
        self.pick(name)

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

    def _load(self, name):
        display = find(self.catalog, name)[1]
        try:
            adapter = self._create(name)
        except Exception as e:
            self.notice.set_text("%s didn't load: %s" % (display, e))
            self.loading = False
            return
        inst = adapter.instrument
        patch = self.prefs.get("patches", {}).get(name)
        if patch and patch in (inst.patches or {}):
            adapter.set_patch(patch)
        self.prefs["name"] = name
        self.name = name
        self._idle_us = None
        self._settle = 0
        self._most_voices = inst.voices
        self._fitted = 0
        self._raised = False
        self._read = None
        self._refused = None
        self.adapter = adapter
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
        try:
            self.output.start(inst)
        except Exception as e:
            self.adapter = None
            inst.deinit()
            self.notice.set_text("No sound out: %s" % (e,))
            self.loading = False
            return
        self.notice.set_text("")
        self.splash.add_flag(lv.obj.FLAG.HIDDEN)
        shown = adapter
        if not self.has_midi():
            from .pads import NotePads, notes_for

            shown = NotePads(adapter, notes_for(self.ai.load(name)), self._pad_note)
        self.panel = self._build_panel(shown, display)
        self._place_menu()
        self._shown = None
        self._since_log = 0
        self._timers = [
            self.scope.every(MIDI_MS, self._midi_tick),
            self.scope.every(FILL_MS, self._fill),
        ]
        self.loading = False
        self._status_tick()

    def _reloaded(self, new, old):
        self.output.start(new)
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
        self._filling = True
        try:
            adapter.instrument.fill()
        finally:
            self._filling = False
        self._fills += 1
        # A new note is read again once its strike has rendered, rather than
        # waiting for the next scheduled look.
        if self._played:
            self._played -= 1
        if self._played == 1 or self._fills % GOVERN_EVERY == 0:
            self._govern(adapter.instrument)

    def _govern(self, inst):
        """Cap the voices at what the pump can render in time.

        The pump renders on a core of its own, so a chord the core can't
        keep up with doesn't slow the app, it starves the speaker: the audio
        runs behind for as long as the keys are held. Each sounding voice
        costs about the same, so from the cost of the blocks just rendered
        this works out how many fit in :data:`BUDGET` of a block's time and
        sets the instrument's ``voices`` to that. The extra notes steal the
        oldest instead of everything going quiet. The cap is set from the
        first sounding voice, before a chord needs it. That voice also wakes
        whatever the voices share, so it reads dearer than the voices after
        it: with every allowed voice sounding and room for one more, the cap
        goes up one, and a count that has fit stays allowed unless the blocks
        go over budget. A cap it just raised stays up until a chord has used
        it or the blocks go over budget: the keys already held can't take the
        new voice, so their reads say nothing about it. A count that went over
        budget isn't tried again until the keys are up, because each try steals
        a note.
        """
        output = self.output
        cost = output.pull_us()
        if cost is None or self._most_voices < 2:
            return
        if self._settle:
            # The blocks right after a cap still carry the voices it stole.
            self._settle -= 1
            return
        sounding = inst.voice_pool.sounding()
        if sounding == 0:
            self._idle_us = cost if self._idle_us is None else min(self._idle_us, cost)
            self._refused = None
            return
        idle = self._idle_us or 0
        budget = BUDGET * output.block_us()
        per_voice = (cost - idle) / sounding
        if per_voice <= 0:
            return
        voices = inst.voices
        fit = max(1, int((budget - idle) / per_voice + 0.5))
        # Just after a key the mean still holds blocks from before it.
        settled = self._played == 0
        if cost <= budget:
            if settled and sounding > self._fitted:
                self._fitted = sounding
            fit = max(fit, self._fitted)
        if fit < voices and (cost > budget or sounding >= voices or not self._raised):
            if cost > budget:
                self._refused = sounding
            inst.voices = fit
            self._raised = False
            self._settle = SETTLE
        elif (
            settled
            and sounding >= voices
            and voices < self._most_voices
            and (self._refused is None or voices + 1 < self._refused)
        ):
            step = per_voice
            read = self._read
            if read is not None and read[0] < sounding and cost > read[1]:
                step = (cost - read[1]) / (sounding - read[0])
            if cost + step <= budget:
                inst.voices = voices + 1
                self._raised = True
                self._settle = SETTLE
        if settled:
            self._read = (sounding, cost)

    def _stop_instrument(self):
        for timer in self._timers:
            timer.deinit()
        self._timers = []
        adapter = self.adapter
        self.adapter = None
        if adapter is not None:
            self.prefs.setdefault("patches", {})[self.name] = adapter.patch_index
            self.output.stop()
            # After the output, so nothing pulls a deinitialised instrument.
            adapter.instrument.deinit()
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
        if load is None:
            return "LOAD --"
        return "LOAD %d%% U%d" % (load, underruns)

    def _status_tick(self, _timer=None):
        if self.inputs is not None and self.panel is None:
            self._show_midi()
        panel = self.panel
        if panel is None or self.loading:
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
        self._stop_instrument()
        if self.output is not None:
            self.output.close()
        if self.inputs is not None:
            self.inputs.close()
            self.inputs = None
