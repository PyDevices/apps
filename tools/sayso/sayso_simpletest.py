# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

import os
import sys

# This file lives in tools/sayso but should be run from the repository root, so lib/ (which holds the package) goes on the path
sys.path.insert(0, os.path.join(os.getcwd(), "lib"))
    
from sayso import SpotifyClient

client = SpotifyClient()
me = client.me()
print(me)
