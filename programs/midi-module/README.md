# MIDI module

MIDI module turns a board into a General MIDI sound module: MIDI from a 5-pin
DIN socket plays a SoundFont out of the board's audio out. It uses the sound
module engine in [`lib/soundmodule`](../../lib/soundmodule): sixteen parts,
Bank Select and Program Change pick the sound, and the parts share one pool of
sampler voices. A press of a key, the touch screen or the Boot button silences
every note, and a display, if the board has one, shows what's playing.

Runs on: a MicroPython board with audio out (`audio_out` in its board package),
a free UART input pin, and `audiodsp` in its firmware. Tested on the Waveshare
ESP32-P4-WIFI6-Touch-LCD-4B and the QT Py ESP32 Pico with the Audio BFF, each
with the self-test below in place of a DIN socket.

## Wire the MIDI input

A MIDI input always goes through an optocoupler, so the board never shares a
ground with the instrument. An H11L1 or a PC900V works at 3.3 V:

| DIN socket | Optocoupler | Board |
|---|---|---|
| pin 4 | through 220 Ω to the LED's anode | |
| pin 5 | the LED's cathode | |
| | a 1N4148 across the LED, cathode to the anode, for reverse voltage | |
| | the output (open collector) | the RX pin, with 1 kΩ to 3V3 |
| | VCC and GND | 3V3 and GND |

DIN pin 2 (the shield) stays unconnected on an input. Pins 4 and 5 are the
ones either side of the middle pin.

## Put it on a board

Install your board's package from
[pydevices](https://github.com/PyDevices/pydevices) first (it brings
`board_config` and `board_peripherals`), and `midiports`:

```bash
mpftp mip install --index https://PyDevices.github.io/mip midiports
```

The engine needs audioinstruments' SoundFont player:
`audioinstruments/__init__`, `_names`, `soundfont`, `soundfont_drums`, and
under `_rack`, `__init__`, `_component`, `_gm`, `_lazy`, `_sf2`, `adapter`,
`soundfont`, `soundfont_drums`, `modules/__init__` and `core/`. Then, from the
apps repo's root:

```bash
mpftp put lib/programkit /lib/programkit
mpftp put lib/soundmodule /lib/soundmodule
mpftp put programs/midi-module/midi_module.py /midi_module.py
```

Put a General MIDI SoundFont (`.sf2`) in `/soundfonts` on the board, or in
`/soundfonts` on its SD card, which is looked at first. The first by name is
used. Then say which pin the optocoupler drives, in `/midi_module.json`:

```json
{"uart": 1, "rx": 32}
```

and make `main.py` say `import midi_module`. The other settings (`tx`, `rate`,
`voices`, `effects`, `master`) are at the top of
[`midi_module.py`](midi_module.py). Sixteen voices with no effects is what a
classic ESP32 holds at 44.1 kHz.

## Check it without a MIDI cable

[`midi_module_selftest.py`](midi_module_selftest.py) plays a four-bar loop
(piano, strings, bass and drums, from
[`midi_module_song.py`](midi_module_song.py)) into the module's own RX pin
from a second UART inside the chip, so the bytes cross a real UART at 31250
baud. Leave the RX pin unwired, put both files on the board, and make
`main.py` say `import midi_module_selftest`. The loop starts 15 seconds after
boot. `"selftest_uart"` in `/midi_module.json` picks the sending UART (2 by
default).
