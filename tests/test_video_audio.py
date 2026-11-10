"""The demo video's soundtrack/subtitle writer and the rig's Bot API stand-in (scripts/video/): no ffmpeg, browser
or Hermes needed."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import wave
from array import array
from pathlib import Path

import pytest

video_dir = Path(__file__).resolve().parent.parent / "scripts" / "video"


def load(name):
    spec = importlib.util.spec_from_file_location(f"video_{name}", video_dir / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audio():
    return load("audio")


@pytest.fixture(scope="module")
def stub():
    return load("bot_api_stub")


def small_manifest():
    board = json.loads((video_dir / "storyboard.json").read_text())
    cfg = dict(board["audio"], sample_rate=8000)
    return {
        "audio": cfg,
        "segments": [
            {"id": "title", "kind": "card", "duration": 2, "subtitle": "Title · Subtitle"},
            {"id": "ask", "kind": "mock", "duration": 3, "subtitle": "Ask caption", "events": [[0.5, "tap"], [2.0, "chime"]]},
            {"id": "close", "kind": "card", "duration": 1, "subtitle": ""},
        ],
    }


def test_cues_are_placed_on_the_video_timeline(audio):
    assert audio.cue_times(small_manifest()) == [(2.5, "tap"), (4.0, "chime")]


def test_subtitles_follow_segments_and_skip_empty(audio):
    srt = audio.subtitles(small_manifest())
    assert srt.splitlines()[:3] == ["1", "00:00:00,100 --> 00:00:01,900", "Title · Subtitle"]
    assert "00:00:02,100 --> 00:00:04,900\nAsk caption" in srt
    assert srt.count(" --> ") == 2


def test_srt_time_formats_hours_minutes_and_millis(audio):
    assert audio.srt_time(3723.4567) == "01:02:03,457"


def test_soundtrack_is_full_length_and_not_clipped(audio, tmp_path, monkeypatch):
    monkeypatch.delenv("VIDEO_BED_FILE", raising=False)
    manifest = small_manifest()
    path = tmp_path / "m.json"
    path.write_text(json.dumps(manifest))
    audio.main(str(path), str(tmp_path / "a.wav"), str(tmp_path / "a.srt"))
    with wave.open(str(tmp_path / "a.wav")) as w:
        assert w.getframerate() == 8000
        assert w.getnframes() == 6 * 8000
        frames = w.readframes(w.getnframes())
    samples = memoryview(frames).cast("h")
    assert 0 < max(abs(x) for x in samples) < 32767


def test_every_storyboard_cue_kind_has_a_sound(audio):
    board = json.loads((video_dir / "storyboard.json").read_text())
    assert set(board["audio"]["cues"]) >= {"tap", "chime"}


def test_stub_parses_json_form_and_multipart(stub):
    assert stub.parse_body("application/json", b'{"chat_id": 5, "text": "hi"}') == {"chat_id": 5, "text": "hi"}
    assert stub.parse_body("application/x-www-form-urlencoded", b"chat_id=5&text=a%20b") == {"chat_id": "5", "text": "a b"}
    body = (b"--XX\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n5\r\n"
            b"--XX\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\nhello\r\n--XX--\r\n")
    assert stub.parse_body("multipart/form-data; boundary=XX", body) == {"chat_id": "5", "text": "hello"}


def test_stub_records_sent_messages(stub, tmp_path, monkeypatch):
    log = tmp_path / "messages.jsonl"
    monkeypatch.setattr(stub, "LOG", str(log))
    sent = stub.result_for("sendMessage", {"chat_id": "42", "text": "*answer*", "parse_mode": "MarkdownV2"})
    assert sent["chat"]["id"] == 42 and sent["text"] == "*answer*"
    line = json.loads(log.read_text().splitlines()[-1])
    assert line["chat_id"] == "42" and line["text"] == "*answer*" and line["method"] == "sendMessage"
    assert line["parse_mode"] == "MarkdownV2"
    assert stub.result_for("getMe", {})["is_bot"] is True
    assert stub.result_for("setMyCommands", {}) is True


def test_voice_lines_fit_their_shots_and_are_disclosed():
    board = json.loads((video_dir / "storyboard.json").read_text())
    voice = [(s, v) for s in board["shots"] for v in s.get("voice", [])]
    assert voice, "the storyboard has narration"
    for shot, v in voice:
        assert 0 <= v["at"] < shot["duration"] and v["text"].strip()
    close = next(s for s in board["shots"] if s["id"] == "close")
    assert any("voice clone" in line for line in close["lines"])  # AI narration is disclosed on screen
    assert "voice" in board["audio"] and 0 < board["audio"]["voice"]["bed_duck"] < 1


def test_bed_is_lowered_under_narration(audio):
    g = audio.duck_curve(100, [(40, 60)], 0.3, 10)
    assert g[0] == 1.0 and g[99] == 1.0
    assert all(abs(g[k] - 0.3) < 1e-6 for k in range(40, 60))
    assert 0.3 < g[35] < 1.0 and 0.3 < g[64] < 1.0


def write_wav(path, samples, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(array("h", samples).tobytes())


def file_cfg(**over):
    board = json.loads((video_dir / "storyboard.json").read_text())
    return {**board["audio"]["bed"], "mode": "file", "file_gain": 0.5, "fade_in_sec": 0.25, "fade_out_sec": 0.25,
            "loop_crossfade_sec": 0.05, **over}


def test_bed_file_short_track_is_looped_to_exact_length(audio, tmp_path):
    track = tmp_path / "bed.wav"
    write_wav(track, [10000] * 4000)  # 0.5 s of a constant level
    buf, record = audio.choose_bed(2.0, file_cfg(), 8000, {"VIDEO_BED_FILE": str(track)})
    assert len(buf) == 16000 and record["bed"] == "file"
    middle = buf[4000:12000]  # past the fades: the loop joins keep the level (no gaps, no doubling)
    assert all(abs(x - 0.5 * 10000 / 32768) < 1e-3 for x in middle)


def test_bed_file_long_track_is_cut_and_faded_to_zero(audio, tmp_path):
    track = tmp_path / "bed.wav"
    write_wav(track, [8000, -8000] * 20000)  # 5 s, longer than the video
    buf, _ = audio.choose_bed(1.5, file_cfg(), 8000, {"VIDEO_BED_FILE": str(track)})
    assert len(buf) == 12000
    assert abs(buf[0]) < 1e-6 and abs(buf[-1]) < 1e-6
    start = [abs(x) for x in buf[:2000]]
    assert all(b >= a - 1e-9 for a, b in zip(start, start[1:]))  # rises smoothly, no jump
    end = [abs(x) for x in buf[-2000:]]
    assert all(b <= a + 1e-9 for a, b in zip(end, end[1:]))  # falls to silence, no sudden stop


def test_bed_file_records_which_file_was_used(audio, tmp_path):
    track = tmp_path / "bed.wav"
    write_wav(track, [1000] * 8000)
    _, record = audio.choose_bed(0.5, file_cfg(), 8000, {"VIDEO_BED_FILE": str(track)})
    assert record == {"bed": "file", "file": "bed.wav", "sha256": hashlib.sha256(track.read_bytes()).hexdigest()}


def test_bed_file_is_still_ducked_under_narration(audio, tmp_path):
    track = tmp_path / "bed.wav"
    write_wav(track, [6000] * 48000)
    line = tmp_path / "line.wav"
    write_wav(line, [0] * 4000)  # a silent 0.5 s line: what is left at its place is the ducked bed
    board = json.loads((video_dir / "storyboard.json").read_text())
    cfg = dict(board["audio"], sample_rate=8000, bed=file_cfg())
    manifest = {"audio": cfg, "segments": [
        {"id": "a", "kind": "card", "duration": 3, "voice": [{"at": 1.0, "wav": str(line), "text": "x", "sec": 0.5}]}]}
    pcm, rate, record = audio.soundtrack(manifest, {"VIDEO_BED_FILE": str(track)})
    assert record["bed"] == "file" and len(pcm) == 3 * rate
    open_level, ducked = abs(pcm[int(0.6 * rate)]), abs(pcm[int(1.25 * rate)])
    assert abs(ducked / open_level - cfg["voice"]["bed_duck"]) < 0.01


def test_bed_sine_fallback_without_file_is_printed_and_recorded(audio, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("VIDEO_BED_FILE", raising=False)
    manifest = small_manifest()
    manifest["audio"]["bed"] = file_cfg()
    path = tmp_path / "m.json"
    path.write_text(json.dumps(manifest))
    audio.main(str(path), str(tmp_path / "a.wav"), str(tmp_path / "a.srt"))
    assert "bed: sine fallback (VIDEO_BED_FILE is not set)" in capsys.readouterr().err
    assert json.loads((tmp_path / "a.json").read_text()) == {"bed": "sine", "fallback": "VIDEO_BED_FILE is not set"}


def test_bed_sine_fallback_for_a_missing_or_broken_file(audio, tmp_path, capsys):
    _, record = audio.choose_bed(0.5, file_cfg(), 8000, {"VIDEO_BED_FILE": str(tmp_path / "gone.mp3")})
    assert record == {"bed": "sine", "fallback": "VIDEO_BED_FILE is not a file"}
    empty = tmp_path / "empty.wav"
    write_wav(empty, [])
    buf, record = audio.choose_bed(0.5, file_cfg(), 8000, {"VIDEO_BED_FILE": str(empty)})
    assert record["bed"] == "sine" and record["fallback"].startswith("could not read") and len(buf) == 4000
    assert capsys.readouterr().err.count("bed: sine fallback") == 2


def test_bed_sine_mode_ignores_the_file(audio, tmp_path):
    track = tmp_path / "bed.wav"
    write_wav(track, [1000] * 8000)
    _, record = audio.choose_bed(0.5, file_cfg(mode="sine"), 8000, {"VIDEO_BED_FILE": str(track)})
    assert record == {"bed": "sine"}


def test_bed_mode_must_be_known(audio):
    with pytest.raises(SystemExit):
        audio.choose_bed(0.5, file_cfg(mode="mp3"), 8000, {})


def test_loud_file_bed_and_narration_are_not_clipped(audio, tmp_path):
    track = tmp_path / "bed.wav"
    write_wav(track, [32767, -32768] * 8000)
    line = tmp_path / "line.wav"
    write_wav(line, [32767, -32768] * 2000)
    board = json.loads((video_dir / "storyboard.json").read_text())
    cfg = dict(board["audio"], sample_rate=8000, bed=file_cfg(file_gain=1.0))
    manifest = {"audio": cfg, "segments": [
        {"id": "a", "kind": "card", "duration": 2, "voice": [{"at": 0.5, "wav": str(line), "text": "x", "sec": 0.5}]}]}
    pcm, _, _ = audio.soundtrack(manifest, {"VIDEO_BED_FILE": str(track)})
    assert max(abs(x) for x in pcm) < 32767


def test_cues_with_zero_gain_are_left_out(audio, monkeypatch):
    manifest = small_manifest()
    manifest["audio"]["bed"] = dict(manifest["audio"]["bed"], mode="sine", gain=0, bass_gain=0, shimmer_gain=0)
    for cue in manifest["audio"]["cues"].values():
        cue["gain"] = 0
    pcm, _, _ = audio.soundtrack(manifest, {})
    assert not any(pcm)
    manifest["audio"]["cues"]["tap"]["gain"] = 0.1
    pcm, rate, _ = audio.soundtrack(manifest, {})
    assert any(pcm[int(2.5 * rate):int(2.6 * rate)])


def test_remix_replaces_only_the_audio_block(tmp_path):
    remix = load("remix")
    manifest = {"canvas": {"fps": 30}, "segments": [{"id": "a", "duration": 1, "voice": [{"at": 0}]}],
                "audio": {"lufs": -14, "bed": {"mode": "sine"}}}
    board = {"audio": {"lufs": -14, "bed": {"mode": "file", "file_gain": 0.8}}, "shots": []}
    path, board_path = tmp_path / "manifest.json", tmp_path / "storyboard.json"
    path.write_text(json.dumps(manifest))
    board_path.write_text(json.dumps(board))
    remix.main(str(path), str(board_path))
    out = json.loads(path.read_text())
    assert out["audio"] == board["audio"]
    assert {k: v for k, v in out.items() if k != "audio"} == {k: v for k, v in manifest.items() if k != "audio"}
    assert remix.remix(out, board)[1] == []
    assert not (tmp_path / "manifest.json.tmp").exists()
