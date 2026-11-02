# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Drive Synth Station through every instrument, with no window and no speaker.

Runs on CPython and on unix MicroPython. The app gets a scope whose timers
the script fires itself, a stand-in audio out that only keeps the sample it
was given (the script pulls the audio from it), and a stand-in keyboard the
script plays. For each instrument it chooses it, checks the panel shows the
instrument's name, macros and patches, plays a note and checks the output
isn't silent, turns a knob and sends a program change and checks the panel
follows. Then it opens a drum machine and a synth with no
keyboard at all and plays them from the pads.

    python station_check.py [NAME ...]

Prints a line per instrument and ``RESULT OK`` at the end, or ``FAIL``
lines and exit status 1.
"""

import sys

import _headless
import lvgl as lv

WIDTH, HEIGHT = 800, 480
_headless.display(WIDTH, HEIGHT)

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)
        print("FAIL", what)


# ---- stand-ins ------------------------------------------------------------


class Out:
    def set_volume(self, percent):
        pass

    def __init__(self):
        self.sample = None

    def attach(self, scope):
        pass

    def play(self, sample):
        self.sample = sample

    def stop(self):
        self.sample = None

    def detach(self):
        pass

    def close(self):
        pass


class Peripherals:
    """``board_peripherals`` for a computer with an audio out and nothing else."""

    AUDIO_OUT = None
    outs = []

    @staticmethod
    def audio_out(fmt):
        out = Out()
        Peripherals.outs.append(out)
        return out


sys.modules["board_peripherals"] = Peripherals


class Timer:
    def __init__(self, ms, callback, periodic):
        self.ms = ms
        self.callback = callback
        self.periodic = periodic
        self.running = True
        self.due = Scope.now + ms

    def deinit(self):
        self.running = False


class Scope:
    now = 0

    def __init__(self):
        self.root = lv.screen_active()
        self.size = (WIDTH, HEIGHT)
        self.timers = []
        self.closes = []
        self._store = {}

    def store(self, name=None):
        return self._store

    def every(self, ms, callback):
        t = Timer(ms, callback, True)
        self.timers.append(t)
        return t

    def after(self, ms, callback):
        t = Timer(ms, callback, False)
        self.timers.append(t)
        return t

    def on_close(self, fn):
        self.closes.append(fn)

    def run(self, rounds=1):
        """Move the clock on 10 ms *rounds* times, firing what falls due.

        A periodic timer fires at most once a round, however short its
        period: the script calls this often enough.
        """
        for _ in range(rounds):
            Scope.now += 10
            for t in list(self.timers):
                if not t.running or Scope.now < t.due:
                    continue
                if t.periodic:
                    t.due = Scope.now + t.ms
                else:
                    t.running = False
                t.callback(t)
            self.timers = [t for t in self.timers if t.running]
            _headless.advance(10)


class Keyboard:
    """A MIDI input port the script plays."""

    def __init__(self):
        self.queue = bytearray()

    def send(self, *data):
        self.queue.extend(bytes(data))

    def any(self):
        return len(self.queue)

    def readinto(self, buf, nbytes=None):
        n = min(len(buf), len(self.queue))
        if not n:
            return None
        for i in range(n):
            buf[i] = self.queue[i]
        self.queue = self.queue[n:]
        return n

    def close(self):
        pass


import audiocore  # noqa: E402

from synthstation import midi, pads, station  # noqa: E402

keyboard = Keyboard()
with_keyboard = [True]


def _open(self):
    inputs = midi.Inputs()
    if with_keyboard[0]:
        inputs.kind = "desktop"
        inputs.ports = [keyboard]
        inputs._desktop_names = ["Test Keys"]
    else:
        inputs.why = "no MIDI input on this computer"
    return inputs


midi.Inputs.open = _open


def peak_of(sample, blocks):
    peak = 0
    for _ in range(blocks):
        result, data = audiocore.get_buffer(sample)
        mv = memoryview(data)
        n = len(mv) // 2
        for i in range(0, n, 7):
            v = mv[2 * i] | (mv[2 * i + 1] << 8)
            if v >= 32768:
                v -= 65536
            if v < 0:
                v = -v
            if v > peak:
                peak = v
    return peak


def play(app, scope, note, velocity=110, pad=None):
    """Sound *note* (or press *pad*), give the instrument its turns, and pull audio."""
    if pad is None:
        keyboard.send(0x90, note, velocity)
    else:
        app.panel.choose_patch(pad)
    sample = Peripherals.outs[-1].sample
    peak = 0
    for _ in range(12):
        scope.run(2)
        peak = max(peak, peak_of(sample, 2))
    if pad is None:
        keyboard.send(0x80, note, 0)
    scope.run()
    return peak


def open_instrument(app, scope, name):
    app.choose(name)
    scope.run(5)
    return app.panel


def exercise(app, scope, name):
    import audioinstruments as ai

    face = ai.load(name)
    panel = open_instrument(app, scope, name)
    check(panel is not None, "%s: the panel opens" % name)
    if panel is None:
        print("     ", app.notice.get_text())
        return
    adapter = app.adapter
    inst = adapter.instrument
    # A name too long for the plate ends in dots: LVGL writes them into the text.
    plate = panel.title.get_text()
    if plate.endswith("..."):
        plate = plate[:-3]
    check(len(plate) >= 4 and face.DISPLAY_NAME.upper().startswith(plate), "%s: the name plate says %s (%r)" % (name, face.DISPLAY_NAME, panel.title.get_text()))
    labels = list(inst.macro_labels)[:16]
    check(list(adapter.macro_labels) == labels, "%s: the macro labels are the instrument's" % name)
    enabled = [e.enabled for e in panel.encoders]
    check(enabled == [i < len(labels) for i in range(16)], "%s: %d encoders are live" % (name, len(labels)))
    declared = inst.patches or {}
    names = [declared[i][0] if i in declared else "Patch %03d" % (i + 1) for i in range(max(declared) + 1 if declared else 0)]
    check(list(adapter.patches) == names, "%s: the pads are the instrument's patches" % name)
    note = face.NOTE_MAP[0][0] if getattr(face, "NOTE_MAP", None) else 60
    peak = play(app, scope, note)
    check(peak > 0, "%s: a note sounds (peak %d)" % (name, peak))
    knob = ""
    if labels:
        # The last knob this instrument has a macro for, and a Sound Controller.
        last = min(len(labels), 12) - 1
        target = 17 if panel.encoders[last].value != 17 else 99
        keyboard.send(0xB0, 30 + last, target)
        scope.run(3)
        check(panel.encoders[last].value == target, "%s: knob CC moves encoder %d to %d (it's %d)" % (name, last + 1, target, panel.encoders[last].value))
        target = 17 if panel.encoders[0].value != 17 else 99
        keyboard.send(0xB0, 70, target)
        scope.run(3)
        knob = "knob %d" % panel.encoders[0].value
        check(panel.encoders[0].value == target, "%s: knob CC moves encoder 1 to %d (it's at %d)" % (name, target, panel.encoders[0].value))
        check(int(inst.get_macro(0)) == target, "%s: knob CC moves macro 0" % name)
    keyboard.send(0xB0, 7, 64)
    scope.run(3)
    check(app.output.volume == 50, "%s: CC 7 sets the volume to 50 (it's %r)" % (name, app.output.volume))
    program = ""
    keys = sorted(inst.patches or {})
    if len(keys) > 1:
        want = keys[1] if adapter.patch_index != keys[1] else keys[0]
        keyboard.send(0xC0, want)
        scope.run(3)
        program = "patch %d" % panel.patch
        check(panel.patch == want, "%s: program change %d lights its pad (lit: %s)" % (name, want, panel.patch))
        check(inst.patch_index == want, "%s: program change reaches the instrument" % name)
    if shots and not SHOT[0]:
        SHOT[0] = True
        keyboard.send(0x90, 60, 100)
        scope.run(60)
        shot(shots + "/panel.raw")
        keyboard.send(0x80, 60, 0)
    print("ok  %-20s %-22s peak %5d  %d macros  %d patches  %s %s" % (
        name, face.DISPLAY_NAME, peak, len(labels), len(names), knob, program))


def shot(path):
    if path:
        _headless.refresh()
        _headless.save_raw(path, WIDTH, HEIGHT)


class _Instrument:
    def __init__(self):
        self.controls = []

    def control_change(self, controller, value):
        self.controls.append(controller)


class _Adapter:
    def __init__(self, macros):
        self.macro_count = macros
        self.instrument = _Instrument()


class _Keyboard:
    """Station.control's only reads, for controllers no instrument here reaches."""

    loading = False

    def __init__(self, macros):
        self.adapter = _Adapter(macros)
        self._knobs = {}
        self._volume = None
        self._held = {}
        self._patch_step = 0
        self._instrument_step = 0


