# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Huey on real LVGL with no window, no network and no sound hardware: a
question is held, heard, answered, acted out and spoken, and what can go
wrong is said on the screen.

    micropython -X heapsize=32M tests/huey_contract.py

``HUEY_PLANT`` swaps in a fault that a check below must catch;
test_huey.py runs each one.
"""

import os
import sys
import time

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path[:0] = [_HERE + "/..", _HERE]

import lvgl as lv

import _headless

W, H = 480, 320
frame = _headless.display(W, H)
_headless.pointer()

import huey_fakes
from apps import huey
from apps.huey import acting, actor, client, turn as turnmod, voice
from apps.perch import stage as stagemod

PLANT = os.getenv("HUEY_PLANT")
PLANTS = (
    "deaf", "no_key", "short_wav", "forgetful", "no_act", "strict", "wrong_rate", "lost_sound",
    "odd_frames", "shut_mouth", "open_speaker", "quiet_trouble", "hot_mic", "tap_asks", "leak",
)  # fmt: skip

stagemod.CACHE_BYTES = 900 * 1024
voice._TAIL_MS = 0  # the stand-in speaker holds nothing back

if PLANT == "deaf":
    actor.Actor.hit = lambda self, x, y: False
elif PLANT == "no_key":
    turnmod.settingsmod.read_key = lambda settings: ""
elif PLANT == "short_wav":
    _header = client.wav_header
    client.wav_header = lambda size, rate, channels=1: _header(size // 2, rate, channels)
elif PLANT == "forgetful":
    turnmod.KEPT = 0
elif PLANT == "no_act":
    actor.Actor.perform = lambda self, colors=None, place=None, variant=None: False
elif PLANT == "strict":
    acting._plain = lambda text: ""
elif PLANT == "wrong_rate":
    _speech = client.Speech

    class _Flat(_speech):
        def __init__(self, reply, rate):
            _speech.__init__(self, reply, rate)
            self.rate = 8000

    client.Speech = _Flat
elif PLANT == "lost_sound":
    _put = voice.Player.put
    voice.Player.put = lambda self, data: _put(self, data[: len(data) // 2 * 1 & ~1 or 2])
elif PLANT == "odd_frames":

    def _put_as_it_came(self, data):
        self._queue.append(data)
        self._put += len(data)

    voice.Player.put = _put_as_it_came
elif PLANT == "shut_mouth":
    turnmod._OPEN_ABOVE = 2.0
elif PLANT == "open_speaker":
    voice.Player.close = lambda self: None
elif PLANT == "quiet_trouble":
    huey._Show.say = lambda self, text, trouble: None
elif PLANT == "hot_mic":
    voice.Recorder.stop = lambda self: self._view[: self._got]
elif PLANT == "tap_asks":
    turnmod.SHORTEST = 0.0
elif PLANT == "leak":
    actor.Actor.close = lambda self: None
elif PLANT is not None:
    raise SystemExit("no such plant: %r" % PLANT)


def check(ok, what):
    if not ok:
        print("FAILED:", what)
        sys.exit(1)


folder = os.getenv("HUEY_SCRATCH") or "."
settings_path = folder + "/settings.json"
key_path = folder + "/huey.key"


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


write(key_path, huey_fakes.KEY + "\n")
write(settings_path, '{"key_file": "%s", "place": "desk", "volume": 55}' % key_path)

server = huey_fakes.Server()
sound = huey_fakes.Sound()
scope = huey_fakes.Scope(lv, (W, H), folder)
huey.start(scope, server.post, sound.microphone, sound.open_speaker)
stage, show, turn = scope.huey
worker = scope.worker


def step(n=1):
    for _ in range(n):
        for tick in scope.ticks:
            tick()
        _headless.advance(stagemod.TICK_MS)
        _headless.refresh()
        if sound.speaker is not None:
            sound.speaker.more()


def settle(limit=300):
    step()
    while stage.busy and limit:
        step()
        limit -= 1
    check(not stage.busy, "a change of place or colours finishes")


def on_huey():
    ox, oy = stage._origin()
    return int(ox), int(oy - H * 0.1)


def hold(seconds):
    """Press Huey, wait, and let go."""
    x, y = on_huey()
    _headless.touch(x, y, True, 0)
    step(3)
    held = turn.state
    time.sleep(seconds)
    step(2)
    ring = not show.ring_obj.has_flag(lv.obj.FLAG.HIDDEN)
    _headless.touch(x, y, False, 0)
    step(3)
    return held, ring


def answer():
    """Run the turn's three legs, a job and a few ticks at a time; return the poses seen and whether the mouth opened."""
    poses = []
    mouths = set()
    for _ in range(3):
        worker.run()
        for _ in range(60):
            step()
            poses.append(stage.pose)
            mouths.add(stage.mouth)
    for _ in range(400):
        if turn.state == "idle":
            break
        step()
        poses.append(stage.pose)
        mouths.add(stage.mouth)
    return poses, mouths


