# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Effect adapters: any library's effect, behind one small shape.

An adapter builds the effect's audio node and describes its parameters, and
the screen builds a knob for each description:

    {"key": "replace", "label": "Replace", "min": 0.0, "max": 1.0,
     "default": 0.5, "unit": ""}

The audio path is the node, in C; the adapter only sets values on it.
"""

from . import CHANNELS, SAMPLE_RATE


class Effect:
    library = ""
    name = ""
    node = None

    def parameters(self):
        return []

    def set(self, key, value):
        raise NotImplementedError

    def get(self, key):
        raise NotImplementedError

    def play(self, source):
        self.node.play(source)

    def stop(self):
        self.node.stop()

    def deinit(self):
        if self.node is not None:
            self.node.deinit()
            self.node = None


class Airwindows(Effect):
    """One of airwindows-py's plug-ins. Every knob is upstream's own 0..1."""

    library = "airwindows"

    def __init__(self, name):
        import audioairwindows

        self.name = name
        self.node = getattr(audioairwindows, name)(
            sample_rate=SAMPLE_RATE, channel_count=CHANNELS)
        self._params = [
            {"key": key, "label": label, "min": 0.0, "max": 1.0,
             "default": default, "unit": ""}
            for key, label, default in self.node.parameters()]

    def parameters(self):
        return self._params

    def set(self, key, value):
        self.node.set(**{key: value})

    def get(self, key):
        return self.node.get(key)

    @staticmethod
    def names():
        try:
            import audioairwindows
        except ImportError:
            return []
        names = getattr(audioairwindows, "__all__", None)
        if not names:
            names = [n for n in dir(audioairwindows)
                     if hasattr(getattr(audioairwindows, n), "parameters")]
        return sorted(names, key=lambda n: n.lower())


def guitar_set(path=None):
    """The curated names from guitar-set.txt, in its order, as
    (group, name) pairs. The first is the one the app opens with."""
    if path is None:
        here = __file__.replace("\\", "/")
        path = here[:here.rfind("/") + 1] + "guitar-set.txt"
    found = []
    group = ""
    try:
        f = open(path)
    except OSError:
        return found
    with f:
        for line in f:
            line = line.strip()
            if line.startswith("##"):
                group = line[2:].strip()
            elif line and not line.startswith("#"):
                found.append((group, line))
    return found


LIBRARIES = {"airwindows": Airwindows}


def make(library, name):
    return LIBRARIES[library](name)
