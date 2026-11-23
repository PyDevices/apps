# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Press a MIDI foot controller's switch from a computer: taps, holds and
double taps sent to a MIDI port, as a momentary switch sends them.

    python tools/backline/pedal_send.py PORT [--cc 80] [--channel 1] STEP...

PORT is part of a MIDI output's name (``windows:`` or ``linux:`` before it
picks the system; the computer's own by default). Each STEP is one of:

- ``tap``: CC 127, then CC 0 a tenth of a second later.
- ``hold``: CC 127, then CC 0 0.8 s later.
- ``double``: two taps a quarter of a second apart.
- ``wait:S``: S seconds of nothing.
- ``pc:N``: a program change to N.
- ``cc:N:V``: controller N set to V.

With a loopback port, Backline's ``tools/backline/host.py --midi`` on the
other end plays the song from these, as it would from the switch. Each step
prints with the second it was sent.
"""

import sys
import time

TAP_S = 0.1
HOLD_S = 0.8
DOUBLE_GAP_S = 0.15


def open_out(spec):
    kind, _, name = spec.partition(":")
    if not name:
        kind, name = ("windows" if sys.platform == "win32" else "linux"), spec
    if kind == "windows":
        from midiports import windows as host
    else:
        from midiports import linux as host
    _in, out = host.ports(name)
    if out is None:
        raise SystemExit("no MIDI output named %r" % name)
    return out


def main(argv):
    port = argv[0]
    cc, ch = 80, 0
    steps = []
    i = 1
    while i < len(argv):
        if argv[i] == "--cc":
            cc = int(argv[i + 1])
            i += 2
        elif argv[i] == "--channel":
            ch = int(argv[i + 1]) - 1
            i += 2
        else:
            steps.append(argv[i])
            i += 1
    out = open_out(port)
    start = time.monotonic()

    def send(*b):
        out.write(bytes(b), len(b))

    def switch(down_s):
        send(0xB0 | ch, cc, 127)
        time.sleep(down_s)
        send(0xB0 | ch, cc, 0)

    for step in steps:
        print("%.2f s %s" % (time.monotonic() - start, step), flush=True)
        kind, _, rest = step.partition(":")
        if kind == "tap":
            switch(TAP_S)
        elif kind == "hold":
            switch(HOLD_S)
        elif kind == "double":
            switch(TAP_S)
            time.sleep(DOUBLE_GAP_S)
            switch(TAP_S)
        elif kind == "wait":
            time.sleep(float(rest))
        elif kind == "pc":
            send(0xC0 | ch, int(rest))
        elif kind == "cc":
            n, _, v = rest.partition(":")
            send(0xB0 | ch, int(n), int(v))
        else:
            raise SystemExit("no step %r" % step)
    time.sleep(0.2)
    out.close()


if __name__ == "__main__":
    main(sys.argv[1:])
