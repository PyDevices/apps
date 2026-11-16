# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Record a question from the board's microphone, and play speech as it arrives.

A `Recorder` fills one buffer, a little on every tick of the app, and a
`Player` writes sound to the speaker the same way, so neither holds the
screen. Both say how loud the sound just handled was, which is what the
ring round Huey and his mouth follow.
"""

from multimer import ticks_diff, ticks_ms

import boarddev
from audiodev import AudioFormat

_LAG_MS = 10  # a microphone is asked only for sound it has surely taken by now
_TAIL_MS = 600  # what a speaker may still hold after the last write


def level(data):
    """How loud 16-bit *data* is, 0 to 1: the largest of a sample in every eight."""
    most = 0
    for i in range(1, len(data), 16):
        high = data[i]
        if high > 127:
            high = 255 - high
        if high > most:
            most = high
    return most / 127


def open_microphone(rate):
    """The board's microphone, open at *rate*, mono."""
    mic = boarddev.pcm_in(AudioFormat(rate, 1, 16))
    mic.open()
    return mic


def open_speaker(rate, channels):
    """The board's speaker, open at *rate*."""
    speaker = boarddev.pcm_out(AudioFormat(rate, channels, 16))
    speaker.open()
    return speaker


class Recorder:
    """A question being recorded, 16-bit mono at *rate*, *seconds* at most.

    Args:
        rate (int): Samples a second.
        seconds (int): The longest recording; its buffer is made once, here.
        opener: What opens the microphone; `open_microphone` unless given.
    """

    def __init__(self, rate, seconds, opener=open_microphone):
        self.rate = rate
        #: The longest recording, in seconds.
        self.most = seconds
        self._opener = opener
        self._buffer = bytearray(rate * 2 * seconds)
        self._view = memoryview(self._buffer)
        self._mic = None
        self._got = 0
        self._began = 0
        #: How loud the newest sound was, 0 to 1, and the loudest of the recording.
        self.level = 0.0
        self.loudest = 0.0

    @property
    def recording(self):
        return self._mic is not None

    @property
    def full(self):
        return self._got >= len(self._buffer)

    def start(self):
        """Open the microphone and begin."""
        self._got = 0
        self.level = self.loudest = 0.0
        self._mic = self._opener(self.rate)
        self._began = ticks_ms()

    def _take(self):
        due = (ticks_diff(ticks_ms(), self._began) - _LAG_MS) * self.rate // 1000 * 2
        want = min(due, len(self._buffer)) - self._got
        want -= want % 2
        if want <= 0:
            return
        piece = self._view[self._got : self._got + want]
        self._mic.readinto(piece)
        self._got += want
        self.level = level(piece)
        if self.level > self.loudest:
            self.loudest = self.level

    def poll(self):
        """Take the sound that has come in since the last call."""
        if self._mic is not None:
            self._take()

    def stop(self):
        """Close the microphone.

        Returns:
            The recording, a view of this recorder's buffer: use it before the next `start`.
        """
        if self._mic is not None:
            try:
                self._take()
            finally:
                mic, self._mic = self._mic, None
                mic.close()
        return self._view[: self._got]

    def seconds(self):
        return self._got / (self.rate * 2)


class Player:
    """Speech played as it arrives.

    A worker `put`s sound in and calls `end` after the last of it; the app
    calls `play` on every tick, which hands the speaker what it has room for.

    Args:
        volume (int): 0 to 100.
        opener: What opens the speaker; `open_speaker` unless given.
    """

    #: Bytes that may wait here; the worker stops reading from the network while it is full.
    ROOM = 256 * 1024

    def __init__(self, volume, opener=open_speaker):
        self._opener = opener
        self._volume = volume
        self._speaker = None
        self._queue = []
        self._put = 0  # bytes put in: only the worker adds to it
        self._odd = b""  # the start of a frame whose end hasn't arrived
        #: Bytes in a frame of the speech: the worker sets it before the first `put`.
        self.frame = 2
        self._part = None  # what is left of the piece being written
        self._ended = False
        self._last = 0
        #: How loud the newest sound written was, 0 to 1.
        self.level = 0.0
        #: Bytes written to the speaker.
        self.played = 0

    # -- from the worker -------------------------------------------------

    def has_room(self):
        return self._put - self.played < self.ROOM

    def put(self, data):
        """Take *data* as it came off the network, and queue the whole frames in it."""
        if self._odd:
            data = self._odd + data
        over = len(data) % self.frame
        self._odd = bytes(data[len(data) - over :]) if over else b""
        if over:
            data = data[: len(data) - over]
        if data:
            self._queue.append(data)
            self._put += len(data)

    def end(self):
        self._ended = True

    # -- from the app ----------------------------------------------------

    def open(self, rate, channels):
        """Open the speaker for speech at *rate*."""
        self._speaker = self._opener(rate, channels)
        self._speaker.set_volume(self._volume)

    @property
    def is_open(self):
        return self._speaker is not None

    def play(self):
        """Hand the speaker what it will take now.

        Returns:
            True once the last of the speech has been played.
        """
        while True:
            if self._part is None:
                if not self._queue:
                    break
                self._part = memoryview(self._queue.pop(0))
            taken = self._speaker.try_write(self._part)
            if taken:
                self.level = level(self._part[:taken])
                self.played += taken
                self._last = ticks_ms()
            if taken < len(self._part):
                self._part = self._part[taken:]
                return False
            self._part = None
        # a write of nothing moves on what the speaker holds back
        self._speaker.try_write(b"")
        if not self._ended:
            return False
        self.level = 0.0
        return self.played == 0 or ticks_diff(ticks_ms(), self._last) > _TAIL_MS

    def close(self):
        """Stop at once and let the speaker go."""
        self._queue = []
        self._part = None
        self._ended = True
        if self._speaker is not None:
            speaker, self._speaker = self._speaker, None
            speaker.close()
