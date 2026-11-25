# Install an app on a board

You can put any app in this repository on a Wi-Fi board with one line at its
REPL. The board fetches the app from GitHub and what it needs from the
OmniPython index and micropython-lib, then Home lists it.

## Before you start

The board needs OmniPython firmware with LVGL, its board config, and Wi-Fi
details in `secrets.py` (`omip` asks at the REPL if there's none). The board
config is one line too; the name is the board's folder under
[board_configs](https://github.com/PyDevices/omnipython/tree/main/board_configs):

```python
import omip
omip.install("github:PyDevices/omnipython/board_configs/busdisplay/i80/wt32sc01-plus")
```

On a CircuitPython board with native USB, the `CIRCUITPY` drive belongs to
your computer, and every install fails with `Read-only filesystem`. Put this
`boot.py` on the drive to hand it to the board, then reset the board. Don't
write to the drive from your computer while the board owns it.

```python
import storage
storage.remount("/", readonly=False)
```

Installing an app needs a current `omip`. Your firmware's copy is older if
`omip.install` on an app puts `app.json` in `/lib`, or if midiEngine's install
copies `/lib/audioinstruments` although the firmware has it frozen in, which
fills a 2 MB filesystem. Put the current one at the board's root, where it runs
ahead of the frozen one, then reset the board:

```python
import mip
mip.install("github:PyDevices/omnipython/lib/omip.py", target="/")
```

CircuitPython has no `mip`, and `omip` skips itself as frozen unless you force
it:

```python
import omip
omip.install("github:PyDevices/omnipython/lib/omip.py", target="/", force=True)
```

On an Arduino GIGA, whose firmware has no `omip`, the writable drive is
`/flash`: put `omip` on it with `mip.install(..., target="/flash/lib")`, and use
`target="/flash"` where a line below says `target="/"`. The
[GIGA Display Shield page](https://github.com/PyDevices/omnipython/blob/main/docs/boards/arduino-giga-display-shield.md)
has the lines.

## Install apps

Name the app's folder under [`apps/`](../../apps):

```python
import omip
omip.install("github:PyDevices/apps/apps/home")
omip.install("github:PyDevices/apps/apps/system")
omip.install("github:PyDevices/apps/apps/bit_world")
```

The full list, with what each app does and needs, is in
[the apps](../reference/apps.md); any folder there installs the same way.

Each app lands in `/apps/<name>`, where Home looks, and what it imports goes in
`/lib`: appkit, touchkit and the other libraries the apps share from the
OmniPython index, as one package (`applibs`), vtterm for the REPL app,
`requests` from micropython-lib for the apps that go online. Anything the
firmware has frozen in is skipped. On a WT32-SC01 Plus over Wi-Fi each of these
took between 6 and 22 seconds.

On CircuitPython, a long run of installs can reach a point where every request
fails at once with `[Errno 5] Input/output error`, or where the board can't
join Wi-Fi again. Ctrl-D doesn't clear it. Reset the board with its reset
button, or with `import microcontroller; microcontroller.reset()`, and run the
line that failed again. What was already installed stays, so you carry on from
that app.

## Install every app

One line puts every app in this repository on the board, each in its own
folder under `/apps`, with what each needs:

```python
import omip
omip.install("github:PyDevices/apps/apps")
```

Every app installs, whether or not the board can run it. One that can't says
why when you start it, and Home can hide it. The apps take about 1.5 MB.
What they need from the index takes up to 1.9 MB more, less whatever your
firmware has frozen in: an `--modules all` build already has most of it. Give
the board 4 MB free to be safe. It leaves alone any app in `/apps` that isn't
from this repository.

Home draws its icons with `ttfio`, which is part of the firmware, not a file
omip can install. A firmware built before `ttfio` was added can't start Home
once the apps are current (`ImportError: no module named 'ttfio'`): flash a
current build first.

Run the same line again to update every app. It fetches each app's files
afresh, so a changed file is replaced. It never deletes, so a file an app no
longer has stays on the board, unused. To clear those out, remove the app's
folder and run the line again.

## Install a program that is an app

Camera, the ESP32-P4 camera program, is an app too. Its line names the
program's folder under [`programs/`](../../programs), and it lands in
`/apps/eyecam`, where Home lists it:

```python
omip.install("github:PyDevices/apps/programs/camera")
```

It needs a firmware with the camera modules and, for detection, model files on
the card: its [README](../../programs/camera/README.md#put-it-on-a-board) says
which.

## Start Home when the board starts

Home's `main.py` goes at the board's root:

```python
omip.install("github:PyDevices/apps/apps/home/main.py", target="/")
```

Reset the board. Home comes up with a tile for each app you installed, and the
gear opens System. On CircuitPython, remove `code.py` first (`os.remove("/code.py")`):
CircuitPython runs it ahead of `main.py`, and a freshly erased board has one. Installing Home doesn't touch `main.py`, so a board that
starts something else keeps doing so until you run this line.

A board that should start in Camera, as a camera does, takes Camera's
`main.py` in its place:

```python
omip.install("github:PyDevices/apps/programs/camera/main.py", target="/")
```

Like Home's, it joins the Wi-Fi in `secrets.py` and starts WebREPL once the
picture is up. A board with no `secrets.py` starts Camera offline.

## Updating, and a particular version

Running the same line again fetches the app's files afresh. Without
`version=` you get the default branch; `version=` takes another branch or a
tag of this repository, for the app's own files. What it needs from the index,
the shared libraries (`applibs`) among them, is that index's latest release,
which can be a pre-release. So the libraries on a board follow the latest
pre-release, while the apps follow the default branch.

A file an app no longer has stays on the board: `omip` replaces files, and
never deletes one. Remove the app's folder first for a clean copy.

What each app does, and what it needs from the board, is in
[the apps](../reference/apps.md). How `omip` finds packages is in omnipython'
[bring-up guide](https://github.com/PyDevices/omnipython/blob/main/docs/guides/bring-up-a-board.md#2-installing-over-wi-fi).
