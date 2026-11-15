# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Checks that Vamp records a take from a MIDI port, on Windows.

The box runs on MicroPython for Windows and reads a Windows MIDI port, with a
panel (an hmilink client in the same process) arming a track and starting a
take as Ostinato's window does. A second process plays a known phrase into
the other end of a loopback, and the check compares the notes the box wrote
into the song with what was played.

    micropython.exe tools/vamp_midi_loopback_check.py box SCENARIO BANK.sf2 OUT.json [norecord]
    python.exe tools/vamp_midi_loopback_check.py send SCENARIO

Run them together, the box first; it writes ``ready.flag`` beside OUT.json
when it is listening. Both need ``midiports`` (and its ``uwin32``), ``hmilink``,
``songmodel`` and ``vamp`` on the path. The port is ``PORT`` below, made with
``midi basic-loopback create --name "PyDevices Loopback"``.

Scenarios: ``quantised`` (sixteenths, overdub on, one old note kept),
``raw`` (quantise off), ``replace`` (overdub off clears the pattern) and
``countin`` (the take starts a bar before the song).
"""

import json
import sys
import time

PORT = "PyDevices Loopback"
STEP = 24                      # ticks in a sixteenth
BAR = 384
TICK_MS = 500 / 96             # 120 BPM
MARGIN_MS = 150                # the box starts the song this long after it's asked
MARK = 110                     # CC numbers that frame a phrase
END = 111

# pitch, velocity, nominal start tick, length in ticks, each a little off the grid
PHRASE = [(60, 100, 98, 50), (64, 64, 198, 19), (67, 127, 280, 72), (72, 80, 386, 48), (76, 90, 388, 96)]
SCENARIOS = {
    "quantised": {"tick0": 0, "quantise": True, "overdub": True, "old": [[0, 24, 50, 100]], "phrase": PHRASE},
    "raw": {"tick0": 0, "quantise": False, "overdub": True, "old": [], "phrase": PHRASE},
    "replace": {"tick0": 0, "quantise": True, "overdub": False, "old": [[0, 24, 50, 100], [48, 24, 52, 100]],
                "phrase": PHRASE},
    "countin": {"tick0": -BAR, "quantise": True, "overdub": True, "old": [],
                "phrase": [(60, 100, -300, 40), (62, 77, 50, 30)]},
}


def events(sc):
    """``[[ms after the marker, [bytes]], ...]`` for a scenario's phrase."""
    out = [[0, [0xB0, MARK, 1]]]
    for pitch, vel, tick, length in sc["phrase"]:
        on = MARGIN_MS + (tick - sc["tick0"]) * TICK_MS
        out.append([round(on, 1), [0x90, pitch, vel]])
        out.append([round(on + length * TICK_MS, 1), [0x80, pitch, 0]])
    last = max(e[0] for e in out) + 400
    out.append([round(last), [0xB0, END, 1]])
    out.sort(key=lambda e: e[0])
    return out


def send(name):
    from midiports import windows

    sc = SCENARIOS[name]
    _, midi_out = windows.ports(PORT)
    if midi_out is None:
        raise SystemExit("no MIDI output named %r" % PORT)
    while True:
        try:
            open("ready.flag").close()
            break
        except OSError:
            time.sleep(0.05)
    sent = []
    t0 = time.perf_counter()
    for ms, data in events(sc):
        while time.perf_counter() - t0 < ms / 1000:
            time.sleep(0.0005)
        buf = bytes(data)
        midi_out.write(buf, len(buf))
        sent.append([round((time.perf_counter() - t0) * 1000, 1), data])
    time.sleep(0.3)
    midi_out.close()
    json.dump(sent, open("sent.json", "w"))
    print("sent", len(sent))