def check_knob_map():
    for offset, count in ((30, 12), (70, 8)):
        for knob in range(count):
            sink = _Keyboard(16)
            station.Station.control(sink, offset + knob, 5)
            check(sink._knobs == {knob: 5}, "CC %d moves macro %d (%r)" % (offset + knob, knob, sink._knobs))
    sink = _Keyboard(16)
    station.Station.control(sink, 7, 64, 0)
    check(sink._volume == 64 and not sink.adapter.instrument.controls, "CC 7 on channel 1 is the volume")
    sink = _Keyboard(16)
    station.Station.control(sink, 7, 64, 1)
    check(sink._volume is None and sink.adapter.instrument.controls == [7], "CC 7 on channel 2 goes to the instrument")
    sink = _Keyboard(16)
    for value in (127, 100, 0, 127):
        station.Station.control(sink, 17, value)
    check(sink._patch_step == 2, "a press counts once, whatever follows it (%d)" % sink._patch_step)
    for controller, attr, step in ((16, "_patch_step", -1), (17, "_patch_step", 1), (18, "_instrument_step", -1), (19, "_instrument_step", 1)):
        sink = _Keyboard(16)
        station.Station.control(sink, controller, 127)
        check(getattr(sink, attr) == step and not sink.adapter.instrument.controls, "CC %d steps by %d" % (controller, step))
    for controller in (15, 20, 29, 42, 69, 78):
        sink = _Keyboard(16)
        station.Station.control(sink, controller, 5)
        check(not sink._knobs and sink.adapter.instrument.controls == [controller], "CC %d goes to the instrument" % controller)
    sink = _Keyboard(2)
    station.Station.control(sink, 32, 5)
    check(not sink._knobs and sink.adapter.instrument.controls == [32], "CC 32 goes to an instrument with two macros")


