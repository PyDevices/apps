# Model files

Wake word, Object detection and Camera's face and people detection run neural
networks that the apps don't carry. You download the files once and put them in
a `models` folder. Each app looks in these places, in this order, and uses the
first that has the file:

| Where | Folder |
|---|---|
| The SD card | `/sd/models` |
| Flash | `/models` (`/flash/models` on an STM32) |
| The data root | `/data/models` |

The firmware needs the matching module too: `tflite` for the wake word, `espdl`
(the `vision` build) for the detectors. An app that can't find its file says so
on screen and names the folder.

## The files

Rename a download to the name in the first column. Apps look for that name.

| File to save as | Used by | Download | License | Size | What it is |
|---|---|---|---|---|---|
| `hey_jarvis.json` | [Wake word](../../apps/wake), [Hands-free medialink](../../apps/medialink_hands_free) (`WAKE_WORD`) | [hey_jarvis.json](https://raw.githubusercontent.com/esphome/micro-wake-word-models/40ff33f57f8fc6ad71a75ef085abbf742495b225/models/v2/hey_jarvis.json) | Apache-2.0 | 388 bytes | The manifest for the "Hey Jarvis" model, version 2, by Kevin Ahrendt |
| `hey_jarvis.tflite` | the same two | [hey_jarvis.tflite](https://raw.githubusercontent.com/esphome/micro-wake-word-models/40ff33f57f8fc6ad71a75ef085abbf742495b225/models/v2/hey_jarvis.tflite) | Apache-2.0 | 52,272 bytes | The microWakeWord model the manifest names; keep this name, the manifest points at it |
| `yolo11n_coco.espdl` | [Object detection](../../apps/detect) | [espdet_yolo11n_160_160_coco.espdl](https://raw.githubusercontent.com/espressif/esp-vision/bd16dbc8677f8d1e0ca7d489c5e6591e574f4f3a/models/espdet/yolo11n/espdet_yolo11n_160_160_coco.espdl) | see below | 2,861,408 bytes | YOLO11n at 160x160, the 80 COCO classes, loaded with `espdl.YOLO11` |
| `pedestrian.espdl` | [Camera](../../programs/camera) (the AI page, people) | [pedestrian_detect_pico.espdl](https://raw.githubusercontent.com/espressif/esp-vision/bd16dbc8677f8d1e0ca7d489c5e6591e574f4f3a/models/pedestrian_detect/pedestrian_detect_pico.espdl) | MIT | 435,280 bytes | ESP-DL's 224x224 pedestrian detector, loaded with `espdl.PedestrianDetect` |
| `face.espdl` | [Camera](../../programs/camera) (the AI page, faces) | [espdet_pico_224_224_face.espdl](https://raw.githubusercontent.com/espressif/esp-vision/bd16dbc8677f8d1e0ca7d489c5e6591e574f4f3a/models/espdet/pico/face/espdet_pico_224_224_face.espdl) | Apache-2.0 | 495,840 bytes | ESP-VISION's ESPDet Pico Face, 224x224, one class "face", loaded with `espdl.ESPDet` |

The two wake word files come from ESPHome's
[micro-wake-word-models](https://github.com/esphome/micro-wake-word-models)
(`models/v2`, an Apache-2.0 repository whose licence covers the model weights).
The three `.espdl` files come from Espressif's
[esp-vision](https://github.com/espressif/esp-vision) `models` folder
(Apache-2.0 as a repository; the pedestrian folder carries its own MIT licence
file). Each link above is pinned to a commit, so it keeps working.

`face.espdl` is not ESP-DL's two-stage `human_face_detect` pair
(`human_face_detect_msr_s8_v1.espdl` and `..._mnp_s8_v1.espdl`). Camera loads
a single-stage detector, so those two files do nothing there. They belong to
`espdl.HumanFaceDetect`, which the
[vision module's face example](https://github.com/PyDevices/micropython-pydevices/blob/main/modules/vision/examples/espdl_face_landmarks.py)
uses.

The YOLO11n weights were trained by Ultralytics, whose own licence is
AGPL-3.0. Espressif publishes the exported `.espdl` file in a repository
under Apache-2.0 without a licence note for that folder, so check the terms
fit your use before you ship it in a product.

## Put them on the board

On a computer, copy the files into a `models` folder at the top of the SD card.
Or put them on flash with [mpftp](https://github.com/PyDevices/mpftp) from the
folder you downloaded to:

```sh
mpftp mkdir /models
mpftp put hey_jarvis.json /models/hey_jarvis.json
mpftp put hey_jarvis.tflite /models/hey_jarvis.tflite
```

A desktop has no card or flash: its folder is `models` in the app's data root
(`~/.local/share/appkit/models` on Linux).

## Check your copy

`sha256sum` on the files as downloaded from the links above:

| File | SHA-256 |
|---|---|
| `hey_jarvis.json` | `b153867d818675d8abcc9dace474afe7f83551ae0d5a9b1d71a98681320185af` |
| `hey_jarvis.tflite` | `21a7976add39ee24ec96c63d96b7aaa18e24d1d9824b963e451da8feb4b78b77` |
| `yolo11n_coco.espdl` | `5978bf70d1464f09ad8f4907b4c59178482c780e7e30a1b3ce0a7d405a5eb62f` |
| `pedestrian.espdl` | `0bc5326cab0f004c9525a2e3e83899b3e7a68796debb2d21c13935329b8006cc` |
| `face.espdl` | `04eec2220adbf642a843c953817fb219a06c094aedb76c181ba2a958c65201dc` |

The older `hey_jarvis.json` and `.tflite` at the top of ESPHome's `models`
folder (version 1) are different files; use the `v2` ones.
