# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Live input to output entirely in C, on the pump's thread, and what it costs.

The microphone is `_audioif.Input` (WASAPI capture) and the speaker is an
`audiobusio.I2SOut` whose sink is "wasapi...", so no Python touches a block.

With the output looped back to the input by a cable, the input is mixed back
into the output at FB, so every click goes round the loop again, quieter each
lap. The tap records what went out; the time from a click to its first echo
is one lap: output, cable, input, and through the graph to the output again.

It also samples how much audio each end holds while it runs: the capture
backlog and the speaker queue.

    micropython -X heapsize=64M tools/stompbox/c_path.py [out=ID] [in=ID] [fx=Galactic]
        [prime=10] [buffer=20] [keep=10] [frames=128] [fb=0.2] [click=0.3]
        [secs=5]
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
opt = {"out": "", "in": "", "fx": "", "prime": "10", "buffer": "20",
       "keep": "10", "frames": "128", "fb": "0.4", "click": "0.3", "secs": "5"}
for a in sys.argv[1:]:
    k, _, v = a.partition("=")
    opt[k] = v
FRAMES = int(opt["frames"])
FB = float(opt["fb"])
CLICK = float(opt["click"])
SECS = float(opt["secs"])
EVERY_MS = 600

sink = "wasapi:%d:2:%s:%s" % (RATE, opt["prime"], opt["buffer"])
if opt["out"]:
    sink += "@" + opt["out"]
mic = _audioif.Input(sample_rate=RATE, channel_count=2, frames=FRAMES,
                     device=opt["in"] or None, keep_ms=int(opt["keep"]))
head = mic
if opt["fx"]:
    import audioairwindows
    fx = getattr(audioairwindows, opt["fx"])(sample_rate=RATE, channel_count=2,
                                            dry_wet=0.0)
    fx.play(mic)
    head = fx

mix = audiomixer.Mixer(voice_count=2, sample_rate=RATE, channel_count=2,
                       buffer_size=FRAMES * 4)
burst = array("h", bytes(192 * 4))
for i in range(192):
    s = int(CLICK * 32767 * math.sin(2 * math.pi * i / 48))
    burst[2 * i] = s
    burst[2 * i + 1] = s
click = audiocore.RawSample(burst, channel_count=2, sample_rate=RATE)

tap = audiopump.Tap(frames=1 << 18, channel_count=2)   # 5.4 s
audiopump.tap(tap)
out = audiobusio.I2SOut(0, 1, 2, sample_rate=RATE, sink=sink)
mix.voice[0].level = FB
mix.voice[0].play(head, loop=False)
out.play(mix, loop=False)

held = []
t0 = time.ticks_ms()
nxt_click = 300
nxt_look = 250
while True:
    el = time.ticks_diff(time.ticks_ms(), t0)
    if el >= SECS * 1000:
        break
    if el >= nxt_click:
        nxt_click += EVERY_MS
        mix.voice[1].play(click)
    if el >= nxt_look:
        nxt_look += 250
        m = mic.stats()
        s = _audioif.sink_stats()
        held.append((m[6] * 1000 / RATE, s[6] * 1000 / RATE if s else -1))
    time.sleep_ms(2)

got = bytearray((1 << 18) * 4)
n = tap.readinto(got)
mstats = mic.stats()
sstats = _audioif.sink_stats()
out.stop()
out.deinit()
audiopump.tap(None)
mic.deinit()

print("sink:", sink, " frames:", FRAMES, " keep_ms:", opt["keep"],
      " fx:", opt["fx"] or "none", " fb:", FB)
print("mic  (frames, short, glitches, dropped, timeouts, buffer, waiting, err):",
      mstats)
print("sink (frames, starved, -, -, timeouts, buffer, queued, err):", sstats)
print("  held ms: capture backlog, speaker queue")
for h in held:
    print("  %6.1f  %6.1f" % h)
if len(held) > 4:
    tot = [h[0] + h[1] for h in held[4:]]
    print("C path holds: min %.1f  mean %.1f  max %.1f ms"
          % (min(tot), sum(tot) / len(tot), max(tot)))

# Segments of sound in the left channel, split by 10 ms of quiet.
x = array("h", got[:n])
frames = len(x) // 2
gate = 650
quiet = RATE // 100
segs = []          # [start, end, peak]
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
# A click, then the first sound at least 20 ms after it and before the next
# click: its echo. The echo's level wanders (a 4-cycle burst through two
# resamplers), so it is found by time, not by height.
for k in range(len(segs) - 1):
    if segs[k][2] < top * 0.8:
        continue
    for j in range(k + 1, len(segs)):
        if segs[j][2] >= top * 0.8:
            break
        if segs[j][0] - segs[k][0] >= RATE // 50:
            laps.append((segs[j][0] - segs[k][0]) * 1000 / RATE)
            break
print("segments:", len(segs), " click peak:", top)
if "segs" in opt:
    for sg in segs:
        print("  seg %8.1f ms  %5.1f ms long  peak %d" % (sg[0] * 1000 / RATE, (sg[1] - sg[0]) * 1000 / RATE, sg[2]))
if laps:
    srt = sorted(laps)
    print("laps ms:", " ".join("%.1f" % v for v in laps))
    print("lap median %.1f ms  spread %.1f ms  (%d clicks)"
          % (srt[len(srt) // 2], srt[-1] - srt[0], len(laps)))
else:
    print("no laps heard")
