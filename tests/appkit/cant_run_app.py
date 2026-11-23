# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""An app that can't run anywhere, for `hidden_contract.py`: it shows
touchkit's can't-run message, as an app missing its hardware does."""

from touchkit import ui


def main(scope):
    ui.missing(scope, "no radio for this", "Nowhere needs a radio this board doesn't have.")
