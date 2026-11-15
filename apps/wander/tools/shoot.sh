#!/bin/sh
# Draw the named stills with MicroPython and turn each BMP into a PNG.
# usage: tools/shoot.sh MICROPYTHON OUT_DIR [NAME ...]
set -e
mp=$1; out=$2; shift 2
timeout 300 "$mp" -X heapsize=128M tools/still.py "$out" "$@"
for f in "$out"/*.bmp; do
  ffmpeg -loglevel error -y -i "$f" "${f%.bmp}.png" && rm "$f"
done
