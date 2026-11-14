# Apps

What each app in `apps/` does. These are the apps Home lists and appkit runs; things that run on their own, like Ostinato and Vamp, are in [programs](../../programs/README.md). Apps that run on a board are also listed in the
[gallery](https://gallery.omnipython.org).

| App | What it does |
|---|---|
| [Synth Station](../../apps/synthstation) | Pick an audioinstruments instrument and play it from a MIDI keyboard, with a front panel for its knobs and patches. |
| [Spotify](../../apps/spotify) | The board is a Spotify Connect speaker, and the screen is its remote. |
| [Clock](../../apps/clock), [Weather](../../apps/weather) | An analog clock and a five-day forecast for a round screen on a desk. [Set one up](../guides/put-a-clock-on-your-desk.md). |
| [Roku remote](../../apps/roku) | A TV remote over the LAN: d-pad, OK, Back, playback, volume and power. |
| [midiEngine](../../apps/midiengine) | A General MIDI sound module: 16 parts from a SoundFont, played from a USB MIDI keyboard. |
| [MP3 player](../../apps/mp3) | The songs on an SD card, with play, previous, next, volume and a spectrum. |
| [Camera](../../apps/camera), [Security camera](../../apps/security), [Object detection](../../apps/detect) | A camera preview, a camera stream, and object detection on the camera. |
| [Cast](../../apps/cast) | A screen of its own on a Roku or a Windows PC over Miracast or HLS, with the panel as its remote. |
| [Stompbox](../../apps/stompbox) | A guitar or a WAV clip through an airwindows effect, with its knobs on screen. Needs a firmware built with audioairwindows. |
| [Sound card](../../apps/card) | The board is a USB speaker for a computer, with a spectrum of what plays. |
| [System](../../apps/system) | Whether the board is well, at a glance: a turning arc and frame rate, a touch test, memory, boot, network, audio and what the board is; `stats()` gives the same from the REPL. |
| [REPL](../../apps/repl) | The board's own Python prompt on its screen, typed on a USB or Bluetooth LE keyboard. Needs [vtterm](https://github.com/PyDevices/pydevices/tree/main/packages/vtterm). |
| [Wake word](../../apps/wake) | Listens on a USB microphone for "Hey Jarvis" and flashes on each detection. |
| [Bit World](../../apps/bit_world) | Bit, a pixel-art robot, as a desk pet, in a platformer and on a reactor deck with a sequencer, scored with synthio. It plays itself until touched. |