def check_menu_and_buttons(app, scope):
    def press(controller):
        keyboard.send(0xB0, controller, 127)
        keyboard.send(0xB0, controller, 0)
        scope.run(5)

    def entry(name):
        return [module for module, _ in app.instruments].index(name)

    count = len(app.instruments)
    open_instrument(app, scope, "poly106")
    keys = sorted(app.adapter.instrument.patches)
    at = keys.index(app.adapter.patch_index)
    press(17)
    check(app.adapter.patch_index == keys[(at + 1) % len(keys)], "Fast Forward is the next patch")
    check(app.panel.patch == app.adapter.patch_index, "the panel follows the next patch")
    press(16)
    check(app.adapter.patch_index == keys[at], "Rewind is the previous patch")
    start = entry("poly106")
    press(19)
    check(app.name == app.instruments[(start + 1) % count][0], "Play is the next instrument (%s)" % app.name)
    check(app.menu.get_selected() == (start + 1) % count, "the menu follows Play")
    check(app.panel is not None and app.adapter is not None, "the next instrument opens")
    press(18)
    check(app.name == "poly106", "Stop is the previous instrument (%s)" % app.name)
    last = open_instrument(app, scope, app.instruments[-1][0])
    check(last is not None and app.menu.get_selected() == count - 1, "choosing the last instrument")
    press(19)
    check(app.name == app.instruments[0][0], "Play wraps round to the first (%s)" % app.name)
    press(18)
    check(app.name == app.instruments[-1][0], "Stop wraps round to the last (%s)" % app.name)
    app.menu.set_selected(entry("poly106"))
    app.menu.send_event(lv.EVENT.VALUE_CHANGED, None)
    scope.run(5)
    check(app.name == "poly106" and app.panel is not None, "the menu changes the instrument (%s)" % app.name)
    check(Peripherals.outs[-1].sample is app.adapter.instrument.output, "the output plays what the menu chose")
    check(app.menu.get_y() + app.menu.get_height() <= app.panel.header.get_height(), "the menu is in the title bar")