# The app opens at the desk, saying how to begin.
settle()
check(stage.place == "desk" and not stage.huey.has_flag(lv.obj.FLAG.HIDDEN), "Huey is at the desk when the app opens")
check(show.said is None and show.noted == "Hold me to talk", "a line says how to begin")

# A touch too short to be a question asks nothing.
held, _ = hold(0.05)
check(held == "listen", "a finger on Huey starts him listening")
check(turn.state == "idle" and not worker.jobs and not server.calls, "a tap sends nothing to the server")
check(sound.mic is not None and not sound.mic.open, "the microphone is closed after a tap")

# A question: held, he faces you and the ring shows what the microphone hears.
step(20)
held, ring = hold(0.7)
check(held == "listen" and ring, "while Huey is held he listens, and a ring shows the microphone's level")
check(turn.state == "hear" and stage.part == "think", "let go, the question is on its way and Huey thinks")
check(not sound.mic.open, "the microphone is closed once the question is asked")
check(len(worker.jobs) == 1, "one request is waiting: the question's words")
server.replies = ['{"say": "Winter! Watch me turn the colour of the sunset over the snow.", "mood": "happy", "colors": "sunset", "prop": "mug", "place": "coast", "variant": "winter"}']
worker.run()
headers, body = server.sent("/audio/transcriptions")
check(headers.get("Authorization") == "Bearer " + huey_fakes.KEY, "the key in the file the settings name goes with each request")
at = body.find(b"RIFF")
check(at > 0 and b"whisper" in body[:at], "the question goes up as a WAV file with the model's name")
size = int.from_bytes(body[at + 40 : at + 44], "little")
recorded = body[at + 44 : at + 44 + size]
check(size > 16000 * 2 * 0.5 and body[at + 44 + size :].startswith(b"\r\n--"), "the WAV says how long it is, and is all there")
check(int.from_bytes(body[at + 24 : at + 28], "little") == 16000 and max(recorded[i] for i in range(1, len(recorded), 2)) > 0x20, "it is the microphone's sound, at 16 kHz")
check(server.heard in show.noted, "what Huey understood is shown")
check(turn.state == "think" and len(worker.jobs) == 1, "then the reply is asked for")
step(40)
check(stage.pose is not None and stage.pose[0] == "think", "while he waits, his eyes wander")
check("Thinking" in show.noted, "the line says which leg he is waiting on")

poses, mouths = answer()
headers, body = server.sent("/chat/completions")
asked = __import__("json").loads(body.decode())
check(asked["messages"][0]["role"] == "system" and "desk" in asked["messages"][0]["content"], "the model is told who Huey is and where")
check(asked["messages"][-1] == {"role": "user", "content": server.heard}, "the question's words are what the model is asked")
check(turn.state == "idle" and turn.trouble is None, "the turn ends")
check(show.said == "Winter! Watch me turn the colour of the sunset over the snow.", "the answer is in the speech bubble")
check(not show.bubble.has_flag(lv.obj.FLAG.HIDDEN), "and the bubble is on the screen")
check((stage.place, stage.variant, stage.scheme) == ("coast", "winter", "sunset"), "Huey goes where the reply said, in the colours it said")
check(("hold", "mug", 0) in poses and ("hold", "mug", 1) in poses, "he speaks holding what the reply said")
check(mouths == {True, False}, "his mouth opens and closes with the sound")
headers, body = server.sent("/audio/speech")
check(__import__("json").loads(body.decode())["input"] == show.said, "the words in the bubble are the words spoken")
check(sound.speaker is not None and sound.speaker.rate == 24000, "the speaker is opened at the speech's own rate")
check(bytes(sound.speaker.got) == server.speech, "every byte of the speech reaches the speaker, and nothing else")
check(sound.speaker.volume == 55, "at the volume in the settings")
check(not sound.speaker.open, "the speaker is closed when the last word is out")
for leg in ("asked", "text", "reply", "voice", "spoke", "sound"):
    check(leg in turn.last, "the turn's %s is timed" % leg)
