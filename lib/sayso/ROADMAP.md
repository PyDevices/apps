# sayso roadmap

What's working today is in the [README](README.md) and
[PORTABILITY.md](PORTABILITY.md).

- **CircuitPython on a board.** sayso runs on a CircuitPython board as it
  does on MicroPython, with the result recorded in `PORTABILITY.md`.
- **Generated specs that match the hand-curated ones.** The schema generator
  keeps the `object_by_key` overrides and Spotify's endpoint removals.
- **More mutation results.** Write methods return a result object, as
  playlist changes return `SnapshotResult`, wherever Spotify's response is
  worth having.
