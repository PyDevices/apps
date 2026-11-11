# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Bluetooth speaker: pair a phone or computer with the board and play.

The board's ``pcm_out`` plays what the sender streams. With a display, it
shows the connection, the title and artist, and on a display tall enough, the
sender's name and a left and right level meter. With ``"phone": true`` it
also follows a phone's battery and calls; the call itself stays on the phone.
Holding any key, the touch screen or the Boot button for a second drops the
sender, so another device can find the speaker.

Settings go in ``/bt_speaker.json`` on the board, all optional::

    {"name": "Kitchen Speaker", "phone": true}

Put this on a board with Bluetooth Classic and have ``main.py`` import it.
"""

import json
import math
import time

import btclassic
from audiodev import AudioFormat
from programkit import Board, Press, Rows

# Change these to match your setup, or put them in /bt_speaker.json.
NAME = None  # the name senders see, or None for the board's hostname
PHONE = False  # follow a phone's battery and calls (a computer may then treat the speaker as a headset)
AHEAD_MS = 60  # audio kept queued ahead of the speaker
HOLD_MS = 1000  # holding a key this long drops the sender
METER_MS = 50  # meter refresh
FLOOR_DB = 48  # the meter's left end, in dB below full scale
FALL = 4  # pixels a meter bar falls per refresh

_CALLS = {
    "incoming": "Incoming call",
    "dialing": "Calling",
    "alerting": "Ringing",
    "active": "On a call",
    "held": "Call on hold",
}

try:
    with open("/bt_speaker.json") as f:
        _settings = json.load(f)
    NAME = _settings.get("name", NAME)
    PHONE = _settings.get("phone", PHONE)
except OSError:
    pass

# Wi-Fi and Bluetooth share the radio on these boards, and with both on the
# audio arrives in bursts and stutters.
try:
    import network

    network.WLAN(network.STA_IF).active(False)
except (ImportError, OSError):
    pass

board = Board()
if not board.has("pcm_out"):
    raise SystemExit("bt_speaker: this board has no pcm_out in its board_peripherals")
pcm_out = board.get("pcm_out")
press = Press(board)
rows = Rows(board.display) if board.display is not None else None

bt = btclassic.Bluetooth()
if NAME:
    bt.config(name=NAME)
name = bt.config("name")
receiver = btclassic.AudioSink(bt)
phone = btclassic.HandsFree(bt) if PHONE else None
print("Pair with %s and play something." % name)

# Where things go: a 128x64 OLED has eight rows, a 128x32 one has four.
if rows is not None and rows.count >= 8:
    SENDER, TITLE, ARTIST, METER = 1, 2, 5, 6
elif rows is not None:
    SENDER, TITLE, ARTIST, METER = None, 1, 3, None
BATTERY_W = 24  # the battery icon's width at the right of the top row


def show_status():
    battery = phone is not None and phone.connected and phone.battery is not None
    width = rows.width - BATTERY_W - 4 if battery else None
    if not receiver.connected:
        rows.line(0, "Pair with", width)
    else:
        state = "Playing" if receiver.playing else "Paused"
        rows.line(0, "%-8s%3d%%" % (state, receiver.volume * 100 // 127), width)
    if SENDER is not None:
        rows.line(SENDER, "From " + receiver.peer_name if receiver.connected else "")


def show_battery():
    """The phone's battery, 0 to 5 bars, as an icon at the top right."""
    x = rows.width - BATTERY_W
    h = rows.height
    rows.rect(x, 0, BATTERY_W, h, False)
    show_status()
    if phone is None or not phone.connected or phone.battery is None:
        return
    rows.rect(x, 0, BATTERY_W - 3, h, True)
    rows.rect(x + 1, 1, BATTERY_W - 5, h - 2, False)
    rows.rect(x + BATTERY_W - 3, h // 4, 2, h // 2, True)
    step = (BATTERY_W - 7) // 5
    for i in range(max(0, min(5, phone.battery))):
        rows.rect(x + 2 + step * i, 2, step - 1, h - 4, True)


def call_lines():
    """The call's three lines while there is one, or None."""
    if phone is None:
        return None
    label = _CALLS.get(phone.call)
    if label is None:
        return None
    if phone.call == "active" and call_started is not None:
        seconds = time.ticks_diff(time.ticks_ms(), call_started) // 1000
        label = "Call %d:%02d" % (seconds // 60, seconds % 60)
    return label, phone.caller or "", ""


def show_middle():
    """The call while there is one, the track while connected, else the name to pair with."""
    lines = call_lines()
    if lines is None and not receiver.connected:
        lines = (name, "", "")
    elif lines is None:
        first, rest = wrap(receiver.title, rows.cols)
        lines = (first, wrap(rest, rows.cols)[0], receiver.artist)
    rows.line(TITLE, lines[0])
    rows.line(TITLE + 1, lines[1])
    rows.line(ARTIST, lines[2])


def wrap(text, width):
    """Split text at the last space that fits in width, or at width if none does."""
    if len(text) <= width:
        return text, ""
    cut = text.rfind(" ", 0, width + 1)
    if cut <= 0:
        return text[:width], text[width:]
    return text[:cut], text[cut + 1 :]


def bar_width(peak, full):
    if peak <= 0:
        return 0
    db = 20 * math.log10(peak / 32767)
    return max(0, min(full, int((db + FLOOR_DB) * full / FLOOR_DB)))


call_started = None
bars = [0, 0]
if rows is not None:
    show_status()
    show_middle()
    if METER is not None:
        meter_x = rows.width // rows.cols + 2  # right of the L and R labels
        meter_w = rows.width - meter_x
        rows.line(METER, "L", meter_x - 2)
        rows.line(METER + 1, "R", meter_x - 2)
    rows.send_all()

buf = bytearray(512 * 4)
speaker = None
rate = 0
ahead = 0
last_meter = last_tick = time.ticks_ms()

while True:
    if receiver.sample_rate and receiver.sample_rate != rate:
        rate = receiver.sample_rate
        if speaker:
            speaker.close()
        speaker = pcm_out(AudioFormat(rate, 2, 16))
        ahead = rate * 4 * AHEAD_MS // 1000

    # The speaker's clock sets the pace: keep AHEAD_MS queued, and draw
    # while it plays.
    if speaker and speaker.queued_size() < ahead:
        receiver.readinto(buf)
        speaker.write(buf)
        continue

    press()
    held = press.held_ms()
    if held is not None and held >= HOLD_MS and receiver.connected:
        print("Held: dropping", receiver.peer_name or "the sender", "so another device can pair")
        receiver.disconnect()

    changed = receiver.changes()
    if changed & btclassic.TRACK:
        print("Playing:", receiver.title, "-", receiver.artist)
    if rows is not None:
        if changed & (btclassic.CONNECTION | btclassic.PEER | btclassic.PLAYING | btclassic.VOLUME):
            show_status()
        if changed & (btclassic.CONNECTION | btclassic.TRACK):
            show_middle()

    if phone is not None:
        changed = phone.changes()
        if phone.audio:
            phone.disconnect_audio()  # no microphone here: the call stays on the phone
        if changed & btclassic.CALL:
            if phone.call == "active":
                if call_started is None:
                    call_started = time.ticks_ms()
            else:
                call_started = None
            print("Call:", phone.call, phone.caller)
        if rows is not None:
            if changed & (btclassic.CONNECTION | btclassic.PHONE):
                show_battery()
            if changed & btclassic.CALL:
                show_middle()

    if rows is None:
        time.sleep_ms(5)
        continue

    now = time.ticks_ms()
    if call_started is not None and time.ticks_diff(now, last_tick) >= 1000:
        last_tick = now
        show_middle()

    # One row a turn, so the audio never waits for the whole screen. Text
    # goes before the meter: while music streams the loop gets here only a
    # few times a second, and the meter would otherwise take every turn.
    if rows.send():
        continue
    if METER is not None and time.ticks_diff(now, last_meter) >= METER_MS:
        last_meter = now
        for i, peak in enumerate(receiver.levels()):
            new = max(bar_width(peak, meter_w), bars[i] - FALL)
            y = (METER + i) * rows.height + 1
            if new > bars[i]:
                rows.rect(meter_x + bars[i], y, new - bars[i], rows.height - 2, True)
            elif new < bars[i]:
                rows.rect(meter_x + new, y, bars[i] - new, rows.height - 2, False)
            bars[i] = new
    else:
        time.sleep_ms(5)
