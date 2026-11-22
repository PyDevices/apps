# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The picker: one screen to choose every connection the device has.

It opens over the running app, on ``lv.layer_top()``, so an app keeps
playing while you move its audio. The first page lists each kind the device
has providers for (audio out, MIDI in, the network, a camera, ...) with what
is chosen now; tap one to see its endpoints and choose. A kind that takes one
endpoint at a time moves the choice to what you tap; one that takes many
adds or drops it. The Shell makes one::

    shell.open_picker()             # the list of kinds
    shell.open_picker("audio.out")  # straight to one kind

Choices are endpointkit's, for the whole device, so a script or another app
sees them at once. While the picker is open it polls endpointkit, so what you
plug in, pair or discover shows up as it's found. A choice that would stop
something sharing its hardware asks first. A kind an app has pinned says so:
the device's choice is kept for when the app lets go.

Everything is in an LVGL focus group too, so an encoder or a gamepad can work
it (``Picker.group``). The functions above the class (`kinds`, `summary`,
`rows`, `toggle`) are the picker without the screen, for a script.
"""

import endpointkit
import lvgl as lv
import iconkit
from iconkit import lvicons

# The icons iconkit draws at the picker's size.
_ICONS = set(iconkit.names(24))

#: The icon a kind gets when iconkit hasn't the one endpointkit names.
OTHER_ICON = "cable"

#: How often, in milliseconds, the open picker asks endpointkit for news.
POLL_MS = 250

_STATES = {
    endpointkit.AVAILABLE: "",
    endpointkit.CONNECTED: "Connected",
    endpointkit.NEEDS_PAIRING: "Needs pairing",
    endpointkit.UNAVAILABLE: "Unavailable",
}


def title(kind):
    """What the picker calls *kind*: endpointkit's title, "Audio out" for ``audio.out``."""
    return endpointkit.title(kind)


def icon(kind):
    """The iconkit name of *kind*'s icon: endpointkit's, or `OTHER_ICON`
    when iconkit hasn't that one."""
    name = endpointkit.icon(kind)
    return name if name in _ICONS else OTHER_ICON


def kinds(registry):
    """The kinds *registry* has providers for, in the order endpointkit knows them."""
    have = [p.kind for p in registry.providers()]
    return [k for k in endpointkit.kinds() if k in have]


def summary(registry, kind):
    """One line on what *kind* uses now: a label, "2 chosen", "Nothing chosen",
    and whose pin it is when an app has pinned it."""
    ids = registry.selection(kind)
    if not ids:
        text = "Nothing chosen"
    elif len(ids) == 1:
        ep = registry.find(ids[0])
        text = ep.label if ep is not None else "Waiting for it"
    else:
        text = "%d chosen" % len(ids)
    pin = registry.pinned(kind)
    if pin is not None:
        text = "%s (pinned by %s)" % (text, pin[0])
    return text


def rows(registry, kind):
    """The endpoints of *kind*, as ``(endpoint, chosen, detail)``.

    *chosen* is True for the device's choice (not a pin's), and *detail* is
    the state worth saying ("Connected", "Needs pairing") with the provider's
    last error after it. A chosen endpoint that isn't found yet is left out:
    `summary` says "Waiting for it".
    """
    chosen = registry.chosen(kind)
    out = []
    for ep in registry.endpoints(kind):
        detail = _STATES.get(ep.state, ep.state)
        if ep.error:
            detail = ("%s: %s" % (detail, ep.error)) if detail else ep.error
        out.append((ep, ep.id in chosen, detail))
    return out


def toggle(registry, kind, endpoint_id, confirm=False):
    """What tapping *endpoint_id* does: the new choice for *kind*, made.

    A `ONE` kind moves its choice there (tapping the chosen one keeps it); a
    `MANY` kind adds it or drops it. Returns the ids now chosen.

    Raises:
        endpointkit.Conflict: as `Registry.select` does, with nothing changed.
    """
    ids = registry.chosen(kind)
    if endpointkit.KINDS[kind] == endpointkit.ONE:
        ids = [endpoint_id]
    elif endpoint_id in ids:
        ids = [i for i in ids if i != endpoint_id]
    else:
        ids = ids + [endpoint_id]
    registry.select(kind, ids, confirm=confirm)
    return registry.chosen(kind)


