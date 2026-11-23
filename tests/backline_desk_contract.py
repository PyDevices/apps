# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's desk view on real LVGL with no window, at 800x480 and 1280x720,
two desks on one box while a song plays: one on the box's own screen through
``hmilink.local``, the other joined over TCP as another computer would.

Each size: both tabs fit the screen; the song-form strip's playhead moves on
as the song plays; the grid has a row for each of the kit's drums the song
uses or every grid shows, and no more; a finger's tap on a cell of the local
desk lands in the box's song and on the remote desk's grid, a tap on the
remote desk lands back on the local one, and the song plays on through both;
a fader moved on one desk moves on the other; the tempo button changes
the box's tempo; and a switch learned from the Pedals section shows on
both desks, and a binding chosen on one shows on the other. Every drum's name in the grid, from any General MIDI kit,
fits its column without dots, the mixer's names keep apart, and the header
shows that another screen has joined and that the desk is cast. The prompt
sheet opens from the header and fits; a groove asked for there (from a
stand-in chat server) shows on both desks before it plays, and Play and
Discard from the remote desk reach the box.

    python tests/backline_desk_contract.py [--plant=NAME]

Needs LVGL, svgio, icons, hmilink, audiodsp and audioinstruments.
``--plant=NAME`` breaks the desk one way (``PLANTS``) and a check must
then fail.
"""

import json
import sys
import time

_here = __file__
_sep = "\\" if "\\" in _here else "/"
_dir = _here.rsplit(_sep, 1)[0] if _sep in _here else "."
sys.path[:0] = [_sep.join((_dir, "..", "apps")), _sep.join((_dir, "..", "lib")), _dir]

import audiocore  # noqa: E402
import hmilink  # noqa: E402
import lvgl as lv  # noqa: E402
from hmilink import local, tcp  # noqa: E402

import _headless  # noqa: E402
from backline import box as boxmod  # noqa: E402
from backline import desk_main, floor, kits, parts  # noqa: E402
from backline.desk import Desk, editor, grid, pedals, perform, prompt, strip  # noqa: E402

PLANTS = ("overflow", "wide-grid", "deaf-cell", "stale-grid", "still-strip", "all-rows", "deaf-fader",
          "long-names", "tight-mixer", "no-joiners", "deaf-learn", "stale-pedals", "deaf-ask", "blind-preview",
          "wide-sheet", "deaf-silence")
#: What the stand-in chat server answers: a 12-bar shuffle, 4 times through, the outro slowing.
SONG = {
    "name": "Slow Twelve", "style": "blues", "tempo": 72, "meter": "4/4", "feel": "shuffle", "swing": 0,
    "kit": "rhythm808", "steps": 12,
    "form": [{"part": "intro", "bars": 1}, {"part": "main1", "bars": 12}, {"part": "outro", "bars": 2}],
    "patterns": {"intro": {"snare": "......xxXxxX", "kick": "X..........."},
                 "main1": {"closed_hat": "x.ox.ox.ox.o", "snare": "...X.....X..", "kick": "X.....X..o.."},
                 "outro": {"closed_hat": "x.ox.ox.ox.o|............", "kick": "X.....X.....|X..........."}},
    "play": {"repeat": 4, "outro_tempo": 48},
}


class _Reply:
    status = 200
    headers = {"content-type": "application/json"}

    def read_all(self, most):
        return json.dumps({"choices": [{"message": {"content": json.dumps(SONG)}}]}).encode()

    def close(self):
        pass


def stand_in(url, headers, pieces, timeout=30):
    """A chat server that always answers with `SONG`."""
    return _Reply()
SIZES = ((800, 480), (1280, 720))
RESULTS = [0, 0]
RATE = 48000


def check(name, ok, detail=""):
    if ok:
        RESULTS[0] += 1
        print("ok   " + name)
    else:
        RESULTS[1] += 1
        print("FAIL " + name + (": " + detail if detail else ""))


def plant(name):
    if name is None:
        return
    print("PLANTED " + name)
    if name == "overflow":
        old = perform.Perform.__init__

        def init(self, parent, x, y, w, h, desk):
            old(self, parent, x, y, w + 160, h, desk)
        perform.Perform.__init__ = init
    elif name == "wide-grid":
        old_build = grid.Grid.build

        def build(self, rows, cols, beat):
            self.w += 12
            old_build(self, rows, cols, beat)
            self.w -= 12
        grid.Grid.build = build
    elif name == "deaf-cell":
        grid.Grid._tapper = lambda self, pitch, c: (lambda e: None)
    elif name == "stale-grid":
        editor.Editor.on_op = lambda self, op: None
    elif name == "still-strip":
        old = strip.Strip.show

        def show(self, tele):
            t = dict(tele)
            t["at"] = 0
            old(self, t)
        strip.Strip.show = show
    elif name == "all-rows":
        parts.rows = lambda voices, doc: [(int(p), n) for p, n in voices]
    elif name == "deaf-fader":
        editor.Editor._fader = lambda self, key, final=False: (lambda value: None)
    elif name == "long-names":
        grid.LABEL_SHARE = 18
        grid.shorter = lambda name: [name]
    elif name == "tight-mixer":
        editor.FADER_NAMES = editor.FADER_NAMES[1:2]
    elif name == "deaf-ask":
        prompt.PromptSheet.ask = lambda self: None
    elif name == "blind-preview":
        prompt.PromptSheet.show_preview = lambda self, p: None
    elif name == "wide-sheet":
        old = prompt.PromptSheet.__init__

        def init(self, parent, x, y, w, h, desk):
            old(self, parent, x, y, w + 120, h, desk)
        prompt.PromptSheet.__init__ = init
    elif name == "no-joiners":
        old_tele = boxmod.Box.telemetry

        def telemetry(self):
            t = old_tele(self)
            t["desks"] = 0
            t["cast"] = ""
            return t
        boxmod.Box.telemetry = telemetry
    elif name == "deaf-silence":
        desk_main.Remote._listen = lambda self, panel, ms: None
    elif name == "deaf-learn":
        pedals.Pedals._learner = lambda self, i: (lambda: None)
    elif name == "stale-pedals":
        old_event = editor.Editor.on_event

        def on_event(self, ev):
            if ev.get("name") != "pedals":
                old_event(self, ev)
        editor.Editor.on_event = on_event
    else:
        raise SystemExit("no such plant: %r" % name)


class Port:
    """A MIDI input that hands out what a test puts in ``waiting``."""

    def __init__(self):
        self.waiting = []

    def any(self):
        return len(self.waiting[0]) if self.waiting else 0

    def readinto(self, buf, nbytes=None):
        if not self.waiting:
            return None
        msg = self.waiting.pop(0)
        buf[:len(msg)] = msg
        return len(msg)


def fits(label):
    """How much wider a label's text is than the label (0 or less fits). LVGL
    hands back a cut label's text with its dots, so dots count as too wide."""
    font = label.get_style_text_font(0)
    text = label.get_text()
    over = floor.text_width(text, font, label.get_style_text_letter_space(0)) - label.get_width()
    return max(1, over) if text.endswith("...") else over


