#!/bin/sh
# Run the app on the desktop at the board's 240x240. Pass a shot list to
# drive it (tools/shoot.py); with none it runs for you to press keys. It runs
# from the repository's root, where the app is apps.eyecam, so a shot list's
# path is made whole first.
if [ $# -gt 0 ]; then set -- "$(realpath "$1")"; fi
cd "$(dirname "$0")/../../.." || exit 1
MP=${MICROPYTHON:-micropython}
# OMNIPYTHON_WIDTH and OMNIPYTHON_HEIGHT pick the panel: 240 is the Eye's. On a
# bigger one the layout is enlarged by a whole number and centred.
export OMNIPYTHON_WIDTH=${OMNIPYTHON_WIDTH:-240} OMNIPYTHON_HEIGHT=${OMNIPYTHON_HEIGHT:-240}
if [ "$OMNIPYTHON_WIDTH" -gt 240 ]; then export OMNIPYTHON_SCALE=${OMNIPYTHON_SCALE:-1}; fi
export OMNIPYTHON_SCALE=${OMNIPYTHON_SCALE:-2}
export MICROPYPATH=".:.frozen:${APPKIT_LIB:-$(pwd)/lib}:$HOME/.micropython/lib:/usr/lib/micropython"
if [ $# -gt 0 ]; then
    exec "$MP" -X heapsize=32M apps/eyecam/tools/shoot.py "$@"
fi
exec "$MP" -X heapsize=32M apps/eyecam/main.py
