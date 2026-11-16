# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Stand-ins for everything Huey reaches outside the app: the server, the worker, the microphone, the speaker.

The contract script and the app's film script both run whole turns on them,
with no network and no sound hardware.
"""

import json

from apps.huey import web
from apps.huey.client import wav_header

KEY = "not-a-real-key"


class _Stream:
    """Bytes read the way a socket is."""

    def __init__(self, data):
        self.data = data
        self.at = 0
        self.closed = False

    def readline(self):
        end = self.data.find(b"\n", self.at) + 1 or len(self.data)
        line = self.data[self.at : end]
        self.at = end
        return line

    def read(self, size):
        piece = self.data[self.at : self.at + size]
        self.at += len(piece)
        return piece

    def close(self):
        self.closed = True


def _chunked(body, size=999):
    out = []
    for at in range(0, len(body), size):
        piece = body[at : at + size]
        out.append(b"%x\r\n" % len(piece) + piece + b"\r\n")
    out.append(b"0\r\n\r\n")
    return b"".join(out)


def tone(seconds, rate=24000, period=96, loud=9000):
    """A square wave as 16-bit mono PCM: something a speaker can be seen to get."""
    one = (loud).to_bytes(2, "little") * (period // 2) + (65536 - loud).to_bytes(2, "little") * (period // 2)
    return one * (int(seconds * rate) // period)


class Server:
    """An OpenAI-compatible server in memory: give it as a `Turn`'s *post*.

    `heard` is what a transcription answers, `replies` the chat answers in
    turn (the last one again when they run out), `speech` the PCM an answer
    is spoken with. `calls` keeps every request as ``(path, headers, body)``.
    `status` other than 200 is what every call answers with.
    """

    def __init__(self):
        self.heard = "what season do you like best"
        self.replies = ['{"say": "Winter. Watch me turn the colour of snow."}']
        self.speech = tone(1.0)
        self.speech_kind = "audio/wav"
        self.status = 200
        self.calls = []
        #: For each request for speech: True when a reply sent in pieces was still arriving.
        self.early = []
        self._chat = None

    def post(self, url, headers, pieces, timeout=30):
        path = url
        for known in ("/audio/transcriptions", "/chat/completions", "/audio/speech"):
            if url.endswith(known):
                path = known
        body = b"".join(bytes(piece) for piece in pieces)
        self.calls.append((path, dict(headers), body))
        if self.status != 200:
            return self._reply(self.status, "application/json", json.dumps({"error": {"message": "the key was refused"}}).encode())
        if path == "/audio/transcriptions":
            return self._reply(200, "application/json", json.dumps({"text": self.heard}).encode())
        if path == "/chat/completions":
            chats = len([call for call in self.calls if call[0] == path])
            text = self.replies[min(chats, len(self.replies)) - 1]
            if json.loads(body).get("stream"):
                # as a server streams it: a few characters an event
                events = []
                for at in range(0, len(text), 7):
                    events.append("data: " + json.dumps({"choices": [{"delta": {"content": text[at : at + 7]}}]}) + "\n\n")
                events.append("data: [DONE]\n\n")
                reply = self._reply(200, "text/event-stream", "".join(events).encode(), chunked=True)
                self._chat = reply._stream
                return reply
            return self._reply(200, "application/json", json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}]}).encode())
        if path == "/audio/speech":
            chat = self._chat
            self.early.append(chat is not None and chat.at < len(chat.data))
            sound = self.speech
            if self.speech_kind == "audio/wav":
                sound = wav_header(len(sound), 24000) + sound
            return self._reply(200, self.speech_kind, sound, chunked=True)
        return self._reply(404, "text/plain", b"no such path")

    def _reply(self, status, kind, body, chunked=False):
        head = "HTTP/1.1 %d X\r\nContent-Type: %s\r\n" % (status, kind)
        if chunked:
            data = (head + "Transfer-Encoding: chunked\r\n\r\n").encode() + _chunked(body)
        else:
            data = (head + "Content-Length: %d\r\n\r\n" % len(body)).encode() + body
        stream = _Stream(data)
        return web.Reply(stream, stream)

    def sent(self, path):
        """The last request to *path*: ``(headers, body)``."""
        for call in reversed(self.calls):
            if call[0] == path:
                return call[1], call[2]
        raise KeyError(path)


class Worker:
    """``scope.worker`` with nothing in the background: `run` does the next job, here and now."""

    def __init__(self):
        self.jobs = []

    def submit(self, work, done=None, key=None, release=None):
        self.jobs.append((work, done))

    def run(self):
        """Do the oldest waiting job and hand its result back; False when none waits."""
        if not self.jobs:
            return False
        work, done = self.jobs.pop(0)
        value = error = None
        try:
            value = work()
        except Exception as e:
            error = e
        if done is not None:
            done(value, error)
        return True

    def cancel(self):
        self.jobs = []


class Microphone:
    """A microphone that hears a steady tone."""

    def __init__(self, rate):
        self.rate = rate
        self.open = True
        self.read = 0

    def readinto(self, buf):
        for i in range(0, len(buf) - 1, 2):
            buf[i] = 0x10
            buf[i + 1] = 0x27 if (self.read + i) % 64 < 32 else 0xD8
        self.read += len(buf)
        return len(buf)

    def close(self):
        self.open = False


class Speaker:
    """A speaker that keeps what it is given, `ROOM` bytes between one `more` and the next."""

    ROOM = 1920

    def __init__(self, rate, channels):
        self.rate = rate
        self.channels = channels
        self.open = True
        self.volume = None
        self.got = bytearray()
        self.room = self.ROOM

    def more(self):
        """Time has passed: there is room again."""
        self.room = self.ROOM

    def set_volume(self, percent):
        self.volume = percent

    def try_write(self, data):
        if len(data) % (2 * self.channels):
            raise ValueError("PCM buffer must contain complete frames")
        taken = min(len(data), self.room)
        taken -= taken % (2 * self.channels)
        self.room -= taken
        self.got += bytes(data[:taken])
        return taken

    def close(self):
        self.open = False


class Sound:
    """Opens `Microphone`s and `Speaker`s for a `Turn`, and keeps the last of each."""

    def __init__(self):
        self.mic = None
        self.speaker = None
        self.no_microphone = False
        self.no_speaker = False

    def microphone(self, rate):
        if self.no_microphone:
            raise OSError("no microphone")
        self.mic = Microphone(rate)
        return self.mic

    def open_speaker(self, rate, channels):
        if self.no_speaker:
            raise OSError("no speaker")
        self.speaker = Speaker(rate, channels)
        return self.speaker


class Scope:
    """As much of an appkit scope as the app uses."""

    def __init__(self, lv, size, data_dir):
        self.size = size
        self.root = lv.obj(None)
        lv.screen_load(self.root)
        self.ticks = []
        self.closers = []
        self.worker = Worker()
        self.data_dir = data_dir

    def every(self, ms, callback):
        self.ticks.append(callback)

    def on_close(self, fn):
        self.closers.append(fn)
