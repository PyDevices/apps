"""Output adapters. The output's clock drives the engine: it pulls the graph.

DefaultOutput is the host's default device through audiodev's player, the
same `play(sample)` shape a board's `audio_out` role returns. WasapiOutput is
a Windows speaker the pump writes itself, with no Python in the path: the
low-latency one, and the one a live input wants.
"""

from . import CHANNELS, SAMPLE_RATE


class DefaultOutput:
    kind = "default"

    def __init__(self, latency=None):
        from audiodev import AudioFormat
        from audiodev import auto

        self.player = auto.audio_out(AudioFormat(SAMPLE_RATE, CHANNELS, 16),
                                     latency=latency)
        self.sample_rate = SAMPLE_RATE
        self.channel_count = CHANNELS
        self.clock = "device"

    def play(self, sample):
        self.player.play(sample)

    def stop(self):
        self.player.stop()

    def service(self):
        self.player.service()

    def describe(self):
        t = self.player.transport
        return "%s, %d Hz" % (type(t).__name__, self.sample_rate)

    def close(self):
        try:
            self.player.stop()
        finally:
            self.player.close()


class WasapiOutput:
    """A Windows speaker written by the pump's own thread (audioif's
    "wasapi" sink). `device` is an endpoint ID, or None for the default.

    `prime_ms` is the silence queued ahead of the first block and
    `buffer_ms` the device buffer asked for: together they set how much the
    speaker holds once the pump is ahead of it."""

    kind = "wasapi"

    def __init__(self, device=None, prime_ms=10, buffer_ms=20):
        import audiobusio

        sink = "wasapi:%d:%d:%d:%d" % (SAMPLE_RATE, CHANNELS, prime_ms,
                                       buffer_ms)
        if device:
            sink += "@" + device
        self.out = audiobusio.I2SOut(0, 1, 2, sample_rate=SAMPLE_RATE,
                                     sink=sink)
        self.device = device
        self.sample_rate = SAMPLE_RATE
        self.channel_count = CHANNELS
        self.clock = "device"
        self.name = device or "default output"
        try:
            import _audioif

            self.name = _audioif.endpoint(device, False)[1]
        except (AttributeError, OSError):
            pass

    @staticmethod
    def available():
        try:
            import _audioif
        except ImportError:
            return False
        return hasattr(_audioif, "sink_stats")

    def play(self, sample):
        self.out.play(sample, loop=False)

    def stop(self):
        self.out.stop()

    def service(self):
        pass

    def stats(self):
        import _audioif

        return _audioif.sink_stats()

    def held_frames(self):
        """Frames queued in the speaker at the pump's last write."""
        st = self.stats()
        return st[6] if st else 0

    def period_frames(self):
        """The Windows engine's period for the speaker, 0 until it opens."""
        st = self.stats()
        return st[8] if st and len(st) > 8 else 0

    def describe(self):
        return "%s, WASAPI on the pump" % self.name

    def close(self):
        self.out.deinit()
