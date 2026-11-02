"""Input-to-output latency through the chain, with a cable from an output
into an input.

The chain runs as it would for a guitar: input → Ring → mixer → pump →
output. Every 300 ms one block of input is replaced by a short 1 kHz burst (the click) on its way
into the ring. That click stands for a known input sample; where it comes
back in through the cable, counted in input samples, is one full trip
(input, chain, output, cable). No passthrough, so nothing feeds back.
The input is saved to roundtrip-in.wav in the current folder.

    micropython -X heapsize=64M tools/roundtrip.py [cushion_ms] [latency]
        [out=ENDPOINT_ID] [in=ENDPOINT_ID] [click=0.3]

out= and in= open those WASAPI endpoints instead of the defaults (see
endpoints.py).
"""

import sys
import time
from array import array

import audiomixer
import audiopump

pos = [a for a in sys.argv[1:] if "=" not in a]
kw = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
here = __file__.replace("\\", "/")
tools = here[: here.rfind("/")]
if "out" in kw or "in" in kw:
    sys.path.insert(0, tools)
    import endpoints

    endpoints.use(kw.get("out"), kw.get("in"))

from audiodev import AudioFormat, auto  # noqa: E402
from audiodev import win_audio  # noqa: E402

RATE = 48000
FRAMES = 256
cushion = int(pos[0]) if pos else 45
lat = pos[1] if len(pos) > 1 else "low"
lat = None if lat == "default" else lat
CLICK = int(float(kw.get("click", 0.3)) * 32767)
keep = cushion * RATE * 2 // 1000
CLICKS = 10
FIRST = 1500   # ms
EVERY = 300    # ms
SECS = (FIRST + EVERY * CLICKS + 500) / 1000

ring = audiopump.Ring(sample_rate=RATE, channel_count=2, frames=FRAMES, capacity=8)
mix = audiomixer.Mixer(voice_count=1, sample_rate=RATE, channel_count=2, buffer_size=FRAMES * 4)
out = auto.audio_out(AudioFormat(RATE, 2, 16), latency=lat)
inp = win_audio.pcm_in(AudioFormat(RATE, 1, 16), latency=lat)
inp.open()
out.play(mix)
mix.voice[0].play(ring, loop=False)

mono = bytearray(FRAMES * 2)
silent = array("h", bytes(FRAMES * 4))
click = array("h", bytes(FRAMES * 4))
# Four cycles of 1 kHz: a pulse of DC mostly dies in an interface's coupling.
import math  # noqa: E402

for i in range(192):
    v = int(CLICK * math.sin(2 * math.pi * i / 48))
    click[2 * i] = click[2 * i + 1] = v
heard = bytearray()
sent = []        # input sample index each click stands for
dropped = 0
t0 = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), t0) < SECS * 1000:
    el = time.ticks_diff(time.ticks_ms(), t0)
    inp._pull()
    if el > 1000:
        extra = inp.queued_size() + ring.level() // 2 - keep
        if extra > 0:
            extra -= extra % 2
            # Dropped input still counts as time gone by.
            heard.extend(bytes(extra))
            inp._pending.consume(extra)
            dropped += extra // 2
    while inp.queued_size() >= FRAMES * 2 and ring.space() >= FRAMES * 4:
        n = inp.readinto(mono)
        at = len(heard) // 2
        heard.extend(mono[:n])
        due = FIRST + EVERY * len(sent)
        if len(sent) < CLICKS and el >= due and n == FRAMES * 2:
            sent.append(at)
            ring.write(click)
        else:
            ring.write(silent if n == FRAMES * 2 else memoryview(silent)[: n * 2])
    out.service()
    time.sleep_ms(1)
out.stop()
out.close()
inp.close()

sys.path.insert(0, here[: here.rfind("/tools/")])
from stompbox import wavfile  # noqa: E402

wavfile.write("roundtrip-in.wav", RATE, 1, heard)

x = array("h", heard)
peak = 0
for v in x:
    if v > peak:
        peak = v
    elif -v > peak:
        peak = -v
gate = max(peak // 3, 300)
print("input peak %d, gate %d, input dropped to hold the cushion: %d samples"
      % (peak, gate, dropped))
trips = []
for s in sent:
    j = s
    end = min(len(x), s + EVERY * RATE // 1000)
    while j < end and -gate < x[j] < gate:
        j += 1
    if j < end:
        trips.append((j - s) * 1000 / RATE)
if not trips:
    print("no click came back: is the cable from the output into the input?")
else:
    trips.sort()
    print("round trip, %d of %d clicks: %s ms" % (len(trips), len(sent),
          ", ".join("%.1f" % t for t in trips)))
    print("median %.1f ms, spread %.1f ms" % (trips[len(trips) // 2], trips[-1] - trips[0]))
