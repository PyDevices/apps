# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""LoRa: the radio's identity, a test packet, and listening for activity.

It needs a board with a ``lora`` role (an SX1262, as on the T-Watch S3). Set
``LORA_MHZ`` to a frequency your region allows before you send: 915 MHz
suits the Americas, Europe uses 868 and much of Asia 433. The radio has
power while the app is open, where the board can switch it.
"""

import sys

import lvgl as lv

from touchkit import ui

LORA_MHZ = 915.0
LORA_DBM = 10


def main(scope):
    board = sys.modules.get("board_config")
    if board is None or "lora" not in getattr(board, "PERIPHERALS", ()):
        ui.missing(scope, "No LoRa radio", "This board has no LoRa radio.")
        return
    peripherals = sys.modules.get("board_peripherals")
    release = getattr(peripherals, "release", None)
    if release is not None:
        scope.on_close(lambda: release("lora"))  # its power off again when you leave
    try:
        radio = board.lora
        radio.configure(LORA_MHZ, sf=9, power_dbm=LORA_DBM)
    except Exception as e:
        ui.missing(scope, "LoRa radio not answering", "The radio didn't answer: %r" % (e,))
        return
    root = scope.root
    root.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    root.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    root.set_style_pad_row(8, 0)
    root.remove_flag(lv.obj.FLAG.SCROLLABLE)
    text = ui.label(root, "%s\nat %.1f MHz" % (radio.version, LORA_MHZ), ui.small, ui.WHITE)
    text.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
    sent = [0]

    def send():
        sent[0] += 1
        try:
            ms = radio.send(b"PyDevices %d" % sent[0])
            text.set_text("%s\nsent #%d, %d ms on air\nat %.1f MHz" % (radio.version, sent[0], ms, LORA_MHZ))
        except Exception as e:
            text.set_text("send failed: %r" % (e,))

    def listen():
        try:
            busy = radio.channel_active()
            text.set_text("%s\nthe channel is %s\nat %.1f MHz" % (radio.version, "busy" if busy else "quiet", LORA_MHZ))
        except Exception as e:
            text.set_text("listening failed: %r" % (e,))

    ui.button(root, "Send", send, color=ui.PANEL)
    ui.button(root, "Listen", listen, color=ui.PANEL)
