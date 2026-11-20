# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Boxes and arrows for a small modulation graph: who shapes whom, and who is heard.

The graph is data. *nodes* are names, in the order to draw them. *edges*
are ``(source, target)`` pairs: the source modulates the target. *carriers*
are the nodes that are heard: they sit on the bottom row and join one output
line. Everything else stacks above what it modulates. *feedback* is one more
``(source, target)`` pair, drawn as a loop round the side in its own colour;
a node that feeds itself is ``(name, name)``.

- ``set_graph(nodes, edges, carriers, feedback)`` draws another graph;
- ``set_selected(name)`` lights the node being edited, and ``None`` lights none;
- ``set_color(name, rgb)`` lights a node in any colour, and ``None`` puts it out;
- a tap on a node calls ``on_press(diagram, name)``.

``arrange()`` is the layout on its own: a column and a row for each node.
"""

import lvgl as lv

from ._draw import box, fill, label, plain, polyline
from ._safe import safe

#: The widest and tallest a node's box grows, however much room there is.
_BOX_W = 84
_BOX_H = 46


def arrange(nodes, edges, carriers):
    """Where each node goes: ``{name: (column, row)}``, row 0 at the bottom.

    Carriers take row 0 and every other node the row above its highest
    target. Columns may fall between whole numbers: a node with several
    modulators sits under the middle of them, and a node that modulates
    several sits over the middle of them when there is room.

    Raises:
        ValueError: An edge names a node that isn't in *nodes*, or the edges
            loop. A loop's closing edge belongs in ``feedback``.
    """
    nodes = list(nodes)
    known = set(nodes)
    targets = {name: [] for name in nodes}
    sources = {name: [] for name in nodes}
    for source, target in edges:
        if source not in known or target not in known:
            raise ValueError("edge %r -> %r names a node that isn't in the graph" % (source, target))
        targets[source].append(target)
        sources[target].append(source)
    for name in carriers:
        if name not in known:
            raise ValueError("carrier %r isn't in the graph" % (name,))

    rows = {}
    walking = set()

    def row_of(name):
        if name in rows:
            return rows[name]
        if name in walking:
            raise ValueError("the edges loop through %r: give the closing edge as feedback" % (name,))
        walking.add(name)
        row = 0
        if name not in carriers:
            for target in targets[name]:
                row = max(row, row_of(target) + 1)
        walking.discard(name)
        rows[name] = row
        return row

    for name in nodes:
        row_of(name)

    # Each modulator belongs to the first target one row below it, and is
    # laid out as part of that target's stack.
    owner = {}
    for name in nodes:
        for target in targets[name]:
            if rows[target] == rows[name] - 1:
                owner[name] = target
                break
    columns = {}
    free = [0]

    def place(name):
        mine = [source for source in sources[name] if owner.get(source) == name]
        for source in mine:
            place(source)
        if mine:
            columns[name] = sum(columns[source] for source in mine) / len(mine)
        else:
            columns[name] = float(free[0])
            free[0] += 1

    for name in nodes:
        if rows[name] == 0:
            place(name)
    for name in nodes:
        if name not in columns:
            place(name)

    def stack(name):
        found = [name]
        for source in sources[name]:
            if owner.get(source) == name:
                found.extend(stack(source))
        return found

    # A node with several targets moves over the middle of them, taking its
    # own stack along, unless that would crowd a neighbour.
    for name in sorted(nodes, key=lambda n: rows[n]):
        below = [target for target in targets[name] if rows[target] < rows[name]]
        if len(below) < 2:
            continue
        shift = sum(columns[target] for target in below) / len(below) - columns[name]
        moving = stack(name)
        clear = True
        for mover in moving:
            for other in nodes:
                if other not in moving and rows[other] == rows[mover] \
                        and abs(columns[other] - columns[mover] - shift) < 0.999:
                    clear = False
        if clear:
            for mover in moving:
                columns[mover] += shift

    left = min(columns.values()) if columns else 0.0
    return {name: (columns[name] - left, rows[name]) for name in nodes}


class RoutingDiagram:
    """A diagram of a modulation graph at (*x*, *y*) in *parent*, *width* x *height*.

    *nodes*, *edges*, *carriers* and *feedback* are the graph, as the
    module's docstring describes. *on_press*, when given, is called as
    ``on_press(diagram, name)`` for a tap on a node.
    """

    def __init__(self, parent, x, y, width, height, theme, nodes=(), edges=(), carriers=(), feedback=None,
                 on_press=None):
        self.theme = theme
        self.on_press = on_press
        self.width = width
        self.height = height
        cell = plain(lv.obj(parent))
        cell.set_pos(x, y)
        cell.set_size(width, height)
        self.obj = cell
        self.nodes = []
        # LVGL holds this callback, and so the diagram and its lines' points,
        # for as long as the object lives, even if the host keeps neither.
        cell.add_event_cb(safe(self._on_delete), lv.EVENT.DELETE, None)
        self.set_graph(nodes, edges, carriers, feedback)

    # ---- what the host calls -------------------------------------------------

    def set_graph(self, nodes, edges, carriers, feedback=None):
        """Draw this graph in place of the one shown. The selection and the colours start again."""
        nodes = list(nodes)
        edges = [tuple(edge) for edge in edges]
        carriers = list(carriers)
        if feedback is not None:
            feedback = tuple(feedback)
            if feedback[0] not in nodes or feedback[1] not in nodes:
                raise ValueError("feedback %r -> %r names a node that isn't in the graph" % feedback)
        places = arrange(nodes, edges, carriers)
        self.nodes = nodes
        self.edges = edges
        self.carriers = carriers
        self.feedback = feedback
        self.places = places
        self.selected = None
        self.colors = {name: None for name in nodes}
        self._boxes = {}
        self._kept = []
        self.obj.clean()
        if nodes:
            self._build()

    def set_selected(self, name):
        """Light node *name* as the one being edited, or none with None."""
        if name is not None and name not in self._boxes:
            raise KeyError(name)
        if name == self.selected:
            return
        before = self.selected
        self.selected = name
        for changed in (before, name):
            if changed is not None:
                self._paint(changed)

    def set_color(self, name, rgb):
        """Light node *name* in *rgb*, or put it out with None."""
        if name not in self._boxes:
            raise KeyError(name)
        if self.colors[name] == rgb:
            return
        self.colors[name] = rgb
        self._paint(name)

    def node(self, name):
        """Node *name*'s LVGL object."""
        return self._boxes[name][0]

    # ---- drawing -------------------------------------------------------------

    def _build(self):
        theme = self.theme
        places = self.places
        span = max(column for column, _ in places.values())
        top_row = max(row for _, row in places.values())
        loop = self.feedback is not None
        # Room on the bottom for the output line, and round the top and the
        # sides for a feedback loop.
        out = max(6, min(18, self.height // 10))
        margin = max(3, min(9, self.width // 36)) if loop else 1
        room_w = self.width - 2 * margin
        room_h = self.height - margin - out
        box_w = int(max(8, min(_BOX_W, room_w / (span + 1) * 0.68)))
        box_h = int(max(8, min(_BOX_H, room_h / (top_row + 1) * 0.62)))
        pitch_x = min(room_w / (span + 1), box_w * 1.9)
        pitch_y = min(room_h / (top_row + 1), box_h * 1.8)
        gap = pitch_y - box_h
        left = margin + (room_w - (span * pitch_x + box_w)) / 2
        base = margin + (room_h - (top_row * pitch_y + box_h)) / 2 + top_row * pitch_y
        self._box_w = box_w
        self._box_h = box_h
        thick = 2 if box_h >= 16 else 1
        self._thick = thick
        head = 3 if gap >= 9 else (2 if gap >= 6 else 0)

        def middle(name):
            column, row = places[name]
            return int(left + column * pitch_x + box_w / 2 + 0.5), int(base - row * pitch_y + 0.5)

        self._where = {name: middle(name) for name in self.nodes}
        wire = theme["legend_dim"]

        # The modulation lines: down from each source, across in the gap
        # above its target, and into the target's top.
        fed = set()
        for source, target in self.edges:
            sx, sy = self._where[source]
            tx, ty = self._where[target]
            if sy >= ty:
                continue
            bend = ty - int(gap / 2 + 0.5)
            if sx == tx:
                self._wire([(sx, sy + box_h), (tx, ty)], wire)
            else:
                self._wire([(sx, sy + box_h), (sx, bend), (tx, bend), (tx, ty)], wire)
            fed.add(target)
        for target in fed:
            tx, ty = self._where[target]
            self._arrow(tx, ty, head, wire)

        # The output: every carrier drops to one line, which leaves downward.
        heard = [name for name in self.nodes if name in self.carriers]
        if heard:
            bus = int(base + box_h + out * 0.45 + 0.5)
            path = []
            for name in heard:
                cx, cy = self._where[name]
                path.extend([(cx, bus), (cx, cy + box_h), (cx, bus)])
            self._wire(path, theme["legend"])
            mid = (path[0][0] + path[-1][0]) // 2
            end = int(base + box_h + out - 1)
            self._wire([(mid, bus), (mid, end)], theme["legend"])
            self._arrow(mid, end, 2 if out < 10 else 3, theme["legend"])

        if loop:
            source, target = self.feedback
            sx, sy = self._where[source]
            tx, ty = self._where[target]
            side = max(sx, tx) + box_w // 2 + margin - thick + 1
            over = ty - max(2, min(margin - 1, int(gap / 3)))
            entry = tx + box_w // 4
            colour = theme["legend_lit"]
            self._wire([(sx + box_w // 2, sy + box_h // 2), (side, sy + box_h // 2), (side, over), (entry, over),
                        (entry, ty)], colour)
            self._arrow(entry, ty, min(head, 2), colour)

        font_h = lv.font_montserrat_14.get_line_height()
        for name in self.nodes:
            cx, cy = self._where[name]
            pad = box(self.obj, cx - box_w // 2, cy, box_w, box_h)
            pad.set_style_radius(3, 0)
            text = None
            if box_h >= font_h - 4:
                text = label(pad, str(name), theme["pad_text"], None, 0)
                text.center()
            if self.on_press is not None:
                pad.add_flag(lv.obj.FLAG.CLICKABLE)
                pad.add_event_cb(safe(self._handler(name)), lv.EVENT.CLICKED, None)
            self._boxes[name] = (pad, text)
            self._paint(name)

    def _on_delete(self, _event):
        self._kept = []

    def _wire(self, path, rgb):
        line, points = polyline(self.obj, path, rgb, self._thick)
        # The line points into this buffer, so it stays here while the line lives.
        self._kept.append(points)
        return line

    def _arrow(self, x, y, size, rgb):
        """An arrowhead pointing down, its tip at (*x*, *y*)."""
        if size:
            self._wire([(x - size, y - size - 1), (x, y - 1), (x + size, y - size - 1)], rgb)

    def _paint(self, name):
        theme = self.theme
        pad, text = self._boxes[name]
        rgb = self.colors[name]
        lit = name == self.selected
        if rgb is not None:
            fill(pad, rgb)
        elif lit:
            fill(pad, theme["pad_lit"], theme["pad_lit_bottom"])
        elif name in self.carriers:
            fill(pad, theme["pad_tint"])
        else:
            fill(pad, theme["pad"], theme["pad_bottom"])
        pad.set_style_border_width(2 if lit else 1, 0)
        pad.set_style_border_color(lv.color_hex(theme["pointer"] if lit else theme["pad_edge"]), 0)
        if text is not None:
            bright = lit or rgb is not None
            text.set_style_text_color(lv.color_hex(theme["pad_lit_text"] if bright else theme["pad_text"]), 0)

    def _handler(self, name):
        def handle(_event):
            if self.on_press is not None:
                self.on_press(self, name)

        return handle
