# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Security cam: the CSI camera streamed as MJPEG, with a preview on the panel.

Open the address on the screen in VLC (Media > Open Network Stream) or any
browser: MJPEG is one HTTP response carrying JPEG after JPEG, which every
player and browser understands. The P4's encoder makes each JPEG; the
network is what limits the frame rate, so ``?q=`` on the address sets the
quality (default ``QUALITY``): lower is smaller and faster.

The camera has one user. The foreground loop takes a preview frame for the
panel and, while anyone is watching, a JPEG for the stream; a server thread
hands each viewer the newest JPEG. Every thread ends when the app closes: a
live thread's stack sits in internal RAM, and a few left behind split it
too small for the video encoder. Flip, mirror, light and brightness are
the Camera app's.

Without a camera the app says so, and Home goes back as usual.
"""

import errno

import lvgl as lv
from multimer import ticks_add, ticks_diff, ticks_ms

from devkit import cam, net, ui
from devkit.clock import sleep_ms

PORT = 8081
QUALITY = 50
PREVIEW = 400
BOUNDARY = "devkitframe"
FRAME_SECONDS = 4  # a viewer that can't take a whole frame in this long is dropped

state = None  # the open app's state, for the console


def main(scope):
    global state
    root = scope.root
    W, H = scope.size
    RX, RY = scope.rect[:2]
    status = ui.status(scope)

    opts = cam.options(scope)
    try:
        c0 = cam.open_camera(opts)
    except Exception as e:
        ui.missing(scope, "no camera", cam.no_camera_text(e, "Security cam"))
        return
    try:
        import _thread
        import socket
    except ImportError as e:
        c0.deinit()
        ui.missing(scope, "missing: %s" % (e,), "Security cam serves its stream from a thread: %s." % (e,))
        return
    st = state = {
        "cam": None, "open": True, "jpeg": None, "seq": 0, "viewers": 0, "conns": [],
        "sent": 0, "dropped": 0, "t0": ticks_ms(), "q": QUALITY, "lock": _thread.allocate_lock(),
    }  # fmt: skip

    cam.apply_controls(c0, opts)
    st["cam"] = c0
    from board_config import display_drv as d

    fb = d.framebuffers()[0]
    cw, chh = c0.size()[:2]
    pw, ph = cam.preview_size(c0, PREVIEW)
    x0, y0 = 24, 8 + (PREVIEW - ph) // 2
    ax, ay = RX + x0, RY + y0
    ui.frame(root, x0, y0, pw, ph)

    rx = 24 + PREVIEW + 24
    rw = W - rx - 24
    title = ui.label(root, lv.SYMBOL.EYE_OPEN + "  Watching", ui.big, ui.ACCENT)
    title.set_pos(rx, 12)
    where = ui.label(root, "", ui.font, ui.WHITE)
    where.set_pos(rx, 64)
    where.set_width(rw)
    live = ui.label(root, "", ui.small, ui.MUTED)
    live.set_pos(rx, 210)
    live.set_width(rw)

    ip = net.ip()
    name = net.hostname()
    if ip:
        where.set_text(
            "In VLC or a browser:\n%shttp://%s:%d" % ("http://%s.local:%d\n" % (name, PORT) if name else "", ip, PORT)
        )
    else:
        where.set_text("No Wi-Fi: nothing to stream to.")

    # -- the stream ---------------------------------------------------------------

    def send_all(c, data):
        # A slow viewer keeps a trickle moving, so the socket's own timeout
        # never fires; give each send a deadline, and stop as soon as the
        # app closes.
        view = memoryview(data)
        end = ticks_add(ticks_ms(), FRAME_SECONDS * 1000)
        while view:
            if not st["open"] or ticks_diff(end, ticks_ms()) < 0:
                raise OSError("too slow" if st["open"] else "closing")
            try:
                n = c.send(view)  # waits at most a second (the viewer's timeout)
            except OSError as e:
                if e.args and e.args[0] in (errno.ETIMEDOUT, errno.EAGAIN):
                    continue
                raise
            if n <= 0:
                raise OSError("closed")
            view = view[n:]

    alive = scope.store()  # threads still running, counted across opens
    alive.setdefault("server", 0)
    alive.setdefault("viewer", 0)

    def viewer(c, q):
        st["viewers"] += 1
        alive["viewer"] += 1
        c.settimeout(1)
        try:
            send_all(
                c,
                b"HTTP/1.0 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary="
                + BOUNDARY.encode()
                + b"\r\nCache-Control: no-store\r\n\r\n",
            )
            seen = -1
            while st["open"]:
                if st["seq"] == seen:
                    sleep_ms(10)
                    continue
                with st["lock"]:
                    img, seen = st["jpeg"], st["seq"]
                if img is None:
                    continue
                send_all(
                    c, ("--%s\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % (BOUNDARY, len(img))).encode()
                )
                send_all(c, img)
                send_all(c, b"\r\n")
                st["sent"] += 1
                st["taken"] = seen
        except OSError as e:
            if e.args and e.args[0] == "too slow":
                st["dropped"] += 1
                print("security cam: dropped a viewer that couldn't keep up")
        finally:
            st["viewers"] -= 1
            alive["viewer"] -= 1
            try:
                st["conns"].remove(c)
            except ValueError:
                pass
            c.close()

    def serve():
        alive["server"] += 1
        try:
            _serve()
        finally:
            alive["server"] -= 1

    def _serve():
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", PORT))
        s.listen(2)
        s.settimeout(0.5)
        while st["open"]:
            try:
                c, _ = s.accept()
            except OSError:
                continue
            try:
                c.settimeout(10)
                req = c.recv(512)
                path = req.split(b" ")[1] if b" " in req else b"/"
                if b"q=" in path:
                    try:
                        st["q"] = min(95, max(10, int(path.split(b"q=")[1][:3])))
                    except ValueError:
                        pass
                if path.startswith(b"/favicon"):
                    c.close()
                    continue
                st["conns"].append(c)
                _thread.start_new_thread(viewer, (c, st["q"]))
            except Exception as e:
                print("security cam:", e)
                c.close()
        s.close()

    if ip:
        _thread.stack_size(16 * 1024)
        try:
            _thread.start_new_thread(serve, ())
        finally:
            _thread.stack_size(0)

    # -- the foreground loop: a preview frame, and a JPEG while anyone watches ----

    def loop():
        c = st["cam"]
        if c is None:
            return
        loops = st["loops"] = st.get("loops", 0) + 1
        watched = st["viewers"] > 0
        # Waiting for a camera frame holds the interpreter, so the sender only
        # runs between captures: with viewers, refresh the panel one loop in
        # four, make a JPEG only once the last one has gone, and yield.
        if not watched or loops % 4 == 0:
            if c.capture_scaled(fb, d.width, d.height, x=ax, y=ay, w=pw, h=ph, timeout=200) is not None:
                d.flush_rect(ax, ay, pw, ph)
        if watched and st.get("taken", -1) == st["seq"] or watched and st["jpeg"] is None:
            img = c.capture_jpeg(st["q"])
            if img:
                with st["lock"]:
                    st["jpeg"] = img
                    st["seq"] += 1
        sleep_ms(2)

    def tick(t=None):
        dt = ticks_diff(ticks_ms(), st["t0"]) or 1
        n = st["viewers"]
        img = st["jpeg"]
        live.set_text(
            "%d watching%s"
            % (
                n,
                ""
                if not n
                else ", %.1f fps, %d KB a frame, quality %d"
                % (st["sent"] * 1000 / dt, len(img) // 1024 if img else 0, st["q"]),
            )
        )
        st["loops"] = 0
        st["sent"] = 0
        st["t0"] = ticks_ms()

    def close():
        st["open"] = False
        c = st["cam"]
        st["cam"] = None
        if c is not None:
            c.deinit()

    scope.on_close(close)
    scope.every(2000, tick)
    tick()
    status.set_text("%dx%d" % (cw, chh))
    c0 = None
    scope.foreground(loop)
