# Install an app on a board

You can put any app in this repository on a Wi-Fi board with one line at its
REPL. The board fetches the app from GitHub and what it needs from the
OmniPython index and micropython-lib, then Home lists it.

## Before you start

The board needs OmniPython firmware with LVGL, its board config, and Wi-Fi
details in `secrets.py` (`omip` asks at the REPL if there's none). The board
config is one line too; the name is the board's folder under
[board_configs](https://github.com/PyDevices/pydevices/tree/main/board_configs):

```python
import omip
omip.install("github:PyDevices/pydevices/board_configs/busdisplay/i80/wt32sc01-plus")
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
mip.install("github:PyDevices/pydevices/lib/omip.py", target="/")
```

CircuitPython has no `mip`, and `omip` skips itself as frozen unless you force
it:

```python
import omip
omip.install("github:PyDevices/pydevices/lib/omip.py", target="/", force=True)
```

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
`/lib`: appkit and touchkit from the OmniPython index, vtterm for the REPL app,
`requests` from micropython-lib for the apps that go online. Anything the
firmware has frozen in is skipped. On a WT32-SC01 Plus over Wi-Fi each of these
took between 6 and 22 seconds.

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
tag of this repository, for the app's own files. What it needs from the index
is that index's latest release.

What each app does, and what it needs from the board, is in
[the apps](../reference/apps.md). How `omip` finds packages is in pydevices'
[bring-up guide](https://github.com/PyDevices/pydevices/blob/main/docs/guides/bring-up-a-board.md#2-installing-over-wi-fi).
