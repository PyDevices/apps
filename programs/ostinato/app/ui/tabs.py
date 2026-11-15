# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The row of tabs on a phone: which page (editor, tracks, inspector, keys) is shown."""

import lvgl as lv

import theme
from theme import px

TABS = (("editor", "Edit"), ("tracks", "Tracks"), ("inspector", "Sound"), ("keys", "Keys"))


class Tabs:
    def __init__(self, parent, rect, app):
        x, y, w, h = rect
        self.root = theme.panel(parent, rect)
        names = [t for t in TABS if t[0] in app.pages]
        gap = px(6)
        bw = (w - gap * (len(names) + 1)) // len(names)
        bh = max(h - 2 * gap, theme.T)
        self.buttons = []
        self.names = []
        for i, (name, word) in enumerate(names):
            b = theme.button(self.root, word, w=bw, h=bh, checkable=True)
            b.obj.set_pos(gap + i * (bw + gap), (h - bh) // 2)
            b.on(lv.EVENT.CLICKED, (lambda n: lambda: app.show_page(n))(name))
            self.buttons.append(b)
            self.names.append(name)

    def show(self, name):
        for n, b in zip(self.names, self.buttons):
            b.checked = n == name
