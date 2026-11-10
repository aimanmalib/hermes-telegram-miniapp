"""Write the demo video's soundtrack and subtitles from record.py's manifest.

    python3 scripts/video/audio.py <manifest.json> <out.wav> <out.srt>

Soundtrack: a soft generated chord bed (sine voices, slow attack) for the whole video, plus a short tick at
every recorded tap and a two-note chime at the cues record.py marked (an Ask delivered, a reply arriving).
When voice.py has placed narration (segment["voice"]), each line is mixed in and the bed and cues are lowered
under it ("bed_duck", with short ramps) so the words stay clear.
Everything is synthesised here, so there is no third-party audio to license. compose.sh normalises the
loudness with ffmpeg afterwards; the numbers here only set the balance between the parts.

Subtitles: one cue per segment, from the caption burned into the frame (cards: their lines), so players
that show captions and viewers who cannot read the burned-in text get the same words.
Settings (chords, gains, cue sounds) come from the storyboard's "audio" block, copied into the manifest.
"""
import json
import math
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
    fade_in, fade_out = cfg["fade_in_sec"] * rate, cfg["fade_out_sec"] * rate
    for k in range(n):
        buf[k] *= min(1.0, k / fade_in, (n - k) / fade_out)
    return buf


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


def soundtrack(manifest):
    cfg = manifest["audio"]
    rate = cfg["sample_rate"]
    total = sum(seg["duration"] for seg in manifest["segments"])
    buf = bed(total, cfg["bed"], rate)
    cues = cfg["cues"]
    for at, kind in cue_times(manifest):
        c = cues[kind]
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
    return array("h", (int(x * scale * 32767) for x in buf)), rate


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
    pcm, rate = soundtrack(manifest)
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    with open(srt_path, "w", encoding="utf-8") as fh:
        fh.write(subtitles(manifest))
    print(f"soundtrack {len(pcm) / rate:.1f}s, {len(cue_times(manifest))} cues; subtitles -> {srt_path}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
