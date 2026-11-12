# iconkit

Material Design icons as antialiased 8-bit alpha masks in Python modules. Frozen
into MicroPython firmware, an icon lives in flash and costs no RAM, and it draws
in LVGL or in pygraphics.

Two sets ship, filled style, from Google's
[Material Design Icons](https://github.com/google/material-design-icons) (Apache
License 2.0, [LICENSE-ICONS](LICENSE-ICONS)):

- 24 px: 128 general-purpose icons (72 KB), listed in [icons_24.txt](icons_24.txt).
- 48 px: 32 app-tile icons (72 KB), listed in [icons_48.txt](icons_48.txt). All 32 are in the 24 px set too.

Names are Material's own (`home`, `wifi`, `battery_charging_full`). WiFi
strength comes as `network_wifi_1_bar`, `network_wifi_2_bar`,
`network_wifi_3_bar` and `network_wifi`.

## Install

Freeze it: appkit's [manifest.py](../appkit/manifest.py) already includes iconkit,
or `include("/path/to/apps/lib/iconkit")` from your own. Without freezing, the
masks load into RAM when imported, so freeze them on a board that is short of it.

Or install the files from raw GitHub with `mip`, one file at a time (leave out
`_a8_48` if you only use the 24 px set):

```python
import mip

for name in ("__init__", "gfx", "lvicons", "_a8_24", "_a8_48"):
    mip.install("github:PyDevices/apps/lib/iconkit/%s.py" % name, target="/lib/iconkit")
```

## Draw an icon

In LVGL, an icon is an `lv.image` in the colour you give it:

```python
import lvgl as lv
from iconkit import lvicons

lvicons.image(lv.screen_active(), "settings", size=48, color=lv.color_hex(0x40A0FF))
```

In pygraphics, `draw` blends the icon over what the framebuffer already shows.
It needs a pygraphics with `FrameBuffer.blit_alpha`, and raises without it:

```python
from iconkit import gfx

gfx.draw(display, "home", 10, 10, 0xFFFF)
```

A display with no framebuffer can take the icon blended onto a flat background
as an RGB565 buffer: `gfx.rgb565("home", color, bg)`. Pass the returned buffer
back as `buf=` to reuse it.

`iconkit.mask("home")` gives the raw `(data, w, h)` for anything else: `data` is
a memoryview of `w * h` alpha bytes, row by row.

An unknown name or size raises `ValueError` and lists what exists.

## Your own icons

[tools/make_icons.py](../../tools/make_icons.py) builds a module in the same
format from any Material icon names. It needs Pillow and a Material Design Icons
checkout, which you name on the command line:

```bash
python tools/make_icons.py path/to/material-design-icons --size 24 \
    --names home,wifi,sd_card --out myicons.py
```

Put `myicons.py` in your app and register it:

```python
import iconkit
import myicons

iconkit.add(myicons)
iconkit.mask("sd_card")
```

A name that another module of the same size already has raises `ValueError`.
`--names-file` takes a list with one name per line and `#` comments, and
`--budget 72k` fails the run when the masks outgrow a size you set.

## Fetch only the icons you need

The full repository is several gigabytes. A sparse checkout fetches just the PNGs
of one size:

```bash
git clone --filter=blob:none --depth 1 --no-checkout https://github.com/google/material-design-icons.git
cd material-design-icons
git sparse-checkout set --no-cone /LICENSE '/png/*/*/materialicons/24dp/1x/'
git checkout
```

That downloads about 125 MB (git's pack of the file listing, plus the 2,170 icons
at 24 px, which are 430 KB themselves). Git still writes an index of the whole
tree, so expect about 800 MB on disk. Each further size is one more pattern, and
adds 2,170 files and about 0.7 MB:

```bash
git sparse-checkout add '/png/*/*/materialicons/48dp/1x/'
```
