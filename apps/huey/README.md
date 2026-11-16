![Huey, a chameleon turned the colour of snow, on a log at a winter coast with a mug in his hand, saying "Winter, easily. Come and see the coast with me, I turn the colour of snow." in a speech bubble, over the question he was asked](docs/images/huey.png)

# Huey

Huey is a PyDevices app: Huey the chameleon as someone to talk to. Hold him,
ask something out loud and let go. He answers through the board's speaker and
in a speech bubble, and acts the answer out: a mood, a change of colours,
something to hold, another place or season.

## On a board

```python
import omip
omip.install("github:PyDevices/apps/apps/huey")
```

That installs [Huey's Perch](../perch) too, whose stage and drawings this app
uses. Home shows Huey on the Desk page. It needs a display with touch, LVGL,
a firmware whose `svgio` has `expand` and `Buffer`, a microphone, Wi-Fi and
a board with PSRAM; a speaker is for hearing the answer, and without one
Huey's words are only shown. It runs on MicroPython-compatible boards.

Huey thinks on a server: any that speaks OpenAI's API for speech to text,
chat and text to speech. As installed he asks
[lite-assistant](https://github.com/PyDevices/lite-assistant) running on a
computer on your network, and needs two things from you: where that computer
is, and a key for the board.

Give the board its own key on the computer that runs lite-assistant:

```bash
lite-assistant users add my-board   # prints the board's key, once
```

Save the key on one line in a file, and put it on the board:

```bash
mpftp put lite-assistant.key /lite-assistant.key
```

Then put the server's address in `/data/huey/settings.json` on the board.
It is the computer's address on your network, lite-assistant's port, and
`/v1`:

```json
{"base_url": "http://192.168.0.10:5000/v1"}
```

Until it has an address, Huey says in his bubble where it goes. On Windows
with lite-assistant running in WSL, the board reaches it at the Windows
computer's address when WSL's networking mode is `mirrored`.

## Talk to him

Touch Huey and keep your finger there while you speak; a ring round his head
shows what the microphone hears. Let go, and the line at the bottom says
what he is waiting for: the words, the reply, the voice. Your question shows
there as Huey understood it. Hold him again at any time to stop him and ask
something else.

Whatever stands in the way is said in the bubble: no Wi-Fi, no key file,
settings that don't read, no microphone, a server that refuses.

## Settings

Settings are one JSON file, `settings.json` in the app's data folder
(`/data/huey` on a board). It holds only what differs from these:

| Setting | As installed | What it is |
|---|---|---|
| `base_url` | `""` | The server: the address its `chat/completions` is under |
| `key_file` | `/lite-assistant.key` | A file with the API key on one line, or `""` for a server that asks for none |
| `stt_model` | `moonshine` | The model that turns your question into text |
| `chat_model` | `gemma-4-E2B-it` | The model that answers |
| `tts_model` | `kokoro` | The model that speaks the answer |
| `voice` | `am_puck` | A voice of that model's, a man's since Huey is a he; `""` for the model's own |
| `speech_rate` | `24000` | The rate of speech sent as bare PCM; WAV carries its own |
| `volume` | `80` | How loud Huey speaks, 0 to 100 |
| `listen_seconds` | `12` | The longest question |
| `place` | `desk` | Where Huey is when the app opens: `coast`, `bench` or `desk` |

To ask [DeepInfra](https://deepinfra.com) instead, copy
[`settings.example.json`](settings.example.json) to
`/data/huey/settings.json` and put your DeepInfra key in `/deepinfra.key`:

```bash
mpftp put settings.example.json /data/huey/settings.json
mpftp put deepinfra.key /deepinfra.key
```

On an ESP32-P4 board a turn through DeepInfra takes about 3 to 4 s from letting go
to Huey's first word, and one through lite-assistant about 5 to 7 s, most of
it the chat model on the computer. Huey keeps his connections to the server
open between questions and starts speaking as soon as the words of his
answer are in, before the rest of it.

Over `https` the connection is encrypted, but MicroPython doesn't check the
server's certificate.

## See him without a board

[`tools/film.py`](tools/film.py) runs a whole conversation on a display in
memory, against a stand-in server, and writes a picture of each moment. It
needs a MicroPython unix port with LVGL and svgio. This made the picture
above:

```bash
cd apps/huey
mkdir out
micropython -X heapsize=128M tools/film.py out
```

[Roadmap](../../ROADMAP.md)

Made by [PyDevices](https://pydevices.com).
