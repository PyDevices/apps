# Programs

A program runs on its own: you start it, and it doesn't need Home. A Home app
is different. It lives in [`apps/`](../apps), has an `app.json`, and appkit
runs it from the home screen.

| Program | What it does |
|---|---|
| [Ostinato](ostinato) | A pattern sequencer and song editor, in a browser or a desktop window. |
| [Vamp](vamp) | Plays Ostinato's songs on one MicroPython, with the screens elsewhere. |

Every program folder has a `README.md` that opens with what the program does,
then a `Runs on:` line naming the boards or computers it works on, then how to
put it there.
