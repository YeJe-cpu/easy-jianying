#!/bin/sh
# Generate small synthetic media for examples and tests (no real footage needed).
set -e
OUT="${1:-work/fixtures}"
mkdir -p "$OUT"
ff() { ffmpeg -v error -y "$@"; }
ff -f lavfi -i testsrc2=size=1920x1080:rate=30:duration=12 -f lavfi -i sine=frequency=440:duration=12 \
   -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$OUT/clip_a.mp4"
ff -f lavfi -i smptehdbars=size=1920x1080:rate=30:duration=12 -f lavfi -i sine=frequency=660:duration=12 \
   -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$OUT/clip_b.mp4"
ff -f lavfi -i mandelbrot=size=1080x1920:rate=30 -t 8 -c:v libx264 -pix_fmt yuv420p "$OUT/portrait.mp4"
ff -f lavfi -i "color=c=0x2a6df4:size=800x800,drawbox=x=200:y=200:w=400:h=400:color=white:t=fill" -frames:v 1 "$OUT/card.png"
ff -f lavfi -i "sine=frequency=220:duration=30,volume=0.3" -c:a libmp3lame "$OUT/bgm.mp3"
echo "fixtures in $OUT"
