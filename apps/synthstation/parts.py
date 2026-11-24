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
#: How long an instrument has had no voice awake before the mix stops pulling
#: it. Its effects run on while it's pulled, at a cost even in silence, and
#: every instrument's sound has died away by the time its last voice sleeps.
PARK_MS = 500


class Part:
    """One channel's instrument.

    *adapter* is the instrument's panel adapter. ``knobs`` and ``program``
    hold the last knob values and program change read from MIDI until the
    app applies them, and ``pad_notes`` is what the pads play on a drum kit.
    ``most`` is the most voices the voice cap gives the instrument: as many
    as it had when it was made, and 1 for an instrument it leaves alone.

    A panel registers with the adapter and never takes itself off, and here
    an instrument outlives the panel that shows it. So the adapter's
    ``on_external_change`` is replaced with one this part can `forget`.
    """

    def __init__(self, name, adapter):
        self.name = name
        self.adapter = adapter
        self.most = adapter.instrument.voices
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

    An instrument that has had no voice awake for `PARK_MS` is parked: the
    mix stops pulling it, so it costs nothing until `wake` or a voice waking
    brings it back. Call `tick` as time passes, and `wake` before a note.
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
        self._instruments = list(instruments)
        self._quiet = [0] * self._count
        self.parked = [False] * self._count

    def wake(self, inst):
        """Pull *inst* again if it was parked, before it's played."""
        for i, each in enumerate(self._instruments):
            if each is inst:
                self._quiet[i] = 0
                if self.parked[i]:
                    self.parked[i] = False
                    self.output.voice[i].play(inst.output, loop=True)
                return

    def tick(self, ms):
        """*ms* more have passed: park the instruments that have stayed
        asleep `PARK_MS`, and bring back any whose voices woke by themselves."""
        mixer = self.output
        if mixer is None:
            return
        for i, inst in enumerate(self._instruments):
            if inst.awake:
                self._quiet[i] = 0
                if self.parked[i]:
                    self.parked[i] = False
                    mixer.voice[i].play(inst.output, loop=True)
            elif not self.parked[i]:
                self._quiet[i] += ms
                if self._quiet[i] >= PARK_MS:
                    self.parked[i] = True
                    mixer.voice[i].stop()

    def deinit(self):
        """Let go of the instruments. Call it once nothing pulls the output."""
        mixer = self.output
        self.output = None
        if mixer is not None:
            for i in range(self._count):
                mixer.voice[i].stop()
            mixer.deinit()