def _render(name, patch, note):
    """A hit on a new instrument, so nothing but the note can make it differ."""
    import audioinstruments.panel

    adapter = audioinstruments.panel.create(name, 48000, channel_count=2)
    inst = adapter.instrument
    if inst.patches:
        adapter.note_program(patch)
    inst.note_on(note, 100)
    out = bytearray()
    for _ in range(150):
        inst.fill()
        _, data = audiocore.get_buffer(inst.output)
        out.extend(bytes(data))
    inst.deinit()
    return bytes(out)


def check_kit_sounds(name, face):
    """Every pad is a sound of its own, and no sound of the kit is left out."""
    laid_out = [note for note, _ in pads.KIT_PADS[name]]
    known = [note for note, _ in face.NOTE_MAP]
    check(not [n for n in laid_out if n not in known], "%s: every pad is a note the kit has" % name)
    check(len(laid_out) <= pads.PAD_COUNT, "%s: its sounds fit the pads" % name)
    probe = _patches(name)
    for patch in probe:
        sounds = {}
        for note in laid_out:
            sound = _render(name, patch, note)
            check(sound not in sounds, "%s patch %d: notes %d and %r are one sound" % (name, patch, note, sounds.get(sound)))
            sounds[sound] = note
        for note in known:
            if note not in laid_out:
                check(_render(name, patch, note) in sounds, "%s patch %d: note %d is a sound no pad plays" % (name, patch, note))


def _patches(name):
    import audioinstruments.panel

    adapter = audioinstruments.panel.create(name, 48000, channel_count=2)
    patches = sorted(adapter.instrument.patches or (0,))
    adapter.instrument.deinit()
    return patches


class _Font:
    """A SoundFont whose kit 0 has a kick, closed hat and tom, and kit 1 a snare and a clap."""

    KITS = {0: (36, 42, 45), 1: (38, 39)}

    def regions(self, bank, program, key, velocity):
        return (key,) if key in self.KITS[program] else ()


class _FontKit:
    bank = _Font()

    def __init__(self, program):
        self.preset = (128, program)


def check_meters(app, scope):
    # The drop-down starts with the patch card and ends with it, or sooner on a
    # panel whose display leaves the meters no room there.
    open_instrument(app, scope, "poly106")
    panel = app.panel
    panel.root.update_layout()
    title = panel._patch_title
    x = app.menu.get_x()
    right = x + app.menu.get_width()
    rule_at = None
    for i in range(panel.root.get_child_count()):
        kid = panel.root.get_child(i)
        if kid.get_height() == 1 and kid.get_y() > title.get_y() and kid.get_x() > x:
            rule_at = kid.get_x() + kid.get_width()
            break
    check(x == title.get_x(), "the menu starts with the patch card (%d, %d)" % (x, title.get_x()))
    meters = app._meters
    check(right <= rule_at, "the menu is no wider than the patch card (%s, %s)" % (right, rule_at))
    display_x = station._display_x(panel)
    gap = panel._s(station.METER_GAP)
    check(
        right == rule_at or right == display_x - 2 * gap - station.Meters.width(panel._s),
        "the menu stops at the card or at the meters (%s, %s, %s)" % (right, rule_at, display_x),
    )
    check(meters is not None, "the meters fit beside the menu")
    bars, lit = meters.bars, meters.lit
    check(
        bars[0].get_x() >= right and bars[1].get_x() + bars[1].get_width() < display_x,
        "the bars are between the menu and the display",
    )

    # The light follows what comes in, a pad past the kit's last sound too.
    def opa():
        return lit.get_style_bg_opa(0)

    scope.run(50)
    check(opa() == 0, "the light is out before a note (%d)" % opa())
    app.parser.feed(bytearray((0x90, 60, 100)), 3)
    app._meter_tick()
    check(opa() > 0, "a note lights it")
    scope.run(50)
    check(opa() == 0, "it goes out by itself (%d)" % opa())
    app.parser.feed(bytearray((0x80, 60, 0)), 3)
    open_instrument(app, scope, "rhythm606")
    meters = app._meters
    lit = meters.lit
    app.parser.feed(bytearray((0x99, 59, 100)), 3)
    app._meter_tick()
    check(opa() > 0, "a pad with no sound lights it")
    app.parser.feed(bytearray((0x89, 59, 0)), 3)

    open_instrument(app, scope, "poly106")
    meters = app._meters

    # Left and right are read apart, and a silent output falls to nothing.
    output = app.output
    real = output._tap

    class OneSide:
        def readinto(self, buf):
            for i in range(0, len(buf), 2):
                buf[i] = 16384
                buf[i + 1] = 0
            return len(buf) * 2

    class Silent:
        def readinto(self, buf):
            return 0

    output._tap = OneSide()
    left, right = output.levels()
    check(abs(left - 0.5) < 0.01 and right == 0, "the channels are read apart (%.2f, %.2f)" % (left, right))
    app._meter_tick()
    check(meters.bars[0].get_value() > 15 and meters.bars[1].get_value() == 0, "so are the bars")
    output._tap = Silent()
    for _ in range(25):
        app._meter_tick()
    check(meters.bars[0].get_value() == 0 and meters.bars[1].get_value() == 0, "with nothing going out they fall")
    output._tap = real
    app._meter_tick()


