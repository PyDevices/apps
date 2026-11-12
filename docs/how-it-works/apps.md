# How the apps are built

An app is a folder under `apps/` with an `__init__.py` and an `app.json`.
The app is a module with a `main(scope)` that builds its screen on
`scope.root` and does nothing when it is imported. appkit calls `main` when
the app opens and cancels everything it made when the app closes, so one
app's memory goes back when it's closed.

The apps share code in `lib/`, and draw their icons with [iconkit](https://github.com/PyDevices/pydevices/tree/main/packages/iconkit), a package of the pydevices repository (every icon is on its [icons page](https://github.com/PyDevices/pydevices/blob/main/packages/iconkit/docs/reference/icons.md)):

- `touchkit`: the helpers the touch-panel apps use (the layout, networking,
  settings, the spectrum and a clock).
- `controlkit`: the shared controls (knobs, sliders, meters, buttons, pads) the instrument panel is laid out from.
- `soundmodule`: the General MIDI engine that midiEngine runs.
- `vamp`: Ostinato's songs on a board.
- `songmodel`: the song that Ostinato and Vamp both edit, and what carries it to a
  front panel.

An app imports from `lib/` and from the libraries in pydevices.
