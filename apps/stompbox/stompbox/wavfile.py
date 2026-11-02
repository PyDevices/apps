"""Read a PCM WAV into an int16 array, on any Python we run on."""

import array
import struct


def read(path):
    """(sample_rate, channel_count, samples): 16-bit PCM, or 24/32-bit and
    8-bit PCM converted to 16, or 32-bit float. Mono stays mono."""
    with open(path, "rb") as f:
        head = f.read(12)
        if len(head) < 12 or head[0:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise ValueError("not a WAV file")
        fmt = None
        while True:
            chunk = f.read(8)
            if len(chunk) < 8:
                raise ValueError("WAV has no data chunk")
            cid = chunk[0:4]
            size = struct.unpack("<I", chunk[4:8])[0]
            if cid == b"fmt ":
                body = f.read(size + (size & 1))
                tag, ch, rate = struct.unpack("<HHI", body[0:8])
                bits = struct.unpack("<H", body[14:16])[0]
                if tag == 0xFFFE and size >= 26:      # WAVE_FORMAT_EXTENSIBLE
                    tag = struct.unpack("<H", body[24:26])[0]
                fmt = (tag, ch, rate, bits)
            elif cid == b"data":
                if fmt is None:
                    raise ValueError("WAV data before fmt")
                data = f.read(size)
                break
            else:
                f.seek(size + (size & 1), 1)
    tag, ch, rate, bits = fmt
    return rate, ch, _to_int16(data, tag, bits)


def _to_int16(data, tag, bits):
    if tag == 1 and bits == 16:
        return array.array("h", data[: len(data) // 2 * 2])
    out = array.array("h")
    if tag == 1 and bits == 8:
        for b in data:
            out.append((b - 128) << 8)
    elif tag == 1 and bits in (24, 32):
        step = bits // 8
        for i in range(0, len(data) - step + 1, step):
            out.append(struct.unpack("<h", data[i + step - 2:i + step])[0])
    elif tag == 3 and bits == 32:
        for i in range(0, len(data) - 3, 4):
            v = struct.unpack("<f", data[i:i + 4])[0]
            v = -1.0 if v < -1.0 else (1.0 if v > 1.0 else v)
            out.append(int(v * 32767))
    else:
        raise ValueError("unsupported WAV format %d/%d-bit" % (tag, bits))
    return out


def write(path, sample_rate, channel_count, pcm):
    """Write int16 PCM bytes as a WAV."""
    n = len(pcm)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + n) + b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, channel_count, sample_rate,
                            sample_rate * channel_count * 2,
                            channel_count * 2, 16))
        f.write(b"data" + struct.pack("<I", n))
        f.write(pcm)