def check_drum_pads(app, scope):
    import audioinstruments as ai

    def hits(*messages):
        """What the instrument is told when *messages* are played."""
        got = []
        adapter = app.adapter
        adapter.note_on = lambda note, velocity: got.append(("on", note))
        adapter.note_off = lambda note: got.append(("off", note))
        for message in messages:
            keyboard.send(*message)
        scope.run(2)
        del adapter.note_on
        del adapter.note_off
        return got

    # The order is literal: a test reading the table would agree with any table.
    check(pads.pad_notes("rhythm606", None) == (36, 38, 42, 46, 41, 48, 49), "Rhythm 606's pads")
    check(pads.pad_notes("rhythm808", None)[:6] == (36, 38, 42, 46, 39, 37), "Rhythm 808's first pads")
    check(pads.pad_notes("electronic_drums5", None) == (36, 38, 42, 46, 41, 45, 48, 49), "Electronic Drums 5's pads")
    check(pads.pad_notes("poly106", None) is None, "a synth isn't laid out")
    check(pads.pad_notes("soundfont_drums", _FontKit(0)) == (36, 42, 45), "a SoundFont kit's pads are what it has")
    check(pads.pad_notes("soundfont_drums", _FontKit(1)) == (38, 39), "the next kit's pads are what that one has")

    for name in pads.KIT_PADS:
        check_kit_sounds(name, ai.load(name))

    open_instrument(app, scope, "rhythm606")
    got = hits((0x99, 36, 100), (0x89, 36, 0), (0x99, 37, 100), (0x99, 42, 100), (0x89, 42, 0))
    check(got == [("on", 36), ("off", 36), ("on", 38), ("on", 49), ("off", 49)], "pads play the kit one sound each (%r)" % (got,))
    check(hits((0x99, 43, 100), (0x89, 43, 0), (0x99, 35, 100), (0x89, 35, 0)) == [], "a pad past the kit's sounds is silent")
    got = hits((0x90, 37, 100), (0x80, 37, 0))
    check(got == [("on", 37), ("off", 37)], "the keys stay General MIDI (%r)" % (got,))
    peak = play_pad(app, scope, 36)
    check(peak > 0, "the first pad sounds (peak %d)" % peak)
    # However dear a block reads, a kit keeps every sound and a synth is capped.
    def governed(name, note):
        open_instrument(app, scope, name)
        inst = app.adapter.instrument
        voices = inst.voices
        output = app.output
        output.pull_us = lambda: 20000
        output.block_us = lambda: 5000
        inst.note_on(note, 100)
        inst.fill()
        app._idle_us = 0
        app._played = 0
        app._settle = 0
        app._govern(inst)
        del output.pull_us
        del output.block_us
        capped = inst.voices
        inst.note_off(note)
        return capped, voices

    capped, voices = governed("rhythm606", 36)
    check(capped == voices == 7, "a kit's voices aren't capped (%d of %d)" % (capped, voices))
    capped, voices = governed("poly106", 60)
    check(capped < voices, "a synth's voices are capped (%d of %d)" % (capped, voices))
    got = hits((0x99, 60, 100), (0x89, 60, 0))
    check(got == [("on", 60), ("off", 60)], "pads play a synth's notes as they are (%r)" % (got,))


