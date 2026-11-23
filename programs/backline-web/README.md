# Backline in a web page

Backline's drum machine, in a browser tab. The page can be the box itself:
it plays the songs through the computer's speakers, shows the floor view,
and takes the pedals from the space bar, the B key or the two pads under
the view. Or it can be the desk for a box somewhere else, showing the same
desk view a board's big screen does.

Either way a board can be the other half. A board with a screen joins the
page's box as its desk, over USB or Bluetooth. A board running Backline is
the box, and the page joins it as a desk over Bluetooth, USB or the network.

Runs on: Chrome or Edge on a computer (Web Bluetooth and WebSerial need
them; the box alone plays in any browser with WebAssembly). The page is
Python, run by MicroPython's WebAssembly build with LVGL, the audio modules
and the Backline app from this repository.

## Serve the page

You need an OmniPython checkout (for hmilink and the icons) and MicroPython's
WebAssembly build, `micropython.mjs` and `micropython.wasm`, in one folder.
From this repository:

```
python programs/backline-web/tools/page.py serve --omnipython ../omnipython --wasm ../omnipython/bin
```

Then open <http://localhost:8930/>. `page.py build OUT` writes the same site
as plain files, for any web server. Browsers allow Bluetooth and USB only on
`localhost` or over HTTPS.

## Play here: the page is the box

Open **Play here** (`?role=box`). Click the page once so the browser lets it
play sound, then tap the space bar to start the song. A tap plays a fill,
holding the pedal moves to the next part, and two taps end the song.
`?song=rock&kit=rhythm909` picks the song and kit to start on.

To give the box a desk on a board, start the desk on the board first, then
click **USB** or **Bluetooth** under the view and choose the board. With
Backline in `/apps/backline` on the board, and hmilink with its Bluetooth
link (`hmilink.ble`), from the board's REPL:

```python
from backline import desk_main
desk_main.main(["ble:Backline"])
```

The board advertises as `Backline`, the name in the box next to the
Bluetooth button. `desk_main.main(["usb"])` waits on a second USB serial port
instead. The board's screen needs to be at least 640x400.

## Desk for a box

Open **Desk for a box** (`?role=desk`) and join the box:

- **Bluetooth**, to a board running Backline whose settings name it. Put
  `{"ble": "Backline"}` in `settings.json` in the app's data folder
  (`/data/backline/` on a board), and start Backline from Home.
- **Network**, to any running Backline on the network: type its address in
  the box and click it. The box listens for desks on port 9300.
- **USB**, to a box that serves its desk link on a serial port. Backline on
  a board doesn't do that yet.

Space and B are the pedals, as on the box.

## Checks

`tests/test_backline_web.py` runs both pages in headless Chromium, with
the board's half in the test's own process. See the top of that file for
what it needs.
