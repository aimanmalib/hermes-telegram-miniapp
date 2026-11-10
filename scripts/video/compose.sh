#!/usr/bin/env bash
# Assemble the demo video from what record.py produced ($VIDEO_OUT/manifest.json):
# cards as stills, screen clips inside the phone frame with their caption, short fades, hard cuts.
#
#   VIDEO_OUT=<record.py output> VIDEO_FILE=<file.mp4> [SAMPLE_DIR=<dir>] scripts/video/compose.sh
#
# Output: H.264 yuv420p, canvas size and fps from the storyboard, AAC soundtrack from audio.py normalised to the
# storyboard's loudness (EBU R128), an English subtitle track, +faststart. The same subtitles are written next
# to the video as <name>.srt, for players and uploads that take a separate caption file.
# A screen shot may keep several parts of its recording ("ranges", a jump cut); they are joined first.
# SAMPLE_DIR (optional) receives one PNG from the middle of each segment, for checking by eye.
set -euo pipefail

: "${VIDEO_OUT:?set VIDEO_OUT to the record.py output folder}"
: "${VIDEO_FILE:?set VIDEO_FILE to the mp4 to write}"
manifest="$VIDEO_OUT/manifest.json"
work="$VIDEO_OUT/segments"
rm -rf "$work"
mkdir -p "$work"

# One tab-separated line per segment: id kind duration png|back clip ranges front x y w h, then fps and fade.
read -r fps fade lufs tp < <(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); a=m["audio"]
print(m["canvas"]["fps"], m["fade_sec"], a["lufs"], a["true_peak"])' "$manifest")
mapfile -t rows < <(python3 - "$manifest" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
for s in m["segments"]:
    if s["kind"] == "card":
        print("\t".join(map(str, [s["id"], "card", s["duration"], s["png"]])))
    else:
        b = s["screen"]
        ranges = s.get("ranges") or [[s["start"], s["start"] + s["duration"]]]
        keep = "+".join(f"between(t,{a},{e})" for a, e in ranges)
        print("\t".join(map(str, [s["id"], "clip", s["duration"], s["back"], s["clip"], keep, s["front"],
                                   b["x"], b["y"], b["w"], b["h"]])))
PY
)

enc=(-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r "$fps" -an)
list="$work/list.txt"
: > "$list"
total=0
mids=()
n=0
for row in "${rows[@]}"; do
  IFS=$'\t' read -r id kind dur a clip keep front x y w h <<< "$row"
  n=$((n + 1))
  seg="$work/$(printf '%02d' "$n")-$id.mp4"
  fades="fade=t=in:st=0:d=$fade,fade=t=out:st=$(python3 -c "print($dur - $fade)"):d=$fade"
  if [[ "$kind" == card ]]; then
    ffmpeg -nostdin -loglevel error -y -loop 1 -framerate "$fps" -t "$dur" -i "$a" \
      -vf "format=yuv420p,$fades" "${enc[@]}" -t "$dur" "$seg"
  else
    cut="$work/$(printf '%02d' "$n")-$id-cut.mp4"
    ffmpeg -nostdin -loglevel error -y -i "$clip" \
      -vf "fps=$fps,select='$keep',setpts=N/$fps/TB" -c:v libx264 -preset fast -crf 14 -an "$cut"
    ffmpeg -nostdin -loglevel error -y \
      -loop 1 -framerate "$fps" -t "$dur" -i "$a" \
      -t "$dur" -i "$cut" \
      -loop 1 -framerate "$fps" -t "$dur" -i "$front" \
      -filter_complex "[1:v]fps=$fps,scale=$w:$h:flags=lanczos,setsar=1,tpad=stop_mode=clone:stop_duration=$dur[c];[0:v][c]overlay=$x:$y:eof_action=repeat[s];[s][2:v]overlay=0:0,format=yuv420p,$fades[v]" \
      -map "[v]" "${enc[@]}" -t "$dur" "$seg"
  fi
  echo "file '$seg'" >> "$list"
  mids+=("$(python3 -c "print($total + $dur / 2)")|$id")
  total=$(python3 -c "print($total + $dur)")
done

mkdir -p "$(dirname "$VIDEO_FILE")"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
srt="${VIDEO_FILE%.*}.srt"
python3 "$here/voice.py" "$manifest"   # narration clips (ElevenLabs, cached); VOICE_OFF=1 skips
python3 "$here/audio.py" "$manifest" "$work/soundtrack.wav" "$work/subtitles.srt"
tmp="$VIDEO_FILE.tmp.mp4"
# Two-pass loudnorm: measure the mix, then apply a linear gain to the target (single pass undershoots on speech with pauses).
meas=$(ffmpeg -nostdin -hide_banner -i "$work/soundtrack.wav" -af "loudnorm=I=$lufs:TP=$tp:LRA=11:print_format=json" -f null - 2>&1 \
  | python3 -c 'import json,re,sys; m=json.loads(re.search(r"\{[^{}]*\}", sys.stdin.read()).group(0))
print(":".join(f"measured_{k}={m["input_"+k]}" for k in ("i", "tp", "lra", "thresh")) + f":offset={m["target_offset"]}")')
ffmpeg -nostdin -loglevel error -y -f concat -safe 0 -i "$list" -i "$work/soundtrack.wav" -i "$work/subtitles.srt" \
  -map 0:v -map 1:a -map 2:s -c:v copy \
  -af "loudnorm=I=$lufs:TP=$tp:LRA=11:$meas:linear=true,aresample=48000" -c:a aac -b:a 160k -ac 2 \
  -c:s mov_text -metadata:s:s:0 language=eng -metadata:s:a:0 language=eng \
  -t "$total" -movflags +faststart "$tmp"
mv "$tmp" "$VIDEO_FILE"
cp "$work/subtitles.srt" "$srt"
echo "wrote $VIDEO_FILE (${total}s planned) and $srt"

if [[ -n "${SAMPLE_DIR:-}" ]]; then
  mkdir -p "$SAMPLE_DIR"
  i=0
  for m in "${mids[@]}"; do
    i=$((i + 1))
    ffmpeg -nostdin -loglevel error -y -ss "${m%%|*}" -i "$VIDEO_FILE" -frames:v 1 "$SAMPLE_DIR/$(printf '%02d' "$i")-${m#*|}.png"
  done
  echo "samples: $i in $SAMPLE_DIR"
fi
