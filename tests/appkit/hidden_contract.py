# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Hiding an app that can't run here, on real LVGL with no window.

The repository's own Home runs through a real Launcher beside Nowhere
(`cant_run_app`), which shows touchkit's shared can't-run message as an
app missing its hardware does. Its "Hide from Home" button takes it off Home's pages; the
Hidden apps app, always on Home's System page, lists it with its reason and
puts it back. Run alone, with no home screen, it offers no Hide button.

    APPKIT_DATA=/tmp/hidden python tests/appkit/hidden_contract.py
    micropython tests/appkit/hidden_contract.py

``HIDDEN_PLANT=<name>`` breaks it one way from `PLANTS`, and the checks
must then fail. Exits 1 if a check fails, 2 if something it needs isn't there.
"""

import os
import sys


def _up(path):
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _join(*parts):
    return "/".join(parts)


_HERE = _up(__file__)
_TESTS = _up(_HERE)
_ROOT = _up(_TESTS)
_LIB = os.getenv("OMNIPYTHON_LIB") or _join(_ROOT, "..", "omnipython", "lib")
_OMNI = _up(_LIB)
# lib first: tests/appkit would hide the real appkit.
_PATHS = [_join(_ROOT, "lib"), _HERE, _TESTS,
          _join(_OMNI, "packages", "icons"),
          _join(_OMNI, "packages", "iconkit", "lib"), _LIB]
if sys.implementation.name != "micropython":
    _PATHS.append(_join(_OMNI, "utils"))   # ttfio over freetype-py; a board has it built in
sys.path[:0] = _PATHS

try:
    import icons  # noqa: F401
    import lvgl as lv
except ImportError as e:
    print("can't run the hidden-apps checks:", e)
    sys.exit(2)

import _headless  # noqa: E402

failures = []
checks = [0]


def check(ok, what):
    checks[0] += 1
    if not ok:
        failures.append(what)
        print("FAILED:", what)


SW, SH = 800, 480
_headless.display(SW, SH)
_headless.pointer()

import time  # noqa: E402

from appkit import launcher as L  # noqa: E402
from appkit.shell import Shell  # noqa: E402
from appdev import App  # noqa: E402
from touchkit import ui  # noqa: E402

# -- plants: each must make a check fail -------------------------------------


def _plant_home_ignores():
    # Home asks the launcher what's hidden; here the answer is always nothing.
    L.Launcher.hidden = lambda self: {}


def _plant_no_button():
    ui.button = lambda *a, **k: (lv.obj(lv.layer_sys()), None)


def _plant_not_saved():
    L._save_hidden = lambda hidden: None


PLANTS = {
    "home_ignores": _plant_home_ignores,
    "no_button": _plant_no_button,
    "not_saved": _plant_not_saved,
}
plant = os.getenv("HIDDEN_PLANT")
if plant:
    PLANTS[plant]()


def settle(ms=200):
    for _ in range(ms // 20):
        _headless.advance(20)


def coords(obj):
    obj.update_layout()
    a = lv.area_t()
    obj.get_coords(a)
    return a.x1, a.y1, a.x2 - a.x1 + 1, a.y2 - a.y1 + 1


def tap(obj):
    obj.scroll_to_view_recursive(False)
    x, y, w, h = coords(obj)
    _headless.touch(x + w // 2, y + h // 2, True, 50)
    _headless.touch(x + w // 2, y + h // 2, False, 50)


def labels(obj, out=None):
    out = [] if out is None else out
    for i in range(obj.get_child_count()):
        c = obj.get_child(i)
        if c.check_type(lv.label_class):
            out.append((c.get_text(), c))
        labels(c, out)
    return out


def texts(obj):
    return [t for t, _ in labels(obj)]


def find(obj, text):
    for t, lbl in labels(obj):
        if t == text:
            return lbl
    return None


def wait_for(la, name):
    # The launcher switches from a timer on the real clock: wait for it, up to 3 s.
    for _ in range(60):
        if la.current == name:
            break
        time.sleep(0.05)
        settle(40)
    settle()


def stored(la):
    return dict(la._hidden or {})


def until(cond):
    # Home's switches run from a timer on the real clock: wait for one, up to 3 s.
    for _ in range(60):
        if cond():
            break
        time.sleep(0.05)
        settle(40)
    settle()


restarts = []


def _no_restart(name, count=1):
    restarts.append(name)
    raise OSError("restarts are recorded, not done, in these checks")


L.restart_into = _no_restart

# -- Home and Nowhere ---------------------------------------------------------

la = L.Launcher(App.current() or App())
la.scan(_join(_ROOT, "apps"))
la.add("nowhere", "cant_run_app")
la.info["nowhere"] = {"name": "nowhere", "title": "Nowhere", "category": "Audio", "icon": "sports_esports", "color": "#445566"}
la.home = "home"
la.shell = Shell(la)
la.boot("home")
settle()
check(stored(la) == {}, "nothing is hidden at first: %r" % (stored(la),))
check("Nowhere" in texts(la.scope.root), "Nowhere has a tile on Home")

la.switch("nowhere")
settle()
hide = find(la.scope.root, "Hide from Home")
check(hide is not None, "a can't-run screen with a home to go to offers Hide from Home: %r" % (texts(la.scope.root),))
if hide is not None:
    tap(hide.get_parent())
    wait_for(la, "home")
check(la.current == "home", "hiding goes home: %r" % (la.current,))
check(stored(la) == {"nowhere": "no radio for this"}, "the hidden list keeps the reason: %r" % (stored(la),))
check(L._load_hidden() == {"nowhere": "no radio for this"}, "and it's saved for the whole device: %r" % (L._load_hidden(),))
check("Nowhere" not in texts(la.scope.root), "Home leaves a hidden app off its pages")
check(restarts == [], "nothing restarted: %r" % (restarts,))

# Hiding changes only Home: the app still runs.
la.switch("nowhere")
settle()
check(la.current == "nowhere" and "no radio for this" in texts(la.scope.root), "a hidden app still runs when asked")
la.switch("home")
settle()

# The Hidden apps app, from its tile.
tile = find(la.scope.root, "Hidden apps")
check(tile is not None, "Home has a Hidden apps tile")
if tile is not None:
    tap(tile.get_parent())
    wait_for(la, "hidden")
on_page = texts(la.scope.root)
check(la.current == "hidden" and "Nowhere" in on_page and "no radio for this" in on_page,
      "Hidden apps lists the app with its reason: %r" % (on_page,))
check(not [t for t in on_page if t.endswith("Back")], "and has no Back button of its own: Home goes back")
unhide = find(la.scope.root, "Unhide")
if unhide is not None:
    tap(unhide.get_parent())
    settle()
check(stored(la) == {}, "Unhide puts it back: %r" % (stored(la),))
check(find(la.scope.root, "Unhide") is None and any(t.startswith("No app is hidden") for t in texts(la.scope.root)),
      "with the last one back, the app says none is hidden: %r" % (texts(la.scope.root),))
la.switch("home")
settle()
check("Nowhere" in texts(la.scope.root) and "Hidden apps" in texts(la.scope.root),
      "back on Home, the app has its tile again, and Hidden apps keeps its own")
la.switch("hidden")
settle()
check(find(la.scope.root, "Unhide") is None and any(t.startswith("No app is hidden") for t in texts(la.scope.root)),
      "opened with nothing hidden, it says so: %r" % (texts(la.scope.root),))
la.stop()

# -- run alone ------------------------------------------------------------------

alone = L.Launcher(App.current() or App())
alone.add("nowhere", "cant_run_app")
alone.shell = Shell(alone)
alone.boot("nowhere")
settle()
check(find(alone.scope.root, "Hide from Home") is None, "run alone, there's no home to hide it from: no button")
alone.stop()

print("%d checks, %d failed" % (checks[0], len(failures)))
sys.exit(1 if failures else 0)
