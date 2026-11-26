# How the apps are built

An app is a folder under `apps/` with an `__init__.py` and an `app.json`.
The app is a module with a `main(scope)` that builds its screen on
`scope.root` and does nothing when it is imported. appkit calls `main` when
the app opens and cancels everything it made when the app closes, so one
app's memory goes back when it's closed.

The apps share code in `lib/`, and draw their icons with [icons](https://github.com/PyDevices/omnipython/tree/main/packages/icons), a package of the omnipython repository that draws Material Symbols at any size (its README shows them):

- `touchkit`: the helpers the touch-panel apps use (the layout, networking,
  settings, the spectrum and a clock).
- `controlkit`: the shared controls (knobs, sliders, meters, buttons, pads, envelope and routing views) the instrument panel is laid out from.
- `soundmodule`: the General MIDI engine that midiEngine runs.
- `vamp`: Ostinato's songs on a board.
- `songmodel`: the song that Ostinato and Vamp both edit, and what carries it to a
  front panel.

An app imports from `lib/` and from the libraries in omnipython.

On a board, an app opens under the status bar, which carries Home, the app's
title and its status line (`scope.status`), then the icons, the clock and the
connections button at the right edge;
`scope.root` is everything below it. An app whose `app.json` says
`"bar": "none"` or `"own"` gets the whole screen instead, with Home in the
corner. [appkit's README](../../lib/appkit/README.md#the-status-bar) has the
details.
