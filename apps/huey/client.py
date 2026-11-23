# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Talk to an OpenAI-compatible server: speech to text, a chat reply, text to speech.

`Client` makes the three calls a turn needs, ``audio/transcriptions``,
``chat/completions`` and ``audio/speech``, against the address and models in
the app's settings. Every call blocks: make it from a worker.
"""

import json

import chatclient
from chatclient import Chat, ServerError, web  # noqa: F401 - Huey's names for them

_EDGE = "huey-speech-edge-7c1f"


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


class Client(chatclient.Client):
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
        chatclient.Client.__init__(self, settings["base_url"], key, post)
        self.settings = settings
        self._speech_post = speech_post or post

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

    def chat(self, messages):
        """The model's reply to *messages*, as text."""
        return chatclient.Client.chat(self, messages, self.settings["chat_model"], max_tokens=200, temperature=0.7)

    def chat_stream(self, messages):
        """The model's reply to *messages* as a `Chat`, to read as it arrives."""
        return chatclient.Client.chat_stream(self, messages, self.settings["chat_model"], max_tokens=200, temperature=0.7)

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
