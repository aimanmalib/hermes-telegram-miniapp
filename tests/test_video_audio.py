"""The demo video's soundtrack/subtitle writer and the rig's Bot API stand-in (scripts/video/): no ffmpeg, browser
or Hermes needed."""

from __future__ import annotations

import importlib.util
import json
import wave
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


def test_soundtrack_is_full_length_and_not_clipped(audio, tmp_path):
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
