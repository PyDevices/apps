"""Start the stompbox app: python run.py [options]; see stompbox/app.py."""

import sys

here = __file__.replace("\\", "/").rsplit("/", 1)[0] if "/" in __file__.replace("\\", "/") else "."
if here not in sys.path:
    sys.path.insert(0, here)

from stompbox import app  # noqa: E402

app.main()
