# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Talk to an OpenAI-compatible server: speech to text, a chat reply, text to speech.

`Client` makes the three calls a turn needs, ``audio/transcriptions``,
``chat/completions`` and ``audio/speech``, against the address and models in
the app's settings. Every call blocks: make it from a worker.
"""

import json

from . import web

_EDGE = "huey-speech-edge-7c1f"


class ServerError(Exception):
    """The server answered, and refused: its status and what it said."""


def wav_header(size, rate, channels=1):
    """The 44 bytes that go before *size* bytes of 16-bit PCM to make a WAV file."""
    block = channels * 2
    head = bytearray(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00")
    head[4:8] = (36 + size).to_bytes(4, "little")
    head += channels.to_bytes(2, "little") + rate.to_bytes(4, "little") + (rate * block).to_bytes(4, "little")
    head += block.to_bytes(2, "little") + b"\x10\x00data" + size.to_bytes(4, "little")
    return bytes(head)


class Speech:
    """Speech on its way from the server: its `rate` and `channels`, and 16-bit PCM through `read`."""

    def __init__(self, reply, rate):
        self._reply = reply
        self._held = b""
        self.rate = rate
        self.channels = 1
        first = self._exactly(12)
        if first[:4] != b"RIFF":
            kind = reply.headers.get("content-type", "")
            if "pcm" not in kind and "octet-stream" not in kind and "l16" not in kind.lower():
                raise ValueError("the speech came as %s, not as WAV or PCM" % (kind or "something unnamed"))
            # bare PCM, at the rate the settings give
            self._held = first
            return
        while True:
            name_size = self._exactly(8)
            size = int.from_bytes(name_size[4:8], "little")
            if name_size[:4] == b"data":
                return
            chunk = self._exactly(size + (size & 1))
            if name_size[:4] == b"fmt ":
                if chunk[0:2] != b"\x01\x00" or chunk[14:16] != b"\x10\x00":
                    raise ValueError("the speech isn't 16-bit PCM")
                self.channels = int.from_bytes(chunk[2:4], "little")
                self.rate = int.from_bytes(chunk[4:8], "little")

    def _exactly(self, size):
        parts = []
        while size > 0:
            data = self._reply.read(size)
            if not data:
                raise ValueError("the speech ended inside its header")
            parts.append(data)
            size -= len(data)
        return b"".join(parts)

    def read(self, size):
        """Up to *size* bytes of sound, and ``b""`` at the end."""
        if self._held:
            data, self._held = self._held, b""
            return data
        return self._reply.read(size)

    def close(self):
        self._reply.close()


class Chat:
    """A reply on its way: `text` so far, `more` to read the next of it, and `done` once it is all here.

    A server that sends the reply whole, not in pieces, gives a `Chat` that
    is done at once.
    """

    def __init__(self, reply):
        self._reply = reply
        self._parts = []
        self._held = b""
        self.done = False
        if "event-stream" not in reply.headers.get("content-type", ""):
            try:
                found = json.loads(reply.read_all(65536).decode())
            finally:
                self.close()
            self._parts.append(found["choices"][0]["message"]["content"] or "")

    @property
    def text(self):
        return "".join(self._parts)

    def more(self):
        """Wait for the next of the reply, and take it in."""
        if self.done:
            return
        data = self._reply.read(1024)
        if not data:
            self.close()
            return
        lines = (self._held + data).split(b"\n")
        self._held = lines.pop()
        for line in lines:
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            line = line[5:].strip()
            if line == b"[DONE]":
                # all of it is here; what follows is the end of the stream
                self._reply.read_all(1024)
                self.close()
                return
            event = json.loads(line)
            if event.get("error"):
                trouble = event["error"]
                raise ServerError("the reply stopped: %s" % (trouble.get("message", trouble) if isinstance(trouble, dict) else trouble,))
            choices = event.get("choices")
            piece = choices and (choices[0].get("delta") or {}).get("content")
            if piece:
                self._parts.append(piece)

    def close(self):
        """Stop reading, whether or not all of it came."""
        self.done = True
        self._reply.close()


class Client:
    """The three calls of a turn, against one server.

    Args:
        settings (dict): ``base_url``, the three models, ``voice`` and
            ``speech_rate``, as `settings.load` gives them.
        key (str): The API key, or ``""`` for a server that asks for none.
        post: What sends a request; `web.post` unless a test gives its own.
        speech_post: What sends the request for speech, when it isn't
            *post*: speech can be asked for while a reply still arrives.
    """

    def __init__(self, settings, key, post=web.post, speech_post=None):
        self.settings = settings
        self._key = key
        self._post = post
        self._speech_post = speech_post or post
        self.base = settings["base_url"].rstrip("/")

    def _send(self, path, headers, pieces, timeout, post=None):
        if self._key:
            headers["Authorization"] = "Bearer " + self._key
        reply = (post or self._post)(self.base + path, headers, pieces, timeout)
        if reply.status != 200:
            try:
                said = reply.read_all(4096).decode()
            finally:
                reply.close()
            try:
                found = json.loads(said)
                detail = found.get("error", found.get("detail", said))
                if isinstance(detail, dict):
                    detail = detail.get("message", detail)
                said = str(detail)
            except ValueError:
                pass
            raise ServerError("%d from %s: %s" % (reply.status, path, " ".join(said.split())[:160]))
        return reply

    def _json(self, path, headers, pieces, timeout):
        reply = self._send(path, headers, pieces, timeout)
        try:
            return json.loads(reply.read_all(65536).decode())
        finally:
            reply.close()

    def transcribe(self, pcm, rate):
        """The words in *pcm*, 16-bit mono sound at *rate*, as text."""
        head = (
            '--%s\r\nContent-Disposition: form-data; name="model"\r\n\r\n%s\r\n'
            '--%s\r\nContent-Disposition: form-data; name="response_format"\r\n\r\njson\r\n'
            '--%s\r\nContent-Disposition: form-data; name="file"; filename="speech.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ) % (_EDGE, self.settings["stt_model"], _EDGE, _EDGE)
        pieces = [head.encode(), wav_header(len(pcm), rate), pcm, ("\r\n--%s--\r\n" % _EDGE).encode()]
        found = self._json("/audio/transcriptions", {"Content-Type": "multipart/form-data; boundary=" + _EDGE}, pieces, 60)
        return found["text"].strip()

    def _chat_body(self, messages):
        body = {"model": self.settings["chat_model"], "messages": messages, "max_tokens": 200, "temperature": 0.7}
        # lite-assistant otherwise offers the model its own tools, which
        # grows the prompt a hundredfold; other servers pass over it
        body["builtin_tools"] = False
        return body

    def chat(self, messages):
        """The model's reply to *messages*, as text."""
        found = self._json("/chat/completions", {"Content-Type": "application/json"}, [json.dumps(self._chat_body(messages)).encode()], 60)
        return found["choices"][0]["message"]["content"] or ""

    def chat_stream(self, messages):
        """The model's reply to *messages* as a `Chat`, to read as it arrives."""
        body = self._chat_body(messages)
        body["stream"] = True
        reply = self._send("/chat/completions", {"Content-Type": "application/json"}, [json.dumps(body).encode()], 60)
        try:
            return Chat(reply)
        except Exception:
            reply.close()
            raise

    def speak(self, text):
        """*text* as speech: a `Speech` to read and then close."""
        body = {"model": self.settings["tts_model"], "input": text, "response_format": "wav"}
        if self.settings["voice"]:
            body["voice"] = self.settings["voice"]
        reply = self._send("/audio/speech", {"Content-Type": "application/json"}, [json.dumps(body).encode()], 60, self._speech_post)
        try:
            return Speech(reply, self.settings["speech_rate"])
        except Exception:
            reply.close()
            raise
