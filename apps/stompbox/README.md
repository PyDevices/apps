# Stompbox

A guitar effects app you play through: an audio input or a WAV clip goes
through an airwindows effect and out to a speaker, with the effect's knobs on
an LVGL window. It runs on MicroPython's Windows port and on CPython.

## Run it

You need a Windows `micropython.exe` built with the airwindows module. From this folder:

```
micropython.exe -X heapsize=128M run.py --clips C:\path\to\wavs
```

That plays WAV clips. To play a guitar through an audio interface instead, name
its capture endpoint. `--out` picks the speaker, or leave it off for the default:

```
micropython.exe -X heapsize=128M run.py --live {0.0.1.00000000}.{your-input-id}
```

The window shows the route and its latency while it plays. When the input and
output are one device they share a clock and the audio passes straight through.
On two devices, a drift resampler holds a ring buffer between them.

The effect list opens on a curated guitar set, kept in
[stompbox/guitar-set.txt](stompbox/guitar-set.txt). "Show all" adds the rest of
the airwindows plug-ins.

`tools/` holds the latency measurements: `chain_depth.py` for what the software
path holds, `roundtrip.py` for a click around a cable from output to input,
`c_path.py` and `drift_path.py` for the C path on one and two clocks.
