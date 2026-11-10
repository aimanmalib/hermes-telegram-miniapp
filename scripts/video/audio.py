"""Write the demo video's soundtrack and subtitles from record.py's manifest.

    python3 scripts/video/audio.py <manifest.json> <out.wav> <out.srt>

Soundtrack: a music bed for the whole video, plus a short tick at every recorded tap and a two-note chime at
the cues record.py marked (an Ask delivered, a reply arriving), each with its own gain (0 = left out).
The bed comes from audio.bed.mode:
  "file"  the audio file named by $VIDEO_BED_FILE (any format ffmpeg reads; a mono 16-bit WAV at the sample
          rate needs no ffmpeg), looped with a crossfade when shorter than the video, cut to length, faded in
          and out, scaled by file_gain. The file is not part of this repository: bring a track you may use.
  "sine"  a soft generated chord bed (sine voices, slow attack); no third-party audio.
"file" without a readable file falls back to "sine" and says so on stderr. Which bed was used (and the file's
sha256) is written next to the wav as <name>.json, so a fallback cannot go out unnoticed.
When voice.py has placed narration (segment["voice"]), each line is mixed in and the bed and cues are lowered
under it ("bed_duck", with short ramps) so the words stay clear. compose.sh normalises the loudness with ffmpeg
afterwards; the numbers here only set the balance between the parts.

Subtitles: one cue per segment, from the caption burned into the frame (cards: their lines), so players
that show captions and viewers who cannot read the burned-in text get the same words.
Settings (chords, gains, cue sounds) come from the storyboard's "audio" block, copied into the manifest.
"""
import hashlib
import json
import math
import os
import subprocess
import sys
import wave
from array import array


def voice_times(manifest):
    """[(seconds into the video, line)] for every narration line voice.py placed."""
    return sorted(((start + v["at"], v) for start, seg in segment_times(manifest) for v in seg.get("voice", [])),
                  key=lambda x: x[0])


