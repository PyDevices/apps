# Roadmap

What's planned for the apps and libraries here. An app or library with a
longer list keeps its own roadmap beside its code, linked below.

## Sound module

The sound module (`lib/soundmodule`) plays whatever a DAW, sequencer or
keyboard sends it over MIDI, the way a hardware tone module does.

- A SysEx request that returns the module's instruments, patches, effects and
  controls, shaped after MIDI-CI Property Exchange.
- On an ESP32-P4 as a USB MIDI device, with 24 voices at 48 kHz stereo.
- Over BLE MIDI.
- Reverb and chorus as true sends per channel, once the sampler can mix its
  voices into a send bus. Today CC91 and CC93 set one master level.

## Vamp

- Recording from a MIDI keyboard such as the DMK-25 on the board's USB host
  port into the selected track. It already plays from one.
- Undo in the window that knows about edits made on other panels.
- The timed voice pool that schedules notes ahead of the audio moving into
  audioinstruments, once a second player needs it.

## Ostinato

- A published copy of the app on the web, so it installs without running a
  local server.
- The rest is in [Ostinato's roadmap](apps/ostinato/ROADMAP.md).

## Synth Station

- [Synth Station's roadmap](apps/synthstation/ROADMAP.md).

## Stompbox

- A level meter with a clip light and a tuner, and several effect slots with
  saved presets, so Stompbox is more than one airwindows effect at a time.

## Clock and Weather

- More faces on the clock, and a way to pick a face that's saved.
- Weather searches by place name, for anywhere outside the US.

## Libraries

- Ship songmodel's front panel page to boards. The wheel carries `page.html`,
  but a `mip` install or a frozen build has only the Python, so today Vamp
  copies the page across itself.
- [appkit](lib/appkit/ROADMAP.md), [controlkit](lib/controlkit/ROADMAP.md)
  and [sayso](lib/sayso/ROADMAP.md) keep their own roadmaps.
