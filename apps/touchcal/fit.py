# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Work out what a touch mapping gets wrong, from taps on targets at known places.

Each tap has the target's place on the screen, the point the board's
``touch_read`` gave (``raw``) and that point after the touch device's rotation
table (``mapped``), which is where LVGL saw the tap. `analyse` fits a straight
line per axis from each to the targets, so it can tell a mirrored axis,
swapped axes, a turn and a scale or offset error apart, and says which
``touch_rotation_table`` entry and which calibration would put every tap on
its target.

The mask bits are the touch devices' own: `SWAP_XY` first, then `REVERSE_X`
and `REVERSE_Y` across the display's width and height.
"""

SWAP_XY = 0b001
REVERSE_X = 0b010
REVERSE_Y = 0b100

#: A fitted scale this close to 1 is right.
SCALE_OK = 0.08

_WORDS = {
    0: "",
    REVERSE_X: "Left and right are swapped: a tap on one side lands on the other.",
    REVERSE_Y: "Top and bottom are swapped: a tap near the top lands near the bottom.",
    REVERSE_X | REVERSE_Y: "Touch is turned 180 degrees from the screen.",
    SWAP_XY: "Touch runs across the screen's diagonal: x and y are swapped.",
    SWAP_XY | REVERSE_X: "Touch is turned 90 degrees from the screen: x and y are swapped, and x is mirrored.",
    SWAP_XY | REVERSE_Y: "Touch is turned 90 degrees from the screen: x and y are swapped, and y is mirrored.",
    SWAP_XY | REVERSE_X | REVERSE_Y: "Touch runs across the screen's other diagonal: x and y are swapped, and both are mirrored.",
}


def mask_name(mask):
    """``mask`` as the touch devices' constant names, such as ``"SWAP_XY | REVERSE_X"``."""
    names = [n for bit, n in ((SWAP_XY, "SWAP_XY"), (REVERSE_X, "REVERSE_X"), (REVERSE_Y, "REVERSE_Y")) if mask & bit]
    return " | ".join(names) if names else "0"


def apply_mask(point, mask, width, height):
    """``point`` through ``mask`` as a touch device maps it, on a ``width`` x ``height`` display."""
    x, y = point[0], point[1]
    if mask & SWAP_XY:
        x, y = y, x
    if mask & REVERSE_X:
        x = width - x - 1
    if mask & REVERSE_Y:
        y = height - y - 1
    return (x, y)


