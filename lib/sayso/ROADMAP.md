# sayso roadmap

What's working today is in the [README](README.md) and
[PORTABILITY.md](PORTABILITY.md).

- **CircuitPython on a board.** sayso runs on a CircuitPython board as it
  does on MicroPython, with the result recorded in `PORTABILITY.md`.
- **Removed endpoints marked.** Client methods Spotify no longer serves to
  Dev Mode apps, such as `user()` and the old `playlist_tracks()`, say so in
  their docstrings and in the endpoint coverage report.
- **Generated specs that match the hand-curated ones.** The schema generator
  keeps the `object_by_key` overrides and Spotify's endpoint removals.
- **More mutation results.** Write methods return a result object, as
  playlist changes return `SnapshotResult`, wherever Spotify's response is
  worth having.
- **Spotify's limits checked before a request,** such as the most IDs one
  request takes, so a write fails with a clear error instead of the API's.
