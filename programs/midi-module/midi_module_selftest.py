# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Check the MIDI module with no MIDI cable: the board sends itself a song.

A second UART drives the module's RX pin from inside the chip (an ESP32's
pins can carry one UART's TX and another's RX at once), and a timer sends a
short General MIDI piece through it at the right times: a piano, strings,
bass and drums. So the bytes cross a real UART at 31250 baud into the same
loop a DIN socket feeds. Have ``main.py`` import this instead of
``midi_module``.

It reads ``rx`` from ``/midi_module.json`` as the module does, and
``selftest_uart`` there names the sending UART (2 unless you say).
"""

import json

import machine
import midi_module_song as song

STEP_MS = 125  # one sixteenth at 120 BPM
START_MS = 15000  # after the SoundFont has opened

with open("/midi_module.json") as f:
    _settings = json.load(f)
RX_PIN = _settings["rx"]
TX_UART = _settings.get("selftest_uart", 2)

state = {"tx": None, "step": -START_MS // STEP_MS, "sent": 0}


def tick(timer):
    step = state["step"]
    state["step"] = step + 1
    if step < 0:
        return
    if state["tx"] is None:
        # Set up after the module's UART, so its RX pin keeps its input.
        # rx=-1 leaves this UART's default RX pin alone: on some ESP32
        # modules that's a flash pin.
        try:
            state["tx"] = machine.UART(TX_UART, baudrate=31250, tx=RX_PIN, rx=-1)
        except (ValueError, TypeError):
            state["tx"] = machine.UART(TX_UART, baudrate=31250, tx=RX_PIN)
        state["tx"].write(song.SETUP)
    data = song.step(step)
    if data:
        state["tx"].write(data)
        state["sent"] += len(data)
    if step % 64 == 0:
        print("selftest: bar %d, %d bytes sent" % (step // 16 + 1, state["sent"]))


machine.Timer(0).init(period=STEP_MS, callback=tick)
import midi_module  # noqa: F401  (runs the module, forever)
