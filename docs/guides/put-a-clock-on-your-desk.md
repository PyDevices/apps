# Put a clock and the weather on your desk

You can turn a round touch board into a desk clock that also shows the weather.
It needs no account or key, only Wi-Fi. This was built on a LILYGO T-RGB 2.1"
round board with MicroPython and LVGL. Any LVGL touch board should work, but
the layouts were only checked at 480x480.

## Put it on the board

From a clone of this repository, with the board on USB as `PORT`:

```bash
for d in /lib/appkit /lib/deskkit /apps /apps/clock /apps/weather; do mpftp mkdir -d PORT $d; done
for f in lib/appkit/*.py; do mpftp put -d PORT $f /lib/appkit/$(basename $f); done
for f in lib/deskkit/*.py; do mpftp put -d PORT $f /lib/deskkit/$(basename $f); done
for f in apps/clock/* apps/weather/*; do mpftp put -d PORT $f /$f; done
touch empty.py && mpftp put -d PORT empty.py /apps/__init__.py
```

Then make this the board's `main.py`:

```python
import deskkit

deskkit.run()
```

The firmware needs `lvgl`, `requests` and the `omnipython` package, which has
`wifi_manager`.

## The first time it starts

1. **Wi-Fi.** The screen shows a QR code. Join the board's network with your
   phone, then pick your own network and type its password. The board remembers
   it. The [Wi-Fi guide](https://github.com/PyDevices/omnipython/blob/main/docs/guides/wifi.md)
   has the details. It needs a network with a plain password: one with a
   sign-in page or a company login won't work.
2. **Where you are.** The board asks [ipwho.is](https://ipwho.is) where its
   public IP address is. The weather shows that city's forecast straight away,
   marked with a location pin, and the clock follows its timezone. Like any web service,
   ipwho.is sees the board's public IP address. It asks again each day, so the
   clock follows daylight saving.
3. **ZIP code, if you want one.** An IP address often points at your
   provider's nearest city rather than your own. Hold your finger on the
   weather, type your US ZIP code on the keypad and press the check mark. The
   weather is for that place from then on, the clock follows its timezone, and
   the board remembers it. Only a place you choose is saved.

If the lookup fails, the weather asks for a ZIP code instead, the clock keeps
the timezone it had (UTC on a fresh start), and the board tries again the next
day.

## Using it

Swipe left or right to move between the clock and the weather. After a minute
without a touch, the weather goes back to the clock.

On the weather, swipe up for the next five days and down to come back. Hold your
finger on the screen to choose a ZIP code or switch between °F and °C. To back
out without changing the place, press the delete key with nothing typed. On the
city from the IP address, °F or °C lasts until the board restarts; choose a ZIP
code to keep it.

The forecast updates every 30 minutes. When the board can't reach the service,
it keeps the last forecast and shows "as of" with its time.

## Choose when the screen is on

By default the screen is lit from 7:00 until 18:00, Monday to Friday. A touch
wakes it for a minute at other times. To change that, pass the hours in
`main.py`:

```python
deskkit.run(awake=(8, 22), weekends=True)   # 8:00 until 22:00, every day
deskkit.run(awake=None)                     # always on
```

## Change the clock's face

Set `FACE` in [`apps/clock/__init__.py`](../../apps/clock/__init__.py) to any
name in `BUILTIN_SKINS` in [`apps/clock/face.py`](../../apps/clock/face.py), or
add a new entry there.

## Weather data

The weather comes from [Open-Meteo](https://open-meteo.com), which is free for
non-commercial use. A commercial product needs one of its paid plans.
