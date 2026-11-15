# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
import types
from _typeshed import Incomplete

DRUM_CHANNEL: int
MELODIC: str
DRUMS: str
PERCUSSION_BANK: int
BANK_INSTRUMENTS: int
BANK_DRUM_MACHINES: int
INSTRUMENTS: Incomplete
DRUM_MACHINES: Incomplete
CC_BANK_MSB: Incomplete
CC_BANK_LSB: Incomplete
CC_VOLUME: Incomplete
CC_PAN: Incomplete
CC_SUSTAIN: Incomplete
CC_REVERB: Incomplete
CC_CHORUS: Incomplete
CC_ALL_SOUND_OFF: Incomplete
CC_RESET_CONTROLLERS: Incomplete
CC_ALL_NOTES_OFF: Incomplete
CC_MOD_WHEEL: Incomplete
CC_EXPRESSION: Incomplete
CC_DATA_MSB: Incomplete
CC_DATA_LSB: Incomplete
CC_DATA_INC: Incomplete
CC_DATA_DEC: Incomplete
CC_NRPN_LSB: Incomplete
CC_NRPN_MSB: Incomplete
CC_RPN_LSB: Incomplete
CC_RPN_MSB: Incomplete
RPN_BEND_RANGE: Incomplete
RPN_FINE_TUNING: Incomplete
RPN_COARSE_TUNING: Incomplete
RPN_NULL: Incomplete
RPN_DEFAULTS: Incomplete
MAX_BEND_RANGE: int
NATIVE_BEND_RANGE: float
MACRO_CC: int
MACRO_CCS: int
MANUFACTURER: int
FAMILY: int
MODEL: int
VERSION: Incomplete
DEVICE_ID: int
DEFAULT_VOLUME: int
DEFAULT_PAN: int
DEFAULT_EXPRESSION: int
VOLUME_MACRO: Incomplete
PAN_MACRO: Incomplete
DEFAULT_REVERB: int
DEFAULT_CHORUS: int
DEFAULT_MASTER: int
VOICES: int
BOARD: Incomplete
BOARD_VOICES: int
RESERVE: int
GAIN: float
PART_LEVEL: float
BEND_CENTER: int
CACHE_SHARE: int
FALLBACK_CACHE_BYTES: Incomplete
MIXER_BUFFER: int
PARTS_MIXER_BUFFER: int
GM_NAMES: Incomplete
GM_KITS: Incomplete

def board_cache_bytes(): ...
def identity_reply(device_id=...): ...

class _Now:
    def __enter__(self): ...
    def __exit__(self, *exc): ...

def deferred(module): ...

class Part:
    channel: Incomplete
    inst: Incomplete
    inst_name: Incomplete
    notes: int
    last: Incomplete
    played: Incomplete
    def __init__(self, channel) -> None: ...
    program: int
    bank_msb: int
    bank_lsb: int
    volume: Incomplete
    expression: Incomplete
    pan: Incomplete
    sustain: bool
    held: Incomplete
    sustained: Incomplete
    bend: Incomplete
    rpn: Incomplete
    params: Incomplete
    reverb: Incomplete
    chorus: Incomplete
    def reset(self) -> None: ...
    @property
    def bend_range(self): ...
    @property
    def tuning(self): ...
    @property
    def drums(self): ...
    @property
    def gm(self): ...

class Module:
    rate: Incomplete
    channels: Incomplete
    bank: Incomplete
    send: Incomplete
    parts: Incomplete
    instruments: Incomplete
    voice_pool: Incomplete
    mixer: Incomplete
    chorus: Incomplete
    output: Incomplete
    reverb: Incomplete
    reverb_level: int
    master_level: Incomplete
    on_master: Incomplete
    error: Incomplete
    loaded: Incomplete
    cache_bytes: Incomplete
    identities: int
    def __init__(self, rate: int = 48000, channels: int = 2, bank=None, create=None, mixer=None, effects: bool = True, kits=None, voices=None, chorus=None, instruments=None, send=None) -> None: ...
    @property
    def voice_count(self): ...
    @voice_count.setter
    def voice_count(self, count) -> None: ...
    def prepare(self): ...
    def wanted(self, part): ...
    def instrument(self, part): ...
    def kit_index(self, program): ...
    def kit_programs(self): ...
    def name(self, channel): ...
    def feed(self, data, nbytes=None) -> None: ...
    def message(self, status, d1, d2: int = 0) -> None: ...
    def sysex(self, data) -> None: ...
    def note_on(self, part, note, velocity) -> None: ...
    def note_off(self, part, note) -> None: ...
    def control(self, part, cc, value) -> None: ...
    def program(self, part, number) -> None: ...
    def bend(self, part, value) -> None: ...
    def data_entry(self, part, cc, value) -> None: ...
    def all_notes_off(self, part) -> None: ...
    def all_sound_off(self, part) -> None: ...
    def reset_controllers(self, part) -> None: ...
    def panic(self) -> None: ...
    def gm_reset(self) -> None: ...
    def set_volume(self, part, value) -> None: ...
    def set_pan(self, part, value) -> None: ...
    def set_master(self, level) -> None: ...
    def set_reverb(self, level) -> None: ...
    chorus_level: Incomplete
    def set_chorus(self, level) -> None: ...
    def fill(self) -> None: ...
    def close(self) -> None: ...
