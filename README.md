![Ostinato, the pattern sequencer, playing a four-bar drum pattern in its desktop window](docs/ostinato.png)

# Apps

The apps for PyDevices boards and desktops. Find one here, copy its files to
your board, and it runs under [appkit](https://github.com/PyDevices/pydevices/tree/main/packages/appkit),
the launcher that runs several apps on one device. Apps that only make sense
on a computer, like Ostinato, run on the desktop.

| App | What it does |
|---|---|
| `apps/synthstation` | Synth Station: pick an audioinstruments instrument and play it from a MIDI keyboard, with a hardware-style control panel for its knobs. |
| `apps/spotify` | The board is a Spotify Connect speaker, and the screen is its remote. |
| `apps/roku` | A TV remote over the LAN. |
| `apps/midiengine` | A General MIDI sound module: 16 parts from a SoundFont, played from every USB MIDI keyboard. |
| `apps/mp3` | The songs on an SD card, with play, previous, next, volume and a spectrum. |
| `apps/camera`, `apps/security`, `apps/detect` | A camera preview, a security stream, and object detection on the camera. |
| `apps/cast`, `apps/effects`, `apps/card`, `apps/instruments`, `apps/system`, `apps/wake` | Casting to a screen, an effects rig, a sound card, the instruments, a system page and a wake word. |
| `apps/ostinato` | Ostinato, a pattern sequencer and song editor in your browser or on the desktop. |

Shared code lives in `lib/`: `devkit` for the touch-panel apps, `controlpanel`
for a front panel, `soundmodule` for the sound module, and `vamp` for
Ostinato's songs on a board.

## Boards

An app is a folder of `.py` files. Each file installs on its own from raw
GitHub with `mip`, so there is no package to publish and no release to wait
for: a push to `main` is what users get. An app's README says which files it
needs and where each one goes. Apps that depend on libraries in `lib/` name
those too.

## Install

The apps are used from a clone, beside the libraries they build on:

```bash
git clone https://github.com/PyDevices/studio
git clone https://github.com/PyDevices/audioinstruments
git clone https://github.com/PyDevices/audioeffects
git clone https://github.com/PyDevices/audiodsp
pip install ./audiodsp numpy
pip install --no-deps ./audioinstruments ./audioeffects/lib/audioeffects
```

## Try it

Render a MIDI file through the sound module to a WAV, with no MIDI hardware.
The sound comes from a General MIDI SoundFont (`.sf2`) that you supply, such
as [GeneralUser GS](https://schristiancollins.com/generaluser.php):

```bash
cd studio
python tools/render_mid.py tests/midi/musicbox1_spooky_waltz.mid take.wav --bank GeneralUser-GS.sf2 --path lib
```

It writes `take.wav`, 53 seconds of celesta, and prints what it measured:

```
notes 261
played 261
held 0
sounding 0
song 53.310
render 0.947
reverb 0
chorus 0
soundmodule: cpython 3.12.3 (linux): 0 bytes of MIDI, 0 Identity Requests answered, render behind by at most 0 ms while playing (0 ms before the first note)
  channel  1:  157 notes, bank 0:0 program 8, Celesta
  channel  2:   56 notes, bank 0:0 program 8, Celesta
  channel  3:   32 notes, bank 0:0 program 8, Celesta
  channel 16:   16 notes, bank 0:0 program 8, Celesta
```

`played` equals `notes` when every note sounded. The `render` and interpreter lines are yours to differ on.

[Docs](docs/index.md) | [Examples](apps/ostinato) | [Roadmap](ROADMAP.md)

Made by [PyDevices](https://pydevices.com).
