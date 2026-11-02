# What an appkit app must provide

An app is a folder under `apps/` that appkit can find, import and run. This page
lists what that takes and where each rule is enforced, so you can check an app
against the code instead of against memory.

## The folder

- The app is a folder directly under `apps/`, with an `app.json`. The folder's
  name is the app's name unless `app.json` gives one.
- `app.json` is a JSON object. Anything else is rejected with an error that
  names the file ([`lib/appkit/index.py`](../../lib/appkit/index.py) line 49).
- `name` is the app's name on the home screen and in the launcher. `title` is
  what the tile says.
- `apps/` is a package: it needs an `__init__.py`. The launcher makes one if it
  can write to the folder, and says so if it can't
  ([`lib/appkit/launcher.py`](../../lib/appkit/launcher.py) lines 162–176).
- An app with an `app.json` but no `__init__.py` is refused when the apps are
  frozen into a firmware ([`index.py`](../../lib/appkit/index.py) line 136).

## A module app

- The app's `__init__.py` defines `main(scope)`. Its import does nothing else:
  no screens, no timers, no devices. The launcher imports the app as
  `apps.<folder>`, so a name that clashes with a library is still fine
  ([`launcher.py`](../../lib/appkit/launcher.py) lines 620–630).
- `main(scope)` is called with the app's scope. Timers created during `main`
  wait until it returns ([`launcher.py`](../../lib/appkit/launcher.py) lines 841–845).
- Everything the app makes goes through `scope`: its screen, its timers, its
  event subscriptions, its devices, its background jobs. Closing the scope
  releases them, and `scope.close()` returns a list of anything it couldn't
  release ([`lib/appkit/scope.py`](../../lib/appkit/scope.py)). The app should
  come back with an empty list.
- Background work goes through `scope.worker`, and its results come back on
  the main thread through `done`.

## A plain script

- `app.json` names the module with `"script": "<module>"`. The script builds its
  own `App`. Choosing it restarts the program into it.
- A program that builds its own launcher calls `appkit.run_pending_script()` first
  thing in `main.py`, before anything opens the display. `appkit.run()` does this for
  you ([appkit README](../../lib/appkit/README.md#a-plain-script)).
- A launcher on a CircuitPython board can't run scripts yet
  ([`launcher.py`](../../lib/appkit/launcher.py) line 375).

## Where to read more

The [appkit README](../../lib/appkit/README.md) has the layout in full, the scope
API, the frozen build and how the launcher picks its home screen.
