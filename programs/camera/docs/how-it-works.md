# How Camera works

## What a board needs

The pages never touch hardware. They ask seams, which come in two sets with
the same methods: `hw.desktop` (stand-ins that run anywhere) and `hw.board`
(any ESP32-P4 board). The board's side takes everything from the board
package: `board_config.camera` (cameraif), `sdcard`, `led`, `accelerometer`,
`pcm_in` and `sleep`. A board that lacks one steps down and says so in the
log:

| Missing | What the program does |
|---|---|
| a MIPI-CSI camera | looks for a USB camera on the host port, then shows the test card |
| a microphone | records video with no sound |
| a card slot | photos and video go to `/photos` and `/videos` on flash |
| an accelerometer | the screen stays upright |
| a sleep helper | interval sleep blanks the screen and wakes on a touch or key |
| `vision` in the firmware | no pedestrian or face detection |
| `usb.device` | the card isn't offered as a disk |

On the ESP32-P4X-EYE every part is there, and nothing changes. On the board
the models go in a `models` folder (`/sd/models` on the card, `/models` or
`/data/models` on flash): `pedestrian.espdl`, `face.espdl` and
`human_face_detect_*.espdl`, and the `mp4mux` package in `/lib/mp4mux`.
The Eye's board config brings its display, keys, accelerometer and
`orientation` helper.

A board config can add two names the program reads:

- `camera_source`: `"csi"`, `"uvc"` or `"testcard"`, to use that source
  rather than the first the board has.
- `camera_buttons`: a dict of `"menu"`, `"up"`, `"down"` and `"encoder"` to key
  codes (or tuples of them), when the board's keypad sends different ones. The
  default is M or Escape, the arrow keys and Enter.

## The screen

The factory layout is fixed at 240x240. Each page is drawn in a 240x240
container (`layout.py`). On a 240x240 panel the container is the screen. On
a bigger one it is enlarged by the whole number that fits, 3x on 720x720 and
2x on 800x480, and centred on a black border.

## The controls

A board with a keypad or an encoder uses them. A board with a touch screen also
gets tap zones over the Menu, Up and Down pictures (`controls.py`): tap one,
tap anywhere else for the knob press, drag up or down for one knob step (up
zooms in), and hold the top picture for Menu where it shows Select.

To leave for Home on a panel the picture fills (720x720 at 3x), hold a finger
in the top-left corner for about a second: the launcher's own Home button is
under the picture there. A wider panel shows that button beside the picture.

## The camera source

Every source answers `size()`, `frame(timeout)`, `start()`, `stop()` and
`deinit()` (`apps/eyecam/hw/sources.py`). A frame is RGB565, borrowed until the
next call.

- **MIPI-CSI**: the board's cameraif camera, used first when there is one.
- **USB**: a UVC camera on the host port, through usbhost's
  `usb.host.video.Camera`. It asks for MJPEG, up to 1280x720 at 25 fps, within
  a webcam's isochronous limit, and the P4's JPEG engine decodes each frame.
  A webcam needs the host port's high speed: plug it into the board's own
  Type-A socket, not behind a hub.
- **Test card**: a still picture, for a board with neither.

Photos and video are cut from whatever frame the source gives, at the
factory's sizes. A camera smaller than the factory's 1920x1080 gives a
smaller cut that is scaled up.

## Video

Video is H.264 from the board's encoder, with the microphone's sound at
16 kHz in the same MP4. The encoder, the colour conversion and the screen all
share the PSRAM and the PPA, so a recording runs slower than the preview: a
P4 board records 720P at 11 to 13 frames a second with sound. 1080P records
at 4 to 7 frames a second on the P4 boards with a big panel (the EYE's small
panel leaves it 10), and a board that can't find memory for the encoder says so
on the screen. A recording goes to the card when one is in, else to flash; a
board whose config has no card-detect pin is taken to have a card until it
fails to mount.

## Where it differs from the factory

| What | Factory | Here |
|---|---|---|
| Preview | LVGL 8 canvas on a transparent screen | an `lv.image` over a 240x240 container |
| Wheel items | `lv_btn` | plain `lv.obj`; they're only scrolled |
| Video | MP4 (MJPEG and PCM) | H.264 in MP4 with 16 kHz sound through `h264enc` and `mp4mux`; MJPEG frames on the desktop |
| Detection | esp-dl in its own task | esp-dl's pedestrian and face models, run in the frame loop and unloaded when the AI page is left |
| Settings | NVS u8, u16 and u32 keys | NVS i32 keys, namespace `p4_eye_cfg`; JSON on a desktop |
| Rotation | LVGL rotation and the PPA | the panel itself turns, and the PPA turns the preview back |
| Card folders | `esp32_p4_pic_save` and `esp32_p4_mp4_save` | `photos` and `videos`, shared with the other camera apps, with flash behind the card |

Where the factory was unclear, the program picks: video needs 100 MB free and
a photo 5 MB; resolution cycles 720P, 1080P, 480P; the delete dialog opens with
NO focused.

## The pictures and fonts

The 21 images are LVGL 9 `.bin` files, drawn from their bytes with no decoder
(about 1.1 MB; the equivalent PNGs decode in 76 to 88 ms on first draw). The
six fonts are KoHo Bold 18 and 28 and SemiBold 14, 18, 22 and 24, made with
`lv_font_conv`. A missing font falls back to Montserrat. [NOTICE](../NOTICE)
has the licences.

## Screens

Each is an LVGL snapshot at 240x240. `tools/run.sh tools/shots.txt` takes all
51 into `$EYECAM_SHOTS` and `tools/shots_to_png.py` makes the PNGs;
`tools/shots-empty.txt` shows the album with no photos. A few are here:
[camera popup at 3x](screens/720-camera-popup.png),
[HUD](screens/03-camera-hud.png), [2x zoom](screens/04-camera-zoom-2x.png),
[recording](screens/24-video-recording.png),
[pedestrian](screens/29-ai-pedestrian.png), [album](screens/32-album-newest.png),
[USB disk](screens/40-usb-connected.png), [settings](screens/45-settings.png),
[camera settings](screens/48-camera-settings.png),
[empty album](screens/60-album-empty.png).
