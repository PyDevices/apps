# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Internet radio: play MP3 streams over Wi-Fi, and step through stations.

Joins Wi-Fi, opens an MP3 stream over HTTP and plays it through the board's
``audio_out``. A press of any key, the touch screen or the Boot button moves
to the next station, and a display, if the board has one, shows which. The
board holds a few seconds of the stream in RAM, so a late packet isn't
heard, and a stream that stops sending is opened again.

The stations are a list of ``http://`` MP3 stream URLs in
``/internet_radio.json`` on the board, or the defaults below::

    {"stations": ["http://ice1.somafm.com/groovesalad-128-mp3"], "volume": 70}

Put this on the board and have ``main.py`` import it.
"""

import io
import json
import socket
import time

import audiomp3
import wifi_manager
from audiodev import AudioFormat
from programkit import Board, Press, Rows

# Change these to match your setup, or put them in /internet_radio.json.
STATIONS = [
    "http://ice1.somafm.com/groovesalad-128-mp3",
    "http://ice1.somafm.com/dronezone-128-mp3",
    "http://ice1.somafm.com/secretagent-128-mp3",
]
VOLUME = 85  # 0 is silent, 100 the loudest
HOSTNAME = "radio"  # the board's name on the network
STALL_MS = 8000  # a stream that sends nothing this long is opened again
BUFFER = 64 * 1024  # bytes of the stream held in RAM; 64 KB is 4 s at 128 kbit/s
START = BUFFER // 2  # bytes to hold before playing starts
REPORT_MS = 10000  # how often the console hears how full the buffer is

try:
    with open("/internet_radio.json") as f:
        _settings = json.load(f)
    STATIONS = _settings.get("stations", STATIONS)
    VOLUME = _settings.get("volume", VOLUME)
    HOSTNAME = _settings.get("hostname", HOSTNAME)
except OSError:
    pass

board = Board()
if not board.has("audio_out"):
    raise SystemExit("internet_radio: this board has no audio_out in its board_peripherals")
audio_out = board.get("audio_out")
press = Press(board)
rows = Rows(board.display) if board.display is not None else None


def show(row, text):
    """A line on the display, if there is one, sent at once."""
    if rows is not None:
        rows.line(row, text)
        rows.send_all()


show(0, "Internet radio")
show(1, "Joining Wi-Fi")
print("internet_radio: joined Wi-Fi at", wifi_manager.connect(hostname=HOSTNAME))
print("internet_radio: next station on", ", ".join(press.sources) or "nothing: this board has no key, touch or Boot button")


def open_stream(url, hops=3):
    """A socket at the stream's first byte, following redirects, and the station's name."""
    host, _, path = url.split("//", 1)[1].partition("/")
    host, _, port = host.partition(":")
    addr = socket.getaddrinfo(host, int(port or 80))[0][-1]
    s = socket.socket()
    s.settimeout(10)
    s.connect(addr)
    s.write(b"GET /%s HTTP/1.0\r\nHost: %s\r\nUser-Agent: PyDevices-radio\r\n\r\n" % (path, host))
    status = s.readline()
    location = None
    title = host
    while True:
        line = s.readline()
        if not line or line == b"\r\n":
            break
        lower = line.lower()
        if lower.startswith(b"location:"):
            location = line[9:].strip().decode()
        elif lower.startswith(b"icy-name:"):
            title = line[9:].strip().decode() or host
    code = int(status.split()[1])
    if code in (301, 302, 303, 307, 308) and location and hops:
        s.close()
        return open_stream(location, hops - 1)
    if code != 200:
        s.close()
        raise OSError("%s answered %d" % (url, code))
    return s, title


class StreamBuffer(io.IOBase):
    """Seconds of the stream held in RAM, between the socket and the decoder.

    The decoder takes only a few milliseconds of sound ahead of the speaker,
    so a TCP segment that comes late would starve it: a blocking socket
    holds the decoder up and the speaker plays gaps, and a non-blocking one
    has it decode silence into the music. Fed from this, the decoder reads
    from memory as it would from a card, and only a stall longer than the
    buffer is heard.
    """

    def __init__(self, sock, size):
        self.sock = sock
        self.buf = bytearray(size)
        self.view = memoryview(self.buf)
        self.read_at = 0
        self.level = 0
        self.received = 0

    def fill(self):
        """Move what the socket has into the buffer. Call it often."""
        size = len(self.buf)
        while self.level < size:
            write_at = (self.read_at + self.level) % size
            room = min(size - self.level, size - write_at)
            try:
                n = self.sock.readinto(self.view[write_at : write_at + room])
            except OSError:
                n = None  # nothing yet on a non-blocking socket
            if not n:
                if n == 0:
                    raise OSError("the station closed the stream")
                return
            self.level += n
            self.received += n

    def readinto(self, buf):
        self.fill()
        size = len(self.buf)
        n = min(len(buf), self.level, size - self.read_at)
        buf[:n] = self.view[self.read_at : self.read_at + n]
        self.read_at = (self.read_at + n) % size
        self.level -= n
        return n if n else None  # None: nothing now, but not the end

    def ioctl(self, request, arg):
        if request == 3:  # poll: readable while anything is held
            return arg & 1 if self.level else 0
        return 0


if board.has("audio_power"):
    board.get("audio_power")(True)

station = 0
while True:
    url = STATIONS[station % len(STATIONS)]
    print("internet_radio: tuning to", url)
    show(0, "Station %d of %d" % (station % len(STATIONS) + 1, len(STATIONS)))
    show(1, url.split("//", 1)[-1])
    show(2, "Tuning")
    speaker = stream = None
    try:
        stream, title = open_stream(url)
        show(1, title)
        stream.setblocking(False)
        held = StreamBuffer(stream, BUFFER)
        # Fill the buffer halfway before the decoder reads the first frame.
        moved = time.ticks_ms()
        while held.level < START:
            held.fill()
            if time.ticks_diff(time.ticks_ms(), moved) > STALL_MS:
                raise OSError("the station sent too little")
            time.sleep_ms(5)
        decoder = audiomp3.MP3Decoder(held)
        print("internet_radio: %s, %d Hz, %d channels" % (title, decoder.sample_rate, decoder.channel_count))
        speaker = audio_out(AudioFormat(decoder.sample_rate, decoder.channel_count, 16))
        speaker.set_volume(VOLUME)  # opening the output sets it to 100
        speaker.play(decoder)
        show(2, "Playing %.1f kHz" % (decoder.sample_rate / 1000))
        # Keep the decoder fed until a press or a stalled stream.
        received = held.received
        moved = report = time.ticks_ms()
        lowest = held.level
        while not press():
            held.fill()
            speaker.service()
            if held.received != received:
                received = held.received
                moved = time.ticks_ms()
            elif time.ticks_diff(time.ticks_ms(), moved) > STALL_MS:
                print("internet_radio: the stream stalled")
                show(2, "Stalled: tuning again")
                break
            lowest = min(lowest, held.level)
            if time.ticks_diff(time.ticks_ms(), report) >= REPORT_MS:
                report = time.ticks_ms()
                print("internet_radio: %d KB held, at least %d KB in the last %d s" % (held.level // 1024, lowest // 1024, REPORT_MS // 1000))
                lowest = held.level
            time.sleep_ms(5)
        else:
            station += 1
    except OSError as e:
        print("internet_radio:", e)
        show(2, str(e))
        time.sleep(3)
    if speaker:
        speaker.stop()
        speaker.close()
    if stream:
        stream.close()
