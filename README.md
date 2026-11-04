![Ostinato, the pattern sequencer, playing a four-bar drum pattern in its desktop window](docs/ostinato.png)

# Apps

The apps for PyDevices: things you run on a board or a desktop.

## Install

The apps are used from a clone, beside the libraries they build on:

```bash
git clone https://github.com/PyDevices/apps
git clone https://github.com/PyDevices/audioinstruments
git clone https://github.com/PyDevices/audioeffects
git clone https://github.com/PyDevices/audiodsp
pip install ./audiodsp numpy
pip install --no-deps ./audioinstruments ./audioeffects/lib/audioeffects
```

The libraries the apps share (`appkit`, `controlkit`, `deskkit`, `sayso`,
`songmodel`, `soundmodule`, `spectrum` and `touchkit`) also install as a package, under
their own names. Each is imported directly, as in `import controlkit`:

```bash
pip install -i https://test.pypi.org/simple/ omnipython-applibs
```

On a board, use `mip.install("applibs", index="https://lib.omnipython.org")`.
To freeze them into firmware, name this repository's folder as a module of the
build: its [manifest.py](manifest.py) lists them.

## Try it

Render a MIDI file through the sound module to a WAV, with no MIDI hardware.
The sound comes from a General MIDI SoundFont (`.sf2`) that you supply, such
as [GeneralUser GS](https://schristiancollins.com/generaluser.php):

```bash
cd apps
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

[Docs](docs/index.md) | [Examples](https://gallery.omnipython.org) | [Roadmap](ROADMAP.md)

Made by [PyDevices](https://pydevices.com).