def tolerance(width, height):
    """A fingertip's width on this screen, in pixels: 8% of the short side, at least 20.

    A tap this far from its target is on it, and a pattern (an offset, say)
    smaller than this is a finger's aim, not a mapping fault.
    """
    return max(20, min(width, height) * 8 // 100)


def _pattern_right(seen, width, height, tol):
    """Whether fit `seen` is the identity: no swap or mirror, the right scale, and no offset past ``tol``."""
    if seen is None or seen["mask"]:
        return False
    for axis, size in (("x", width), ("y", height)):
        a, b = seen[axis]
        mid = (size - 1) / 2
        if abs(a - 1) > SCALE_OK or abs((mid - b) / a - mid) > tol:
            return False
    return True


def _mean(values):
    return sum(values) / len(values)


def _line(src, dst):
    """``(a, b)`` for the least-squares line ``dst = a * src + b``, or None when ``src`` doesn't vary."""
    ms, md = _mean(src), _mean(dst)
    var = sum((s - ms) * (s - ms) for s in src)
    if var < 1e-9:
        return None
    a = sum((s - ms) * (d - md) for s, d in zip(src, dst)) / var
    return (a, md - a * ms)


def _corr(src, dst):
    ms, md = _mean(src), _mean(dst)
    vs = sum((s - ms) * (s - ms) for s in src)
    vd = sum((d - md) * (d - md) for d in dst)
    if vs < 1e-9 or vd < 1e-9:
        return 0.0
    return sum((s - ms) * (d - md) for s, d in zip(src, dst)) / (vs * vd) ** 0.5


def fit(points, targets):
    """Fit ``targets`` from ``points``, one axis at a time.

    Args:
        points (list): ``(x, y)`` as read.
        targets (list): ``(x, y)`` where each one should have been.

    Returns:
        dict: ``swap`` (target x follows the points' y), ``x`` and ``y``, each
        the ``(a, b)`` of ``target = a * point + b`` for that target axis, and
        ``mask``, the transform the fit amounts to. None when the points don't
        spread out on either axis.
    """
    px = [p[0] for p in points]
    py = [p[1] for p in points]
    tx = [t[0] for t in targets]
    ty = [t[1] for t in targets]
    straight = abs(_corr(px, tx)) + abs(_corr(py, ty))
    crossed = abs(_corr(py, tx)) + abs(_corr(px, ty))
    swap = crossed > straight
    lx = _line(py if swap else px, tx)
    ly = _line(px if swap else py, ty)
    if lx is None or ly is None:
        return None
    mask = (SWAP_XY if swap else 0) | (REVERSE_X if lx[0] < 0 else 0) | (REVERSE_Y if ly[0] < 0 else 0)
    return {"swap": swap, "x": lx, "y": ly, "mask": mask}


def _edges(line, size):
    """Where a fitted axis reads at the screen's two edges: ``(at 0, at size - 1)``."""
    a, b = line
    return (round((0 - b) / a), round((size - 1 - b) / a))


def analyse(taps, width, height, mask=None, rotation=0, table=None):
    """What's wrong with a touch mapping, from taps on targets.

    Args:
        taps (list): dicts with ``target`` and ``mapped``, each ``(x, y)``,
            and ``raw``, the ``touch_read`` point, or None where the board's
            touch device couldn't be reached.
        width (int): The display's width, as the touch device maps it.
        height (int): Its height.
        mask (int): The rotation table entry in use, or None if unknown.
        rotation (int): The touch device's rotation, in degrees.
        table (tuple): The board's ``touch_rotation_table``, or None.

    Returns:
        dict: ``ok`` (the taps follow the targets, each within twice
        `tolerance`, and no press started on the last one), ``off`` (each tap's distance
        from its target, in pixels), ``worst``, ``tolerance``, ``seen`` (the
        `fit` of the mapped points), ``words`` (what's wrong, in plain
        sentences), ``stale`` (how many presses began on the tap before's
        point, when any did) and ``fix`` (the table entry and calibration that would be
        right, or None without raw points).
    """
    tol = tolerance(width, height)
    targets = [tuple(t["target"]) for t in taps]
    mapped = [tuple(t["mapped"]) for t in taps]
    off = [round(((m[0] - t[0]) ** 2 + (m[1] - t[1]) ** 2) ** 0.5) for m, t in zip(mapped, targets)]
    worst = max(off) if off else 0
    seen = fit(mapped, targets)
    # Right when the taps follow the targets with no pattern to their misses
    # and none is far out: a fingertip's aim, not the mapping.
    ok = _pattern_right(seen, width, height, tol) and worst <= 2 * tol
    out = {"ok": ok, "off": off, "worst": worst, "tolerance": tol, "seen": seen, "words": [], "fix": None}
    words = out["words"]
    stale = _stale(taps, tol)
    if stale:
        # A press that read the last tap's point throws the fit off, so the
        # fault is that, not a pattern.
        out["ok"] = False
        out["stale"] = stale
        words.append(
            "Each press starts where the last one ended: the touch controller's first read of %d of the taps "
            "was the tap before's point, so a tap can press what you touched last." % stale
        )
        return out
    if ok:
        words.append("Taps land where you touch: %d px off on average, the worst %d px." % (round(sum(off) / len(off)), worst))
    if seen is None:
        words.append("The taps all read the same place: the touch controller isn't reporting where you touch.")
        return out
    if not out["ok"]:
        if seen["mask"]:
            words.append(_WORDS[seen["mask"]])
        words.extend(_scale_words(seen, width, height, tol))
        if len(words) == 0:
            far = [i + 1 for i, d in enumerate(off) if d > 2 * tol]
            if far:
                words.append("Tap %s landed %d px from its target, far past the others." % (" and ".join(str(n) for n in far), worst))
            else:
                words.append("Taps land up to %d px from their targets." % worst)

    raws = [t.get("raw") for t in taps]
    if None in raws:
        return out
    raws = [tuple(r[:2]) for r in raws]
    need = fit(raws, targets)
    if need is None:
        return out
    good = need["mask"]
    after = fit([apply_mask(r, good, width, height) for r in raws], targets)
    fix = {"mask": good, "mask_name": mask_name(good), "rotation": rotation, "table": None, "calibration": None}
    if table is not None:
        new = list(table)
        new[(rotation // 90) % 4] = good
        fix["table"] = new
    if after is not None:
        cal = {}
        for axis, size in (("x", width), ("y", height)):
            a, b = after[axis]
            if abs(a - 1) > SCALE_OK or abs(b) > tol:
                # Where touch_read's own axis reads at the screen's edges, and
                # where it should: the mask may swap and reverse it on the way.
                raw_axis = ("y" if axis == "x" else "x") if need["swap"] else axis
                rev = good & (REVERSE_X if axis == "x" else REVERSE_Y)
                should = (size - 1, 0) if rev else (0, size - 1)
                cal[axis] = {"raw_axis": raw_axis, "reads": _edges(need[axis], size), "should": should}
        fix["calibration"] = cal or None
    out["fix"] = fix
    if not out["ok"]:
        if mask is not None and good != mask:
            words.append("Fix: the rotation table's entry for rotation %d should be %s, not %s." % (rotation, mask_name(good), mask_name(mask)))
        for axis in ("x", "y"):
            c = (fix["calibration"] or {}).get(axis)
            if c:
                words.append(
                    "Fix: touch_read's %s reads %d at the %s edge and %d at the %s; it should read %d and %d."
                    % (c["raw_axis"], c["reads"][0], "left" if axis == "x" else "top", c["reads"][1],
                       "right" if axis == "x" else "bottom", c["should"][0], c["should"][1])
                )
    return out


def _stale(taps, tol):
    """How many taps began with a first read on the tap before them, far from where they settled."""
    count = 0
    for before, tap in zip(taps, taps[1:]):
        first = tap.get("first")
        if first is None or before.get("raw") is None:
            continue
        on_before = abs(first[0] - before["raw"][0]) + abs(first[1] - before["raw"][1]) <= 2 * tol
        settled_far = abs(first[0] - tap["raw"][0]) + abs(first[1] - tap["raw"][1]) > 4 * tol
        if on_before and settled_far:
            count += 1
    return count


def _scale_words(seen, width, height, tol):
    """Sentences for a fitted scale or offset that's wrong."""
    out = []
    for axis, size, across, lo, hi in (("x", width, "width", "left", "right"), ("y", height, "height", "up", "down")):
        a, b = seen[axis]
        if abs(abs(a) - 1) > SCALE_OK:
            out.append("Taps spread over %d%% of the screen's %s instead of all of it." % (round(100 / abs(a)), across))
        if seen["swap"]:
            continue  # an offset along a swapped axis has no plain direction
        # Where a touch at the middle of this axis lands, against the middle.
        mid = (size - 1) / 2
        shift = (mid - b) / a - mid
        if abs(shift) > tol:
            out.append("Taps land %d px too far %s." % (abs(round(shift)), hi if shift > 0 else lo))
    return out
