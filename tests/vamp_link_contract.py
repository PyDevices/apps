# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Vamp over its link, in one process, with no sound card: the box (an
engine whose output this check pulls, so it owns the clock) and two panels
on hmilink TCP, the way Ostinato's window and the browser page drive it.

    micropython -X heapsize=64M tests/vamp_link_contract.py BANK.sf2 [--plant nomute|norecord]
    python tests/vamp_link_contract.py BANK.sf2

MICROPYPATH (or PYTHONPATH) needs the apps repo's programs/ and lib/, hmilink and the audio
libraries. A panel loads a song, presses Play, changes the tempo, mutes a
track, adds a note, puts a reverb on the master and stops. After each step
the box's song must equal the panel's, and the engine must have acted on it.
A second panel that joins at the end must get the same song, and the box
must serve its page. ``--plant nomute`` starts the box with a planted fault
(it echoes mutes without applying them), and the check must fail.
"""

import sys

import hmilink
from hmilink import tcp

import songmodel
from songmodel import model
from vamp import engine as be
from vamp.device import BoxDevice

FAILS = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)
    return ok


def song():
    """Two SoundFont tracks: hats on the kit, and a line on program 0."""
    p = model.new_project()
    p["name"] = "Link check"
    p["tempo"] = 120.0
    drums = model.track("drums", "soundfont_drums", "Hats")
    drums["patterns"][0]["notes"] = [[i * model.STEP * 2, model.STEP, 42, 100] for i in range(8)]
    lead = model.track("synth", "soundfont", "Saw")
    lead["patterns"][0]["notes"] = [[i * model.PPQ, model.STEP, 60 + i, 90] for i in range(4)]
    p["tracks"] = [drums, lead]
    return p


class Rig:
    def __init__(self, bank, plant):
        self.frames = 0
        self.eng = be.BoxEngine(bank, None, self.clock)
        self.port = 9300 + (self.ticks() % 500)
        self.dev = BoxDevice(self.eng, port=self.port, bind="127.0.0.1", page=songmodel.page(),
                             log=lambda *a: None, plant=plant)
        self.panels = []

    @staticmethod
    def ticks():
        return be.ticks_ms()

    def clock(self):
        return self.frames

    def panel(self):
        p = hmilink.Panel(tcp.connect("127.0.0.1", self.port))
        self.panels.append(p)
        self.run(lambda: p.ready, "the song from the box")
        return p

    def step(self):
        """One pass of the box's loop, a block of audio and every panel."""
        self.eng.sequence()
        self.dev.poll()
        for p in self.panels:
            p.poll()
        import audiocore

        _r, b = audiocore.get_buffer(self.eng.output)
        self.frames += len(b) // 4

    def waited(self, since, seconds):
        """True once ``seconds`` have passed both on this clock and in the box's
        audio, from ``since = (ticks_ms(), frames)``. The box plays by the
        blocks it is pulled for, so a slow machine is slow in audio time too: a
        wait on the playhead counts the box's seconds, and a wait on the
        network counts the wall's."""
        t, frames = since
        return (be.ticks_diff(be.ticks_ms(), t) > seconds * 1000
                and self.frames - frames > seconds * be.SR)

    def run(self, cond=None, what="", blocks=None, seconds=10, step=None):
        """Step until ``cond()`` holds (raises after ``seconds`` of the wall and
        of the box's audio, see ``waited``), or for ``blocks``."""
        step = step or self.step
        if cond is None:
            for _ in range(blocks):
                step()
            return True
        since = (be.ticks_ms(), self.frames)
        while not cond():
            step()
            if self.waited(since, seconds):
                raise RuntimeError("no %s in %d s" % (what, seconds))
        return True

    def settle(self, cond, seconds=3):
        """Step until ``cond()`` holds; False if it doesn't within ``seconds``."""
        try:
            return self.run(cond, "", seconds=seconds)
        except RuntimeError:
            return False

    def same(self, p):
        return p.doc == self.dev.model.doc


def get_page(port):
    """The page the box serves on its hmilink port, over plain HTTP."""
    import socket

    s = socket.socket()
    s.connect(socket.getaddrinfo("127.0.0.1", port)[0][-1])
    s.send(b"GET / HTTP/1.1\r\nHost: box\r\n\r\n")
    return s