def play_pad(app, scope, note):
    keyboard.send(0x99, note, 110)
    sample = Peripherals.outs[-1].sample
    peak = 0
    for _ in range(12):
        scope.run(2)
        peak = max(peak, peak_of(sample, 2))
    keyboard.send(0x89, note, 0)
    scope.run()
    return peak


def main(names, shots=None):
    check_knob_map()
    import audioinstruments as ai

    scope = Scope()
    app = station.Station(scope)
    scope.run(8)
    check(app.panel is not None, "the last instrument opens by itself")
    check(app.name == station.DEFAULT, "with nothing saved, that's %s (it's %s)" % (station.DEFAULT, app.name))
    check("EXIT" not in app.panel.buttons, "there's no EXIT")
    check(app.splash.has_flag(lv.obj.FLAG.HIDDEN), "the splash is gone once it opens")
    check(app.inputs is not None and app.inputs.kind == "desktop", "the keyboard is open")
    for name in names or ai.ALL:
        exercise(app, scope, name)
    check_menu_and_buttons(app, scope)
    check_drum_pads(app, scope)
    check_meters(app, scope)

    # With no keyboard, bank A plays notes and the patches move up a bank.
    with_keyboard[0] = False
    for fn in scope.closes:
        fn()
    scope = Scope()
    app = station.Station(scope)
    scope.run(8)
    check(not app.has_midi(), "no keyboard: the app knows")
    check("No MIDI" in app.midi_label.get_text(), "no keyboard: the splash says so")
    for name in ("rhythm808", "poly106"):
        panel = open_instrument(app, scope, name)
        check(panel is not None, "%s with no keyboard: the panel opens" % name)
        if panel is None:
            continue
        check(panel.adapter.patches[0] != app.adapter.patches[0], "%s: bank A is notes" % name)
        check(panel.subtitle.get_text().startswith("NO MIDI"), "%s: the panel says there's no keyboard" % name)
        scope.run(60)
        check((panel.display._text[1] or "").startswith("LOAD"), "%s: the display shows the load" % name)
        peak = play(app, scope, None, pad=2)
        check(peak > 0, "%s: pad 3 plays a note (peak %d)" % (name, peak))
        if len(app.adapter.patches) > 1:
            panel.choose_patch(16 + 1)
            check(app.adapter.patch_index == 1, "%s: bank B's second pad picks patch 2" % name)
        # RELOAD builds the instrument again and the output plays the new one.
        old = app.adapter.instrument
        panel.adapter.request_reload()
        scope.run(4)
        check(app.adapter.instrument is not old, "%s: RELOAD builds a new instrument" % name)
        check(Peripherals.outs[-1].sample is app.adapter.instrument.output, "%s: the output plays the new one" % name)
        peak = play(app, scope, None, pad=4)
        check(peak > 0, "%s: it sounds after RELOAD (peak %d)" % (name, peak))
        print("ok  %-20s pads play, peak %d, subtitle %r" % (name, peak, panel.subtitle.get_text()))
    app.inputs.kind = "desktop"
    app.inputs.ports = [keyboard]
    app.inputs._desktop_names = ["Test Keys"]
    scope.run(60)
    scope.run(5)
    check(app.panel is not None and app._panel_midi, "a keyboard arriving reopens the panel for it")
    check(not app.panel.subtitle.get_text().startswith("NO MIDI"), "the panel no longer says NO MIDI")
    check(station.current is app, "station.current is the running app")
    for fn in scope.closes:
        fn()
    check(app.panel is None, "close takes the panel down")
    check(station.current is None, "close clears station.current")


SHOT = [False]
args = sys.argv[1:]
shots = None
if "--shots" in args:
    i = args.index("--shots")
    shots = args[i + 1]
    del args[i:i + 2]
main(args, shots)
if failures:
    print("RESULT FAIL", len(failures))
    sys.exit(1)
print("RESULT OK")
