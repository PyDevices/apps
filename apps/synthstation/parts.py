# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""An instrument for each MIDI channel, and their sum for the audio out.

Channel 1 always has an instrument. Any other channel can have one of its
own, and a channel without one plays channel 1's. A `Part` is one channel's
instrument with what MIDI has left waiting for it; a `Mix` is what the output
plays when more than one channel has an instrument.
"""

#: MIDI's channels, counted from 0 here and from 1 on the screen.
CHANNELS = 16
#: The mix's buffer in bytes: 512 stereo frames, about 11 ms at 48 kHz.
MIX_BUFFER = 2048


class Part:
    """One channel's instrument.

    *adapter* is the instrument's panel adapter. ``knobs`` and ``program``
    hold the last knob values and program change read from MIDI until the
    app applies them, and ``pad_notes`` is what the pads play on a drum kit.

    A panel registers with the adapter and never takes itself off, and here
    an instrument outlives the panel that shows it. So the adapter's
    ``on_external_change`` is replaced with one this part can `forget`.
    """

    def __init__(self, name, adapter):
        self.name = name
        self.adapter = adapter
        self.knobs = {}
        self.program = None
        self.pad_notes = None
        self.pad_patch = None
        self.struck = {}
        self._listeners = []
        adapter.on_external_change(self._relay)
        adapter.on_external_change = self._listeners.append

    def _relay(self, kind, index, value):
        for listener in self._listeners:
            listener(kind, index, value)

    def forget(self):
        """Stop telling the panel that was listening: it's gone."""
        del self._listeners[:]


class Mix:
    """Several instruments summed into one ``output``.

    Each plays at full level, so an instrument is as loud in a mix as it is
    alone, and a sum past full scale is held there rather than wrapping.
    """

    def __init__(self, instruments, rate, channels):
        import audiomixer

        mixer = audiomixer.Mixer(
            voice_count=len(instruments), buffer_size=MIX_BUFFER, channel_count=channels,
            bits_per_sample=16, samples_signed=True, sample_rate=rate)
        for i, inst in enumerate(instruments):
            mixer.voice[i].play(inst.output, loop=True)
        self.output = mixer
        self._count = len(instruments)

    def deinit(self):
        """Let go of the instruments. Call it once nothing pulls the output."""
        mixer = self.output
        self.output = None
        if mixer is not None:
            for i in range(self._count):
                mixer.voice[i].stop()
            mixer.deinit()
