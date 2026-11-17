# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""The sound module's engine: sixteen parts, one per MIDI channel, mixed through chorus and reverb."""

from typing import Any, Callable, ContextManager, Sequence

DRUM_CHANNEL: int
READY_CHANNELS: tuple[int, ...]
MELODIC: str
DRUMS: str
PERCUSSION_BANK: int
BANK_INSTRUMENTS: int
BANK_DRUM_MACHINES: int
INSTRUMENTS: tuple[str | None, ...]
DRUM_MACHINES: tuple[str | None, ...]
CC_BANK_MSB: int
CC_BANK_LSB: int
CC_VOLUME: int
CC_PAN: int
CC_SUSTAIN: int
CC_REVERB: int
CC_CHORUS: int
CC_ALL_SOUND_OFF: int
CC_RESET_CONTROLLERS: int
CC_ALL_NOTES_OFF: int
CC_MOD_WHEEL: int
CC_EXPRESSION: int
CC_DATA_MSB: int
CC_DATA_LSB: int
CC_DATA_INC: int
CC_DATA_DEC: int
CC_NRPN_LSB: int
CC_NRPN_MSB: int
CC_RPN_LSB: int
CC_RPN_MSB: int
RPN_BEND_RANGE: tuple[int, int]
RPN_FINE_TUNING: tuple[int, int]
RPN_COARSE_TUNING: tuple[int, int]
RPN_NULL: tuple[int, int]
RPN_DEFAULTS: dict[tuple[int, int], int]
MAX_BEND_RANGE: int
NATIVE_BEND_RANGE: float
MACRO_CC: int
MACRO_CCS: int
MANUFACTURER: int
FAMILY: int
MODEL: int
VERSION: tuple[int, int, int, int]
DEVICE_ID: int
DEFAULT_VOLUME: int
DEFAULT_PAN: int
DEFAULT_EXPRESSION: int
VOLUME_MACRO: int
PAN_MACRO: int
DEFAULT_REVERB: int
DEFAULT_CHORUS: int
DEFAULT_MASTER: int
VOICES: int
BOARD: bool
BOARD_VOICES: int
RESERVE: int
GAIN: float
PART_LEVEL: float
BEND_CENTER: int
CACHE_SHARE: int
FALLBACK_CACHE_BYTES: int
MIXER_BUFFER: int
PARTS_MIXER_BUFFER: int
GM_NAMES: tuple[str, ...]
GM_KITS: tuple[tuple[int, str], ...]

def board_cache_bytes() -> int | None:
    """The bound for the open bank's samples on a board, or None on CPython."""
def identity_reply(device_id: int = ...) -> bytes:
    """The Identity Reply this module sends, F0 to F7."""
def deferred(module: Module | None) -> ContextManager[Any]:
    """Queue the voices' writes inside a `with` block and send them together at the end."""

class Part:
    """One MIDI channel's state."""

    channel: int
    inst: Any
    inst_name: str | None
    notes: int
    last: tuple[int, int] | None
    played: dict[tuple[int, int, int], list[Any]]
    program: int
    bank_msb: int
    bank_lsb: int
    volume: int
    expression: int
    pan: int
    sustain: bool
    held: set[int]
    sustained: set[int]
    bend: int
    rpn: tuple[int, int] | None
    params: dict[tuple[int, int], int]
    reverb: int
    chorus: int
    def __init__(self, channel: int) -> None: ...
    def reset(self) -> None: ...
    @property
    def bend_range(self) -> float:
        """Pitch Bend Sensitivity in semitones, cents included."""
    @property
    def tuning(self) -> float:
        """Fine and coarse tuning together, in semitones."""
    @property
    def drums(self) -> bool: ...
    @property
    def gm(self) -> bool:
        """True when the part's bank is General MIDI's."""

class Module:
    """Sixteen parts, mixed, with chorus and reverb on the master."""

    rate: int
    channels: int
    bank: str | None
    send: Callable[[bytes], Any] | None
    parts: list[Part]
    instruments: bool
    voice_pool: Any
    mixer: Any
    chorus: Any
    output: Any
    reverb: Any
    reverb_level: int
    chorus_level: int
    master_level: int
    on_master: Callable[[int], Any] | None
    error: BaseException | None
    loaded: Any
    cache_bytes: int | None
    identities: int
    def __init__(
        self,
        rate: int = 48000,
        channels: int = 2,
        bank: str | None = None,
        create: Callable[..., Any] | None = None,
        mixer: Any = None,
        effects: bool = True,
        kits: list[int] | None = None,
        voices: int | None = None,
        chorus: bool | None = None,
        instruments: bool | None = None,
        send: Callable[[bytes], Any] | None = None,
    ) -> None: ...
    @property
    def voice_count(self) -> int | None:
        """How many engine voices the parts share, or None without a shared pool."""
    @voice_count.setter
    def voice_count(self, count: int) -> None: ...
    def prepare(self) -> Any:
        """Open the bank now, so no part has to; None with the reason in `error`."""
    def ready(self, channels: Sequence[int] = ...) -> None:
        """Make these parts' instruments now, so a first note doesn't have to."""
    def wanted(self, part: Part) -> str | None:
        """The instrument the part's bank and program ask for."""
    def instrument(self, part: Part) -> Any:
        """The part's instrument, made on first use; None without one."""
    def kit_index(self, program: int) -> int:
        """The drum instrument's patch for GM drum program `program`."""
    def kit_programs(self) -> list[int]:
        """The GM drum program numbers the bank has kits for, in order."""
    def name(self, channel: int) -> str:
        """What channel `channel` plays."""
    def feed(self, data: bytes | bytearray | memoryview, nbytes: int | None = None) -> None:
        """Parse raw MIDI 1.0 bytes, the first `nbytes` when given."""
    def message(self, status: int, d1: int, d2: int = 0) -> None:
        """One channel message: `status` with its channel, and its data."""
    def sysex(self, data: bytes) -> None:
        """Handle the bytes between F0 and F7."""
    def note_on(self, part: Part, note: int, velocity: int) -> None: ...
    def note_off(self, part: Part, note: int) -> None: ...
    def control(self, part: Part, cc: int, value: int) -> None: ...
    def program(self, part: Part, number: int) -> None: ...
    def bend(self, part: Part, value: int) -> None: ...
    def data_entry(self, part: Part, cc: int, value: int) -> None: ...
    def all_notes_off(self, part: Part) -> None: ...
    def all_sound_off(self, part: Part) -> None: ...
    def reset_controllers(self, part: Part) -> None: ...
    def panic(self) -> None: ...
    def gm_reset(self) -> None: ...
    def set_volume(self, part: Part, value: int) -> None:
        """A volume slider for one channel: the path CC7 takes."""
    def set_pan(self, part: Part, value: int) -> None:
        """A pan slider for one channel: the path CC10 takes."""
    def set_master(self, level: int | float) -> None:
        """The master level, 0-100."""
    def set_reverb(self, level: int) -> None: ...
    def set_chorus(self, level: int) -> None: ...
    def fill(self) -> None:
        """Let the parts' instruments move their notes and knobs on."""
    def close(self) -> None: ...
