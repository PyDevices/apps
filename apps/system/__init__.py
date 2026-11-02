# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""System: the heap, the last switches, and what the apps left running.

The heap line is the one to watch: switching back and forth all day should
leave "in use" where it started, give or take a few KB. Wi-Fi setup puts
the phone setup page up until a network is joined.
"""

from touchkit import net, shell, ui


def main(scope):
    root = scope.root
    W, H = scope.size
    launcher = scope.launcher
    body = ui.label(root, "", ui.small, ui.WHITE)
    body.set_pos(16, 12)
    body.set_width(W - 32)
    st = {"block": None}

    def measure():
        st["block"] = launcher.heap()[1]
        tick()

    b, _ = ui.button(root, "Measure largest block", measure, w=300, h=52)
    b.set_pos(W - 316, H - 64)

    def wifi_setup():
        # The setup page blocks until a network is joined: never from a timer.
        if scope.foreground(job, steps=False):
            ui.status(scope).set_text("Wi-Fi setup: join the board's network from a phone")
        else:
            ui.status(scope).set_text("Wi-Fi setup waits for the foreground loop (appkit.serve())")

    def job():
        net.setup_job()
        scope.foreground(None)

    def cancel_setup():
        try:
            import wifi_manager

            wifi_manager.cancel()
        except Exception:
            pass

    scope.on_close(cancel_setup)
    w, _ = ui.button(root, "Wi-Fi setup", wifi_setup, w=220, h=52)
    w.set_pos(W - 552, H - 64)

    def tick(t=None):
        lines = [shell.heap_text()]
        if st["block"]:
            lines.append("largest free block %.1f MB" % (st["block"] / 1e6))
        base = launcher.baseline
        if base and base[0]:
            lines.append(
                "at start: free %.1f MB; restart below %.1f MB free" % (base[0] / 1e6, (launcher.min_free or 0) / 1e6)
            )
        lines.append(
            "restarts in a row before this boot: %d;  BOOT presses: %d" % (launcher.restarts, shell.boot_presses)
        )
        lines.append("")
        lines.append("last switches (app, how, ms, free MB after the close):")
        for name, how, ms, free in getattr(launcher, "history", ())[-8:]:
            lines.append(
                "   %-12s %-7s %5s ms   %s"
                % (name, how, ms if ms is not None else "-", "%.2f" % (free / 1e6) if free else "-")
            )
        if launcher.problems:
            lines.append("last close reported: " + "; ".join(launcher.problems[:2]))
        a = shell.audit()
        lines.append("")
        lines.append(
            "audio pump %s, I2S %s, USB host devices %s, SD %s"
            % (a.get("audiopump"), a.get("i2s"), a.get("host_devices"), a.get("sd") or "not mounted")
        )
        rssi = net.rssi()
        name = net.hostname()
        ip = net.ip()
        lines.append(
            "Wi-Fi: %s"
            % (
                "%s, RSSI %d dBm, WebREPL %s"
                % ((name + ".local") if name else net.ip(), rssi, "on" if net.webrepl_on() else "off")
                if rssi
                else ("this computer's network, %s" % ip if ip else "not connected")
            )
        )
        body.set_text("\n".join(lines))

    tick()
    scope.every(3000, tick)
