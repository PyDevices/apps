# Bluetooth speaker

Bluetooth speaker turns a board into a speaker your phone or computer pairs
with and plays through. With a display, it shows the connection, the title and
artist, and on a display tall enough, the sender's name and a left and right
level meter. Holding a key, the touch screen or the Boot button for a second
drops the sender, so another device can find the speaker.

Runs on: a MicroPython board with Bluetooth Classic and audio out (`pcm_out`
in its board package): ESP32 boards, and the Pico W and Pico 2 W family.
Tested on the QT Py ESP32 Pico with the Audio BFF and a 128x64 SH1106 OLED,
and the Pimoroni Pico Plus 2 W with a Pico-Audio board and a Pico-OLED-2.23.

## Put it on a board

The firmware needs `btclassic`. Install your board's package from
[pydevices](https://github.com/PyDevices/pydevices) first (it brings
`board_config` and `board_peripherals`), then, from the apps repo's root:

```bash
mpftp put lib/programkit /lib/programkit
mpftp put programs/bt-speaker/bt_speaker.py /bt_speaker.py
```

and make `main.py` say `import bt_speaker`. Reset the board, pair with its
name and play something.

## Settings

All optional, in `/bt_speaker.json` on the board:

```json
{"name": "Kitchen Speaker", "phone": true}
```

`name` is what senders see; without it, the speaker uses the board's hostname.
With `phone` on, the speaker also shows a phone's battery and calls (the call
itself stays on the phone). A computer may then list the speaker as a headset
as well. The rest of the settings are at the top of
[`bt_speaker.py`](bt_speaker.py).
