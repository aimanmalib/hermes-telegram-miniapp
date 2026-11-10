"""Render the demo video's narration with ElevenLabs, one clip per storyboard voice line.

    python3 scripts/video/voice.py <manifest.json>

Each screen or card shot may carry "voice": [{"at": seconds into the shot, "text": "..."}]. Every line is sent to the
ElevenLabs text-to-speech API once and cached by a hash of (text, voice, model, settings) under $VIDEO_OUT/voice/,
converted to mono WAV at the soundtrack's rate, and its length measured. The result is written back into the
manifest as segment["voice"] = [{"at", "text", "wav", "sec"}], which audio.py mixes over the music bed.

A line that would still be speaking when the next line starts, or past the end of the video, stops the run: shorten
the text or move "at" in storyboard.json. Nothing is sped up.

Environment:
  ELEVENLABS_API_KEY_FILE  KEY=VALUE file holding ELEVENLABS_API_KEY (never printed, never copied)
  ELEVENLABS_VOICE_ID      the voice to use; the storyboard's audio.voice block sets model and settings
  VOICE_OFF=1              skip narration (the video keeps the music bed and cues only)
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


def api_key():
    path = os.environ.get("ELEVENLABS_API_KEY_FILE", "")
    if not path:
        sys.exit("voice: set ELEVENLABS_API_KEY_FILE (or VOICE_OFF=1)")
    for line in Path(path).read_text().splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    sys.exit(f"voice: no ELEVENLABS_API_KEY in {path}")


def tts(text, voice_id, cfg, key, mp3):
    body = json.dumps({"text": text, "model_id": cfg["model"], "voice_settings": cfg["settings"]}).encode()
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
                                 data=body, method="POST",
                                 headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if len(data) < 2000:
        sys.exit(f"voice: ElevenLabs returned {len(data)} bytes for {text[:40]!r}")
    mp3.write_bytes(data)


def seconds(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def lines_on_timeline(manifest):
    """[(absolute start, segment, line)] in video order."""
    out, t = [], 0.0
    for seg in manifest["segments"]:
        for line in seg.get("voice_lines", []):
            out.append((t + line["at"], seg, line))
        t += seg["duration"]
    return out, t


def main(manifest_path):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    for seg in manifest["segments"]:
        seg.pop("voice", None)
    if os.environ.get("VOICE_OFF") == "1":
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print("voice: off")
        return
    cfg = manifest["audio"]["voice"]
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
    if not voice_id:
        sys.exit("voice: set ELEVENLABS_VOICE_ID (or VOICE_OFF=1)")
    cache = manifest_path.parent / "voice"
    cache.mkdir(exist_ok=True)
    rate = manifest["audio"]["sample_rate"]
    timeline, total = lines_on_timeline(manifest)
    key = None
    placed = []
    for start, seg, line in timeline:
        digest = hashlib.sha256(json.dumps([line["text"], voice_id, cfg["model"], cfg["settings"]]).encode()).hexdigest()[:16]
        mp3, wav = cache / f"{digest}.mp3", cache / f"{digest}.wav"
        if not mp3.exists():
            key = key or api_key()
            tts(line["text"], voice_id, cfg, key, mp3)
        if not wav.exists():
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(mp3), "-af",
                            "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                            "silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                            "-ac", "1", "-ar", str(rate), str(wav)], check=True)
        sec = seconds(wav)
        placed.append((start, sec, line["text"]))
        seg.setdefault("voice", []).append({"at": line["at"], "text": line["text"], "wav": str(wav), "sec": round(sec, 3)})
    gap = cfg.get("min_gap_sec", 0.25)
    for (a, la, ta), (b, _, tb) in zip(placed, placed[1:]):
        if a + la + gap > b:
            sys.exit(f"voice: {ta[:40]!r} runs {a + la + gap - b:.2f} s into the next line {tb[:40]!r}")
    if placed and placed[-1][0] + placed[-1][1] > total - cfg.get("tail_sec", 0.3):
        sys.exit(f"voice: the last line ends after the video ({placed[-1][0] + placed[-1][1]:.2f} s of {total} s)")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    spoken = sum(s for _, s, _ in placed)
    print(f"voice: {len(placed)} lines, {spoken:.1f} s spoken, cache {cache}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
