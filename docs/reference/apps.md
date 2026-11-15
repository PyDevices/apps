# Apps

What each app in `apps/` does. These are the apps Home lists and appkit runs; things that run on their own, like Ostinato and Vamp, are in [programs](../../programs/README.md). Apps that run on a board are also listed in the
[gallery](https://gallery.omnipython.org). Each installs on a board with
`omip.install("github:PyDevices/apps/apps/<folder>")`, its folder named in the link
([install an app](../guides/install-an-app.md)).

| App | What it does |
|---|---|
| [Synth Station](../../apps/synthstation) | Pick an audioinstruments instrument and play it from a MIDI keyboard, with a front panel for its knobs and patches. |
| [Spotify](../../apps/spotify) | The board is a Spotify Connect speaker, and the screen is its remote. |
| [Clock](../../apps/clock), [Weather](../../apps/weather) | An analog clock and a five-day forecast for a round screen on a desk. [Set one up](../guides/put-a-clock-on-your-desk.md). |
| [Roku remote](../../apps/roku) | A TV remote over the LAN: d-pad, OK, Back, playback, volume and power. |
| [midiEngine](../../apps/midiengine) | A General MIDI sound module: 16 parts from a SoundFont, played from a USB MIDI keyboard. |
| [MP3 player](../../apps/mp3) | The songs on the SD card or the board's flash, with play, previous, next, volume and a spectrum. |
| [Video Camera](../../apps/camera), [Security camera](../../apps/security), [Object detection](../../apps/detect) | A camera preview, a camera stream, and object detection on the camera (which needs a [model file](models.md)). |
| [Camera for the ESP32-P4](../../programs/camera) | The ESP32-P4X-EYE's camera app on any ESP32-P4: photos, H.264 video with sound, an album and detection (which needs [model files](models.md)). A program that installs as an app, with `omip.install("github:PyDevices/apps/programs/camera")`. |
| [Cast](../../apps/cast) | A screen of its own on a Roku or a Windows PC over Miracast or HLS, with the panel as its remote. |
| [Stompbox](../../apps/stompbox) | A guitar or a WAV clip through an airwindows effect, with its knobs on screen. Needs a firmware built with audioairwindows. |
| [Sound card](../../apps/card) | The board is a USB speaker for a computer, with a spectrum of what plays. |
| [MIDI Controller](../../apps/midicontroller) | A MIDI controller on the screen, for a synth or a DAW: tabs of 16 pads in four banks, 16 knobs, 16 faders, an eight-strip mixer with mute and solo, an XY pad with transport buttons, and two octaves of keys. Sends over USB as a MIDI device, to a synth on the USB host port, over Bluetooth LE MIDI, to a computer's own MIDI ports, or, in a browser page, to the outputs Web MIDI offers, and what comes back moves the controls. Each control's note or CC can be changed on the screen. Needs a screen of 480 x 320 or larger, and `midiports` or `bledev` for the way out. |
| [Gamepad](../../apps/gamepad) | On a board with a USB device port, the screen is a game controller for a computer or another board: a d-pad, a stick and eight buttons. On a board with a USB host port, it shows the gamepad plugged into it, each button, stick, hat and axis as it moves. A board with both asks which. Needs a screen of 480 x 320 or larger, `usb-hid` for the first and `usb-host-hid` for the second. |
| [System](../../apps/system) | Whether the board is well, at a glance: a turning arc and frame rate, a touch test, memory, boot, network, audio and what the board is; `stats()` gives the same from the REPL. |
| [REPL](../../apps/repl) | The board's own Python prompt on its screen, typed on a USB or Bluetooth LE keyboard. Draws with [vtterm](https://github.com/PyDevices/pydevices/tree/main/packages/vtterm), which installs with it, and needs firmware whose `palettes` has its ANSI palette (`palettes.ansi`). It needs `os.dupterm` too, which CircuitPython doesn't have, so Home leaves it out there. |
| [Wake word](../../apps/wake) | Listens on a USB microphone for "Hey Jarvis" and flashes on each detection. Needs [model files](models.md). |
| [Bit World](../../apps/bit_world) | Bit, a pixel-art robot, as a desk pet, in a platformer and on a reactor deck with a sequencer, scored with synthio. It plays itself until touched. A script app: while it runs the board has no WebREPL, so connect again after it quits ([plain scripts](../../lib/appkit/README.md#plain-scripts)). |
| [Home](../../apps/home) | The home screen: a tile for each installed app, and the gear that opens System. Its `main.py` starts it when the board does. |
| [Walkie-talkie](../../apps/medialink_walkie_talkie), [Hands free](../../apps/medialink_hands_free), [Baby monitor](../../apps/medialink_baby_monitor) | Voice between two devices on one network: hold a button to talk, speak and take the turn, or listen to a room. Each needs a microphone, a speaker and mDNS. Hands free can start a turn only on a wake word (needs [model files](models.md)). |
| [Doorbell](../../apps/medialink_doorbell), [Video doorbell](../../apps/medialink_video_doorbell), [Videophone](../../apps/medialink_videophone), [Surveillance camera](../../apps/medialink_surveillance_camera) | Sound and pictures between two devices on one network: ring a house and talk to whoever answers, see who is at the door, call with video, or watch a camera in another room. The picture side needs a camera and a JPEG decoder. |
