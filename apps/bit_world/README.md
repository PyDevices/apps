![Bit World's workshop: Bit, a robot with a screen for a face, hovers between a night window and three status panels, with the scene tabs and the exit X along the top](docs/images/bit_world.png)

# Bit World

Bit World is a PyDevices app: Bit, a hovering robot, moves through three
pixel-art scenes drawn with pygraphics and scored with synthio, on
MicroPython-compatible boards and on CPython. It plays itself until you touch
it.

## On a board

Copy `apps/bit_world/` to `/apps/bit_world/` with mpftp, mpremote or any
file tool, leaving out `tests/` and `docs/`. Home shows it on the Desk page.
It needs a display and the pygraphics, palettes, audiodsp and multimer libraries, and
plays its music through the board's audio out when there is one.

It turns a portrait panel to landscape when the display can turn what's
drawn. A display that can't, such as the Arduino GIGA Display Shield's
framebuffer, keeps its portrait layout.

Choosing it restarts the board into Bit World alone, so it has the panel and
the processor to itself. The X at the right of the stage bar, or Esc on a
keyboard, quits back to Home.

## Play it

Touch or click a tab to change scene, AUTO to stop or start the tour, and
SND to mute. On a keyboard, 1, 2 and 3 change scene, A or Tab toggles the
tour, M mutes, and Space and F are each scene's two actions.

## Choose where the music plays

At start Bit World prints every sound output it can find and plays to the
one chosen for the whole device, from the connections picker on Home. Set
`BIT_WORLD_AUDIO` to a word of an output's name to choose it from the
script instead. On a Windows PC, `BIT_WORLD_AUDIO=realtek` prints:

```text
Bit World: audio out 'System default' (win_audio-out:default)
Bit World: audio out 'Speakers (Realtek(R) Audio)' (win_audio-out:Speakers (Realtek(R) Audio))
Bit World: playing to 'Speakers (Realtek(R) Audio)'
```

It lists and picks with endpointkit, the same calls any script uses;
`pick_audio_out` in `bit_output.py` is the whole of it. A board lists the
outputs its firmware registers with endpointkit.

[Roadmap](../../ROADMAP.md)

Made by [PyDevices](https://pydevices.com).
