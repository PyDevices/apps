# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Live input through the chain to the default output, and how much audio
each stage holds while it runs, in milliseconds. It measures what the
software path adds; the converters and the cable are not in it.

    micropython -X heapsize=64M tools/stompbox/chain_depth.py [SECONDS] [latency]
"""

import sys
import time
from array import array

import audiomixer
import audiopump
from audiodev import AudioFormat, auto
from audiodev import win_audio

RATE = 48000
FRAMES = 256
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 6
lat = sys.argv[2] if len(sys.argv) > 2 else "low"
lat = None if lat == "default" else lat
# "trim=MS": drop the input backlog startup leaves behind, keeping MS of it
trim = None
for a in sys.argv[3:]:
    if a.startswith("trim="):
        trim = int(a[5:]) * RATE * 2 // 1000

ring = audiopump.Ring(sample_rate=RATE, channel_count=2, frames=FRAMES, capacity=8)
try:
    import audioairwindows
    fx = audioairwindows.Galactic(sample_rate=RATE, channel_count=2, dry_wet=0.0)
    fx.play(ring)
    head = fx
except ImportError:
    head = ring
mix = audiomixer.Mixer(voice_count=1, sample_rate=RATE, channel_count=2, buffer_size=FRAMES * 4)
out = auto.audio_out(AudioFormat(RATE, 2, 16), latency=lat)
inp = win_audio.pcm_in(AudioFormat(RATE, 1, 16), latency=lat)
inp.open()
out.play(mix)
mix.voice[0].play(head, loop=False)

mono = bytearray(FRAMES * 2)
st = array("h", bytes(FRAMES * 4))
ms = lambda nbytes, fs: nbytes * 1000 / (RATE * fs)

samples = []
t0 = time.ticks_ms()
nxt = 1000
while time.ticks_diff(time.ticks_ms(), t0) < secs * 1000:
    inp._pull()
    if trim and time.ticks_diff(time.ticks_ms(), t0) > 1000:
        extra = inp.queued_size() + ring.level() // 2 - trim
        if extra > 0:
            inp._pending.consume(extra - extra % 2)
    while inp.queued_size() >= FRAMES * 2 and ring.space() >= FRAMES * 4:
        n = inp.readinto(mono)
        m = array("h", mono)
        for i in range(n // 2):
            st[2 * i] = m[i]
            st[2 * i + 1] = m[i]
        ring.write(memoryview(st)[: n * 2] if n < FRAMES * 2 else st)
    out.service()
    el = time.ticks_diff(time.ticks_ms(), t0)
    if el >= nxt:
        nxt += 250
        t = out.transport
        samples.append((ms(inp.queued_size(), 2), ms(ring.level(), 4),
                        ms(t.queued_size(), 4), ms(t.device_frames() * 4, 4),
                        ring.stats()))
    time.sleep_ms(1)

bf = out.transport.buffer_frames
bf = bf() if callable(bf) else bf
out.stop()
out.close()
inp.close()
print("latency profile:", lat, " output transport:", type(out.transport).__name__,
      " pump driver:", audiopump.driver(), " threaded:", audiopump.threaded())
print("output device buffer: %d frames = %.1f ms" % (bf, bf * 1000 / RATE))
print("  in-queue  ring  out-queue (of it in the device)  ms; underruns")
for s in samples:
    print("  %6.1f  %6.1f  %6.1f (%5.1f)   %d" % (s[0], s[1], s[2], s[3], s[4][3]))
if samples:
    tot = [s[0] + s[1] + s[2] for s in samples[4:]] or [0]
    print("underruns after the first second: %d" % (samples[-1][4][3] - samples[3][4][3]))
    print("software path holds: min %.1f  mean %.1f  max %.1f ms"
          % (min(tot), sum(tot) / len(tot), max(tot)))
