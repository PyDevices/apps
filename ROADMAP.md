# Roadmap

What's planned for the apps and libraries here. An app or library with a
longer list keeps its own roadmap beside its code, linked below.

## Sound module

The sound module (`lib/soundmodule`) plays whatever a DAW, sequencer or
keyboard sends it over MIDI, the way a hardware tone module does.

- A SysEx request that returns the module's instruments, patches, effects and
  controls, shaped after MIDI-CI Property Exchange.
- On an ESP32-P4 as a USB MIDI device, with 24 voices at 48 kHz stereo.
- Reverb and chorus as true sends per channel, once the sampler can mix its
  voices into a send bus. Today CC91 and CC93 set one master level.

## Vamp

- Undo in the window that knows about edits made on other panels.

## Eye Camera

- Record a USB camera's microphone as the video's sound on a board with no microphone of its own.
- Run on ESP32-S31 boards with a USB camera, once MicroPython runs there.

## Ostinato

- A published copy of the app on the web, so it installs without running a
  local server.
- The rest is in [Ostinato's roadmap](programs/ostinato/ROADMAP.md).

## Synth Station

- [Synth Station's roadmap](apps/synthstation/ROADMAP.md).

## Shell

- A Shell app: a command line on the board's own screen, through vtterm, for
  looking after a board (list, copy, remove and read files). Its first version
  runs micropython-lib's upysh, all in Python.

## Stompbox

- A tuner, and several effect slots with saved presets, so Stompbox is more
  than one airwindows effect at a time.

## Bluetooth Receiver

- Calls' audio through the speaker and microphones on ESP32-S31 boards, once
  that chip's Bluetooth controller carries a call's audio link reliably.

## Clock

- More faces on the clock, and a way to pick a face that's saved.

## Programs

- The programs in `programs/` that run on a computer rather than a board
  move to a repository of their own; any that run on a board become apps.

## Libraries

- [appkit](lib/appkit/ROADMAP.md), [controlkit](lib/controlkit/ROADMAP.md)
  and [sayso](lib/sayso/ROADMAP.md) keep their own roadmaps.
