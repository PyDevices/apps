# Changelog

## 0.1.3.dev7

- appkit: one bar along the top instead of two. The status bar carries Home, the app's title and its status line, then the clock and the icons, so apps get up to 32 px more of the screen. On a narrow screen the status line takes a row under the bar only once the app sets it. Home's settings and hidden-apps buttons are on the bar too, and the tiles take the row they used.
- touchkit: under the compact cap, the title row sits inside the circle on a round screen, with Home at its left.
- Bluetooth Receiver: the calls switch moves into the app's area when the bar is too narrow for it.
- applibs: the apps extra asks for omnipython-desktop 0.8.1.dev5 or later, the first with the status bar's Bluetooth item.

## 0.1.3.dev6

- appkit: mirror a board's screen to a browser from the picker's Cast to, behind the board's WebREPL password; the status bar shows a cast icon while it's on, and "viewing" while a browser watches.
- appkit: type on a USB keyboard plugged into the board's host port.
- Backline: the asked-for song shows on a board's own desk; one view's art at a time, so the desk opens on an 8 MB board, and switching views is quicker.

## 0.1.3.dev5

- applibs: one package on the library index holds every library in lib/, chatclient included, so `mip install applibs` brings them all, and a library added to lib/ is published with it. Each app's package.json asks for applibs.
- Backline: a drum machine played with your foot, from a switch on a pin, the BOOT button or a MIDI foot controller, with a desk view on the box, another computer, a browser or a TV, and grooves you can ask for in words.
- appkit: a status bar, on by default, and a picker over the running app for every connection that pairs, joins and asks for a password or PIN on the keyboard. Apps follow the sound output, MIDI and network chosen for them, and Home and the apps draw with icons instead of iconkit.
- Home: hide an app that can't run here, and put it back.
- midiEngine: reads the MIDI inputs chosen in the picker, and moves when they change.

## 0.1.3.dev4

- Bluetooth Receiver: shows the phone's battery and signal, has a call card, and shuffle and repeat buttons that follow the phone's player.
- Bit World: frames make a tenth of the garbage they did, draw without returning an Area, and put frames and sprites outside the heap where the firmware has offheap.

## 0.1.3.dev3

- controlkit: EnvelopeView draws a multi-stage envelope and RoutingDiagram draws an operator routing diagram.

## 0.1.3.dev2

- Stompbox: recordings keep every block the audio pump sends. A block that landed while the recorder was reading used to be lost and another doubled, about 29 splices a second on an ESP32-P4.

## 0.1.3.dev1

- soundmodule: opening a bank makes channel 1's and the drums' instruments, so the first key on a keyboard plays on time. With a large SoundFont on an ESP32-P4 that first note took 200 ms or more; it now takes about 50 ms. It needs audioinstruments 0.5.3.dev2 or later.
- Ostinato installs the released stack without `--pre`.

## 0.1.2

- The 0.1.2 release: everything in 0.1.2.dev1 to 0.1.2.dev16 below. `pip install omnipython-applibs` gets it from PyPI.

## 0.1.2.dev16

- omnipython-applibs is on PyPI, pre-releases included: `pip install --pre omnipython-applibs`.

## 0.1.2.dev15

- appkit: a launcher switch tries to allocate the heap an app wants before it restarts the board. On an ESP32 whose heap grows on demand, switching apps no longer restarts it for room it could have had.
- Camera: closing it closes the camera, and the next open makes a new one, so its frame buffers are free again. A 1080P photo on the ESP32-P4X-EYE encodes on the P4's JPEG engine, in under a second instead of ten.
- Synth Station, midiEngine: play them over Bluetooth MIDI on a board with Bluetooth LE. It uses `midiports.ble` from omnipython 0.8.0.dev24 or later.
- Synth Station: a pause in the main thread no longer counts as starved sound, and a board playing on its own I2S reports the silence the driver counted, where the firmware has it.
- Bluetooth speaker: a one-second sink, so a phone's bursts don't drop frames; it needs omnipython 0.8.0.dev20 or later.
- Home: a Wi-Fi connection that `boot.py` already made stays up, and a running WebREPL is left alone.
- Bit World: colors come from the palettes library, which installing the app now pulls in.

## 0.1.2.dev14

- appkit: a worker no longer hangs when a callback submits a job while another `submit()`, `pending()` or `cancel()` is running on the same thread.
- sayso: the same fix for a callback inside a call on its own thread.
- The apps are named OmniPython: environment variables begin `OMNIPYTHON_` (the `PYDEVICES_` names are no longer read), and the packages and mip names are `omnipython-*`.
- Huey: lite-assistant is the default server, and speech starts with the first words.
- Huey's Perch: needs svgio's compact form; Huey is "he" throughout.

## 0.1.2.dev13

