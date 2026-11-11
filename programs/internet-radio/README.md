# Internet radio

Internet radio plays MP3 streams over Wi-Fi. A press of a key, the touch screen
or the Boot button moves to the next station, and a display, if the board has
one, shows which station is playing. The board holds a few seconds of the
stream in RAM, so a late packet isn't heard, and a stream that stops sending
is opened again.

Runs on: a MicroPython board with Wi-Fi and audio out (`audio_out` in its board
package) and `audiomp3` in its firmware. Tested on the QT Py ESP32 Pico with
the Audio BFF and a 128x64 SH1106 OLED, and the Waveshare
ESP32-P4-WIFI6-Touch-LCD-4B.

## Put it on a board

Install your board's package from
[pydevices](https://github.com/PyDevices/pydevices) first (it brings
`board_config`, `board_peripherals` and `wifi_manager`), and put your network
in `secrets.py` as `WIFI_SSID` and `WIFI_PASSWORD`. Then, from the apps repo's
root:

```bash
mpftp put lib/programkit /lib/programkit
mpftp put programs/internet-radio/internet_radio.py /internet_radio.py
```

and make `main.py` say `import internet_radio`.

## Settings

All optional, in `/internet_radio.json` on the board:

```json
{"stations": ["http://ice1.somafm.com/groovesalad-128-mp3"], "volume": 70, "hostname": "radio"}
```

A station is an `http://` MP3 stream URL. Without the file, three SomaFM
stations play. The buffer and stall settings are at the top of
[`internet_radio.py`](internet_radio.py).
