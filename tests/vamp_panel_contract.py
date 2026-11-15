# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Vamp's front panel against a real box, in one process with no sound card
and no window: the box of ``vamp_link_contract.py``, and the panel
(``vamp.panel`` and, where LVGL is, its 800x480 screen ``vamp.panel_view``)
joined to it over hmilink TCP.

    python tests/vamp_panel_contract.py BANK.sf2 [--plant nohead|noedit|noecho] [--shot OUT.raw] [--no-screen]
    micropython -X heapsize=64M tests/vamp_panel_contract.py BANK.sf2

With LVGL the panel is pressed with a finger on a display that draws into
memory, and what it painted is checked; without it the same presses go to the
panel's own calls, and the screen's checks are skipped with a line that says
so (``--need-screen`` makes that a failure, and ``--no-screen`` leaves the
screen out where there is one). After each press the box's song
must equal the panel's and the engine must have acted. ``--plant`` breaks the
panel one way, and the check must then fail: ``nohead`` (it ignores where the
box is playing), ``noedit`` (a press on the grid changes nothing on the box),
``noecho`` (it ignores another panel's edits). ``--shot`` saves a frame of the
kit playing: a ``width height`` line, then RGB565 pixels.
"""

import sys

from songmodel import model
from vamp import panel as panel_module
from vamp.panel import Front, join

import vamp_link_contract as link
from vamp_link_contract import check

argv = sys.argv[1:]
PLANT = argv[argv.index("--plant") + 1] if "--plant" in argv else None
SHOT = argv[argv.index("--shot") + 1] if "--shot" in argv else None
WIDTH, HEIGHT = 800, 480

try:
    import lvgl as lv
except ImportError:
    lv = None
    if "--need-screen" in argv:
        raise
if "--no-screen" in argv:
    lv = None

if lv is not None:
    import _headless
    from vamp import panel_view


def song():
    """A kit with two bars of hats, and a one-bar line from middle C."""
    p = model.new_project()
    p["name"] = "Panel check"
    p["tempo"] = 120.0
    drums = model.track("drums", "soundfont_drums", "Hats")
    drums["patterns"][0] = model.pattern(2)
    drums["patterns"][0]["notes"] = [[i * model.STEP * 2, model.STEP, 42, 100] for i in range(16)]
    lead = model.track("melodic", "soundfont", "Saw")
    lead["patterns"][0]["notes"] = [[i * model.PPQ, model.STEP * 2, 60 + i, 90] for i in range(4)]
    p["tracks"] = [drums, lead]
    return p


def plant(front):
    if PLANT == "nohead":
        front._place_head = lambda: None
    elif PLANT == "noedit":
        sent = front._send

        def dropped(kind, path, value=None):
            return True if "/notes/" in path else sent(kind, path, value)

        front._send = dropped
    elif PLANT == "noecho":
        front._on_op = lambda op: None


def main():
    bank = link.be.sf.open_bank(argv[0])
    rig = link.Rig(bank, None)
    rig.dev.model.load(song())
    box = rig.dev.model.doc
    eng = rig.eng

    front = Front(lambda: join("127.0.0.1", rig.port))
    plant(front)
    view = None
    if lv is not None:
        _headless.display(WIDTH, HEIGHT)
        _headless.pointer()
        view = panel_view.View(front, lv.screen_active())
    else:
        print("SKIP the screen: no lvgl here, or --no-screen, so only the panel's own calls ran")

    def step():
        rig.step()
        if view is not None:
            view.step()
            _headless.advance(1)
        else:
            front.poll()

    def settle(cond, seconds=3):
        t = link.be.ticks_ms()
        while not cond():
            step()
            if link.be.ticks_diff(link.be.ticks_ms(), t) > seconds * 1000:
                return False
        return True

    def tap(x, y):
        _headless.touch(x, y, True, 40)
        step()
        _headless.touch(x, y, False, 40)
        step()

    def press(widget, call):
        """A finger on the widget where there's a screen, else the call it makes."""
        if view is not None:
            tap(*panel_view.center(widget()))
        else:
            call()

    def press_cell(row, col):
        if view is not None:
            tap(*view.cell_center(row, col))
        else:
            front.toggle(row, col)

    def same():
        return front.doc == box and not front.panel._sent

    def painted(row, col):
        return view.painted[row * panel_module.STEPS + col]

    # -- joining --
    check(settle(lambda: front.doc is not None), "the panel joins the box and has its song")
    check(front.doc == box and len(front.rows()) == 6, "the song on show is the box's, a kit of six rows")
    cells = front.cells()
    check([cells[2 * 16 + c] for c in range(16)] == [1, 0] * 8 and sum(cells) == 8,
          "the grid has the hats on every other step of the Hat row")
    if view is not None:
        step()
        check(view.w == WIDTH and view.h == HEIGHT and view.grid_rows == 6 and len(view.cells) == 96,
              "the screen is 800x480 with a 6 by 16 grid")
        check(view.tempo.get_text() == "120" and view.name.get_text() == "Panel check" and len(view.rows) == 2,
              "the screen shows the song's name, its tempo and both tracks")
        check(bytes(view.painted) == bytes(cells), "the screen painted the hats")

    # -- play, and the playhead --
    press(lambda: view.play, front.toggle_play)
    check(settle(lambda: eng.transport["playing"] and front.playing), "Play: the box plays and the panel knows")
    heads = set()

    def watch():
        if front.head is not None:
            heads.add(front.head)
            if front.tick is not None and front.head != int((front.tick % (2 * model.BAR)) // model.STEP):
                heads.add(-1)
        return len(heads) >= 6

    check(settle(watch) and -1 not in heads, "the playhead moves with the box's tick (%s)" % sorted(heads))
    check(settle(lambda: front.bar == 1) and settle(lambda: front.bar == 0),
          "the bar on show follows the playhead into bar 2 and back")
    if view is not None:
        check(settle(lambda: view.head_step is not None and view.head_step == front.head % 16
                     and not view.head.has_flag(lv.obj.FLAG.HIDDEN)),
              "the screen lights the column the box is playing")
        check(view.play.text.get_text() == "Stop", "the Play button reads Stop")

    # -- editing the kit --
    press(lambda: view.bar_down, lambda: front.page(-1))
    step()
    check(not front.follow and front.bar == 0, "a bar button stops the following, on bar 1")
    kick = [4 * model.STEP, model.STEP, 36, 100]
    notes = box["tracks"][0]["patterns"][0]["notes"]
    before = eng.stats["notes"]
    press_cell(5, 4)
    check(settle(lambda: kick in notes and same()), "a press on the Kick row puts a kick on the box's step 5")
    if view is not None:
        check(painted(5, 4) == panel_module.START, "the screen lights that cell")
    press_cell(5, 4)
    check(settle(lambda: kick not in notes and same(), 2) and len(notes) == 16,
          "a second press takes the kick away again")
    press_cell(5, 0)
    settle(lambda: same() and len(notes) == 17, 2)

    press(lambda: view.tempo_up, lambda: front.tempo(1))
    press(lambda: view.tempo_up, lambda: front.tempo(1))
    check(settle(lambda: box["tempo"] == 122.0 and same()), "Tempo +, twice: the box is at 122")
    press(lambda: view.swing_up, lambda: front.swing(5))
    check(settle(lambda: box["swing"] == 5 and same()), "Swing +: the box swings 5")
    press(lambda: view.rows[0].mute, lambda: front.mute(0))
    check(settle(lambda: eng.level_of(box["tracks"][0]) == 0.0 and same()), "M: the box mutes the kit")
    press(lambda: view.rows[0].mute, lambda: front.mute(0))
    press(lambda: view.rows[1].solo, lambda: front.solo(1))
    check(settle(lambda: box["tracks"][1]["solo"] and not box["tracks"][0]["mute"]
                 and eng.level_of(box["tracks"][0]) == 0.0 and same()), "S on the line: the box plays it alone")
    press(lambda: view.rows[1].solo, lambda: front.solo(1))
    front.volume(1, 50)
    check(settle(lambda: box["tracks"][1]["volume"] == 50 and same()), "a volume of 50 reaches the box")
    if view is not None:
        check(view.tempo.get_text() == "122" and view.swing.get_text() == "5", "the screen shows 122 and 5")

    # -- the melodic track --
    press(lambda: view.rows[1].obj, lambda: front.select(1))
    lead = box["tracks"][1]
    check(settle(lambda: front.selected == 1 and eng.selected == lead["id"]),
          "a press on the second track selects it, here and for the box's keyboard")
    check(len(front.rows()) == 12 and front.rows()[-1][1] == "C3" and sum(front.cells()) == 0,
          "it shows an octave from C3, where the line has no notes")
    press(lambda: view.octave_up, lambda: front.octave(1))
    step()
    cells = front.cells()
    check(front.rows()[-1][1] == "C4" and cells[11 * 16] == 1 and cells[11 * 16 + 1] == 2 and cells[10 * 16 + 4] == 1,
          "Octave +: the line's C4 is on step 1 and held through step 2, its C#4 on step 5")
    if view is not None:
        check(view.grid_rows == 12 and len(view.cells) == 192 and bytes(view.painted) == bytes(cells),
              "the screen has a 12 by 16 grid with the line painted")
    g4 = [2 * model.STEP, model.STEP, 67, 100]
    press_cell(4, 2)
    check(settle(lambda: g4 in lead["patterns"][0]["notes"] and same()), "a press puts a G4 on the box's step 3")

    # -- another panel --
    other = rig.panel()
    front.take("grid")
    other.send("add", "/tracks/1/patterns/0/notes/-", [8 * model.STEP, model.STEP, 71, 100])
    other.send("replace", "/tracks/1/volume", 30)
    ok = settle(lambda: not other._sent and same())
    if view is None:
        check(ok and front.take("grid") and front.cells()[0 * 16 + 8] == 1,
              "another panel's note: this panel has it, and knows its grid is out of date")
    else:
        step()
        check(ok and painted(0, 8) == panel_module.START, "another panel's note lights its cell on this screen")
        check(view.rows[1].volume.get_value() == 30, "another panel's volume moves this screen's slider")

    # -- a take --
    press(lambda: view.play, front.toggle_play)
    check(settle(lambda: not eng.transport["playing"] and not front.playing and front.head is None),
          "Stop: the box stops and the playhead goes out")
    press(lambda: view.rec, front.toggle_armed)
    press(lambda: view.play, front.toggle_play)
    check(settle(lambda: eng.take.recording and eng.take.armed == lead["id"]),
          "Rec then Play: the box records a take into the selected track")
    rig.run(blocks=100)
    rig.dev.midi(0x90, 62, 100)
    rig.run(blocks=20)
    rig.dev.midi(0x80, 62, 0)
    check(settle(lambda: any(n[2] == 62 for n in front.doc["tracks"][1]["patterns"][0]["notes"]) and same()),
          "a key played on the box is a note in the panel's song")
    press(lambda: view.rec, front.toggle_armed)
    press(lambda: view.play, front.toggle_play)
    check(settle(lambda: not eng.take.recording and not eng.transport["playing"] and eng.take.armed is None),
          "Rec and Stop: the take ends and the track is disarmed")
    check(eng.pool.late == 0, "no late notes (%d)" % eng.pool.late)
    check(eng.stats["notes"] > before, "the box kept playing through the edits")

    if SHOT and view is not None:
        press(lambda: view.rows[0].obj, lambda: front.select(0))
        press(lambda: view.play, front.toggle_play)
        settle(lambda: front.head == 6, 5)
        _headless.advance(40)
        _headless.refresh()
        _headless.save_raw(SHOT, WIDTH, HEIGHT)
        press(lambda: view.play, front.toggle_play)

    # -- the box goes away --
    other.close()
    rig.dev.close()
    check(settle(lambda: front.doc is None and front.status != "Joined", 5), "the box closes: the panel says so")
    if view is not None:
        step()
        check(view.grid.has_flag(lv.obj.FLAG.HIDDEN) and view.message.get_text() != "",
              "the screen puts the grid away and says it's waiting")
    front.close()
    print("vamp panel contract:", "FAILED " + "; ".join(link.FAILS) if link.FAILS else "all passed",
          "(plant: %s)" % PLANT)
    if link.FAILS:
        sys.exit(1)


main()
