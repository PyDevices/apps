# What an appkit app must provide

## The folder

| Requirement | Enforced by |
|---|---|
| A folder directly under `apps/`, with an `app.json` | [`launcher.py`](../../lib/appkit/launcher.py) lines 590–630 |
| `app.json` is a JSON object | [`index.py`](../../lib/appkit/index.py) line 49 |
| `name` is the app's name; the folder's name is the default | [`launcher.py`](../../lib/appkit/launcher.py) line 625 |
| `title` is the tile's text, and the name is used when it's missing | [`home.py`](../../lib/appkit/home.py) line 18 |
| `apps/` has an `__init__.py` (the launcher writes one if it can) | [`launcher.py`](../../lib/appkit/launcher.py) lines 161–176 |
| An `app.json` with no `__init__.py` is refused in a frozen build | [`index.py`](../../lib/appkit/index.py) line 136 |

## A module app

| Requirement | Enforced by |
|---|---|
| `__init__.py` defines `main(scope)` | [`launcher.py`](../../lib/appkit/launcher.py) line 841 |
| Import has no effect beyond defining `main` | Convention; the launcher imports the app as `apps.<folder>` ([`launcher.py`](../../lib/appkit/launcher.py) line 630) |
| Timers made during `main` start when it returns | [`launcher.py`](../../lib/appkit/launcher.py) lines 843–844 |
| Everything made goes through `scope`, and `scope.close()` returns `[]` | [`scope.py`](../../lib/appkit/scope.py) line 469 |
| Background work uses `scope.worker`; results return through `done` on the main thread | [`worker.py`](../../lib/appkit/worker.py) line 164 |

## A plain script

| Requirement | Enforced by |
|---|---|
| `app.json` has `"script": "<module>"`; the script builds its own `App` | [`launcher.py`](../../lib/appkit/launcher.py) lines 626–628 |
| Choosing a script restarts the program into it | [appkit README](../../lib/appkit/README.md#a-plain-script) |
| A program that builds its own launcher calls `appkit.run_pending_script()` first in `main.py` | [appkit README](../../lib/appkit/README.md#a-plain-script) |
| CircuitPython boards can't run scripts | [`launcher.py`](../../lib/appkit/launcher.py) line 375 |
