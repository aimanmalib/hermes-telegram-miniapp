#!/usr/bin/env bash
# Cut the README clip from the composed demo video: the phone screen only, as a palette GIF.
#
#   VIDEO_OUT=<record.py output> VIDEO_FILE=<demo.mp4> GIF_START=<seconds> [GIF_SEC=10] [GIF_WIDTH=480] [GIF_FPS=15] \
#     scripts/video/gif.sh docs/demo.gif
#
# The screen rectangle comes from the manifest (the same box compose.sh scales each clip into).
set -euo pipefail

: "${VIDEO_OUT:?set VIDEO_OUT to the record.py output folder}"
: "${VIDEO_FILE:?set VIDEO_FILE to the composed mp4}"
: "${GIF_START:?set GIF_START to the first second of the clip}"
out="${1:?usage: $0 <out.gif>}"
read -r x y w h < <(python3 -c 'import json,sys
m=json.load(open(sys.argv[1]))
b=next(s["screen"] for s in m["segments"] if "screen" in s)
print(b["x"], b["y"], b["w"], b["h"])' "$VIDEO_OUT/manifest.json")
ffmpeg -nostdin -loglevel error -y -ss "$GIF_START" -t "${GIF_SEC:-10}" -i "$VIDEO_FILE" \
  -vf "crop=$w:$h:$x:$y,fps=${GIF_FPS:-15},scale=${GIF_WIDTH:-480}:-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" \
  "$out"
echo "wrote $out ($(du -h "$out" | cut -f1))"
