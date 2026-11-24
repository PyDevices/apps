![Ostinato, the pattern sequencer, playing a four-bar drum pattern in its desktop window](docs/ostinato.png)

# Apps

The apps for PyDevices: things you run on a board or a desktop. A Home app lives in `apps/`; a program, which runs on its own, lives in [`programs/`](programs/README.md).

## Install

On a Wi-Fi board, one line installs every app with what each needs, and
another starts Home at boot ([install an app](docs/guides/install-an-app.md)
has the lines for one app at a time):

```python
import omip
omip.install("github:PyDevices/apps/apps")
omip.install("github:PyDevices/apps/apps/home/main.py", target="/")
```

On a computer, pip installs every app as the package `apps`, from the main
branch, with the libraries they share and everything else they need:

```bash
pip install "omnipython-apps @ git+https://github.com/PyDevices/apps#subdirectory=apps"
```

Every app installs, whether or not it can run there; one that can't says why
when you start it. To build the apps into a firmware instead, see
[freeze the apps](docs/guides/freeze-the-apps.md).

The libraries the apps share, every folder in [`lib/`](lib), also install as
one package. Each is imported directly, as in `import controlkit`:

```bash
pip install "omnipython-applibs[apps]"
```

The `apps` extra brings LVGL and omnipython-desktop, which controlkit, appkit
and the other libraries that draw need on a computer. On a board, use
`mip.install("applibs", index="https://lib.omnipython.org")`. To freeze them
into firmware, name this repository's folder as a module of the build: its [manifest.py](manifest.py) lists them.

To work on the apps, or run the sound module and Vamp from a clone, see
[install](docs/get-started/install.md).

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
