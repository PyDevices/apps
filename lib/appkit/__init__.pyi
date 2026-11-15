# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit: apps you can switch between, and a launcher to run them."""

from .foreground import serve as serve
from .launcher import Launcher as Launcher, host as host, run_pending_script as run_pending_script
from .scope import AppScope as AppScope
from .shell import Shell as Shell

def run(name: str | None = None, folder: str = 'apps', *, data_root: str | None = None) -> Launcher | None:
    """Run the apps in `folder`: a home screen listing them, or app `name` alone.

    Ends in the main-thread loop and returns the `Launcher` when the program
    quits. In a browser it returns the launcher at once. `data_root` moves every
    app's `data_dir` and the launcher's restart file.
    """
