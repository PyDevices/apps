# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Checks which Spotify OpenAPI schemas the object specs cover."""

from .object_specs import SPOTIFY_OBJECT_SPECS as SPOTIFY_OBJECT_SPECS

OPENAPI_SCHEMA_NAMES: tuple[str, ...]
SCHEMA_TO_SPEC: dict[str, str]
SKIPPED_SCHEMA_NAMES: tuple[str, ...]

def spec_names() -> tuple[str, ...]: ...
def uncovered_schema_names() -> tuple[str, ...]: ...
