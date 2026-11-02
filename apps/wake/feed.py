# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A USB microphone's audio, brought to what the wake-word model takes:
16 kHz mono 16-bit.

``open_mic`` asks the mic for the model's own rate first. 16 kHz goes
straight in, and a mic that only offers stereo (a webcam's, often) is
downmixed in C as the packets land: usb-host-audio's ``Microphone`` does
that for ``channels=1``. A mic without 16 kHz is opened at 48, 32 or
24 kHz, and ``Feed`` brings it down through a 6th-order elliptic low-pass
at 7 kHz: every third sample of 48 kHz, every second of 32 kHz, and
24 kHz with a zero after each sample (48 kHz) and then every third. A mic
with none of those (44.1 kHz, 8 kHz, 24-bit only) raises ``Unsupported``,
which names what it does offer.

No LVGL or USB here, so a test drives it on CPython or MicroPython with a
stand-in microphone.
"""

try:
    from ulab import numpy as np
    from ulab import scipy as _spy

    _sosfilt = _spy.signal.sosfilt
except ImportError:  # CPython, for the tests
    import numpy as np
    from scipy.signal import sosfilt as _sosfilt

_FLOAT = getattr(np, "float64", None) or np.float  # ulab has only np.float

MODEL_RATE = 16000
#: The rates the app takes, in the order it asks for them, with the
#: (up, down) that brings each to 16 kHz.
PLANS = ((16000, 1, 1), (48000, 1, 3), (32000, 1, 2), (24000, 2, 3))

# scipy.signal.ellip(6, 0.5, 60, 7000, fs=FS, output="sos"): passband to
# 7 kHz within 0.5 dB, 60 dB down above it, at the rate after any zeros.
_SOS = {
    48000: (
        (0.006933717795, 0.00939545639, 0.006933717795, 1.0, -1.367576716, 0.5231455731),
        (1.0, -0.2072824888, 1.0, 1.0, -1.229819789, 0.7273085523),
        (1.0, -0.6643733109, 1.0, 1.0, -1.157143099, 0.9194936469)),
    32000: (
        (0.02239589618, 0.03897715383, 0.02239589618, 1.0, -1.002252672, 0.3533378446),
        (1.0, 0.7689714327, 1.0, 1.0, -0.6025153495, 0.6537500441),
        (1.0, 0.3251754601, 1.0, 1.0, -0.3538671505, 0.9017749359)),
}


class Unsupported(ValueError):
    """The mic has no stream the app can use; the message says what it
    offers."""


def offers(text):
    """What a mic offers, in words, from usb-host-audio's ``ValueError``
    ("... it offers: itf 1 alt 1: in 16000/32000 Hz x 2ch x 16bit, ep ...").
    Only its inputs; an empty string when it lists none."""
    seen = []
    for chunk in text.split("itf ")[1:]:
        if ": " not in chunk:
            continue
        what = chunk.split(": ", 1)[1].split(", ep", 1)[0].strip()
        if not what.startswith("in "):
            continue
        parts = what[3:].split(" x ")
        if len(parts) != 3:
            continue
        rates = []
        for r in parts[0].replace(" Hz", "").split("/"):
            try:
                hz = int(r)
            except ValueError:
                rates.append(r)
                continue
            rates.append(("%d" % (hz // 1000)) if hz % 1000 == 0 else ("%.1f" % (hz / 1000)))
        ch = parts[1].replace("ch", "")
        ch = {"1": "mono", "2": "stereo"}.get(ch, ch + " channels")
        said = "%s kHz %s %s-bit" % ("/".join(rates), ch, parts[2].replace("bit", ""))
        if said not in seen:
            seen.append(said)
    return ", ".join(seen)


def open_mic(Microphone, dev, ring_ms=500):
    """``(mic, feed)``: the mic opened at the first rate of ``PLANS`` it
    offers, 16-bit mono, and the ``Feed`` for that rate. Raises
    ``Unsupported`` when it offers none of them."""
    last = ""
    for rate, _, _ in PLANS:
        try:
            mic = Microphone(dev, rate=rate, channels=1, bits=16, ring_ms=ring_ms)
        except ValueError as e:
            last = str(e)
            continue
        return mic, Feed(rate)
    said = offers(last)
    raise Unsupported("this mic offers %s; the wake word takes 16, 24, 32 or 48 kHz 16-bit"
                      % (said or "no input stream"))


class Feed:
    """Bytes from the mic in (``push``), 16 kHz int16 out, as a list of
    bytes objects for ``ww.process``. At 16 kHz what goes in comes out,
    whole samples at a time; otherwise in 10 ms blocks, the filter's state
    kept from one to the next."""

    def __init__(self, rate):
        for r, up, down in PLANS:
            if r == rate:
                break
        else:
            raise ValueError("no plan for %d Hz" % rate)
        self.rate, self.up, self.down = rate, up, down
        self.block = rate // 100 * 2  # 10 ms of input, in bytes
        self._pending = bytearray()
        if up == down:
            self._sos = None
        else:
            self._sos = np.array(_SOS[rate * up])
            self._zi = np.zeros((3, 2))

    def push(self, data):
        out = []
        if self._sos is None:
            p = self._pending
            if p:  # half a sample left from the last push
                p += data
                data = p
            n = len(data) & ~1
            if n:
                out.append(bytes(data[:n]))
            self._pending = bytearray(data[n:])
            return out
        p = self._pending
        p += data
        block = self.block
        at = 0
        while len(p) - at >= block:
            out.append(self._convert(p[at:at + block]))
            at += block
        self._pending = p[at:] if at else p
        return out

    def _convert(self, raw):
        x = np.array(np.frombuffer(raw, dtype=np.int16), dtype=_FLOAT)
        if self.up > 1:
            z = np.zeros(len(x) * self.up, dtype=_FLOAT)
            z[::self.up] = x * self.up  # keeps the level after the zeros
            x = z
        y, self._zi = _sosfilt(self._sos, x, zi=self._zi)
        y = np.clip(y[::self.down], -32768, 32767)
        return np.array(y, dtype=np.int16).tobytes()
