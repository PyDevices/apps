# Freeze the apps into a firmware

You can build the apps into a MicroPython firmware, so a board has them
without a filesystem copy. Home lists frozen apps beside any in `/apps`, and an
app you install in `/apps` later takes the place of the frozen one of the same
name.

## With omnipython-builds

Name this repository's `apps` folder as a module of the build, after `all` or
whatever else you build:

```bash
git clone https://github.com/PyDevices/apps
./build_mp.py --port esp32 --board ESP32_GENERIC_S3 --variant SPIRAM_OCT --flash 16MB \
    --modules all,../apps/apps
```

That freezes every app, and the libraries in [`lib/`](../../lib) that they
share, appkit among them. The rest of what the apps need (LVGL, icons, the
instruments and effects) comes from the build's other modules: `all` has it.

## From your own board manifest

One line in the board's `manifest.py` does the same:

```python
include("path/to/apps/apps")
```

To freeze some of the apps, name them. An app that draws with another's code
(Huey with Perch's) brings that app too:

```python
include("path/to/apps/apps", apps="home,clock,system")
```

`libs=False` leaves the libraries out, for a build that freezes them
another way. `native=False` takes the `@micropython.native` decorators out of
the frozen copies, for a port with no native code emitter. It's on by default
for the Windows and webassembly ports when the build is from omnipython-builds.

The freeze checks each app's `app.json`, and its icon against the names the
`icons` package has. It finds that package where omnipython-builds puts it, or
on the build's import path, and stops when it's in neither.

## What a frozen app can't do

A freeze carries Python, not files. The index of every app's `app.json` is
frozen as a module, and so are the other files an app reads beside its code,
such as Backline's starter songs. An app reads those through
[`appkit.assets`](../../lib/appkit/assets.py), which finds them frozen when
they aren't on the filesystem. An app of your own that opens a file beside
its code with `open()` needs the same change before it can be frozen.
A file too large to freeze, such as Backline's drum bank, is fetched on the
app's first start ([give Backline its drums](give-backline-its-drums.md)).

A frozen app can't be changed on the board. To try a newer copy, install it
into `/apps` ([install an app](install-an-app.md)): that copy runs instead,
until you remove its folder.
