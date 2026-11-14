![the camera's main menu](docs/screens/01-main-camera.png)

# Camera

Camera is a camera app for an ESP32-P4 board: photos, H.264 video with sound,
an album, the card as a USB disk, pedestrian and face detection, four screen
rotations and interval shooting. It is the ESP32-P4X-EYE's own camera app,
screen for screen, written as a PyDevices app so that other boards run it too.

Runs on: the ESP32-P4X-EYE, and desktop MicroPython at 240x240 or larger.
Other ESP32-P4 boards run the same code and step down to what they have, but
haven't been tried yet; the USB camera source is written and not yet run on a
camera. [What each board does](docs/how-it-works.md#what-a-board-needs).

## Try it on a desktop

You need desktop MicroPython with LVGL and the PyDevices libraries
(`bin/micropython` from micropython-pydevices). From this folder:

```
MICROPYTHON=path/to/micropython tools/run.sh
```

The picture is a test card with a figure walking across it. The keys stand in
for the board:

| Key | Board control |
|---|---|
| M | Menu button |
| Up, Down | Up and Down buttons |
| Enter, middle mouse button | knob press |
| `+` and `-`, mouse wheel | one knob detent left or right (three make a step) |
| S | card in or out |
| F | card full |
| U | a USB host on the upper port, or not |
| R | turn the board 90 degrees |

The mouse works as a touch screen too: click a Menu, Up or Down picture, click
the page for the knob press, and drag up or down to turn the knob.

`PYDEVICES_WIDTH` and `PYDEVICES_HEIGHT` pick a bigger panel. The layout is
drawn once at 240x240, enlarged by a whole number and centred, so
`PYDEVICES_WIDTH=720 PYDEVICES_HEIGHT=720 tools/run.sh` shows it at 3x.

## Put it on a board

The firmware is MicroPython from micropython-pydevices with `cameraif`, `ppa`,
`jpegio`, `h264enc` and `vision`. Install your board's package from
[pydevices](https://github.com/PyDevices/pydevices) first, then put the app on
it:

```
mpftp put eye_camera.py /eye_camera.py
mpftp put -r apps/eyecam /apps/eyecam
```

and make `main.py` say `import eye_camera`. The app is about 1.4 MB with its
pictures and fonts. [Putting the rest on the card and the board](docs/how-it-works.md#what-a-board-needs)
(models, `mp4mux`, the Eye's own parts) is in the guide; the models are
downloaded from [these links](../../docs/reference/models.md).

Docs: [how it works](docs/how-it-works.md). Examples: [the shot lists](tools).
Roadmap: [ROADMAP.md](../../ROADMAP.md).

The factory pictures are Espressif's, under the Apache licence, and the
fonts are KoHo, under the SIL Open Font Licence: see [NOTICE](NOTICE).

Made by [PyDevices](https://pydevices.com).
