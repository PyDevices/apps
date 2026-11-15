# appkit

Run several apps in one program, switch between them, and get each app's
memory back when it closes. A launcher and the apps it runs make an **app
set**: a watch with a face, a step counter and a TV remote, or a panel with
a camera, a music player and a home screen.

appkit builds on [appdev](https://github.com/PyDevices/pydevices/blob/main/docs/guides/the-app-loop.md)
and runs wherever appdev does: CPython, MicroPython and CircuitPython, on a
desktop or a board. You don't need it to write an app. A script that builds
an `App` and runs works exactly as before. appkit is for when you want
several apps on one device and a way to move between them.

## Install

pydevices is frozen into the firmware, and appkit needs it for `appdev`,
`events` and `multimer`. appkit itself comes from this repository: copy the
files of [`lib/appkit`](lib/appkit) to `/lib/appkit` on a board, with
[mpftp](https://github.com/PyDevices/mpftp), `mpremote` or any file tool. On a
CPython or CircuitPython desktop, put this repository's `lib` on `PYTHONPATH`.

appkit's Home and its apps draw with [iconkit](https://github.com/PyDevices/pydevices/tree/main/packages/iconkit), which lives in the pydevices repository as its own package (`omnipython-iconkit`). Including appkit's `manifest.py` in a firmware build freezes iconkit with it, from the folder you pass as `iconkit=` (pydevices' `packages/iconkit`) or, without that, from the omnipython-lib tree in `$PYDEVICES_LIBRARY`; with neither the build stops and says so. Getting appkit with `require("appkit", library="omnipython-lib")` brings iconkit along. Otherwise install iconkit the way you do pydevices itself.

On a Wi-Fi board, `omip` installs appkit, or an app with
everything it needs, into the folders appkit looks in:

```python
import omip
omip.install("appkit")
omip.install("github:PyDevices/apps/apps/home")
```

[Install an app](../../docs/guides/install-an-app.md) has the rest, and the
`main.py` that starts Home at boot.

## An app

An app is a module, or a package, with a `main(scope)` that does nothing
at import time. It makes everything through `scope`:

```python
import lvgl as lv

def main(scope):
    label = lv.label(scope.root)
    label.set_text("0 s")
    seconds = [0]

    @scope.every(1000)
    def tick(timer):
        seconds[0] += 1
        label.set_text("%d s" % seconds[0])
```

When the app closes, its scope cancels its timers, drops its event
subscriptions, unregisters its devices, deletes its screen and removes its
modules from `sys.modules`.

## What an app gets on `scope`

| | |
|---|---|
| `scope.root` | The LVGL object to build on: the whole screen, or the area a shell leaves for apps |
| `scope.size`, `scope.rect` | `root`'s `(width, height)`, and its `(x, y, width, height)` on the panel, for drawing straight into the framebuffer |
| `scope.worker` | A background thread shared by every app |
| `scope.data_dir` | A folder for the app's own files; `scope.data_dir_of("camera")` is another app's |
| `scope.store()` | A dict that's still there the next time the app opens |
| `scope.foreground(fn)` | The program's main loop calls `fn()` over and over, for work too heavy for a timer |

`scope.worker.submit(work, done)` runs `work()` in the background and then
calls `done(value, error)` on the main thread, so the screen never waits on
the network:

```python
def main(scope):
    label = lv.label(scope.root)

    def done(value, error):
        label.set_text("failed: %s" % error if error else value)

    scope.worker.submit(lambda: fetch_weather(), done, key="weather")
```

A second job with the same `key` replaces one still waiting. When the app
closes, anything it queued and hasn't started is dropped, and a job of its
that finishes later isn't delivered. `scope.worker.busy` is true while the
thread is running a job, any app's: check it before closing a connection
a job might be using. Where there are no threads (the
browser, CircuitPython on a board, MicroPython on Windows) the work runs on
a timer instead, one job at a time.

A blocking call that uses something the app would close at once, such as an
mDNS server, passes `release=`. `release()` runs once for that job, on the
thread after `work()` returns, even if the app has closed by then; a job
dropped before it starts gets its `release()` at close. Close doesn't wait
for a call in progress, and the call is never left using a closed resource:

```python
def main(scope):
    mdns = MDNS()
    scope.worker.submit(lambda: mdns.find("peer", timeout=2), done,
                        key="peer", release=mdns.deinit)
```

Don't also `adopt()` the object that `release` closes, or close will tear it
down while the call still uses it.

`scope.data_dir` is made the first time an app asks for it, at
`<data root>/<app>`, and `scope.data_dir_of(name)` is app *name*'s folder,
for an app that shows another's files. The data root is:

| Where | Data root |
|---|---|
| Linux | `$XDG_DATA_HOME/appkit`, or `~/.local/share/appkit` |
| Windows | `%LOCALAPPDATA%\appkit` |
| macOS | `~/Library/Application Support/appkit` |
| A board, the browser | `/data` |

`appkit.run(data_root="/sd/data")` (or the same argument to `Shell`) moves
it everywhere. Without that, `APPKIT_DATA` moves it on a desktop.

Files a person brings or keeps, like songs, SoundFonts, photos and models, go
in a folder named for their kind, the same name on the SD card, on flash and
in the data root: `/sd/music`, `/music` and `/data/music`. `appkit.places`
reads all three and saves to the first that takes a file, and
`places.hold_card(scope)` mounts the card while the app is open.

`scope.store()` is the app's own dict, kept in RAM while the program runs;
`scope.store("other")` is another app's. Nothing in it is written to flash,
so save what must survive a reset to `data_dir`. Keep plain data in it:
a function or object of the app's would keep the whole app in memory.

## Work too heavy for a timer

Some work can't run from a timer: waiting on each camera frame, or copying
audio every millisecond. Hand it to the program's main loop instead:

```python
def main(scope):
    def frame():
        camera.capture(buffer)      # waits for one frame, then returns
        display.show(buffer)

    scope.foreground(frame)
```

The loop calls `frame()` over and over, outside every timer callback, until
the app closes or calls `scope.foreground(None)`. `appkit.run()` ends in
that loop. A program that builds its own `Launcher` ends in it too, with
`appkit.serve()` as the last line of `main.py`.

There's one foreground function at a time. The timers still preempt it,
so a switch can close the app while its function is mid-call: return
promptly once the app has closed, and anything raised after that is
ignored.

Where nothing runs the loop (a browser page, or the REPL after Ctrl-C), a
function that does one step and returns, like `frame()`, runs from a timer
instead. One that never returns, like an audio loop, says so with
`scope.foreground(loop, steps=False)`. It then waits for the loop, so it
can't take over the REPL, and `scope.foreground()` returns False so the
app can say it's waiting. Ctrl-C in the loop gives you the REPL with every
timer still running, and `appkit.serve()` picks the loop up again. A Ctrl-C
that lands inside a timer's callback is held until the callback ends, so
it sometimes needs pressing twice.

On a CircuitPython board Ctrl-C ends `code.py`, display and all, so there's
no REPL to go to while the apps run. The loop reads the console instead:
type a line and it runs in `code.py`'s namespace, with its value printed.
`launcher.current` or `import apps.system; apps.system.stats()` answer
while the apps keep running.

## An app set

Put each app in its own folder under `apps/`, with an `app.json` naming it:

```text
main.py
apps/
    __init__.py         empty: apps/ is a package
    hello/
        app.json        {"name": "hello", "title": "Hello"}
        __init__.py     def main(scope): ...
    ticker/
        ...
```

Then `main.py` is:

```python
import appkit
appkit.run()            # a home screen with a button for each app
```

The apps are imported as `apps.hello`, `apps.ticker`, so an app can be
called anything, `json` or the name of a library it uses, without either
hiding the other. When `apps/` has no `__init__.py`, `scan()` makes one;
where it can't (a read-only filesystem) it stops with an error saying to
add an empty one.

When `apps/` holds an app named `home`, `appkit.run()` starts that as the
home screen instead of its own list of buttons.

`appkit.run("hello")` runs one app on its own, with the whole screen and no
home screen. An app set that wants its own home screen, chrome or launcher
setup builds a `Launcher` itself. Its `Shell` subclass gives apps a smaller
area by overriding `make_root()`, and its own Home button by overriding
`make_home_button()`. The default Home button sits at the top right; on a
round screen it's a small round button on the diagonal, inside the circle.

[`examples/appkit_simpletest`](examples/appkit_simpletest) is an app set of
two apps, a counter and a greeter, laid out this way.

## Plain scripts

A script that builds its own `App` when it's imported, like a game, can sit
on the home screen too. Give it a folder with an `app.json` that names the
module to run:

```text
apps/
    blocks/
        app.json        {"name": "blocks", "title": "Blocks", "script": "blocks"}
        blocks.py       app = App(board_config) ...
```

A script needs a fresh program, so choosing it restarts into it. The script
has the board until its `App` quits, even if it keeps running on timers
after its last line. Then the program restarts to the home screen.

While a script runs, the board has no WebREPL. The script starts before the
program joins Wi-Fi and starts WebREPL, so connect again after the script
quits, or reset the board.
`launcher.add_script("blocks", "examples.blocks")` registers one without a
folder.

`appkit.run()` runs a pending script before anything else. An app set that
builds its own `Launcher` calls `appkit.run_pending_script()` first thing in
`main.py`, before anything opens the display. Where the script keeps running on
timers after it returns, as on an ESP32, it returns True, and `main.py` then
does nothing more:

```python
from appkit import Launcher, run_pending_script

if not run_pending_script():
    import board_config
    ...
```

On a CircuitPython board the launcher keeps the next app's name in
`/data/.next_app`, so CIRCUITPY has to be writable from code. While a
computer has the drive mounted it isn't: a script then doesn't start, and a
restart for memory carries on in-process instead.

## A frozen build

A firmware build can freeze the apps with appkit. MicroPython can't freeze
an `app.json`, so appkit's manifest turns them into one module,
`_appkit_apps`, and `scan()` reads that when the `apps` folder isn't there.
The apps are frozen as the package `apps`, whatever their folder is
called.
In the board's `manifest.py`:

```python
import os
include("/path/to/appkit", apps=os.path.abspath("apps"))
```

`python -m appkit.index apps -o _appkit_apps.py` writes the same module
from a shell.

## Memory

Three things keep an app's memory alive after it closes, so avoid them:
storing one of its functions or objects in another module (a callback
parked in a shared list), making timers or subscriptions on `scope.app`
instead of `scope`, and helper modules outside the app's own package.

If an app leaks anyway, the launcher notices. After each close it checks
free heap and the largest free block. When either is below its threshold,
or the app's `close()` failed, it restarts the program straight into the
next app: a soft reset on a board, a fresh process on the desktop, a reload
in the browser. On desktop MicroPython and CircuitPython, run the program
under the launcher so it can restart, into an app or a script:

```bash
python -m appkit.launcher -- micropython main.py
```

## What's here

| Path | What it is |
|---|---|
| [`lib/appkit/`](lib/appkit) | The package: `AppScope`, `Launcher`, `Shell`, `run()`, the worker, the foreground loop, the data folders and the index generator |
| [`manifest.py`](manifest.py) | appkit's MicroPython manifest, for a frozen build |
| [`tests/`](tests) | The scope's leak test, the launcher's switch and restart runs, the services on `scope`, and a round trip through a script on a sample app set, on CPython and MicroPython, each with planted faults that must fail |

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

Run them from this folder. They take pydevices' `lib` from this repository
(or `PYDEVICES_LIB`), iconkit from `packages/iconkit/lib` in the same
pydevices checkout (or `ICONKIT_LIB`) and, for the MicroPython half, a unix `micropython`
(from `PYDEVICES_MICROPYTHON` or `PATH`). Without one, the MicroPython checks
skip loudly.

Planned work is in [ROADMAP.md](ROADMAP.md).
