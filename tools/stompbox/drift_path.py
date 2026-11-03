# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The live path between two clocks, and whether its ring holds.

The microphone (`_audioif.Input` with a Ring) writes on its own thread at
its own pace; an `audiopump.DriftResampler` reads the Ring at the speaker's
pace and steers its ratio to hold `target` frames. This runs that path for
`secs` seconds and prints, once a second: the resampler's fill and ppm, its
underruns, the Ring's overruns, and what the software path holds in all
(microphone backlog + ring + speaker queue).

With the output looped back to the input by a cable it also clicks, mixes
the input back in at FB, and measures the lap from the tap, as c_path.py
does. Keep FB at 0.2 to 0.4: a loop at full level howls.

    micropython -X heapsize=64M tools/stompbox/drift_path.py [out=ID] [in=ID]
        [clock=two|same] [target=1024] [fb=0] [click=0] [secs=60]
        [buffer=20] [prime=10]

clock=two puts the resampler in even when both ends are one device, which
is how to measure what it costs on a loop cable.
"""

import math
import sys
import time
from array import array

import _audioif
import audiobusio
import audiocore
import audiomixer
import audiopump

RATE = 48000
opt = {"out": "", "in": "", "clock": "two", "target": "1024", "fb": "0",
       "click": "0", "secs": "60", "buffer": "20", "prime": "10",
       "block": "128", "blocks": "64"}
for a in sys.argv[1:]:
    k, _, v = a.partition("=")
    opt[k] = v
FB = float(opt["fb"])
CLICK = float(opt["click"])
SECS = float(opt["secs"])
TARGET = int(opt["target"])
BLOCK = int(opt["block"])
TAPPING = CLICK > 0 and SECS <= 20

out_id = opt["out"] or None
in_id = opt["in"] or None
print("out:", _audioif.endpoint(out_id, False))
print("in: ", _audioif.endpoint(in_id, True))
print("same_clock says:", _audioif.same_clock(out_id, in_id), " running:",
      opt["clock"])

sink = "wasapi:%d:2:%s:%s" % (RATE, opt["prime"], opt["buffer"])
if out_id:
    sink += "@" + out_id

drift = None
if opt["clock"] == "two":
    ring = audiopump.Ring(sample_rate=RATE, channel_count=2, frames=BLOCK,
                          capacity=int(opt["blocks"]))
    mic = _audioif.Input(sample_rate=RATE, channel_count=2, frames=BLOCK,
                         device=in_id, ring=ring)
    drift = audiopump.DriftResampler(ring, target=TARGET)
    head = drift
else:
    mic = _audioif.Input(sample_rate=RATE, channel_count=2, frames=BLOCK,
                         device=in_id)
    head = mic

mix = audiomixer.Mixer(voice_count=2, sample_rate=RATE, channel_count=2,
                       buffer_size=BLOCK * 4)
burst = array("h", bytes(192 * 4))
for i in range(192):
    s = int(CLICK * 32767 * math.sin(2 * math.pi * i / 48))
    burst[2 * i] = s
    burst[2 * i + 1] = s
click = audiocore.RawSample(burst, channel_count=2, sample_rate=RATE)

if TAPPING:
    tap = audiopump.Tap(frames=1 << 18, channel_count=2)
    audiopump.tap(tap)
out = audiobusio.I2SOut(0, 1, 2, sample_rate=RATE, sink=sink)
mix.voice[0].level = FB
mix.voice[0].play(head, loop=False)
out.play(mix, loop=False)


def held_ms():
    m = mic.stats()
    s = _audioif.sink_stats()
    ring_f = drift.fill if drift is not None else 0
    return (m[6] * 1000 / RATE, ring_f * 1000 / RATE,
            (s[6] if s else 0) * 1000 / RATE)


rows = []
rates = []
t0 = time.ticks_ms()
nxt_click = 300
nxt_look = 1000
while True:
    el = time.ticks_diff(time.ticks_ms(), t0)
    if el >= SECS * 1000:
        break
    if CLICK > 0 and el >= nxt_click:
        nxt_click += 600
        mix.voice[1].play(click)
    if el >= nxt_look:
        nxt_look += 1000
        h = held_ms()
        if drift is not None:
            rs = ring.stats() if hasattr(ring, "stats") else None
            row = (el / 1000, drift.fill, drift.ppm, drift.underruns,
                   h[0] + h[1] + h[2], h)
            print("t %5.0f s  fill %6.1f  ppm %+8.2f  underruns %d  held %5.1f ms"
                  " (mic %.1f ring %.1f spk %.1f)"
                  % (row[0], row[1], row[2], row[3], row[4], h[0], h[1], h[2]))
        else:
            row = (el / 1000, 0, 0, 0, h[0] + h[2], h)
            print("t %5.0f s  held %5.1f ms (mic %.1f spk %.1f)"
                  % (row[0], row[4], h[0], h[2]))
        rows.append(row)
        rates.append((el, mic.stats()[0], (_audioif.sink_stats() or (0,))[0],
                      ring.stats()[0] // 4 if drift is not None else 0))
    time.sleep_ms(5)

got = None
n = 0
if TAPPING:
    got = bytearray((1 << 18) * 4)
    n = tap.readinto(got)
mstats = mic.stats()
sstats = _audioif.sink_stats()
out.stop()
out.deinit()
if TAPPING:
    audiopump.tap(None)
mic.deinit()

print("sink:", sink, " clock:", opt["clock"], " target:", TARGET, " fb:", FB)
print("mic  (frames, lost/short, glitches, dropped, timeouts, buffer, waiting,"
      " err, period, latency):", mstats)
print("sink (frames, starved, -, -, timeouts, buffer, queued, err, period,"
      " latency):", sstats)
if drift is not None:
    print("ring stats:", ring.stats() if hasattr(ring, "stats") else "-")
    late = [r for r in rows if r[0] >= 30] or rows[len(rows) // 2:]
    if late:
        fills = [r[1] for r in late]
        ppms = [r[2] for r in late]
        print("after %.0f s: fill %.1f..%.1f (target %d), ppm %+.2f..%+.2f,"
              " underruns %d" % (late[0][0], min(fills), max(fills), TARGET,
                                 min(ppms), max(ppms), rows[-1][3]))
if len(rates) > 12:
    a, b = rates[5], rates[-1]
    secs = (b[0] - a[0]) / 1000
    print("rates over %.0f s: mic %.1f, speaker %.1f, ring writes %.1f frames/s"
          % (secs, (b[1] - a[1]) / secs, (b[2] - a[2]) / secs,
             (b[3] - a[3]) / secs))
held = [r[4] for r in rows[2:]]
if held:
    print("software holds: min %.1f  mean %.1f  max %.1f ms"
          % (min(held), sum(held) / len(held), max(held)))
per = (mstats[8] if len(mstats) > 8 else 0) + (sstats[8] if sstats and len(sstats) > 8 else 0)
print("device periods: %.1f ms (mic %d + speaker %d frames)"
      % (per * 1000 / RATE, mstats[8] if len(mstats) > 8 else 0,
         sstats[8] if sstats and len(sstats) > 8 else 0))

if got is not None:
    x = array("h", got[:n])
    frames = len(x) // 2
    gate = 650
    quiet = RATE // 100
    segs = []
    cur = None
    last = -quiet
    for i in range(frames):
        v = x[2 * i]
        if v < 0:
            v = -v
        if v >= gate:
            if cur is None or i - last > quiet:
                cur = [i, i, v]
                segs.append(cur)
            else:
                cur[1] = i
                if v > cur[2]:
                    cur[2] = v
            last = i
    top = 0
    for s in segs:
        if s[2] > top:
            top = s[2]
    laps = []
    for k in range(len(segs) - 1):
        if segs[k][2] < top * 0.8:
            continue
        for j in range(k + 1, len(segs)):
            if segs[j][2] >= top * 0.8:
                break
            if segs[j][0] - segs[k][0] >= RATE // 50:
                laps.append((segs[j][0] - segs[k][0]) * 1000 / RATE)
                break
    if laps:
        srt = sorted(laps)
        print("laps ms:", " ".join("%.1f" % v for v in laps))
        print("lap median %.1f ms  spread %.1f ms  (%d clicks)"
              % (srt[len(srt) // 2], srt[-1] - srt[0], len(laps)))
    else:
        print("no laps heard (segments %d)" % len(segs))