step(80)
check(stage.part == "idle", "then Huey goes back to his own life")
step(200)
check(show.said is None and show.bubble.has_flag(lv.obj.FLAG.HIDDEN), "the bubble goes away after a while")

# A second question: the model is shown the first, and a reply in plain words is spoken as it is.
server.heard = "and what do you eat"
server.replies.append("Crickets, **mostly**.")
hold(0.6)
answer()
asked = __import__("json").loads(server.sent("/chat/completions")[1].decode())
roles = [m["role"] for m in asked["messages"]]
check(roles == ["system", "user", "assistant", "user"], "the conversation so far goes with the next question")
check("coast (winter)" in asked["messages"][0]["content"], "and the model is told where Huey is now")
check(show.said == "Crickets, mostly." and turn.trouble is None, "a reply that is plain words is said as it is")
check(stage.place == "coast", "and Huey stays where he was")

# What Huey doesn't have is left out, and the rest is done.
server.replies.append('Sure! ```json\n{"say": "Off to the desk.", "prop": "sword", "place": "desk", "mood": "furious"}\n```')
hold(0.6)
answer()
check(show.said == "Off to the desk." and stage.place == "desk", "an object among other words is found, and a prop Huey doesn't have is left out")
check(turn.trouble is None, "without trouble")

# The server refuses: the screen says so, in words.
server.status = 401
hold(0.6)
answer()
check(turn.state == "idle" and turn.trouble is not None and "401" in turn.trouble, "a refusal from the server ends the turn")
check(show.said == turn.trouble and "Traceback" not in show.said, "and is said on the screen, in a sentence")
check(huey_fakes.KEY not in show.said, "which never shows the key")
check(stage.part == "idle", "Huey goes back to his own life")
server.status = 200

# No speaker: the answer is still shown.
sound.no_speaker = True
server.replies.append('{"say": "You can read me."}')
calls = len(server.calls)
hold(0.6)
answer()
check(turn.state == "speak" and stage.part == "speak", "with no speaker Huey mouths the words")
time.sleep(60 * len("You can read me.") / 1000 + 0.9)
step(3)
check(turn.mute and turn.state == "idle" and turn.trouble is None, "with no speaker the turn still ends well")
check(show.said == "You can read me.", "and the answer is in the bubble")
sound.no_speaker = False

# No microphone, no key, settings that aren't JSON: each is said, and nothing is sent.
calls = len(server.calls)
sound.no_microphone = True
hold(0.2)
check(turn.state == "idle" and show.said is not None and "microphone" in show.said, "no microphone is said on the screen")
sound.no_microphone = False
remove(key_path)
hold(0.2)
check(show.said is not None and "key" in show.said and key_path in show.said, "a missing key file is said on the screen, with its name")
write(key_path, huey_fakes.KEY)
write(settings_path, '{"key_file": ')
hold(0.2)
check(show.said is not None and "settings" in show.said, "settings that aren't JSON are said on the screen")
write(settings_path, '{"key_fill": "x"}')
hold(0.2)
check(show.said is not None and "key_fill" in show.said, "a setting there isn't is named")
check(len(server.calls) == calls and not worker.jobs, "and none of them sends anything")

# Closing lets go of the pictures, the microphone and the speaker.
write(settings_path, '{"key_file": "%s"}' % key_path)
x, y = on_huey()
_headless.touch(x, y, True, 0)
step(3)
check(turn.state == "listen" and sound.mic.open, "held again, he listens")
for fn in scope.closers:
    fn()
scope.root.delete()
check(not sound.mic.open, "closing the app closes the microphone")
check(not stage._frames and stage._shown is None and stage.held_bytes() <= len(stage._ground), "and drops every picture")
remove(key_path)
remove(settings_path)
print("ok")
