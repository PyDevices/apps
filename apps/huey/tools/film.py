# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Run a conversation with Huey on a display in memory and write a picture of each moment.

    micropython -X heapsize=128M tools/film.py OUT_DIR [WIDTH HEIGHT]

Run it from the app's folder, in a checkout of the apps repository, with a
MicroPython unix port that has LVGL and svgio. Nothing leaves the computer:
the server, the microphone and the speaker are the stand-ins the tests use.
Each picture is a 16-bit BMP named for the moment it shows.
"""

import sys
import time

sys.path.insert(0, "../..")
sys.path.insert(0, "../../tests")

import _headless  # noqa: E402
import huey_fakes  # noqa: E402
import lvgl as lv  # noqa: E402

from apps import huey  # noqa: E402
from apps.huey import voice  # noqa: E402
from apps.perch.stage import TICK_MS  # noqa: E402
from apps.perch.tools.still import write_bmp  # noqa: E402

REPLY = (
    '{"say": "Winter, easily. Come and see the coast with me, I turn the colour of snow.", '
    '"mood": "happy", "prop": "mug", "place": "coast", "variant": "winter"}'
)


def main():
    out = sys.argv[1]
    w, h = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (800, 480)
    frame = _headless.display(w, h)
    _headless.pointer()
    with open(out + "/huey.key", "w") as f:
        f.write(huey_fakes.KEY)
    with open(out + "/settings.json", "w") as f:
        f.write('{"base_url": "http://stand-in.invalid:5000/v1", "key_file": "%s/huey.key"}' % out)
    voice._TAIL_MS = 0
    server = huey_fakes.Server()
    server.heard = "Which season do you like best?"
    server.replies = [REPLY]
    server.speech = huey_fakes.tone(3.0)
    sound = huey_fakes.Sound()
    scope = huey_fakes.Scope(lv, (w, h), out)
    huey.start(scope, server.post, sound.microphone, sound.open_speaker)
    stage, show, turn = scope.huey

    def step(n=1):
        for _ in range(n):
            for tick in scope.ticks:
                tick()
            _headless.advance(TICK_MS)
            _headless.refresh()
            if sound.speaker is not None:
                sound.speaker.more()

    def shoot(name):
        write_bmp("%s/%s.bmp" % (out, name), frame, w, h)
        print(name, turn.state, stage.part, stage.pose, repr(show.noted))

    def settle():
        step()
        while stage.busy:
            step()

    settle()
    step(30)
    shoot("1_idle")
    ox, oy = stage._origin()
    x, y = int(ox), int(oy - h * 0.1)
    _headless.touch(x, y, True, 0)
    step(20)
    time.sleep(1.2)
    step(3)
    shoot("2_listening")
    _headless.touch(x, y, False, 0)
    step(40)
    shoot("3_making_out_the_words")
    scope.worker.run()
    step(45)
    shoot("4_thinking")
    scope.worker.run()
    step(6)
    shoot("5_answer_arrives")
    settle()
    step(10)
    shoot("6_finding_his_voice")
    scope.worker.run()
    shot = False
    for _ in range(600):
        step()
        if turn.state == "speak" and stage.mouth and stage.pose == ("hold", "mug", 1) and not shot:
            shoot("7_speaking")
            shot = True
        if turn.state == "idle":
            break
    step(12)
    shoot("8_settling")
    step(260)
    shoot("9_back_to_his_own_life")
    server.status = 401
    _headless.touch(*((int(stage._origin()[0]), int(stage._origin()[1] - h * 0.1)) + (True, 0)))
    step(4)
    time.sleep(0.6)
    step(2)
    _headless.touch(0, 0, False, 0)
    step(3)
    scope.worker.run()
    step(20)
    shoot("10_trouble")
    for fn in scope.closers:
        fn()


main()
