# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Camera: a live preview from the CSI camera, and a shutter.

The preview is cameraif's ``capture_scaled``: the P4's pixel accelerator
scales each frame straight into a square of the panel's framebuffer, beside
the LVGL widgets, and only that square is presented. It runs as the set's
foreground loop, one frame per call, so LVGL and the timers keep going
between frames.

The shutter takes a JPEG on the P4's encoder (``capture_jpeg``) and saves it
in ``/sd/photos`` on the SD card, mounted while the app is open. Without a
card it goes to ``/photos`` on flash, or ``/data/photos`` when flash won't
take it (`appkit.places`). The last shot shows on the right, and every shot
in all three folders is on a small web page on the board: open the address
on the screen from a phone or a PC.

Without a camera the app says so, and Home goes back as usual.
"""

import os

import lvgl as lv

from touchkit import cam, net, ui
from touchkit.clock import sleep_ms

PREVIEW = 400  # the preview's longer side on the panel
QUALITY = 85
PORT = 8080
THUMB = 160

state = None  # the open app's state, for the console


def _save(path, data):
    for attempt in range(3):
        try:
            with open(path, "wb") as f:
                f.write(data)
            if os.stat(path)[6] == len(data):
                return True
        except OSError as e:
            print("camera: write", path, e)
        sleep_ms(100)
    try:
        os.remove(path)  # don't leave an empty or short file behind
    except OSError:
        pass
    return False


def main(scope):
    global state
    root = scope.root
    W, H = scope.size
    RX, RY = scope.rect[:2]
    status = ui.status(scope)
    st = state = {"cam": None, "shots": 0, "last": None, "server": None, "open": True}
    keep = {}  # the thumbnail's pixels, while LVGL shows them
    opts = cam.options(scope)

    try:
        st["cam"] = cam.open_camera(opts)
    except Exception as e:
        ui.missing(scope, "no camera", cam.no_camera_text(e, "Video Camera"))
        return
    c0 = st["cam"]
    pw, ph = cam.preview_size(c0, PREVIEW)
    x0, y0 = 24, 8 + (PREVIEW - ph) // 2  # in root
    ui.frame(root, x0, y0, pw, ph)

    top = 8
    rx = 24 + PREVIEW + 24
    rw = W - rx - 24
    shutter, _ = ui.button(root, lv.SYMBOL.IMAGE + "  Shoot", lambda: shoot(), w=rw, h=72, font=ui.big, color=ui.ACCENT)
    shutter.set_pos(rx, top)
    bw = (rw - 16) // 3
    light_b, light_l = ui.button(root, "", lambda: cycle_light(), w=bw, h=52, font=ui.small)
    light_b.set_pos(rx, top + 84)
    flip_b, _ = ui.button(root, "Flip", lambda: toggle("flip"), w=bw, h=52, font=ui.small)
    flip_b.set_pos(rx + bw + 8, top + 84)
    mirror_b, _ = ui.button(root, "Mirror", lambda: toggle("mirror"), w=bw, h=52, font=ui.small)
    mirror_b.set_pos(rx + 2 * (bw + 8), top + 84)
    bright_l = ui.label(root, "", ui.small, ui.MUTED)
    bright_l.set_pos(rx, top + 146)
    slider = lv.slider(root)
    slider.set_range(0, 100)
    slider.set_size(rw - 16, 14)
    slider.set_pos(rx + 8, top + 172)
    slider.set_value(opts["bright"], False)
    thumb = lv.image(root)
    thumb.set_pos(rx + (rw - THUMB) // 2, top + 200)
    thumb.set_size(THUMB, THUMB)
    info = ui.label(root, "", ui.small, ui.MUTED)
    info.set_pos(rx, top + 200 + THUMB + 4)
    info.set_width(rw)

    sd = cam.mount_sd(readonly=False)
    scope.on_close(lambda: cam.unmount_sd(sd))

    def show_opts():
        light_l.set_text("Light: " + cam.LIGHT[opts["light"] % len(cam.LIGHT)][0])
        bright_l.set_text("Brightness %d%%" % opts["bright"])
        for b, key in ((flip_b, "flip"), (mirror_b, "mirror")):
            b.set_style_bg_color(ui.ACCENT if opts[key] else ui.PANEL, 0)

    def apply():
        if st["cam"] is not None:
            cam.apply_controls(st["cam"], opts)
        show_opts()

    def cycle_light():
        opts["light"] = (opts["light"] + 1) % len(cam.LIGHT)
        apply()

    def toggle(key):
        # Flip or mirror: open the camera again, turned, so the colours follow.
        opts[key] = not opts[key]
        old = st["cam"]
        st["cam"] = None
        if old is not None:
            old.deinit()
        try:
            st["cam"] = cam.open_camera(opts)
        except Exception as e:
            status.set_text("camera: %s" % (e,))
            return
        apply()

    def bright_moved(e):
        opts["bright"] = slider.get_value()
        apply()

    slider.add_event_cb(bright_moved, lv.EVENT.RELEASED, None)
    slider.add_event_cb(
        lambda e: bright_l.set_text("Brightness %d%%" % slider.get_value()), lv.EVENT.VALUE_CHANGED, None
    )
    apply()
    from board_config import display_drv as d

    fb = d.framebuffers()[0]
    ax, ay = RX + x0, RY + y0  # on the panel

    def preview():
        c = st["cam"]
        if c is None:
            return
        if c.capture_scaled(fb, d.width, d.height, x=ax, y=ay, w=pw, h=ph, timeout=200) is not None:
            d.flush_rect(ax, ay, pw, ph)

    def shoot():
        c = st["cam"]
        img = c.capture_jpeg(QUALITY) if c is not None else None
        if not img:
            status.set_text("no frame")
            return
        try:
            path = cam.next_name(scope)
        except OSError as e:
            status.set_text("nowhere to save: %s" % (e,))
            return
        if not _save(path, img):
            status.set_text("couldn't save the photo")
            return
        st["shots"] += 1
        st["last"] = path
        px, tw, th = ui.decode_jpeg(img, THUMB)
        ui.rgb565_image(thumb, px, tw, th, keep)
        status.set_text("saved %s (%d KB)" % (path.rsplit("/", 1)[1], len(img) // 1024))

    # -- the web page: every shot, newest first ----------------------------------

    def start_server():
        import socket
        import _thread

        def serve():
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", PORT))
            s.listen(2)
            s.settimeout(0.5)
            st["server"] = s
            while st["open"]:
                try:
                    c, _ = s.accept()
                except OSError:
                    continue
                try:
                    c.settimeout(5)
                    _reply(c)
                except Exception as e:
                    print("camera web:", e)
                finally:
                    c.close()
            s.close()

        _thread.stack_size(16 * 1024)
        try:
            _thread.start_new_thread(serve, ())
        finally:
            _thread.stack_size(0)

    def _reply(c):
        line = c.readline()
        while c.readline() not in (b"\r\n", b"\n", b""):
            pass
        parts = line.split()
        path = parts[1].decode() if len(parts) > 1 else "/"
        if parts and parts[0] == b"POST" and path.startswith("/delete/"):
            # One photo, or "all" of them.
            key = path[8:]
            for k, p in cam.photos(scope):
                if key == "all" or k == key:
                    try:
                        os.remove(p)
                    except OSError as e:
                        print("camera web: delete %s: %s" % (p, e))
            c.write(b"HTTP/1.0 303 See Other\r\nLocation: /\r\n\r\n")
            return
        if path.startswith("/photo/"):
            key = path[7:]
            for k, p in cam.photos(scope):
                if k == key:
                    c.write(b"HTTP/1.0 200 OK\r\nContent-Type: image/jpeg\r\n\r\n")
                    with open(p, "rb") as f:
                        buf = bytearray(16384)
                        while True:
                            n = f.readinto(buf)
                            if not n:
                                break
                            c.write(buf[:n])
                    return
            c.write(b"HTTP/1.0 404 Not Found\r\n\r\n")
            return
        photos = cam.photos(scope)
        rows = "".join(
            '<div><a href="/photo/{0}"><img src="/photo/{0}" loading="lazy"></a><br>{1}{2}</div>'.format(
                k,
                k.replace("/", ": "),
                ' <form method=post action="/delete/{0}" onsubmit="return confirm(\'Delete {0}?\')">'
                "<button>Delete</button></form>".format(k),
            )
            for k, p in photos
        )
        if photos:
            rows = (
                '<form method=post action="/delete/all" onsubmit="return confirm(\'Delete every photo?\')">'
                "<button class=all>Delete all</button></form>"
            ) + rows
        html = (
            "<!doctype html><meta name=viewport content='width=device-width'>"
            "<title>Camera</title><style>body{font-family:sans-serif;background:#0b0e14;color:#ccc}"
            "div{display:inline-block;margin:6px;font-size:13px;vertical-align:top}"
            "img{width:220px;border-radius:8px}form{display:inline}"
            "button{background:#3a2028;color:#f9b;border:1px solid #634;border-radius:6px;padding:2px 8px;cursor:pointer}"
            "button.all{margin:0 6px 10px;padding:6px 12px}</style><h2>Camera</h2>"
            + (rows or "<p>No photos yet: press Shoot on the board.</p>")
        )
        c.write(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n")
        c.write(html.encode())

    ip = net.ip()
    name = net.hostname()
    if ip:
        info.set_text(
            "Photos go to the board's flash.\nOpen %shttp://%s:%d to see them."
            % ("http://%s.local:%d or " % (name, PORT) if name else "", ip, PORT)
        )
        try:
            start_server()
        except Exception as e:
            print("camera: web page:", e)
    else:
        info.set_text("Photos go to the board's flash.\nNo Wi-Fi: no web page.")

    def close():
        st["open"] = False  # the web page's thread ends within half a second
        c = st["cam"]
        st["cam"] = None
        if c is not None:
            c.deinit()

    scope.on_close(close)
    status.set_text("%s ready" % (c0.sensor()[0],) if hasattr(c0, "sensor") else "ready")
    c0 = None
    scope.foreground(preview)
