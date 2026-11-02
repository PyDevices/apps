# How the apps are built

An app is a folder under `apps/` with an `__init__.py` and an `app.json`.
The app is a module with a `main(scope)` that builds its screen on
`scope.root` and does nothing when it is imported. appkit calls `main` when
the app opens and cancels everything it made when the app closes, so one
app's memory goes back when it's closed.

The apps share code in `lib/`:

- `touchkit`: the helpers the touch-panel apps use (the layout, networking,
  settings, the spectrum and a clock).
- `controlpanel`: the hardware-style front panel that Synth Station draws.
- `soundmodule`: the General MIDI engine that midiEngine runs.
- `vamp`: Ostinato's songs on a board.
- `songlink`: the song that Ostinato and Vamp both edit, and what carries it to a
  front panel.

An app imports from `lib/` and from the libraries in pydevices.
