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

## Camera

- Record a USB camera's microphone as the video's sound on a board with no microphone of its own.
- Run on ESP32-S31 boards with a USB camera, once MicroPython runs there.

## Ostinato

- A published copy of the app on the web, so it installs without running a
  local server.
- The rest is in [Ostinato's roadmap](programs/ostinato/ROADMAP.md).

## Home

- Stay reachable over WebREPL however the board restarts: when `boot.py` has
  already joined Wi-Fi, Home leaves the connection alone, so a script app or a
  reset that skips `main.py` no longer drops it.

## Synth Station

- [Synth Station's roadmap](apps/synthstation/ROADMAP.md).

## Stompbox

- A tuner, and several effect slots with saved presets, so Stompbox is more
  than one airwindows effect at a time.

## Clock

- More faces on the clock, and a way to pick a face that's saved.

## Libraries

- [appkit](lib/appkit/ROADMAP.md), [controlkit](lib/controlkit/ROADMAP.md)
  and [sayso](lib/sayso/ROADMAP.md) keep their own roadmaps.
