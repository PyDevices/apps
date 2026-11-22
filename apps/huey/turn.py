# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""One turn of a conversation with Huey, from the question to the last word of the answer.

A `Turn` takes a press and a release, records what is said between them and
sends it through the three legs of an answer: the sound becomes text, the
text gets a reply, the reply becomes speech. Each leg runs on the app's
worker, so the picture keeps moving, and each one's time is kept in `last`.
"""

import time
from multimer import ticks_diff, ticks_ms

from . import acting, servers, settings as settingsmod, web
from .client import Client
from .voice import Player, Recorder

try:
    import network
except ImportError:  # a computer is on its network already
    network = None
try:
    from _thread import get_ident
except ImportError:  # no threads: the worker runs its jobs between ticks
    get_ident = None

RATE = 16000  # what the question is recorded at
SHORTEST = 0.4  # seconds: a shorter hold is a tap, not a question
KEPT = 6  # messages of the conversation the model is shown again
_OPEN_ABOVE = 0.1  # how loud the speech must be for his mouth to open


class Turn:
    """The conversation: `press` and `release` Huey, and call `tick` on every tick of the app.

    Args:
        stage: The `actor.Actor` that plays it out.
        show: Where words go: ``note(text)`` for what is happening,
            ``heard(text)`` for the question as it was understood,
            ``say(text, trouble)`` for the answer or what went wrong, and
            ``ring(level)`` for how loud the microphone hears, None when he isn't listening.
        worker: The app's ``scope.worker``.
        path (str): The settings file.
        post: What sends a request; a `web.Session`'s, kept from turn to
            turn, unless a test gives its own.
        microphone: What opens the microphone at a rate, in place of the board's.
        speaker: What opens the speaker at a rate and a count of channels, in place of the board's.
    """

    def __init__(self, stage, show, worker, path, post=None, microphone=None, speaker=None):
        self.stage = stage
        self.show = show
        self.worker = worker
        self.path = path
        #: The connections to the server, kept open across legs and turns:
        #: one for words, one for speech, which can be asked for while the
        #: reply still arrives. None when a test sends its own way.
        self.session = self.voice_session = None
        speech_post = None
        if post is None:
            self.session = web.Session()
            self.voice_session = web.Session()
            post, speech_post = self.session.post, self.voice_session.post
        self._post = post
        self._speech_post = speech_post
        self._microphone = microphone
        self._speaker = speaker
        #: "idle", "listen", "hear", "think", "voice" (the speech is on its way) or "speak".
        self.state = "idle"
        #: What the last finished turn took: seconds of question in ``asked``;
        #: milliseconds in ``text``, ``reply``, ``voice`` (to the first
        #: sound) and ``spoke``; bytes of speech in ``sound``; the question
        #: and the answer as ``heard`` and ``said``.
        self.last = {}
        #: Why the last turn stopped short, or None.
        self.trouble = None
        #: True once a speaker was asked for and there was none: answers are then only shown.
        self.mute = False
        self.history = []
        self.settings = None
        self._client = None
        self._recorder = None
        for session in (self.session, self.voice_session):
            if session is not None:
                session.close()
        self._player = None
        self._id = 0
        self._began = 0
        self._format = None
        self._act = None
        self._asked = None
        self._rest = None  # (turn, text): the whole reply, come after his words
        self._timing = {}
        self._open_for = 0
        self._until = 0
        self._thread = None  # the worker's thread, while it is running a job of this turn's
        #: Ticks that arrived on the worker's thread, and were left for the next one.
        self.strays = 0

    def _job(self, work):
        """*work* as the worker runs it: for as long as it runs, `astray` knows the worker's thread."""

        def run():
            self._thread = get_ident() if get_ident is not None else None
            try:
                return work()
            finally:
                self._thread = None

        return run

    def astray(self):
        """True when this is the worker's thread, in the middle of a job.

        Where threads share one interpreter lock (an ESP32), a timer's
        callback runs on whichever thread looks for one next, and that can
        be the worker, part way through a network call on its own small
        stack. A place or a pose isn't drawn from there: the app leaves a
        tick that finds itself there to the next one.
        """
        if self._thread is None or get_ident() != self._thread:
            return False
        self.strays += 1
        return True

    # -- what stands in the way ------------------------------------------

    def ready(self):
        """Load the settings and the key.

        Returns:
            None when a turn can begin, or what to tell the person holding Huey.
        """
        try:
            self.settings = settingsmod.load(self.path)
        except ValueError as e:
            return "My settings need a fix: %s." % (e,)
        # The server chosen in the device's picker, when there is one.
        self.settings = servers.use(self.settings)
        if not self.settings["base_url"]:
            return "Tell me where my server is: its address goes in %s as base_url." % self.path
        try:
            key = settingsmod.read_key(self.settings)
        except OSError:
            return "I need a key to think with. Put it in %s, a file the settings name." % self.settings["key_file"]
        if network is not None and not network.WLAN(network.STA_IF).isconnected():
            return "I'm not on Wi-Fi, so I can't think. Join a network and hold me again."
        self._client = Client(self.settings, key, self._post, self._speech_post)
        return None

    def _stop(self, why):
        """End the turn here, and say *why* on the screen."""
        self._id += 1
        self.state = "idle"
        self.trouble = why
        self._drop_player()
        print("huey:", why)
        self.show.ring(None)
        self.show.note("")
        self.show.say(why, True)
        self.stage.rest()

    def _drop_player(self):
        if self._player is not None:
            player, self._player = self._player, None
            try:
                player.close()
            except Exception as e:
                print("huey: closing the speaker:", e)

    # -- the question ------------------------------------------------------

    def press(self):
        """A finger on Huey: whatever he was doing stops, and he listens."""
        self._id += 1
        self._drop_player()
        self.trouble = None
        why = self.ready()
        if why:
            self._stop(why)
            return
        seconds = self.settings["listen_seconds"]
        if self._recorder is None or self._recorder.most != seconds:
            if self._microphone is None:
                self._recorder = Recorder(RATE, seconds)
            else:
                self._recorder = Recorder(RATE, seconds, self._microphone)
        try:
            self._recorder.start()
        except Exception as e:
            self._stop("I can't hear you: no microphone answers here (%s)." % (e,))
            return
        self.state = "listen"
        self._began = ticks_ms()
        self._warm()
        self.stage.listen()
        self.show.say(None, False)
        self.show.note("Listening")

    def _warm(self):
        """While the question is asked, open the connections its answer will need."""
        sessions, base = (self.session, self.voice_session), self._client.base
        if sessions[0] is None:
            return

        def warm():
            for session in sessions:
                try:
                    session.warm(base, 30)
                except Exception as e:
                    # the leg that needs it opens it again, and says so if it can't
                    print("huey: opening a connection early:", e)

        self.worker.submit(self._job(warm))

    def release(self):
        """The finger lifts: the question is over, and its answer is on the way."""
        if self.state != "listen":
            return
        try:
            sound = self._recorder.stop()
        except Exception as e:
            self._stop("I lost the microphone (%s)." % (e,))
            return
        self.show.ring(None)
        if self._recorder.seconds() < SHORTEST:
            self.state = "idle"
            self.show.note("Hold me while you talk")
            self.stage.rest()
            return
        self._hear(sound, RATE, self._recorder.seconds())

    def hear(self, sound, rate):
        """Take a question already recorded, 16-bit mono *sound* at *rate*, as if it had just been asked.

        Returns:
            None, or what stands in the way of a turn.
        """
        self._id += 1
        self._drop_player()
        self.trouble = None
        why = self.ready()
        if why:
            self._stop(why)
            return why
        self.show.say(None, False)
        self._hear(sound, rate, len(sound) / (rate * 2))
        return None

    def _hear(self, sound, rate, seconds):
        self.state = "hear"
        self._timing = {"asked": seconds}
        self._began = ticks_ms()
        self.stage.think()
        client, turn = self._client, self._id
        self.worker.submit(self._job(lambda: client.transcribe(sound, rate)), lambda text, error: self._on_text(turn, text, error))

    def _leg(self, name):
        now = ticks_ms()
        self._timing[name] = ticks_diff(now, self._began)
        self._began = now

    def _on_text(self, turn, text, error):
        if turn != self._id:
            return
        if error is not None:
            self._stop("I couldn't make out the words: %s." % (error,))
            return
        self._leg("text")
        if not text:
            self._stop("I didn't catch that. Hold me and say it again?")
            return
        self._timing["heard"] = text
        self.show.heard(text)
        self.show.note("Thinking")
        self.state = "think"
        stage = self.stage
        messages = [{"role": "system", "content": acting.prompt(stage.place, stage.variant, stage.scheme)}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": text})
        client = self._client

        def think():
            # read until the words he says are whole; the rest comes while he says them
            chat = client.chat_stream(messages)
            try:
                while not chat.done and acting.early(chat.text) is None:
                    chat.more()
            except Exception:
                chat.close()
                raise
            return chat

        self.worker.submit(self._job(think), lambda chat, error: self._on_reply(turn, text, chat, error))

    def _on_reply(self, turn, asked, chat, error):
        if turn != self._id:
            if chat is not None:
                chat.close()
            return
        if error is not None:
            self._stop("I couldn't think of an answer: %s." % (error,))
            return
        self._leg("reply")
        self._asked = asked
        if chat.done:
            try:
                act = acting.read(chat.text, self.stage.place)
            except ValueError:
                self._stop("I lost my words. Hold me and ask again?")
                return
            say, chat = act.say, None
        else:
            # the words are whole and the rest is on its way: he can begin
            act = None
            say = acting.early(chat.text)
        self._act = act
        self._rest = None
        self._timing["said"] = say
        self.show.say(say, False)
        if act is not None:
            self._acted(act)
        if self.mute:
            self._speak_silently(say)
            if chat is not None:
                self.worker.submit(self._job(lambda: self._read_rest(turn, chat)))
            return
        self.state = "voice"
        self._format = None
        if self._speaker is None:
            player = self._player = Player(self.settings["volume"])
        else:
            player = self._player = Player(self.settings["volume"], self._speaker)
        client = self._client

        def fetch():
            try:
                speech = client.speak(say)
                try:
                    player.frame = 2 * speech.channels
                    self._format = (turn, speech.rate, speech.channels)
                    while turn == self._id and self._player is player:
                        if not player.has_room():
                            if chat is not None and not chat.done:
                                self._read_rest(turn, chat, False)
                            else:
                                time.sleep(0.02)
                            continue
                        data = speech.read(4096)
                        if not data:
                            break
                        player.put(data)
                finally:
                    speech.close()
                    player.end()
            finally:
                if chat is not None:
                    self._read_rest(turn, chat)

        self.worker.submit(self._job(fetch), lambda _, error: self._on_spoken(turn, error))

    def _read_rest(self, turn, chat, wait=True):
        """On the worker: more of the reply, all of it when *wait*, handed to `tick` once it is all here."""
        if chat.done:
            return  # an earlier call read the end and handed it over
        try:
            chat.more()
            while wait and turn == self._id and not chat.done:
                chat.more()
        except Exception as e:
            # he has said his words; what he does with them is lost
            print("huey: the rest of the reply:", e)
            chat.close()
            return
        if not chat.done:
            if wait:
                chat.close()  # the turn moved on
        else:
            self._rest = (turn, chat.text)

    def _acted(self, act):
        """The reply is all here: remember it, and act it out."""
        self.history.append({"role": "user", "content": self._asked})
        self.history.append({"role": "assistant", "content": act.record()})
        self.history = self.history[-KEPT:] if KEPT else []
        self.stage.perform(act.colors, act.place, act.variant)
        if self.state == "speak":
            self.stage.mood = act.mood or "calm"
            self.stage.prop = act.prop

    def _on_spoken(self, turn, error):
        if turn == self._id and error is not None:
            self._stop("I couldn't find my voice: %s." % (error,))

    def _speak_silently(self, say):
        self.state = "speak"
        self._leg("voice")
        self._until = 60 * len(say) + 800
        self._pose()

    def _pose(self):
        act = self._act
        self.stage.speak((act and act.mood) or "calm", act and act.prop)

    # -- every tick --------------------------------------------------------

    def tick(self):
        rest = self._rest
        if rest is not None and rest[0] == self._id:
            # the reply is all here, perhaps after his words were said
            self._rest = None
            try:
                self._act = acting.read(rest[1], self.stage.place)
            except ValueError:
                pass  # nothing more to act out than the words he said
            else:
                self._acted(self._act)
        state = self.state
        if state == "idle":
            return
        waited = ticks_diff(ticks_ms(), self._began) // 1000
        if state == "listen":
            try:
                self._recorder.poll()
            except Exception as e:
                self._stop("I lost the microphone (%s)." % (e,))
                return
            self.show.ring(self._recorder.level)
            self.show.note("Listening  %d s" % waited)
            if self._recorder.full:
                self.release()
        elif state == "hear":
            self.show.note("Making out the words  %d s" % waited)
        elif state == "think":
            self.show.note("Thinking  %d s" % waited)
        elif state == "voice":
            self.show.note("Finding my voice  %d s" % waited)
            found = self._format
            if found is not None and found[0] == self._id:
                self._format = None
                try:
                    self._player.open(found[1], found[2])
                except Exception as e:
                    # the words are on the screen: the turn goes on without sound
                    print("huey: no speaker:", e)
                    self.mute = True
                    self._drop_player()
                    self._speak_silently(self._timing["said"])
                    self.show.note("No speaker here: read my words")
                    return
                self._leg("voice")
                self.state = "speak"
                self.show.note("")
                self._pose()
        elif state == "speak":
            if self._player is None:
                # no speaker: his mouth keeps time with the length of the words
                self._open_for = (self._open_for + 1) % 8
                self.stage.mouth = self._open_for < 4
                if ticks_diff(ticks_ms(), self._began) >= self._until:
                    self._finish(0)
                return
            try:
                done = self._player.play()
            except Exception as e:
                self._stop("My speaker stopped: %s." % (e,))
                return
            # open on a loud moment, and for a few ticks, so it doesn't flutter
            if self._player.level > _OPEN_ABOVE:
                self._open_for = 3
            elif self._open_for:
                self._open_for -= 1
            self.stage.mouth = self._open_for > 0
            if done:
                self._finish(self._player.played)

    def _finish(self, sound):
        self._leg("spoke")
        self._timing["sound"] = sound
        self.last = self._timing
        self._drop_player()
        self.state = "idle"
        self.show.note("")
        self.stage.settle()
        t = self.last
        print("huey: asked %.1f s, text %d ms, reply %d ms, voice %d ms, spoke %d ms" % (t["asked"], t["text"], t["reply"], t["voice"], t["spoke"]))

    def close(self):
        """Stop whatever is under way and let the microphone and speaker go."""
        self._id += 1
        self.state = "idle"
        self._drop_player()
        if self._recorder is not None and self._recorder.recording:
            try:
                self._recorder.stop()
            except Exception as e:
                print("huey: closing the microphone:", e)
        self._recorder = None
        for session in (self.session, self.voice_session):
            if session is not None:
                session.close()
