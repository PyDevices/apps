"""The stompbox app: a guitar effects app you play through.

The same code runs on CPython (the desktop wheels) and MicroPython (the
Windows port and boards): no f-strings with `=`, no os.path, no argparse.
"""

SAMPLE_RATE = 48000
CHANNELS = 2
BLOCK_FRAMES = 256