class Picker:
    """The picker overlay: made hidden, shown by `open`.

    Args:
        registry (endpointkit.Registry): whose choices it shows; the
            device's (endpointkit's own) when None.
        parent: the LVGL object it covers; ``lv.layer_top()`` when None.
        poll_ms (int): how often the open picker polls the registry, or 0
            to leave polling to someone else.
    """

    def __init__(self, registry=None, parent=None, poll_ms=POLL_MS):
        self.registry = registry if registry is not None else endpointkit.registry
        self.kind = None   # the kind on show, or None for the list of kinds
        self.group = lv.group_create()
        self.asking = None   # the conflict message box, while it's open
        self._dirty = False
        self._timer = None
        self._listening = None   # the callback subscribed, while open
        self._poll_ms = poll_ms

        root = lv.obj(parent if parent is not None else lv.layer_top())
        root.set_size(lv.pct(100), lv.pct(100))
        root.set_style_radius(0, 0)
        root.set_style_pad_all(0, 0)
        root.set_style_border_width(0, 0)
        root.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        root.add_flag(lv.obj.FLAG.HIDDEN)
        self.root = root

        bar = lv.obj(root)
        bar.set_size(lv.pct(100), lv.SIZE_CONTENT)
        bar.set_style_pad_all(4, 0)
        bar.set_style_radius(0, 0)
        bar.set_style_border_width(0, 0)
        bar.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.back = lv.button(bar)
        lvicons.image(self.back, "arrow_back", 24).center()
        self.back.set_size(48, 40)
        self.back.align(lv.ALIGN.LEFT_MID, 0, 0)
        self.back.add_event_cb(lambda e: self.show(None), lv.EVENT.CLICKED, None)
        self.heading = lv.label(bar)
        self.heading.align(lv.ALIGN.CENTER, 0, 0)
        self.scan = lv.button(bar)
        lvicons.image(self.scan, "refresh", 24).center()
        self.scan.set_size(48, 40)
        self.scan.align(lv.ALIGN.RIGHT_MID, -56, 0)
        self.scan.add_event_cb(lambda e: self._rescan(), lv.EVENT.CLICKED, None)
        self.close_button = lv.button(bar)
        lvicons.image(self.close_button, "close", 24).center()
        self.close_button.set_size(48, 40)
        self.close_button.align(lv.ALIGN.RIGHT_MID, 0, 0)
        self.close_button.add_event_cb(lambda e: self.close(), lv.EVENT.CLICKED, None)

        self.note = lv.label(root)
        self.note.set_width(lv.pct(100))
        self.note.set_style_pad_hor(8, 0)
        self.note.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.list = lv.list(root)
        self.list.set_width(lv.pct(100))
        self.list.set_flex_grow(1)
        self.list.set_style_radius(0, 0)
        self.list.set_style_border_width(0, 0)

    # -- opening and closing ----------------------------------------------------

    def is_open(self):
        return not self.root.has_flag(lv.obj.FLAG.HIDDEN)

    def open(self, kind=None):
        """Show the picker over everything, at *kind*'s page or the list of kinds."""
        if self._listening is None:
            # Kept: endpointkit unsubscribes by identity, and each
            # self._changed is a new bound method.
            self._listening = self.registry.subscribe(None, self._changed)
        if self._poll_ms and self._timer is None:
            self._timer = lv.timer_create(lambda t: self.tick(), self._poll_ms, None)
        self.root.remove_flag(lv.obj.FLAG.HIDDEN)
        self.root.move_foreground()
        self.show(kind)

    def close(self):
        """Hide it; the choices made stay made."""
        self._dismiss()
        if self._listening is not None:
            self.registry.unsubscribe(self._listening)
            self._listening = None
        if self._timer is not None:
            self._timer.delete()
            self._timer = None
        self.root.add_flag(lv.obj.FLAG.HIDDEN)

    def tick(self):
        """Poll the registry and redraw what changed; the open picker's timer calls it."""
        self.registry.poll()
        if self._dirty and self.asking is None:
            self.show(self.kind)

    def _changed(self, event, kind):
        if self.kind is None or kind == self.kind:
            self._dirty = True

    # -- the pages --------------------------------------------------------------

    def show(self, kind):
        """Draw the list of kinds (*kind* None) or one kind's endpoints."""
        self._dirty = False
        self.kind = kind
        self.list.clean()
        self.group.remove_all_objs()
        if kind is None:
            self.heading.set_text("Connections")
            self.back.add_flag(lv.obj.FLAG.HIDDEN)
            self.scan.add_flag(lv.obj.FLAG.HIDDEN)
            self.note.add_flag(lv.obj.FLAG.HIDDEN)
            found = kinds(self.registry)
            for k in found:
                self._row(icon(k), title(k), summary(self.registry, k), lambda e, k=k: self.show(k))
            if not found:
                self.list.add_text("Nothing to connect to here.")
        else:
            self.heading.set_text(title(kind))
            self.back.remove_flag(lv.obj.FLAG.HIDDEN)
            self.scan.remove_flag(lv.obj.FLAG.HIDDEN)
            pin = self.registry.pinned(kind)
            if pin is not None:
                self.note.set_text("%s is using its own choice while it runs. Yours is kept for after." % pin[0])
                self.note.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                self.note.add_flag(lv.obj.FLAG.HIDDEN)
            found = rows(self.registry, kind)
            for ep, chosen, detail in found:
                self._row("check" if chosen else None, ep.label, detail,
                          lambda e, i=ep.id: self.choose(i))
            if not found:
                self.list.add_text("Nothing found yet.")
        self.group.add_obj(self.close_button)
        if kind is not None:
            self.group.add_obj(self.back)
            self.group.add_obj(self.scan)

    def _row(self, icon_name, text, detail, on_click):
        b = self.list.add_button(None, None)
        b.set_style_pad_ver(6, 0)
        b.set_flex_flow(lv.FLEX_FLOW.ROW)
        b.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        slot = lv.obj(b)
        slot.set_size(24, 24)
        slot.set_style_bg_opa(lv.OPA.TRANSP, 0)
        slot.set_style_border_width(0, 0)
        slot.set_style_pad_all(0, 0)
        slot.remove_flag(lv.obj.FLAG.CLICKABLE)
        if icon_name:
            # The row's own text colour: the white default vanishes on a light theme.
            lvicons.image(slot, icon_name, 24, b.get_style_text_color(0)).center()
        words = lv.obj(b)
        words.set_flex_grow(1)
        words.set_height(lv.SIZE_CONTENT)
        words.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        words.set_style_bg_opa(lv.OPA.TRANSP, 0)
        words.set_style_border_width(0, 0)
        words.set_style_pad_all(0, 0)
        words.remove_flag(lv.obj.FLAG.CLICKABLE)
        words.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        name = lv.label(words)
        name.set_text(text)
        if detail:
            small = lv.label(words)
            small.set_text(detail)
            small.set_style_text_opa(lv.OPA._70, 0)
        b.add_event_cb(on_click, lv.EVENT.CLICKED, None)
        self.group.add_obj(b)
        return b

    # -- choosing ---------------------------------------------------------------

    def choose(self, endpoint_id, confirm=False):
        """Tap *endpoint_id* on the kind on show; a conflict opens a question first."""
        kind = self.kind
        try:
            toggle(self.registry, kind, endpoint_id, confirm=confirm)
        except endpointkit.Conflict as c:
            self._ask(c, endpoint_id)
            return
        self.show(kind)

    def _ask(self, conflict, endpoint_id):
        self._dismiss()
        box = lv.msgbox(self.root)
        box.add_flag(lv.obj.FLAG.IGNORE_LAYOUT)   # over the page, not in its column
        box.center()
        ep = self.registry.find(endpoint_id)
        box.add_title("Stop %s?" % ", ".join(e.label for e in conflict.stops))
        box.add_text("%s uses the same hardware (%s)." % (
            ep.label if ep is not None else endpoint_id, ", ".join(conflict.resources)))
        go = box.add_footer_button("Stop it")
        no = box.add_footer_button("Cancel")
        go.add_event_cb(lambda e: self._answer(endpoint_id, True), lv.EVENT.CLICKED, None)
        no.add_event_cb(lambda e: self._answer(endpoint_id, False), lv.EVENT.CLICKED, None)
        self.asking = box
        self.group.add_obj(go)
        self.group.add_obj(no)
        lv.group_focus_obj(no)

    def _answer(self, endpoint_id, go):
        self._dismiss()
        if go:
            self.choose(endpoint_id, confirm=True)
        else:
            self.show(self.kind)

    def _dismiss(self):
        if self.asking is not None:
            self.asking.delete()
            self.asking = None

    def _rescan(self):
        if self.kind is not None:
            self.registry.refresh(self.kind)
        self.show(self.kind)
