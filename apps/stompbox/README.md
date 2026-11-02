# Stompbox

Play a guitar or a WAV clip through an airwindows effect, with the effect's
knobs on screen. It runs like the other apps here: from the launcher, on a board
or on a desktop interpreter.

## Run it

You need a firmware or desktop interpreter built with the
[airwindows](https://github.com/PyDevices/airwindows) module. Without it, the
app says so and goes no further. Copy this folder to `/apps/stompbox` on a board
and open Stompbox from Home. On a computer, run the launcher from this
repository's root:

```python
import appkit

appkit.run("stompbox")
```

## Clips

On a board the clips are in `/sd/guitar-clips`, and the card is mounted read-only
while the app is open. On a computer they're in `~/music/guitar-clips`, or the
folder `STOMPBOX_CLIPS` names. Each clip is read into memory, so a board's RAM
sets how long one can be.

## Live

Live appears where there's an input to open, and plays it through the effect. On
a board that's the input sharing the speaker's I2S clocks, such as the ES7210
microphones on an ESP32-P4 panel. A microphone beside its own speaker howls, so
turn Master down before you tap it. On Windows it's a capture device, and two
settings choose the devices:

- `STOMPBOX_INPUT` is the capture endpoint's ID. The default input if unset.
- `STOMPBOX_OUT` is the speaker's. The default output if unset.

`STOMPBOX_LIVE`, set to anything, opens the app on Live. When the input and output
are one device they share a clock and the audio passes straight through. On two
devices, a drift resampler holds a ring buffer between them, and the screen shows
the latency.

## Effects

The list opens on a curated guitar set, kept in [guitar-set.txt](guitar-set.txt).
"Show all" adds the rest of the plug-ins your build carries: every one on a
desktop build, and 140 on a board unless the build chose otherwise.

A board can carry an effect it can't run in real time: on an ESP32-P4, PointyGuitar
reaches 1%, and TapeDelay2, PitchDelay, TakeCare and Tremolo about a quarter. The
app measures each one as it plays. It opens on the first in the list that keeps
up, and when you pick one that doesn't, the screen says how far behind it is.

## Measure it

[`tools/stompbox`](../../tools/stompbox) holds the desktop tools. `drive.py` runs
the app from a script and records what it plays. `chain_depth.py` measures what
the software path holds, `roundtrip.py` sends a click around a cable from output
to input, and `c_path.py` and `drift_path.py` time the C path on one and two
clocks.
