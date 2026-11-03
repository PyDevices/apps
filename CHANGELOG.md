# Changelog

## Unreleased

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
