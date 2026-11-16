# AGENTS.md

- Tests: `python -m unittest discover -s tests` from a Python with audiodsp installed. The wrapper puts the `lib/` of the audioinstruments and audioeffects checkouts beside this one (or `$AUDIOINSTRUMENTS_DIR`, `$AUDIOEFFECTS_DIR`) on every interpreter's path. An interpreter with audioinstruments frozen in (an old `bin/micropython`) shadows them, and needs audiodsp's `audiosampler`. MicroPython and CircuitPython need `-X heapsize=64M`: five instruments outgrow the 8 MB default.
- Every check in `tests/engine_contract.py` has a plant in `PLANTS` that must make it fail. Add one with each new check.
- The contract runs on MicroPython and CircuitPython too: no `os.path`, no f-strings with `=`, and `memoryview.cast` isn't there (use `array.array("h", bytes(buf))`). CircuitPython's audio buffers count samples, not bytes.
- `tools/gate.py` drives Windows from WSL: REAPER, a loopback MIDI port and a CPython venv on Windows. A Windows process outlives a timeout on the WSL side; the gate ends them by command line.
- REAPER sends CC0 = 0 to every part when it stops. What a part played is in `Part.played`, not in its bank at the end.
- Home apps (an `app.json`, run by appkit) live in `apps/`; things that run on their own (Ostinato, Vamp) live in `programs/`. Libraries live in `lib/` (soundmodule, songmodel). Code two of them share goes in `lib/` (`songmodel`); Ostinato's `tools/gen_boot.py` lists what its page loads from there, so run it after adding a shared file.
- iconkit lives in the omnipython repository (`packages/iconkit`). appkit's tests find it beside `OMNIPYTHON_LIB`'s `lib`, or in `ICONKIT_LIB`; the index check raises with the fix when it isn't importable.
- Vamp's tests need hmilink: `$HMILINK_PATH`, or a `omnipython` checkout beside this one. CI sets `VAMP_REQUIRE=1` so a missing piece fails instead of skipping.
- Vamp's front panel is pressed through LVGL on a display in memory (`tests/vamp_panel_contract.py`), and each plant in `PANEL_PLANTS` must fail it. CI's MicroPython has no LVGL, so there the screen's checks run on CPython only.
- sayso's tests: `PYTHONPATH=lib python -m unittest discover -s tests/sayso` from the root. The offline tests need no credentials; `test_live.py` skips without a `sayso.local.json`. Never commit `sayso.local.json`, `tokens.json` or `lib/sayso/examples/write_examples.json`.
- To test sayso without a network, replace `sayso.transport.requests` with a mock that has `get`/`post` (and `put`/`delete` for writes) before you build `SpotifyClient`.
- Spotify's Dev Mode removed `GET /users/{id}` and the legacy playlist track endpoints ([PORTABILITY.md](lib/sayso/PORTABILITY.md)). Don't add `fetch_method` on `User`.
- Stompbox's meter check (`tests/stompbox_check.py`) needs no airwindows: a stand-in effect passes the audio through. To run the app itself on a computer, CPython with `omnipython-airwindows` installed works: `tools/stompbox/drive.py` plays a clip, prints the meter and saves the screen.
- tests/ has an `appkit` folder, which hides the real `appkit` when `tests/` is first on the path: put `lib/` before it.
- The MIDI Controller app's screen test runs `tests/midicontroller_contract.py` against `midiports` and `iconkit` from an omnipython checkout (`$OMNIPYTHON_DIR`, or one beside this one), and skips without it. CI sets `MIDICONTROLLER_REQUIRE=1`.
- The Gamepad app's screen test runs `tests/gamepad_contract.py` against `usb-hid` and `usb-host-hid` from an omnipython checkout (`$OMNIPYTHON_DIR`, or one beside this one), and skips without them. CI sets `GAMEPAD_REQUIRE=1`.
