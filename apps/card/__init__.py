# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Sound card: the board as a USB speaker, with the spectrum of what the PC
plays under the header.

The board is "Speakers (Espressif Device)" on Windows, on its device USB
port: usb-device-audio's speaker streams from the USB interrupt into an
audiopump ring, and audiodsp's pump plays that ring on the codec. Python only
keeps the clock feedback in step and follows the PC's volume. The meter is
the pump's own tap, so it shows whatever the pump plays.

It needs micropython-lib's ``usb-device`` and pydevices' ``usb-device-audio`` in
``/lib``, and gallery's spectrum analyzer for the meter.
"""

import lvgl as lv

import spectrum
from touchkit import ui

VOLUME = 85  # the panel's listening level; the PC's slider moves it down from here


def _percent(spk):
    if spk.mute:
        return 0
    db = max(-50 * 256, min(0, spk.volume))
    return round(VOLUME * (1 + db / (50 * 256)))


def main(scope):
    status = ui.status(scope)
    try:
        import audiopump
        import usb.device
        from audiodev import AudioFormat, pump
        from boarddev import pcm_out
        from usb.device.audio import SpeakerInterface
    except ImportError as e:
        status.set_text("missing: %s" % e)
        ui.label(scope.root, "This needs usb-device and usb-device-audio in /lib.", ui.font, ui.WHITE).align(
            lv.ALIGN.CENTER, 0, 0
        )
        return

    fmt = AudioFormat(48000, 2, 16)
    ring = audiopump.Ring(sample_rate=48000, channel_count=2, frames=480, capacity=8)
    spk = SpeakerInterface(sink=ring)
    usb.device.get().init(spk, builtin_driver=True)
    transport = pcm_out(fmt)
    while transport is not None and getattr(transport, "wire", None) is None:
        transport = getattr(transport, "_inner", None)
    driver = pump.BusioDriver(transport.wire, fmt, power=getattr(transport, "audio_power", None),
                              volume=VOLUME, transport=transport)
    pump.owner().play(spk, ring, driver=driver, raises=True)
    state = {"m": None, "level": None, "bytes": None}

    try:
        from pump_levels import TapLevels

        m = spectrum.meter(scope, lambda bands: TapLevels(bands, rate=48000, channels=2), 0)
        state["m"] = m
    except Exception as e:
        print("card: no meter:", e)

    def close():
        pump.owner().stop(spk)
        usb.device.get().init(builtin_driver=True)  # the console alone again
        state["m"] = None

    scope.on_close(close)

    def begin(t):
        if state["m"] is not None:
            spectrum.start(state["m"], scope, (getattr(scope, "header", None) or scope.root,))

    scope.after(300, begin)

    def service(t):
        # Keep the clock feedback in step with the ring, and the codec with
        # the PC's volume slider and mute.
        spk.service()
        now = _percent(spk)
        if now != state["level"]:
            transport.set_volume(now)
            state["level"] = now

    scope.every(5, service)

    def tick(t):
        got = ring.stats()[0]
        playing = spk.streaming and got != state["bytes"]
        state["bytes"] = got
        status.set_text('Play to "Speakers (Espressif Device)"   %s' % ("playing" if playing else "idle"))

    tick(None)
    scope.every(1000, tick)
