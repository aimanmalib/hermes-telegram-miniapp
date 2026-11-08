"""The demo video's storyboard and frame layout (scripts/video/): no browser or Hermes needed."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

video_dir = Path(__file__).resolve().parent.parent / "scripts" / "video"


@pytest.fixture(scope="module")
def frames():
    spec = importlib.util.spec_from_file_location("video_frames", video_dir / "frames.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def board():
    return json.loads((video_dir / "storyboard.json").read_text())


def test_storyboard_fits_an_x_video(board):
    # X takes up to 140 s; the entry asks for under 90 s. Fades sit inside each shot, so this is the length.
    assert sum(s["duration"] for s in board["shots"]) <= 89.5
    assert len({s["id"] for s in board["shots"]}) == len(board["shots"])
    for shot in board["shots"]:
        assert shot["kind"] in {"card", "mock", "app"}
        assert shot["duration"] > 2 * board["fade_sec"]
        assert shot.get("caption") or shot.get("lines")


def test_mock_screen_is_labelled(board):
    for shot in board["shots"]:
        if shot["kind"] == "mock":
            assert shot["mock"]["label"].strip()


def test_phone_screen_keeps_the_viewport_ratio_and_fits(frames, board):
    screen, outer = frames.phone_box(board)
    assert screen["w"] % 2 == 0 and screen["h"] % 2 == 0
    assert abs(screen["h"] / screen["w"] - 844 / 390) < 0.01
    assert outer["x"] >= 0 and outer["x"] + outer["w"] <= board["canvas"]["width"]
    assert outer["y"] > 0 and outer["y"] + outer["h"] <= board["canvas"]["height"]
    assert screen["x"] - outer["x"] == board["phone"]["bezel"]


def test_live_caption_needs_a_live_rig(frames):
    shot = {"id": "s", "caption": "Live from Hermes v{hermes_version}", "needs_live": True}
    assert frames.caption_text(shot, {"live": True, "hermes_version": "0.23.0"}) == "Live from Hermes v0.23.0"
    with pytest.raises(SystemExit):
        frames.caption_text(shot, {"live": False, "hermes_version": "0.23.0"})
    with pytest.raises(SystemExit):
        frames.caption_text(shot, {})


def test_plain_caption_does_not_need_a_rig(frames):
    assert frames.caption_text({"id": "s", "caption": "Read logs."}, {}) == "Read logs."


def test_cards_escape_text(frames, board):
    shot = {"id": "close", "lines": ["<b>repo</b>", "a & b"]}
    out = frames.card_html(shot, board)
    assert "&lt;b&gt;repo&lt;/b&gt;" in out and "a &amp; b" in out
