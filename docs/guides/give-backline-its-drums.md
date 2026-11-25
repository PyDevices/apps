# Give Backline its drums

Backline plays its songs on a small SoundFont drum kit of its own,
`backline-drums.sf2` (1.6 MB). The bank isn't kept in this repository, so
each way of installing Backline gets it from
`https://github.com/PyDevices/lib/releases/download/backline-drums-1/backline-drums.sf2`.
The drum machines (Rhythm 808, 909, 606, 78 and Electronic Drums 5) need no
file, and you can pick one from the kit list at any time.

## How each install gets the bank

| You installed Backline with | The bank comes | It lands in |
|---|---|---|
| `omip.install("github:PyDevices/apps/apps/backline")` on a board | with the app's other files | `/apps/backline/soundfonts` |
| `pip install` on a computer | on Backline's first start | Backline's data folder (`~/.local/share/appkit/backline` on Linux) |
| a firmware with the apps frozen in | on Backline's first start, over the board's Wi-Fi | the first `soundfonts` folder that takes a file: `/sd/soundfonts` with a card in, else `/soundfonts` |

While the bank downloads, the screen says so and nothing plays. Backline
checks the download's SHA-256 before it keeps it, so a broken download leaves
nothing behind and Backline tries again on its next start.

## With no network

Download `backline-drums.sf2` from the link above on a computer and copy it to
the folder in the table. On a board that's one line from the computer:

```sh
mcuctl put backline-drums.sf2 /sd/soundfonts/backline-drums.sf2
```

If Backline can't fetch the bank, the screen says why and where the file goes.
The drum machines still play.

## Play another SoundFont

Any General MIDI SoundFont with a drum kit on bank 128 works:

- Put its `.sf2` in a `soundfonts` folder (`~/soundfonts` on a computer, or
  `/sd/soundfonts`, `/soundfonts` or `/data/soundfonts` on a board). It shows in
  the kit list under its file name.
- Or set the `SOUNDFONT` environment variable to its path. Backline then plays
  it in place of its own bank.

A large bank such as FluidR3_GM (148 MB) plays from an SD card on an ESP32-S3
with 8 MB of PSRAM, and takes over a minute to open there.

## Where the bank comes from

The sounds are the FreePats
[synthesizer percussion](https://freepats.zenvoid.org/Percussion/electric-percussion.html)
(version 2022-07-18), made by Roberto with Yoshimi and Geonkick and published
under the [CC0 public domain dedication](https://creativecommons.org/publicdomain/zero/1.0/).
[`tools/backline/make_drums.py`](../../tools/backline/make_drums.py) lays them
out as a General MIDI drum kit: kick on 36, snare on 38, the hats on 42, 44 and
46 in one choke group, toms, crash, ride, shakers and claves. It copies the
recordings unchanged, and gives the same file every time from the same source.