def box(name, bank, out_path, plant=None):
    import audiocore
    from hmilink import tcp
    import hmilink
    import songmodel
    from midiports import windows
    from songmodel import model
    from vamp import engine as be
    from vamp.device import BoxDevice
    from vamp.main import _Parser

    sc = SCENARIOS[name]
    log = []
    frames = [0]
    t_start = time.ticks_ms()
    eng = be.BoxEngine(be.sf.open_bank(bank), None, lambda: frames[0])
    dev = BoxDevice(eng, port=9411, bind="127.0.0.1", page=songmodel.page(), log=lambda *a: None, plant=plant)
    panel = hmilink.Panel(tcp.connect("127.0.0.1", 9411))

    def step():
        eng.sequence()
        dev.poll()
        panel.poll()
        _r, b = audiocore.get_buffer(eng.output)
        frames[0] += len(b) // 4

    def until(cond, seconds=5):
        t = time.ticks_ms()
        while not cond():
            step()
            if time.ticks_diff(time.ticks_ms(), t) > seconds * 1000:
                raise RuntimeError("timed out")

    until(lambda: panel.ready)
    panel.command("listen", me=panel.me)
    project = model.new_project()
    project["tempo"] = 120.0
    project["quantise"] = sc["quantise"]
    project["overdub"] = sc["overdub"]
    track = model.track("synth", "soundfont", "Keys")
    track["patterns"][0]["bars"] = 2
    track["patterns"][0]["notes"] = [list(n) for n in sc["old"]]
    project["tracks"] = [track]
    tid = track["id"]
    panel.command("load", project=project, by=[panel.me, 1])
    until(lambda: dev.model.doc["tracks"][0]["patterns"][0]["notes"] == sc["old"] and tid in eng.tracks)
    panel.command("engines", msg={"t": "select", "track": tid, "armed": tid}, by=panel.me)
    until(lambda: eng.take.armed == tid)
    midi_in, _ = windows.ports(PORT)
    if midi_in is None:
        raise SystemExit("no MIDI input named %r" % PORT)
    parser = _Parser()
    buf = bytearray(64)
    msgs = []
    open("ready.flag", "w").write("1")
    heard = []                      # (frame, message) as the box saw each
    marker = None
    while True:
        # Keep the engine's clock on the wall clock, as a pump would.
        want = time.ticks_diff(time.ticks_ms(), t_start) * 48
        while frames[0] < want:
            step()
        n = midi_in.readinto(buf)
        if n:
            parser.feed(buf, n, msgs)
            for m in msgs:
                heard.append((frames[0], m))
                if m[0] == 0xB0 and m[1] == MARK:
                    marker = frames[0]
                    panel.command("engines", msg={"t": "transport", "play": True, "at": 0,
                                                  "tick": float(sc["tick0"]), "record": True}, by=panel.me)
                elif m[0] == 0xB0 and m[1] == END:
                    break
                else:
                    dev.midi(*m)
            else:
                msgs.clear()
                time.sleep_ms(1)
                continue
            break
        time.sleep_ms(1)
    anchor = dict(eng.transport)
    until(lambda: panel.doc == dev.model.doc, 3)
    panel.command("stop", by=panel.me)
    for _ in range(50):
        step()
    got = dev.model.doc["tracks"][0]["patterns"][0]["notes"]
    result = {"scenario": name, "got": got, "panel_has_it": panel.doc == dev.model.doc, "anchor": anchor,
              "marker_frame": marker, "heard": [[f, list(m)] for f, m in heard]}
    result["fails"] = verify(sc, got, eng, marker)
    json.dump(result, open(out_path, "w"))
    print(name, "FAILED: " + "; ".join(result["fails"]) if result["fails"] else "passed", "notes:", got)
    dev.close()
    return 1 if result["fails"] else 0


def verify(sc, got, eng, marker):
    """What the song should hold, worked out from when each key was played."""
    fails = []
    want = [list(n) for n in sc["old"]] if sc["overdub"] else []
    new = []
    for pitch, vel, tick, length in sc["phrase"]:
        on = marker + int((MARGIN_MS + (tick - sc["tick0"]) * TICK_MS) * 48)
        off = marker + int((MARGIN_MS + (tick - sc["tick0"] + length) * TICK_MS) * 48)
        start, end = eng.tick_at(on), eng.tick_at(off)
        if start < -STEP / 2:
            continue
        if sc["quantise"]:
            start = int(round(start / STEP)) * STEP % (2 * BAR)
            size = max(STEP, int(round((end - eng.tick_at(on)) / STEP)) * STEP)
        else:
            size = end - start
            start = start % (2 * BAR)
        new.append((pitch, vel, start, size))
    recorded = [n for n in got if n not in want]
    if sorted(n for n in want if n in got) != sorted(want):
        fails.append("old notes %s became %s" % (want, [n for n in got if n in want]))
    if len(recorded) != len(new):
        fails.append("%d notes recorded, %d expected (%s)" % (len(recorded), len(new), recorded))
        return fails
    tol_start, tol_size = (0, 0) if sc["quantise"] else (4, 5)
    for (pitch, vel, start, size), n in zip(sorted(new), sorted(recorded, key=lambda n: n[2])):
        if (n[2], n[3]) != (pitch, vel) or abs(n[0] - start) > tol_start or abs(n[1] - size) > tol_size:
            fails.append("wanted pitch %d vel %d at %.1f for %.1f, got %s" % (pitch, vel, start, size, n))
    return fails


if __name__ == "__main__":
    if sys.argv[1] == "send":
        send(sys.argv[2])
    else:
        sys.exit(box(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else None))