def main(argv):
    bank = be.sf.open_bank(argv[1])
    plant = argv[argv.index("--plant") + 1] if "--plant" in argv else None
    rig = Rig(bank, plant)
    p = rig.panel()
    p.command("listen", me=p.me)

    events = []
    p.on_event = events.append
    wanted = song()
    p.command("load", project=wanted, by=[p.me, 1])
    rig.run(lambda: any(e.get("name") == "loaded" for e in events), "load")
    rig.run(lambda: p.doc.get("name") == wanted["name"], "the loaded song")
    check(rig.settle(lambda: rig.same(p) and len(rig.eng.tracks) == 2),
          "load: the box has the panel's song and builds both tracks")
    failed = [e["msg"] for e in events if e.get("name") == "engine" and e["msg"].get("t") == "failed"]
    check(not failed, "every track built (%s)" % [m.get("why") for m in failed])

    p.command("play", tick=0.0, by=p.me)
    rig.settle(lambda: rig.eng.stats["notes"] > 0)
    notes = rig.eng.stats["notes"]
    check(rig.eng.transport["playing"] and notes > 0, "play: the box plays (%d notes)" % notes)

    def edit(kind, pointer, value, what, acted):
        before = rig.eng.stats["notes"]
        p.send(kind, pointer, value)
        check(rig.settle(lambda: not p._sent and rig.same(p) and acted()), what)
        return rig.eng.stats["notes"] - before

    edit("replace", "/tempo", 140.0, "tempo: the box's song and its engine are at 140",
         lambda: rig.eng.project["tempo"] == 140.0 and abs(rig.eng.ticks_per_frame() * 60 * be.SR / model.PPQ - 140) < 1e-6)
    tracks = rig.dev.model.doc["tracks"]
    edit("replace", "/tracks/0/mute", True, "mute: the box mutes the track",
         lambda: rig.eng.level_of(tracks[0]) == 0.0)
    edit("add", "/tracks/1/patterns/0/notes/-", [model.STEP * 2, model.STEP, 43, 100],
         "a note added: the box's pattern has it",
         lambda: [model.STEP * 2, model.STEP, 43, 100] in rig.eng.project["tracks"][1]["patterns"][0]["notes"])
    edit("replace", "/master/rack", [{"name": "Reverb", "bypass": False, "macros": {}}],
         "a master reverb: the box's rack has it", lambda: rig.eng.rack is not None)
    rig.run(blocks=400)
    check(rig.eng.stats["notes"] > notes, "the box kept playing through the edits (%d notes)" % rig.eng.stats["notes"])
    check(rig.eng.pool.late == 0, "no late notes (%d)" % rig.eng.pool.late)

    # A take, as the window starts one: arm the track, play with record on,
    # and a keyboard on the box plays a note a beat in.
    lead = rig.dev.model.doc["tracks"][1]["id"]
    p.command("engines", msg={"t": "select", "track": lead, "armed": lead}, by=p.me)
    p.command("engines", msg={"t": "transport", "play": True, "at": 0, "tick": 0.0, "record": True}, by=p.me)
    rig.settle(lambda: rig.dev.engine.take.recording)
    rig.run(blocks=100)
    rig.dev.midi(0x90, 72, 100)
    rig.run(blocks=20)
    rig.dev.midi(0x80, 72, 0)
    heard = [n for n in rig.dev.model.doc["tracks"][1]["patterns"][0]["notes"] if n[2] == 72]
    check(len(heard) == 1 and heard[0][3] == 100 and heard[0][0] % model.STEP == 0,
          "a take: the box's keyboard note is in the armed track, on a sixteenth (%s)" % heard)
    check(rig.settle(lambda: rig.same(p)), "a take: the panel has the recorded note")

    p.command("stop", by=p.me)
    check(rig.settle(lambda: not rig.eng.transport["playing"]), "stop: the box stops")

    other = rig.panel()
    check(other.doc == p.doc,
          "a panel joining now gets the same song")

    s = get_page(rig.port)
    got = b""
    for _ in range(400):
        rig.step()
        try:
            s.setblocking(False)
            chunk = s.recv(4096)
            if chunk:
                got += chunk
            elif got:
                break
        except OSError:
            pass
        if b"</html>" in got:
            break
    s.close()
    check(got.startswith(b"HTTP/1.") and b"</html>" in got, "the box serves the browser panel (%d bytes)" % len(got))

    for q in rig.panels:
        q.close()
    rig.dev.close()
    print("vamp link contract:", "FAILED " + "; ".join(FAILS) if FAILS else "all passed", "(plant: %s)" % plant)
    if FAILS:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
