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
firmware with `svgio`, a microphone, Wi-Fi and a board with PSRAM; a speaker
is for hearing the answer, and without one Huey's words are only shown. It
runs on MicroPython-compatible boards.

Huey thinks on a server: any that speaks OpenAI's API for speech to text,
chat and text to speech. As installed he asks [DeepInfra](https://deepinfra.com),
and wants your key in a file on the board:

```bash
mpftp put deepinfra.key /deepinfra.key
```

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
| `base_url` | `https://api.deepinfra.com/v1/openai` | The server: the address its `chat/completions` is under |
| `key_file` | `/deepinfra.key` | A file with the API key on one line, or `""` for a server that asks for none |
| `stt_model` | `openai/whisper-large-v3-turbo` | The model that turns your question into text |
| `chat_model` | `mistralai/Mistral-Small-3.2-24B-Instruct-2506` | The model that answers |
| `tts_model` | `inworld-ai/realtime-tts-1.5-mini` | The model that speaks the answer |
| `voice` | `Dennis` | A voice of that model's, a man's since Huey is a he; `""` for the model's own |
| `speech_rate` | `24000` | The rate of speech sent as bare PCM; WAV carries its own |
| `volume` | `80` | How loud Huey speaks, 0 to 100 |
| `listen_seconds` | `12` | The longest question |
| `place` | `desk` | Where Huey is when the app opens: `coast`, `bench` or `desk` |

To use a server of your own, such as
[lite-assistant](https://github.com/PyDevices/lite-assistant) on a computer
on your network, change the address, the models and the key file.
[`settings.example.json`](settings.example.json) does that:

```json
{
  "base_url": "http://192.168.1.20:5000/v1",
  "key_file": "",
  "stt_model": "moonshine",
  "chat_model": "e2b",
  "tts_model": "kokoro",
  "voice": "am_puck"
}
```

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