def coords(o):
    a = lv.area_t()
    o.get_coords(a)
    return a.x1, a.y1, a.x2, a.y2


def outside(root, w, h):
    """The objects that reach past the screen, or past a parent that doesn't
    scroll that way."""
    bad = []

    def walk(o, clip):
        if o.has_flag(lv.obj.FLAG.HIDDEN):
            return
        x1, y1, x2, y2 = coords(o)
        if clip is not None and (x1 < clip[0] - 1 or x2 > clip[2] + 1 or
                                 (clip[1] is not None and (y1 < clip[1] - 1 or y2 > clip[3] + 1))):
            bad.append((x1, y1, x2, y2))
        inner = (x1, y1, x2, y2)
        if o.has_flag(lv.obj.FLAG.SCROLLABLE) and o.get_child_count() and o is not root:
            # A list that scrolls up and down may run long, never wide.
            inner = (x1, None, x2, None) if o.get_scroll_dir() == lv.DIR.VER else None
        for i in range(o.get_child_count()):
            walk(o.get_child(i), inner)

    walk(root, (0, 0, w - 1, h - 1))
    return bad


def run_size(w, h):
    tag = "%dx%d" % (w, h)
    _headless.display(w, h)
    _headless.pointer().set_display(_headless._state["display"])
    scr = lv.obj(None)
    lv.screen_load(scr)
    other = lv.obj(None)          # the remote desk's screen: drawn into, never shown
    frames = [0]
    box = boxmod.Box(lambda: frames[0], song="rock", kit="rhythm808", now_ms=lambda: frames[0] * 1000 // RATE,
                     ask_settings={"base_url": "http://stand-in/v1", "key_file": "", "chat_model": "m"}, post=stand_in)
    box.device._tele_ms = 0
    listener = box.device.add(local.serve())
    served = box.device.add(tcp.serve(0, bind="127.0.0.1"))
    port = served.sock.getsockname()[1]
    near = hmilink.Panel(local.connect(listener))
    box.poll()
    near.poll()
    desk = Desk(scr, (w, h), near)
    far = desk_main.Remote(other, (w, h), "127.0.0.1", port)
    e = box.engine
    spb = RATE * 60.0 / e.project["tempo"]

    def run(beats):
        end = frames[0] + int(beats * spb)
        while frames[0] < end:
            box.service()
            audiocore.get_buffer(box.bus.output)
            frames[0] += 256
            if frames[0] % 1024 == 0:
                box.poll()
                box.device._telemetry()
                desk.poll()
                far.step()
                _headless.advance(5)
        for _ in range(3):
            box.poll()
            desk.poll()
            far.step()

    def settle(done, seconds=3.0):
        """Poll every side, the song held still, until ``done()`` or the time is up.
        A TCP link takes a few passes to carry an op both ways."""
        end = time.monotonic() + seconds
        while not done() and time.monotonic() < end:
            box.poll()
            box.device._telemetry()
            desk.poll()
            far.step()
            time.sleep(0.005)
        return done()

    run(0.1)
    check(tag + ": the remote desk joins over TCP",
          settle(lambda: far.desk.panel is not None and far.desk.panel.doc is not None))
    for tab in ("perform", "edit"):
        desk.show_tab(tab)
        _headless.advance(5)
        _headless.refresh()
        bad = outside(desk.base, w, h)
        check(tag + ": the %s tab fits the screen" % tab, not bad, "outside: %r" % bad[:4])
    desk.show_tab("perform")
    e.gesture(0, "tap")
    run(9.0)                      # into main 1
    x0 = desk.perform.strip.head_x()
    run(1.0)
    x1 = desk.perform.strip.head_x()
    check(tag + ": the song form's playhead moves on as it plays", 0 <= x0 < x1, "%d -> %d" % (x0, x1))

    desk.show_tab("edit")
    run(0.1)
    ed, fed = desk.editor, far.desk.editor
    pitches = [p for p, _n in ed.grid.rows]
    kit = set(p for p, _n in box.voices())
    used = set(n[2] for pat in e.project["tracks"][0]["patterns"] for n in pat["notes"])
    want = sorted((set(parts.CORE) & kit) | used, reverse=True)
    check(tag + ": the grid has a row for each drum the song uses or every grid shows", pitches == want,
          "%r, not %r" % (pitches, want))
    main = e.project["parts"]["mains"][0]
    check(tag + ": both desks follow the playing part", ed.pattern == main and fed.pattern == main,
          "%r, %r" % (ed.pattern, fed.pattern))
    col = 6                       # a step no starter song plays the clap on
    pitch = 39 if 39 in pitches else pitches[0]
    step = ed.bar * ed.cols + col
    before = ed.grid.level(pitch, col)
    x, y = ed.grid.center(pitch, col)
    _headless.touch(x, y, True, 40)
    _headless.touch(x, y, False, 40)
    run(0.2)
    settle(lambda: parts.cell(box.model.doc["tracks"][0]["patterns"][main]["notes"], pitch, step, ed.ticks) >= 0 and
           fed.grid.level(pitch, col) > 0)
    notes = box.model.doc["tracks"][0]["patterns"][main]["notes"]
    landed = parts.cell(notes, pitch, step, ed.ticks) >= 0
    check(tag + ": a tap on a cell lands in the box's song", before == 0 and landed, "before %d" % before)
    fed.grid.bar = ed.bar
    fed.show_cells()
    check(tag + ": the remote desk shows the tap", fed.grid.level(pitch, col) == 1, repr(fed.grid.level(pitch, col)))
    fed._tap(pitch, step)
    run(0.2)
    settle(lambda: ed.grid.level(pitch, col) == 2)
    check(tag + ": the remote desk's tap comes back to the local desk", ed.grid.level(pitch, col) == 2 and
          fed.grid.level(pitch, col) == 2, "%d, %d" % (ed.grid.level(pitch, col), fed.grid.level(pitch, col)))
    t = box.telemetry()
    same = near.doc["tracks"][0]["patterns"] == box.model.doc["tracks"][0]["patterns"] == \
        far.desk.panel.doc["tracks"][0]["patterns"]
    check(tag + ": the song plays on, both desks holding the box's song", t["playing"] and same, repr(t["part"]))
    ed._fader("kick", True)(40)
    run(0.2)
    settle(lambda: fed.faders["kick"].get_value() == 40)
    check(tag + ": a fader moved on one desk moves on the other", box.model.doc["tracks"][0]["mix"]["kick"] == 40 and
          fed.faders["kick"].get_value() == 40, repr(fed.faders["kick"].get_value()))
    names = [ed.grid.base.get_child(i) for i in range(ed.grid.base.get_child_count())]
    names = [o for o in names if hasattr(o, "get_text")]
    over = [(o.get_text(), fits(o)) for o in names if fits(o) > 0]
    check(tag + ": the grid's drum names fit without dots", len(names) == len(ed.grid.rows) and not over, repr(over))
    gm = [(p, n) for p, n in kits.GM_DRUMS]
    ed.grid.build(gm, ed.cols, 4)
    ed.grid.base.update_layout()
    names = [ed.grid.base.get_child(i) for i in range(ed.grid.base.get_child_count())]
    over = [(o.get_text(), fits(o)) for o in names if hasattr(o, "get_text") and fits(o) > 0]
    check(tag + ": every General MIDI drum's name fits without dots", not over, repr(over))
    ed.rebuild(box.model.doc, box.voices())
    labels = ed.fader_labels
    font = labels[0].get_style_text_font(0)
    gaps = []
    for a, b in zip(labels, labels[1:]):
        wa = floor.text_width(a.get_text(), font)
        wb = floor.text_width(b.get_text(), font)
        # each name is centred in its label: the space between the two texts
        gaps.append((b.get_x() + (b.get_width() - wb) // 2) - (a.get_x() + (a.get_width() + wa) // 2))
    wide = [o.get_text() for o in labels if fits(o) > 0]
    check(tag + ": the mixer's names keep apart and none is cut", min(gaps) >= 4 and not wide,
          "%r, gaps %r" % ([o.get_text() for o in labels], gaps))
    ped, fped = ed.pedals, fed.pedals
    x1, y1, x2, y2 = coords(ed.pedals_btn)
    _headless.touch((x1 + x2) // 2, (y1 + y2) // 2, True, 40)
    _headless.touch((x1 + x2) // 2, (y1 + y2) // 2, False, 40)
    _headless.refresh()
    shown = not ped.base.has_flag(lv.obj.FLAG.HIDDEN) and ed.mixer.has_flag(lv.obj.FLAG.HIDDEN)
    bad = outside(desk.base, w, h)
    check(tag + ": the Pedals button shows the switches in the mixer's place, and they fit",
          shown and not bad, "shown %r, outside: %r" % (shown, bad[:4]))
    port = Port()
    box.midi_in = port
    x1, y1, x2, y2 = coords(ped.learn_buttons[1])
    _headless.touch((x1 + x2) // 2, (y1 + y2) // 2, True, 40)
    _headless.touch((x1 + x2) // 2, (y1 + y2) // 2, False, 40)
    settle(lambda: box.midi.learning == 1 and ped.learn_buttons[1].get_child(0).get_text() == pedals.LEARNING, 1.0)
    armed = box.midi.learning == 1 and ped.learn_buttons[1].get_child(0).get_text() == pedals.LEARNING
    port.waiting.append(bytes((0xB0, 80, 127)))
    run(0.1)
    want = "2  CC 80 ch 1"
    settle(lambda: fped.learn_buttons[1].get_child(0).get_text() == want, 1.0)
    texts = [ped.learn_buttons[1].get_child(0).get_text(), fped.learn_buttons[1].get_child(0).get_text()]
    ped.base.update_layout()
    room = ped.learn_buttons[1].get_width() - floor.text_width(texts[0], ped.learn_buttons[1].get_child(0)
                                                                .get_style_text_font(0))
    check(tag + ": a switch's button arms it, and the switch it learns shows on both desks",
          armed and texts == [want, want] and box.midi.slots[1]["msg"] == ["cc", 0, 80] and
          room >= 8, "armed %r, %r, %d px to spare" % (armed, texts, room))
    fill = [b for b, _l in fped.bindings].index("fill") if fped.bindings else -1
    fped._binder(1)(fill)
    settle(lambda: ped.menus[1].get_selected() == fill, 1.0)
    check(tag + ": a binding chosen on one desk reaches the box and the other desk",
          box.midi.slots[1]["bind"] == "fill" and ped.menus[1].get_selected() == fill >= 0,
          "%r, %r" % (box.midi.slots[1]["bind"], ped.menus[1].get_selected()))
    box.midi_in = None
    ed._toggle_pedals()
    settle(lambda: not desk.remote_icon.has_flag(lv.obj.FLAG.HIDDEN), 1.0)
    joined = not desk.remote_icon.has_flag(lv.obj.FLAG.HIDDEN)
    uncast = desk.cast_icon.has_flag(lv.obj.FLAG.HIDDEN)
    box.cast = "Living room"
    settle(lambda: not desk.cast_icon.has_flag(lv.obj.FLAG.HIDDEN), 1.0)
    cast = not desk.cast_icon.has_flag(lv.obj.FLAG.HIDDEN)
    box.cast = ""
    check(tag + ": the header shows another screen joined, and the cast while there is one",
          joined and uncast and cast, "joined %r, no cast hidden %r, cast %r" % (joined, uncast, cast))
    desk.show_tab("perform")
    tempo = e.project["tempo"]
    b = desk.perform.base
    plus = None
    for i in range(b.get_child_count()):
        c = b.get_child(i)
        if c.get_child_count() == 1 and c.has_flag(lv.obj.FLAG.CLICKABLE) and coords(c)[0] > w * 0.85:
            plus = c
    if plus is not None:
        x1, y1, x2, y2 = coords(plus)
        _headless.touch((x1 + x2) // 2, (y1 + y2) // 2, True, 40)
        _headless.touch((x1 + x2) // 2, (y1 + y2) // 2, False, 40)
    run(0.2)
    check(tag + ": the tempo button changes the box's tempo", e.project["tempo"] == int(tempo + 0.5) + 1,
          "%r -> %r" % (tempo, e.project["tempo"]))
    check_prompt(tag, w, h, box, desk, far, run, settle)
    # The box stops answering with its socket still open, as one that resets does.
    for _ in range(desk_main.SILENT_MS // desk_main.STEP_MS + 2):
        far.step()
    check(tag + ": a remote desk whose box goes silent says the box went away", far.desk.panel is None and
          "went away" in (far.desk.message or ""), repr((far.desk.panel, far.desk.message)))
    far.close()
    near.close()
    box.close()
    scr.delete()
    other.delete()


def press(o):
    x1, y1, x2, y2 = coords(o)
    _headless.touch((x1 + x2) // 2, (y1 + y2) // 2, True, 40)
    _headless.touch((x1 + x2) // 2, (y1 + y2) // 2, False, 40)


def check_prompt(tag, w, h, box, desk, far, run, settle):
    """The prompt sheet: open, fits, asks, shows the song on both desks, plays and lets it go."""
    e = box.engine
    e.stop()
    first = box.model.doc["name"]
    press(desk.prompt_button)
    _headless.advance(5)
    _headless.refresh()
    sheet = desk.prompt
    check(tag + ": the header's button opens the prompt sheet, and the keys type into it",
          sheet.shown() and desk.typing())
    bad = outside(desk.base, w, h)
    check(tag + ": the prompt sheet fits the screen", not bad, "outside: %r" % bad[:4])
    sheet.field.set_text("a slow 12-bar blues at 72, 4 times through, slowing in the outro")
    press(sheet.ask_button)
    run(0.1)
    fp = far.desk.prompt
    settle(lambda: fp.preview is not None and sheet.preview is not None)
    shown = not sheet.card.has_flag(lv.obj.FLAG.HIDDEN) and sheet.title.get_text() == "Slow Twelve"
    check(tag + ": the song asked for shows on the desk before it plays: name, plan and form",
          box.ask_state == "ready" and shown and "4 times through" in sheet.plan.get_text()
          and len(sheet.strip.objs) == 3 and not e.transport["playing"],
          "%r %r %d" % (box.ask_state, sheet.title.get_text(), len(sheet.strip.objs)))
    check(tag + ": and on the remote desk", fp.preview is not None and fp.title.get_text() == "Slow Twelve")
    _headless.refresh()
    bad = outside(desk.base, w, h)
    check(tag + ": the song's card fits the sheet", not bad, "outside: %r" % bad[:4])
    fp._doer("play")()
    settle(lambda: e.transport["playing"])
    check(tag + ": Play on the remote desk starts it on the box", e.transport["playing"] and
          box.model.doc["name"] == "Slow Twelve" and e.form.repeat == 4)
    run(1.0)
    fp._doer("discard")()
    settle(lambda: box.model.doc["name"] == first and sheet.preview is None)
    check(tag + ": Discard brings back the song from before, and the card goes",
          box.model.doc["name"] == first and not e.transport["playing"] and sheet.card.has_flag(lv.obj.FLAG.HIDDEN))
    desk.toggle_prompt()
    check(tag + ": closed, the keys are the pedals again", not sheet.shown() and not desk.typing())


def main():
    p = None
    for a in sys.argv[1:]:
        if a.startswith("--plant="):
            p = a[len("--plant="):]
    plant(p)
    for w, h in SIZES:
        run_size(w, h)
    print("%d passed, %d failed" % (RESULTS[0], RESULTS[1]))
    if RESULTS[1]:
        sys.exit(1)


main()