def read_wav(path, rate):
    with wave.open(path, "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != rate:
            raise SystemExit(f"{path}: expected mono 16-bit {rate} Hz")
        pcm = array("h")
        pcm.frombytes(w.readframes(w.getnframes()))
    return pcm


def duck_curve(n, spans, depth, ramp):
    """1.0 everywhere except inside the spoken spans, where it falls to `depth` with linear ramps of `ramp` samples."""
    g = array("f", [1.0]) * n
    for a, b in spans:
        for k in range(max(0, a - ramp), min(n, b + ramp)):
            if k < a:
                d = 1.0 - (1.0 - depth) * (k - (a - ramp)) / ramp
            elif k >= b:
                d = depth + (1.0 - depth) * (k - b) / ramp
            else:
                d = depth
            g[k] = min(g[k], d)
    return g


def segment_times(manifest):
    """[(start, segment)] on the video timeline."""
    out, t = [], 0.0
    for seg in manifest["segments"]:
        out.append((t, seg))
        t += seg["duration"]
    return out


def cue_times(manifest):
    """[(seconds into the video, kind)] for every tap and cue inside the kept parts of the screen shots."""
    return sorted((start + t, kind) for start, seg in segment_times(manifest) for t, kind in seg.get("events", []))


def decode(path, rate):
    """The file as mono floats in -1..1 at `rate`: read directly when it is already a mono 16-bit WAV at that rate,
    otherwise decoded by ffmpeg."""
    try:
        with wave.open(path, "rb") as w:
            if w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == rate:
                pcm = array("h")
                pcm.frombytes(w.readframes(w.getnframes()))
                return array("f", (x / 32768 for x in pcm))
    except (wave.Error, EOFError):
        pass
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path, "-f", "s16le", "-acodec", "pcm_s16le",
                          "-ac", "1", "-ar", str(rate), "-"], check=True, capture_output=True).stdout
    pcm = array("h")
    pcm.frombytes(raw[:len(raw) // 2 * 2])
    return array("f", (x / 32768 for x in pcm))


def loop_to(pcm, n, xfade):
    """`pcm` repeated until it is `n` samples long, each repeat joined with a linear crossfade of `xfade` samples."""
    if not pcm:
        raise ValueError("empty bed file")
    out = array("f", pcm[:n])
    xfade = max(0, min(xfade, len(pcm) // 2))
    while len(out) < n:
        start = len(out) - xfade
        for j in range(xfade):
            t = (j + 1) / (xfade + 1)
            out[start + j] = out[start + j] * (1 - t) + pcm[j] * t
        out.extend(pcm[xfade:xfade + n - len(out)])
    return out


def fade_ends(buf, cfg, rate):
    fade_in, fade_out = max(1.0, cfg["fade_in_sec"] * rate), max(1.0, cfg["fade_out_sec"] * rate)
    n = len(buf)
    for k in range(n):
        buf[k] *= min(1.0, k / fade_in, (n - 1 - k) / fade_out)
    return buf


def file_bed(total, cfg, rate, path):
    """The bed from an audio file: looped, cut to the video, faded at both ends, scaled by file_gain."""
    n = int(total * rate)
    pcm = loop_to(decode(path, rate), n, int(cfg.get("loop_crossfade_sec", 1.0) * rate))
    gain = cfg["file_gain"]
    for k in range(n):
        pcm[k] *= gain
    return fade_ends(pcm, cfg, rate)


def choose_bed(total, cfg, rate, env=os.environ):
    """(buffer, record): the bed the storyboard asks for, or the sine bed with the reason it fell back."""
    mode = cfg.get("mode", "sine")
    if mode not in ("file", "sine"):
        raise SystemExit(f"audio.bed.mode must be 'file' or 'sine', not {mode!r}")
    if mode == "file":
        path = env.get("VIDEO_BED_FILE", "")
        reason = "VIDEO_BED_FILE is not set" if not path else None if os.path.isfile(path) else "VIDEO_BED_FILE is not a file"
        if reason is None:
            try:
                buf = file_bed(total, cfg, rate, path)
            except (OSError, ValueError, subprocess.CalledProcessError) as e:
                reason = f"could not read VIDEO_BED_FILE: {type(e).__name__}"
            else:
                sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
                return buf, {"bed": "file", "file": os.path.basename(path), "sha256": sha}
        print(f"bed: sine fallback ({reason})", file=sys.stderr)
        return bed(total, cfg, rate), {"bed": "sine", "fallback": reason}
    return bed(total, cfg, rate), {"bed": "sine"}


def bed(total, cfg, rate):
    """The chord bed: each chord fades in over attack_sec and hands over to the next; the whole fades at both ends."""
    n = int(total * rate)
    buf = array("f", bytes(4 * n))
    chords, step = cfg["chords"], cfg["chord_sec"]
    attack = cfg["attack_sec"]
    for i in range(math.ceil(total / step) + 1):
        notes = chords[i % len(chords)]
        a, b = max(0, int((i * step - attack / 2) * rate)), min(n, int(((i + 1) * step + attack / 2) * rate))
        voices = [(2 * math.pi * f / rate, cfg["gain"] / len(notes)) for f in notes]
        voices.append((2 * math.pi * notes[0] / 2 / rate, cfg["bass_gain"]))
        voices.append((2 * math.pi * notes[-1] * 2 / rate, cfg["shimmer_gain"]))
        ramp = attack * rate
        for k in range(a, b):
            env = min(1.0, (k - a) / ramp, (b - k) / ramp)
            buf[k] += env * sum(g * math.sin(w * k) for w, g in voices)
    return fade_ends(buf, cfg, rate)


def add_tone(buf, at, freqs, ms, gain, rate):
    """A short plucked tone (fast attack, exponential decay) mixed in at `at` seconds."""
    start, length = int(at * rate), int(ms / 1000 * rate)
    decay = length / 5
    for j in range(length):
        k = start + j
        if k >= len(buf):
            break
        env = min(1.0, j / (0.004 * rate)) * math.exp(-j / decay)
        buf[k] += gain * env * sum(math.sin(2 * math.pi * f * j / rate) for f in freqs) / len(freqs)


def soundtrack(manifest, env=os.environ):
    """(pcm, rate, record): the mixed soundtrack and which bed it used."""
    cfg = manifest["audio"]
    rate = cfg["sample_rate"]
    total = sum(seg["duration"] for seg in manifest["segments"])
    buf, record = choose_bed(total, cfg["bed"], rate, env)
    cues = cfg["cues"]
    for at, kind in cue_times(manifest):
        c = cues[kind]
        if c["gain"] > 0:
            add_tone(buf, at, c.get("freqs", [c.get("freq")]), c["ms"], c["gain"], rate)
    lines = voice_times(manifest)
    if lines:
        vc = cfg["voice"]
        spans, clips = [], []
        for at, v in lines:
            pcm = read_wav(v["wav"], rate)
            a = int(at * rate)
            spans.append((a, a + len(pcm)))
            clips.append((a, pcm))
        g = duck_curve(len(buf), spans, vc["bed_duck"], int(vc["duck_ramp_sec"] * rate))
        for k in range(len(buf)):
            buf[k] *= g[k]
        gain = vc["gain"] / 32768
        for a, pcm in clips:
            for j, x in enumerate(pcm):
                if a + j >= len(buf):
                    break
                buf[a + j] += x * gain
    peak = max(1e-9, max(abs(x) for x in buf))
    scale = min(1.0, 0.89 / peak)
    return array("h", (int(x * scale * 32767) for x in buf)), rate, record


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def subtitles(manifest):
    cues = []
    for start, seg in segment_times(manifest):
        text = seg.get("subtitle", "").strip()
        if text:
            cues.append(f"{len(cues) + 1}\n{srt_time(start + 0.1)} --> {srt_time(start + seg['duration'] - 0.1)}\n{text}\n")
    return "\n".join(cues)


def main(manifest_path, wav_path, srt_path):
    manifest = json.load(open(manifest_path))
    pcm, rate, record = soundtrack(manifest)
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    with open(srt_path, "w", encoding="utf-8") as fh:
        fh.write(subtitles(manifest))
    with open(os.path.splitext(wav_path)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    print(f"soundtrack {len(pcm) / rate:.1f}s, bed {record['bed']}, {len(cue_times(manifest))} cues; subtitles -> {srt_path}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
