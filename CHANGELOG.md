# Changelog

## Unreleased

## 0.1.2.dev5

- Clock shows local time before a place is chosen: when the board joins a network it looks up the timezone of its public IP address (ipwho.is), and again each day for daylight saving. A place chosen in Weather still wins.
- touchkit: a board without deskkit fails loudly instead of skipping the clock.
- Camera: its main.py joins Wi-Fi and starts WebREPL when there's a secrets.py.

## 0.1.2.dev4

- The board sets its clock when it joins a network, and again each day, so Clock shows the time without waiting for a forecast. With no place chosen it shows UTC.
- Home joins a known network and starts WebREPL at boot.
- Camera: the P4 camera program installs with omip, as a Home app or the board's main.py; it has a Home icon, and closes and opens again cleanly.
- Video Camera: the preview app's new name; it says photos go to the SD card when one is in.
- Video Camera, Detect, Security and Mp3 work on a display with no framebuffer.
- Synth Station installs controlkit, which its instrument panel draws with.
- Cast casts with the castdisplay package.
- Install an app: spots an older omip, updates it on CircuitPython, and removes code.py for Home.

## 0.1.2.dev3

- Install any app on a board with one omip line: each app has its own package.json and installs to /apps/<name>.
- REPL: the board's Python prompt as an app.
- Bit World: a script app with an exit button; Home's main.py doesn't build Home over a script app that runs on timers.
- Apps find and save their files on the SD card, then flash, then the data root.
- Models: one page says which model files Wake word, Object detection and Camera need, and where to get them.
- The libraries in the index declare what they import, so installing appkit brings iconkit; deskkit and programkit are published.

## 0.1.2.dev2

- Camera: the camera app for any ESP32-P4 board and a USB camera.
- Home and the apps draw Material icons from iconkit.
- Programs: Ostinato and Vamp move to programs/; internet radio, MIDI module and Bluetooth speaker run on any board.
- Sound module: patch, key and macro names for DAWs (MIDNAM and .ins).
- Sound card and Surveillance camera say what is missing on a board without it.
- touchkit: a board with no BOOT button role boots without a warning.

## 0.1.2.dev1

- appkit, touchkit and System run on CircuitPython boards.
- System: an at-a-glance check that scales from 240x240 to 1280x720, laid out inside the circle on round screens.
- appkit and Home: no restart after System, and a round-screen layout.
- Sound module: Expression (CC11) works on instrument parts as well as SoundFont parts, and a part keeps it when its instrument is made again, by a bank change or All Sound Off.

## 0.1.2.dev0

- Wake word: the app listens through medialink.wakeword and tflite.
- `appkit.run()` starts the folder's own Home when it has one, and keeps a scanned Home.
- Spectrum runs on CPython and moves every frame on a desktop window.
- midiEngine says on the status line when the sound can't start.

## 0.1.1

- midiEngine hears every MIDI input on a computer, and on a MicroPython without a
  native emitter it opens in a moment rather than 15 s over a network drive.
- Synth Station and midiEngine ask a computer's audio output for its low-latency
  profile, so a key sounds about 50 ms after it's played, not 200.
- sayso, the Spotify Web API client, moves into `lib/` and ships with `applibs`:
  on the library index, where it also installs on its own, and in
  `omnipython-applibs`. It imports as `sayso`, as before.
- The Effects rig app is gone. Stompbox replaces it.
- Object detection shows about two frames a second on an ESP32-P4. It was one
  frame every seven seconds, nearly all of it spent copying the preview to the panel.
- Stompbox is a real app: open it from Home on a board or a desktop interpreter,
  with Live where the board's microphone shares the speaker's clocks. On a board
  it measures the effect against real time, opens on the first one that keeps
  up, and says on screen when one you pick doesn't.
- touchkit's Home button and BOOT button work without `main.py` setting
  `shell.launcher`: making a `TouchShell` sets it. Before, they did nothing.
- Synth Station stops trying a voice count that went over budget until you lift
  your hands: each try stole a note you were holding.
- The shared libraries publish as `applibs`: on the library index, where each
  also installs on its own, and on TestPyPI as `omnipython-applibs`.
- The sound module: sixteen parts on one pool of voices, General MIDI from a
  SoundFont, audioinstruments' instruments on bank 80 and drum machines on
  bank 81, RPN pitch bend and tuning, reverb and chorus sends, and the
  Identity Reply. It runs headless on CPython, MicroPython and CircuitPython.
- Ostinato, the pattern sequencer and song editor, and Vamp, which plays its
  songs on a board, move into this repository.
- The instruments on banks 80 and 81 are audioinstruments' rack set. A
  program an earlier set had and this one doesn't plays nothing, and the
  programs after it keep their numbers. `Module.fill()` moves the
  instruments' notes and knobs into the sound: call it before each pull of
  `output` (`soundmodule.run` and `render_mid.py` do). MicroPython needs ulab
  built in as well as audiodsp.
- Ostinato plays audioinstruments' 33 instruments. Its new-project tracks, demo
  song and sketches use the rack's names, knob labels and drum notes; the
  browser app loads numpy for them. `tools/sketch_render.py` renders each
  song's tracks and checks every one makes sound.
- A gate that plays ordinary General MIDI files through the module and
  measures the result.
