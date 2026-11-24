# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""General MIDI sound module: MIDI from a 5-pin DIN socket plays a SoundFont.

MIDI bytes arriving on a UART play General MIDI through the sound module's
engine (sixteen parts sharing one pool of sampler voices), out of the board's
``audio_out``. The audio pump renders it in C on its own task. A press of any
key, the touch screen or the Boot button silences every note, and a display,
if the board has one, shows what's playing.

The SoundFont is the one ``bank`` names in the settings, or else the first
``.sf2`` by name in ``/sd/soundfonts`` on the board's SD card, or else in
``/soundfonts`` on its flash, or else in ``/data/soundfonts`` (``/flash/...``
on an STM32). Settings go in ``/midi_module.json``; ``rx``, the pin the
optocoupler drives, is the one you must give::

    {"uart": 1, "rx": 13}

Samples are read from the bank the first time a note needs them, so a note
waits while its sample is read. At start the program times a read of the
bank and says how long its largest sample would take, when that is long
enough to hear.

Put this on the board with its libraries and have ``main.py`` import it.
"""

import gc
import json
import os
import sys
import time

from audiodev import AudioFormat
from programkit import Board, Press, Rows

# Change these to match your setup, or put them in /midi_module.json.
MIDI_UART = 1  # the UART the DIN input is read on
MIDI_RX = None  # the pin the optocoupler's output drives; required
MIDI_TX = -1  # a MIDI out pin, or -1 for none
RATE = 44100  # Hz
VOICES = 16  # the sampler's voices; each costs about 4% of a classic ESP32's core at 44.1 kHz
EFFECTS = False  # the reverb alone takes most of a classic ESP32's core
MASTER = 80  # the output's volume, 0 to 100; MIDI's master volume changes it
BANK = None  # a .sf2 path, to play it rather than the first one found
SLOW_MS = 100  # a sample read this long is a note heard late
STATUS_MS = 10000

try:
    with open("/midi_module.json") as f:
        _settings = json.load(f)
    MIDI_UART = _settings.get("uart", MIDI_UART)
    MIDI_RX = _settings.get("rx", MIDI_RX)
    MIDI_TX = _settings.get("tx", MIDI_TX)
    RATE = _settings.get("rate", RATE)
    VOICES = _settings.get("voices", VOICES)
    EFFECTS = _settings.get("effects", EFFECTS)
    MASTER = _settings.get("master", MASTER)
    BANK = _settings.get("bank", BANK)
except OSError:
    pass
if MIDI_RX is None:
    raise SystemExit('midi_module: say which pin the MIDI input is wired to: {"rx": 13} in /midi_module.json')

board = Board()
if not board.has("audio_out"):
    raise SystemExit("midi_module: this board has no audio_out in its board_peripherals")
press = Press(board)
rows = Rows(board.display) if board.display is not None else None


def show(row, text):
    """A line on the display, if there is one, sent at once."""
    if rows is not None:
        rows.line(row, text)
        rows.send_all()


show(0, "MIDI module")

# Wi-Fi off: on most of these boards it shares a radio or a core with the audio.
try:
    import network

    network.WLAN(network.STA_IF).active(False)
except (ImportError, OSError):
    pass

# The card holds the SoundFont, and the libraries when flash has no room.
flash = "/flash" if sys.platform == "pyboard" else ""  # an STM32's / only holds mounts
folders = [flash + "/soundfonts", flash + "/data/soundfonts"]
if board.has("sdcard"):
    try:
        os.listdir("/sd")
    except OSError:
        try:
            os.mount(board.get("sdcard"), "/sd")
        except OSError as e:
            print("midi_module: no SD card:", e)
    folders.insert(0, "/sd/soundfonts")
    sys.path.insert(0, "/sd/lib")
from midiports import uart
from soundmodule import engine

found = []
for folder in folders:
    try:
        found += [folder + "/" + n for n in sorted(os.listdir(folder)) if n.lower().endswith(".sf2")]
    except OSError:
        pass
if BANK is not None:
    try:
        os.stat(BANK)
    except OSError:
        show(1, "No SoundFont")
        raise SystemExit("midi_module: the bank in /midi_module.json, %s, isn't there" % BANK)
    bank = BANK
elif found:
    bank = found[0]
else:
    show(1, "No SoundFont")
    raise SystemExit("midi_module: no SoundFont: put a .sf2 in %s" % " or ".join(folders))
others = [b for b in found if b != bank]
if others:
    print('midi_module: playing %s; to play another, name it in /midi_module.json, as {"bank": "%s"}'
          % (bank, others[0]))
name = bank.rsplit("/", 1)[1]
show(1, name)

# The UART, at MIDI's 31250 baud. The engine reads raw MIDI itself, running
# status and all, so it takes the port's bytes as they come. There is no
# MIDI out, so the engine's replies (an Identity Reply) go nowhere.
# Both pins are given where the port allows it: on some ESP32 modules a
# UART's default TX pin is a flash or PSRAM pin, and -1 leaves it alone.
try:
    _, port = uart.ports(MIDI_UART, tx=MIDI_TX, rx=MIDI_RX, rxbuf=1024)
except (ValueError, TypeError):
    _, port = uart.ports(MIDI_UART, rx=MIDI_RX, rxbuf=1024)

# The engine, with the SoundFont's presets read before anything plays.
module = engine.Module(RATE, 2, bank=bank, voices=VOICES, effects=EFFECTS, send=None)
started = time.ticks_ms()
if module.prepare() is None:
    show(2, "Can't open it")
    raise SystemExit("midi_module: can't open %s: %s" % (bank, module.error))
print("midi_module: %s open in %d ms, %d voices, %d KB free"
      % (name, time.ticks_diff(time.ticks_ms(), started), module.voice_count, gc.mem_free() // 1024))


def read_speed(path, nbytes=32768):
    """Bytes a second read from the middle of ``path``, where a big bank
    keeps its samples."""
    buf = bytearray(nbytes)
    with open(path, "rb") as f:
        f.seek(os.stat(path)[6] // 2)
        t = time.ticks_ms()
        got = f.readinto(buf)
        ms = time.ticks_diff(time.ticks_ms(), t)
    return got * 1000 // max(ms, 1)


# A note waits while its sample is read from the bank the first time.
speed = read_speed(bank)
largest = max((s.end - s.start) * 2 for s in module.loaded.font.samples)
wait_ms = largest * 1000 // speed
if wait_ms >= SLOW_MS:
    print("midi_module: %s reads at %d KB/s, so a note waits up to %.1f s the first time it plays a sample"
          " (the largest is %d KB). A smaller bank, on flash or a faster card, plays without the wait."
          % (name, speed // 1024, wait_ms / 1000, largest // 1024))
    show(3, "Slow: notes wait %.1f s" % (wait_ms / 1000))

# The output. The pump pulls the engine's mix from here on.
if board.has("audio_power"):
    board.get("audio_power")(True)
out = board.get("audio_out")(AudioFormat(RATE, 2, 16))
module.on_master = out.set_volume
module.set_master(MASTER)
out.play(module.output)

print("midi_module: listening on UART %d, RX pin %s" % (MIDI_UART, MIDI_RX))
print("midi_module: all notes off on", ", ".join(press.sources) or "nothing: this board has no key, touch or Boot button")
show(2, "MIDI in: UART %d, pin %s" % (MIDI_UART, MIDI_RX))

buf = bytearray(256)
received = 0
next_status = time.ticks_add(time.ticks_ms(), STATUS_MS)
while True:
    # Hand whatever arrived to the engine. Its voice writes are queued and
    # reach the pump together, so a chord waits for one block, not three.
    n = port.readinto(buf)
    if n:
        with engine.deferred(module):
            module.feed(buf, n)
        received += n
    module.fill()

    if press():
        module.panic()
        print("midi_module: all notes off")
        show(3, "All notes off")

    # Now and then, what's playing.
    if time.ticks_diff(time.ticks_ms(), next_status) >= 0:
        next_status = time.ticks_add(next_status, STATUS_MS)
        pool = module.voice_pool
        sounding = pool.sounding() if pool else 0
        parts = ["%d:%s" % (p.channel + 1, module.name(p.channel)) for p in module.parts if p.inst is not None]
        print("midi_module: %d bytes, %d voices sounding, %s" % (received, sounding, ", ".join(parts)))
        show(3, "%d voices, %d bytes" % (sounding, received))
    time.sleep_ms(2)
