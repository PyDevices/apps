# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Make Backline's default drum bank from the FreePats synthesizer percussion.

    python tools/backline/make_drums.py SOURCE.sf2 OUT.sf2

``SOURCE.sf2`` is ``SynthesizerPercussion-20220718.sf2`` from
https://freepats.zenvoid.org/Percussion/SynthesizerPercussion/SynthesizerPercussion-SF2-20220718.7z
(SHA-256 6ff6580165061eac3113a9961e1e93860c9af87a82b523a49949f099d6f47ea3),
listed on https://freepats.zenvoid.org/Percussion/electric-percussion.html and
published under CC0. Its sounds sit on keys 48 to 66 in an order of their own. This writes
the same samples, byte for byte, as one General MIDI drum kit: bank 128,
preset 0, kick on 36, snare on 38, hats on 42, 44 and 46 in one choke group, and
so on (``KEYS`` below). Each key plays its sample at the pitch it was recorded,
with the source's attenuation and velocity layers.

The same source always gives the same file, the one `kits.DEFAULT_BANK` names.
"""

import struct
import sys

#: Source sample -> the General MIDI keys it plays on.
KEYS = {
    "Kick04": (36,),
    "Kick06": (35,),
    "Snare09": (38,),
    "Snare14": (40,),
    "Clap01": (39,),
    "ClosedHiHat01-01": (42,),
    "ClosedHiHat02-01": (44,),
    "OpenHiHat02-01": (46,),
    "Cymbal01-01": (49, 57),
    "Cymbal01-02": (49, 57),
    "Cymbal01-03": (49, 57),
    "Cymbal02": (51, 59),
    "LowTom02-01": (41,),
    "LowTom02-02": (43,),
    "MidTom02-01": (45,),
    "MidTom02-02": (47,),
    "HighTom02-01": (48,),
    "HighTom02-02": (50,),
    "Shaker04": (70,),
    "ShakerLong01": (69,),
    "Claves01": (75,),
}
#: Keys that cut each other off, like a real hi-hat.
HATS = (42, 44, 46)

INSTRUMENT, KEY_RANGE, VEL_RANGE, ATTENUATION, SAMPLE_ID = 41, 43, 44, 48, 53
EXCLUSIVE_CLASS, ROOT_KEY = 57, 58
INFO = (
    (b"ifil", struct.pack("<HH", 2, 1)),
    (b"isng", b"EMU8000"),
    (b"INAM", b"Backline Drums"),
    (b"ICOP", b"CC0 1.0 public domain dedication"),
    (b"ICMT", b"FreePats synthesizer percussion 2022-07-18 by Roberto, "
              b"https://freepats.zenvoid.org/, laid out as a General MIDI drum kit"),
    (b"ISFT", b"make_drums.py"),
)


def chunks(data: bytes, start: int, end: int):
    """Each (id, body start, body end) of the RIFF chunks between ``start`` and ``end``."""
    while start < end:
        cid, size = data[start:start + 4], struct.unpack_from("<I", data, start + 4)[0]
        yield cid, start + 8, start + 8 + size
        start += 8 + size + (size & 1)


def read(path: str) -> tuple[bytes, dict, list]:
    """The source's sample data, its sample headers by name, and its zones in order.

    A zone is (sample name, generators). The cymbal has one zone for each
    velocity, taking turns among three recordings.
    """
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"RIFF" or data[8:12] != b"sfbk":
        raise ValueError(f"{path} is not a SoundFont")
    lists = {data[a:a + 4]: (a + 4, b) for cid, a, b in chunks(data, 12, len(data)) if cid == b"LIST"}
    smpl = next(data[a:b] for cid, a, b in chunks(data, *lists[b"sdta"]) if cid == b"smpl")
    pdta = {cid: data[a:b] for cid, a, b in chunks(data, *lists[b"pdta"])}
    shdr = [pdta[b"shdr"][i:i + 46] for i in range(0, len(pdta[b"shdr"]) - 46, 46)]
    names = [h[:20].rstrip(b"\0").decode() for h in shdr]
    bags = [struct.unpack_from("<H", pdta[b"ibag"], i)[0] for i in range(0, len(pdta[b"ibag"]), 4)]
    gens = [struct.unpack_from("<HH", pdta[b"igen"], i) for i in range(0, len(pdta[b"igen"]), 4)]
    zones = []
    for first, after in zip(bags, bags[1:]):
        zone = dict(gens[first:after])
        if SAMPLE_ID in zone:
            zones.append((names[zone[SAMPLE_ID]], zone))
    return smpl, dict(zip(names, shdr)), zones


def riff(cid: bytes, body: bytes) -> bytes:
    return cid + struct.pack("<I", len(body)) + body + b"\0" * (len(body) & 1)


def fixed(text: bytes, size: int) -> bytes:
    """``text`` as a fixed-size name field, null-padded and always null-ended."""
    return text[: size - 1].ljust(size, b"\0")


def build(source: str) -> bytes:
    """The bank, as the bytes of a SoundFont file."""
    smpl, headers, zones = read(source)
    missing = sorted(set(KEYS) - set(headers))
    if missing:
        raise ValueError(f"{source} has no sample {', '.join(missing)}")
    order = list(KEYS)
    # A copied header keeps the source's sampleLink; every sample here is mono,
    # so nothing reads it.
    shdr = b"".join(headers[name] for name in order) + fixed(b"EOS", 20) + bytes(26)
    igen, ibag = [], []
    for key in sorted({k for keys in KEYS.values() for k in keys}):
        for name, zone in zones:
            if key not in KEYS.get(name, ()):
                continue
            ibag.append(struct.pack("<HH", len(igen), 0))
            igen.append(struct.pack("<HBB", KEY_RANGE, key, key))
            for gen in (VEL_RANGE, ATTENUATION):
                if gen in zone:
                    igen.append(struct.pack("<HH", gen, zone[gen]))
            if key in HATS:
                igen.append(struct.pack("<HH", EXCLUSIVE_CLASS, 1))
            igen.append(struct.pack("<HH", ROOT_KEY, key))
            igen.append(struct.pack("<HH", SAMPLE_ID, order.index(name)))
    ibag.append(struct.pack("<HH", len(igen), 0))
    igen.append(bytes(4))
    pdta = (
        riff(b"phdr", fixed(b"Standard", 20) + struct.pack("<HHH3I", 0, 128, 0, 0, 0, 0)
             + fixed(b"EOP", 20) + struct.pack("<HHH3I", 0, 0, 1, 0, 0, 0)),
        riff(b"pbag", struct.pack("<4H", 0, 0, 1, 0)),
        riff(b"pmod", bytes(10)),
        riff(b"pgen", struct.pack("<HH", INSTRUMENT, 0) + bytes(4)),
        riff(b"inst", fixed(b"Drums", 20) + struct.pack("<H", 0) + fixed(b"EOI", 20) + struct.pack("<H", len(ibag) - 1)),
        riff(b"ibag", b"".join(ibag)),
        riff(b"imod", bytes(10)),
        riff(b"igen", b"".join(igen)),
        riff(b"shdr", shdr),
    )
    # INFO strings are null-ended and an even number of bytes long.
    info = [riff(cid, body if cid == b"ifil" else body + b"\0" * (2 - len(body) % 2)) for cid, body in INFO]
    body = (b"sfbk" + riff(b"LIST", b"INFO" + b"".join(info)) + riff(b"LIST", b"sdta" + riff(b"smpl", smpl))
            + riff(b"LIST", b"pdta" + b"".join(pdta)))
    return b"RIFF" + struct.pack("<I", len(body)) + body


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        sys.exit(__doc__.split("\n\n")[1])
    data = build(argv[1])
    with open(argv[2], "wb") as f:
        f.write(data)
    print(f"{argv[2]}: {len(data)} bytes")


if __name__ == "__main__":
    main(sys.argv)