- Huey: a new app. Hold Huey the chameleon, ask him something out loud, and he answers in speech and a speech bubble, acting the answer out with a mood, colours, a prop or a place. It talks to an OpenAI-compatible server named in its settings file.
- Huey's Perch: a new app of vector art drawn by svgio. Huey, a chameleon, walks, catches bugs and changes colour at the coast, a workbench and a desk, with each season ready before it shows. It needs firmware with `svgio`.
- appkit: a worker's `done()` runs on the main thread on an ESP32 too. There it could run on the worker's own thread, and a `done()` that submitted the next job could stop every timer on the board.
- Synth Station: an instrument for each MIDI channel, with one voice cap shared by every instrument playing; on boards that play through `audio_out` it caps voices and counts underruns.
- Stompbox: a level meter and a clip light beside Master.
- Ostinato: layouts for phones and for windows around 1280x720; `fetch_midi.py` finds midiports where it lives now.
- controlkit: an encoder's ring can fill from the middle or show one dot, and an encoder in a small cell drops its legend.
- sayso: Spotify's limits are checked before a request, and removed endpoints are marked.
- songmodel: the front panel page installs with the package.

## 0.1.2.dev12

- Gamepad: a new app that makes the board a USB game controller, or tests a gamepad plugged into its USB host port. It needs pydevices 0.8.0.dev20 or later, and firmware that freezes `usb.host.hid_generic` for the host side.
- MIDI Controller: a new app with pads, knobs, faders, a mixer, an XY pad and keys. It plays out as a USB MIDI device, to a synth on the USB host port, over BLE-MIDI, or to a computer's or a browser's MIDI outputs.
- Vamp: a front panel for an 800x480 touch screen, and a take recorded from the box's MIDI keyboard.
- touchkit, Desk Clock, Card: the board answers to `boarddev.name()`, the one name Wi-Fi, Bluetooth and mDNS use. It needs pydevices 0.8.0.dev20 or later.
- appkit: buttons, list rows, tabs, sliders and switches light up under the mouse.
- REPL: page back through the scrollback.
- Ostinato, Vamp: the MIDI loopback's name comes from `midiports.LOOPBACK` (PyDevices Loopback on Windows).
- Sound module: a REAPER bank file with the patch names.
- applibs: type stubs for the 61 public modules in `lib/`.

## 0.1.2.dev11

- touchkit.net: a CircuitPython board rejoins its network after the access point drops, on the same 30 s to 5 minute schedule as a first join. MicroPython's poll still stops at the first join.
- touchkit.net: an offline MicroPython board joins in the background through `wifi_manager.connect(wait=False)`, the route CircuitPython takes. It needs pydevices 0.8.0.dev19 or later.
- touchkit: Home leaves a WebREPL that `boot.py` already started listening, so an open session isn't dropped, and CircuitPython no longer prints an error about the missing `webrepl` module at every boot.
- midi-module: its install line names lib.omnipython.org.

## 0.1.2.dev10

- touchkit.net: an offline CircuitPython board keeps its screen. A join there holds the screen for about 10 s, and one used to start on every poll; now a failed join waits 30 s before the next, doubling to 5 minutes. `keep_time()` raises a `RuntimeError` when LVGL hasn't started, where it used to crash the interpreter.
- Bit World makes its four full-screen buffers first, so it fits on an 800x480 panel.

## 0.1.2.dev9

- touchkit.net: an offline CircuitPython board joins Wi-Fi through wifi_manager, where it used to print an error every few seconds and never join.

## 0.1.2.dev8

- CircuitPython: Clock, Weather, Roku and Spotify run there. appkit.net gives sockets, HTTP and the clock with the same calls on every Python: a socketpool on CircuitPython, with adafruit_requests for HTTP, and an SNTP query for the clock. The board now sets its clock from the network on CircuitPython too, and the timezone lookup from the IP address works there.
- An app.json can list what an app needs from the interpreter (`"needs": ["os.dupterm"]`), and Home leaves out an app this Python lacks. REPL needs `os.dupterm`, so CircuitPython boards don't list it.
- MP3 says so when the board has no audio out, and Bit World runs silent without `board_peripherals`, where both used to stop with an ImportError.
- Each app's package.json lists adafruit_requests under `circuitpython` when the app reaches HTTP.

## 0.1.2.dev7

- Weather shows a forecast straight away: until you choose a ZIP code it uses the city the board's public IP address is in (ipwho.is), marked with a location pin, in °F in the US and °C elsewhere. A place you choose wins and is the one saved; if the lookup fails, Weather asks for a ZIP code as before.

## 0.1.2.dev6

- deskkit: the clock runs on CircuitPython, which has no time.gmtime, so Clock shows local time there too.
- Install guide: what to do when CircuitPython installs stop with Errno 5.

## 0.1.2.dev5

- Clock shows local time before a place is chosen: when the board joins a network it looks up the timezone of its public IP address (ipwho.is), and again each day for daylight saving. A place chosen in Weather still wins.
- touchkit installs deskkit, which sets the board's clock on joining a network; a board without it now reports the missing package instead of skipping the clock.

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
