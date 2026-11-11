# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The camera's settings, kept where the factory firmware keeps them.

On the board they live in NVS namespace ``p4_eye_cfg`` under the factory's
key names. MicroPython's ``esp32.NVS`` stores only 32-bit integers and
blobs, and NVS won't read or overwrite a key as a type other than the one it
was written with, so a value the factory firmware left (as u8, u16 or u32)
reads as the default here and is replaced by an i32 on the first change. On
a desktop the settings go to ``settings.json`` in the app's data folder.
Every change is saved at once, as the factory does.
"""

import json

try:
    import esp32
except ImportError:
    esp32 = None

NAMESPACE = "p4_eye_cfg"

# Resolution index as stored: 0 = 720P, 1 = 1080P, 2 = 480P (the factory's
# order, which is also the order the Settings row cycles through).
RESOLUTIONS = ("720P", "1080P", "480P")

# key: (NVS type, default)
FIELDS = {
    "od": ("u8", 1),
    "resolution": ("u8", 1),
    "flash": ("u8", 1),
    "int_time": ("u16", 30),
    "magnify": ("u16", 1),
    "int_active": ("u8", 0),
    "wake_time": ("u32", 0),
    "photo_count": ("u16", 0),
    "contrast": ("u32", 53),
    "saturation": ("u32", 63),
    "brightness": ("u32", 54),
    "hue": ("u32", 2),
    "gyroscope": ("u8", 0),
}


class Settings:
    """``settings.od``, ``settings.int_time`` and so on, saved on assignment."""

    def __init__(self, path=None):
        self._vals = {}
        self._nvs = None
        self._path = path
        if esp32 is not None and path is None:
            self._nvs = esp32.NVS(NAMESPACE)
            for key, (_kind, default) in FIELDS.items():
                try:
                    self._vals[key] = self._nvs.get_i32(key)
                except OSError:
                    self._vals[key] = default
        else:
            data = {}
            if path is not None:
                try:
                    with open(path) as f:
                        data = json.load(f)
                except (OSError, ValueError):
                    data = {}
            for key, (_kind, default) in FIELDS.items():
                self._vals[key] = int(data.get(key, default))

    def __getattr__(self, key):
        try:
            return self._vals[key]
        except KeyError:
            raise AttributeError(key)

    def set(self, key, value):
        """Set and save one value."""
        if key not in FIELDS:
            raise KeyError(key)
        value = int(value)
        if self._vals.get(key) == value:
            return
        self._vals[key] = value
        self._save(key)

    def _save(self, key):
        if self._nvs is not None:
            try:
                self._nvs.set_i32(key, self._vals[key])
            except OSError:
                # The factory's value under another type: drop it, then write.
                self._nvs.erase_key(key)
                self._nvs.set_i32(key, self._vals[key])
            self._nvs.commit()
        elif self._path is not None:
            with open(self._path, "w") as f:
                json.dump(self._vals, f)

    def resolution_name(self):
        return RESOLUTIONS[self.resolution % len(RESOLUTIONS)]
