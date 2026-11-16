# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The sound out, and what rendering it costs.

On a board whose ``board_peripherals`` publishes ``AUDIO_OUT`` with an I2S
wire, and whose firmware has the audio pump's I2S driver, the instrument's
output goes to the pump, which pulls it on its own core and writes each
block straight into I2S. The codec is powered through the board's
``audio_power`` when it has one. Anywhere else (a desktop) it plays through
the board config's ``audio_out``, which uses the pump too where there is
one.

`Output.load` reads the pump's status block: how long a block of
audio took to render, as a share of how long it lasts, and how many times
the speaker ran dry since the instrument started. Where ``audio_out`` plays
through the pump, it reads the pump's own status block, so a board that
plays that way gets the same readout and the same voice cap.
"""

import struct
import sys
from array import array

RATE = 48000
CHANNELS = 2
#: Codec volume, 0 to 100, on a board that has one.
VOLUME = 85
#: The I2S DMA ring, in descriptors of so many frames. 4 x 128 is 10.7 ms
#: of latency at 48 kHz: short enough to play, long enough to ride out a
#: screen redraw.
DMA_DESC = 4
DMA_FRAME = 128

#: A browser's queue, in 10 ms chunks, and how far a stall may catch up, which
#: has to clear the queue or the first stall cuts the queue back to it. 40 ms
#: plays well on a keyboard; 120 ms rode out more but was too slow to play.
BROWSER_LOOKAHEAD = 4
BROWSER_CATCHUP = 6

#: What :meth:`Output.levels` looks at: the newest 100 ms, every 40th frame, which
#: is enough for a meter and costs the app about a millisecond.
LEVEL_FRAMES = 4800
LEVEL_STEP = 40
#: The pump's tap holds this much, more than the app reads between two looks.
TAP_FRAMES = 8192

_BLOCKS_FOREVER = 0x7FFFFFFF
# The status block's words (audiodsp's audiopump).
_BLOCKS, _BYTES, _PULL_US, _SINK_BYTES, _MAX_PULL_US, _DMA_BYTES = 0, 1, 12, 15, 20, 21


class Output:
    """Plays one instrument at a time.

    *scope* is the app's scope: the desktop output runs its service on the
    app's timers. Construct it once; `start` and `stop` swap
    instruments; `close` powers the codec down.
    """

    def __init__(self, scope, rate=RATE, channels=CHANNELS):
        self.scope = scope
        self.rate = rate
        self.channels = channels
        self.instrument = None
        self._out = None
        self._status = None
        self._powered = False
        #: The codec volume asked for since opening, or None for the default.
        self.volume = None
        self._wire = None
        self._power = None
        self._dma_at_start = 0
        self._starved = 0
        self._base = 0
        self._last = None
        self._gov = None
        self._block_us = None
        self._owner = None
        self._tap = None
        self._level_buf = None
        self.underruns = 0
        self.load_pct = None
        self.worst_pct = None
        import board_peripherals as bp

        self._bp = bp
        try:
            import audiopump
        except ImportError:
            audiopump = None
        try:
            import _audioif  # the pump's I2S driver, on a board
        except ImportError:
            _audioif = None
        wire = getattr(getattr(bp, "AUDIO_OUT", None), "wire", None)
        if wire is not None and _audioif is not None and hasattr(_audioif, "i2s_start"):
            self._audioif = _audioif
            self._pump = audiopump
            self._wire = wire
            self._power = getattr(bp, "audio_power", None)
        else:
            self._audioif = None
            self._pump = audiopump

    @property
    def on_board(self):
        """True when this drives the board's I2S itself."""
        return self._wire is not None

    def start(self, inst):
        """Play *inst*'s output, replacing whatever was playing."""
        self.stop()
        self.underruns = 0
        self._starved = 0
        self._base = 0
        self._last = None
        self._gov = None
        self._block_us = None
        self._owner = None
        self.load_pct = None
        self.worst_pct = None
        if self._wire is not None:
            if self._power is not None and not self._powered:
                self._power(True, volume=VOLUME if self.volume is None else self.volume)
                self._powered = True
            w = self._wire
            self._audioif.i2s_start(
                w.port, w.sck, w.ws, w.sd, self.rate, bits=16, channels=self.channels,
                mclk=-1 if w.mck is None else w.mck, mclk_fs=w.mck_fs,
                dma_desc=DMA_DESC, dma_frame=DMA_FRAME)
            self._status = bytearray(self._pump.STATUS_BYTES)
            self._dma_at_start = self._dma()
            self._pump.spawn(inst.output, _BLOCKS_FOREVER, self._status, sink=True, timeout_ms=500)
        else:
            from audiodev import AudioFormat

            # A computer's default output buffers for playback, too long for keys.
            kwargs = {}
            if sys.platform == "webassembly":
                kwargs = {"lookahead_chunks": BROWSER_LOOKAHEAD, "max_catchup_chunks": BROWSER_CATCHUP}
            out = self._bp.audio_out(AudioFormat(self.rate, self.channels, 16), latency="low", **kwargs)
            out.attach(self.scope)  # its service() on the app's timer
            if self.volume is not None:
                out.set_volume(self.volume)
            out.play(inst.output)
            self._out = out
        self._attach_tap()
        self.instrument = inst

    def stop(self):
        """Silence. The instrument is left as it is, not deinitialised."""
        self.instrument = None
        if self._tap is not None:
            self._pump.tap(None)
        if self._wire is not None:
            if self._status is not None:
                self._pump.shutdown()  # stops the pump task and closes I2S
                self._status = None
            return
        out = self._out
        self._out = None
        if out is not None:
            out.stop()
            out.detach()
            out.close()

    def _attach_tap(self):
        pump = self._pump
        if pump is None or not hasattr(pump, "Tap"):
            return
        if self._tap is None:
            self._tap = pump.Tap(frames=TAP_FRAMES, channel_count=self.channels)
            self._level_buf = array("h", bytes(LEVEL_FRAMES * self.channels * 2))
        pump.tap(self._tap)

    def levels(self):
        """The newest audio's left and right peaks, 0.0 to 1.0.

        Both 0.0 when nothing new has gone out, or where there's no tap.
        """
        if self._tap is None:
            return 0.0, 0.0
        buf = self._level_buf
        channels = self.channels
        samples = self._tap.readinto(buf) // 2
        left = right = 0
        for i in range(0, samples - channels + 1, LEVEL_STEP * channels):
            v = buf[i]
            if v < 0:
                v = -v
            if v > left:
                left = v
            v = buf[i + channels - 1]
            if v < 0:
                v = -v
            if v > right:
                right = v
        return left / 32768, right / 32768

    def set_volume(self, percent):
        """The codec's volume, 0 to 100, now and for the next instrument."""
        self.volume = percent
        if self._powered:
            self._power(True, volume=percent)
        elif self._out is not None:
            self._out.set_volume(percent)

    def close(self):
        self.stop()
        if self._powered:
            self._powered = False
            try:
                self._power(False)
            except Exception:
                pass

    def _dma(self):
        if hasattr(self._audioif, "i2s_dma_bytes"):
            return self._audioif.i2s_dma_bytes()
        return 0

    def _pump_owner(self):
        """audiodev's pump owner, once ``audio_out`` plays through the pump."""
        out = self._out
        if out is None or not getattr(out, "pumped", False):
            return None
        if self._owner is None:
            try:
                from audiodev import pump

                self._owner = pump.owner()
            except Exception:
                return None
        return self._owner

    def _status_block(self):
        if self._status is not None:
            return self._status
        owner = self._pump_owner()
        if owner is None:
            return None
        try:
            return owner.status()
        except Exception:
            return None

    def load(self):
        """Update ``load_pct``, ``worst_pct`` and ``underruns``; return them.

        ``load_pct`` is the render time of the blocks since the last call as
        a percentage of the time they last: over 100 can't keep up.
        ``worst_pct`` is the slowest single block since `start`.
        ``underruns`` counts the calls between which the speaker ran out of
        audio (on a board), or blocks the output had no room for (on a
        desktop). Both loads are None until there's something to measure.
        """
        status = self._status_block()
        if status is None or self._pump is None:
            return self.load_pct, self.worst_pct, self.underruns
        # What the DMA has clocked out is read before the pump's counters, not
        # after: if this thread is held up between the two reads, the bytes
        # the pump wrote meanwhile must not look like silence. Read the other
        # way round, a 200 ms pause here was reported as 200 ms starved.
        dma_now = self._dma() if self._status is not None else 0
        w = struct.unpack_from("<%dQ" % self._pump.STATUS_WORDS, status)
        blocks, nbytes, pull_us = w[_BLOCKS], w[_BYTES], w[_PULL_US]
        last = self._last
        self._last = (blocks, nbytes, pull_us)
        if last is not None and blocks > last[0]:
            frames = (nbytes - last[1]) // (self.channels * 2)
            if frames > 0:
                self.load_pct = (pull_us - last[2]) * self.rate // (frames * 10000)
            block_frames = frames // (blocks - last[0])
            if block_frames:
                self.worst_pct = w[_MAX_PULL_US] * self.rate // (block_frames * 10000)
        driver_count = getattr(self._audioif, "i2s_starved_bytes", None) if self._status is not None else None
        if driver_count is not None:
            # The I2S driver counts, in its own interrupt, every descriptor
            # that went out with no audio in it and every stretch the DMA was
            # stopped. That is the silence itself. The byte totals compared
            # below miss most of a flash write, which holds off the very
            # interrupt that counts the bytes clocked out: 64 KB written to
            # a board's flash cost 750 to 920 ms of sound and they showed 80
            # to 220.
            starved = driver_count()
            if starved > self._starved:
                self._starved = starved
                self.underruns += 1
            return self.load_pct, self.worst_pct, self.underruns
        if self._status is not None:
            dma = dma_now - self._dma_at_start
        else:
            # Through audio_out the pump counts what its own I2S clocked out;
            # a desktop's pump never touches I2S and leaves this at 0.
            dma = w[_DMA_BYTES] if self._pump.STATUS_WORDS > _DMA_BYTES else 0
        if dma:
            # On a board the DMA clocks out silence when the pump is late:
            # bytes it sent that the pump never wrote are a gap you heard.
            gap = dma - w[_SINK_BYTES]
            if gap > self._starved:
                self._starved = gap
                # The ring clocks silence before the first block lands:
                # that's the start, not a gap.
                if last is not None:
                    self.underruns += 1
                else:
                    self._base = gap
        else:
            owner = self._pump_owner()
            if owner is not None:
                try:
                    self.underruns = owner.health().get("dropped", 0)
                except Exception:
                    pass
        return self.load_pct, self.worst_pct, self.underruns

    def pull_us(self):
        """Mean render time of a block since the last call, in microseconds.

        None when nothing plays through the pump, or no block has landed
        since the last call. The pump renders on its own core, so this is
        what the instrument costs, whoever is late.
        """
        status = self._status_block()
        if status is None or self._pump is None:
            return None
        w = struct.unpack_from("<%dQ" % self._pump.STATUS_WORDS, status)
        last = self._gov
        self._gov = (w[_BLOCKS], w[_PULL_US], w[_BYTES])
        if last is None or w[_BLOCKS] <= last[0]:
            return None
        blocks = w[_BLOCKS] - last[0]
        frames = (w[_BYTES] - last[2]) // (self.channels * 2 * blocks)
        if frames > 0 and self._status is None:
            # audio_out chose the block; on our own I2S it's DMA_FRAME.
            self._block_us = frames * 1000000 // self.rate
        return (w[_PULL_US] - last[1]) // blocks

    def block_us(self):
        """How long one block of the pump lasts, in microseconds.

        Measured from the blocks `pull_us` last read; until then, the block
        this drives I2S with itself.
        """
        if self._block_us is not None:
            return self._block_us
        return DMA_FRAME * 1000000 // self.rate

    def starved_ms(self):
        """On a board, the silence heard since `start`, in ms."""
        return (self._starved - self._base) * 1000 // (self.rate * self.channels * 2)
