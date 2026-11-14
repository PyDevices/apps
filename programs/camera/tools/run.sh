#!/bin/sh
# Run the app on the desktop at the board's 240x240. Pass a shot list to
# drive it (tools/shoot.py); with none it runs for you to press keys.
cd "$(dirname "$0")/.." || exit 1
MP=${MICROPYTHON:-micropython}
# PYDEVICES_WIDTH and PYDEVICES_HEIGHT pick the panel: 240 is the Eye's. On a
# bigger one the layout is enlarged by a whole number and centred.
export PYDEVICES_WIDTH=${PYDEVICES_WIDTH:-240} PYDEVICES_HEIGHT=${PYDEVICES_HEIGHT:-240}
if [ "$PYDEVICES_WIDTH" -gt 240 ]; then export PYDEVICES_SCALE=${PYDEVICES_SCALE:-1}; fi
export PYDEVICES_SCALE=${PYDEVICES_SCALE:-2}
export MICROPYPATH=".:.frozen:${APPKIT_LIB:-$(pwd)/../../lib}:$HOME/.micropython/lib:/usr/lib/micropython"
if [ $# -gt 0 ]; then
    exec "$MP" -X heapsize=32M tools/shoot.py "$@"
fi
exec "$MP" -X heapsize=32M main.py
