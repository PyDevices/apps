# Programs

A program runs on its own: you start it, and it doesn't need Home. A Home app
is different. It lives in [`apps/`](../apps), has an `app.json`, and appkit
runs it from the home screen.

| Program | What it does |
|---|---|
| [Bluetooth speaker](bt-speaker) | A speaker your phone or computer pairs with, on a board with Bluetooth Classic. |
| [Camera](camera) | The ESP32-P4X-EYE's camera app: photos, video with sound, an album and detection, on a board's MIPI camera or a USB one. |
| [Internet radio](internet-radio) | Plays MP3 streams over Wi-Fi; a press changes station. |
| [MIDI module](midi-module) | A General MIDI sound module: MIDI from a DIN socket plays a SoundFont. |
| [Ostinato](ostinato) | A pattern sequencer and song editor, in a browser or a desktop window. |
| [Vamp](vamp) | Plays Ostinato's songs on one MicroPython, with the screens elsewhere. |

Every program folder has a `README.md` that opens with what the program does,
then a `Runs on:` line naming the boards or computers it works on, then how to
put it there.
