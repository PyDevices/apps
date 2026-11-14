# AGENTS.md

- Bit World is a script app (`"script"` in `app.json`): `bit_world.py` builds its own `App` when imported, and the launcher restarts the board into it. Its modules import each other by name, because the launcher puts this folder on `sys.path`; it isn't a package.
- Run the tests from this folder: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m unittest discover -s tests -v`, on a CPython with pygraphics and audiodsp, and pydevices' `lib` on the path (`PYDEVICES_LIB`).
- Quitting must leave nothing running: the exit button and Esc call `app.request_quit()`, whose `on_quit` closes the audio, and the launcher restarts back to Home. A timer or stream made outside `app` outlives the quit.
- Every sprite, palette and synth patch here is a `.py` module, so the app copies to a board and bundles into a web page with no image files.
- `BIT_WORLD_ACT=0`, `1` or `2` starts in the Workshop, Sky Ruins or Cyber-Deck act, which helps for screenshots.
- `bit_sound.py` retries `audio_out.play()` on input and on each music step until it succeeds, because a browser refuses audio until the first click or key press.
- Tick callbacks take the timer argument (`def step(self, timer=None)`). Without it you get a black frame and a single traceback.
- On a board whose panel gives out two scan-out buffers (`display_drv.share_framebuffer` with two entries from `framebuffers()`), the app draws straight into the back buffer and repaints only what moved: each act's `draw_changes` must give the same pixels as its `draw`. After changing an act, run `tests/repaint_check.py`; it compares the two frame by frame.
- Never slice a panel's buffer from Python (`buf[a:b] = ...`): on an ESP32-S3 each row costs milliseconds. Copy rectangles with `FrameBuffer.blit`, as `restore_rects` does.
