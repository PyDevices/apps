# What an appkit app must provide

## The folder

| Requirement | Enforced by |
|---|---|
| A folder directly under `apps/`, with an `app.json` | [`launcher.py`](../../lib/appkit/launcher.py) lines 590–630 |
| `app.json` is a JSON object | [`index.py`](../../lib/appkit/index.py) line 49 |
| `name` is the app's name; the folder's name is the default | [`launcher.py`](../../lib/appkit/launcher.py) line 625 |
| `title` is the text a home screen shows; the name is used when it's missing | [`home.py`](../../lib/appkit/home.py) line 18 |
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

## Fields a home screen reads

These are optional. A home screen that reads them places the app; the apps
repo's [Home](../../apps/home/__init__.py) does.

| Field | Meaning | Read by |
|---|---|---|
| `category` | The page the app's tile is on. Pages are in alphabetical order. No category: the app is on a "More" page, last. | [`apps/home/__init__.py`](../../apps/home/__init__.py) lines 77–80 |
| `symbol` | A name on `lv.SYMBOL`, such as `"AUDIO"`. Default `"LIST"`. | [`apps/home/__init__.py`](../../apps/home/__init__.py) line 65 |
| `color` | The tile's colour as `"#RRGGBB"`. Default `"#44505E"`. | [`apps/home/__init__.py`](../../apps/home/__init__.py) line 66 |
| `tile` | `false` keeps the app off the pages. Default `true`. | [`apps/home/__init__.py`](../../apps/home/__init__.py) line 75 |
| `gear` | `true` on the one app the gear button opens. | [`apps/home/__init__.py`](../../apps/home/__init__.py) lines 94–96 |
