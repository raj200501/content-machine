import json
import subprocess
from pathlib import Path

from app.config import Settings
from app.media.reel_renderer import caption_chunks, plan_scenes, render_reel
from app.media.voice import TimedLine, TimedWord, _say_money


def test_money_is_spoken_naturally() -> None:
    assert _say_money("The posting lists $47–$58/hr.") == "The posting lists 47 to 58 dollars an hour."
    assert _say_money("up to $120K/yr") == "up to 120 thousand dollars a year"


def test_caption_chunks_break_on_punctuation_and_length() -> None:
    words = [TimedWord(w, i * 0.2, i * 0.2 + 0.2) for i, w in enumerate("Stripe: machine learning engineer intern in San Francisco.".split())]
    chunks = caption_chunks(words)
    assert chunks[0] == [0]  # "Stripe:" stands alone
    assert all(len(chunk) <= 4 for chunk in chunks)


def test_scene_plan_uses_metadata_and_numbers_points() -> None:
    lines = [TimedLine(f"line {i}", i, i + 1, i + 0.8, []) for i in range(5)]
    row = {"metadata_json": json.dumps({"scenes": [{"kind": "hook"}, {"kind": "job", "company": "Stripe"}, {"kind": "point"}, {"kind": "point"}, {"kind": "cta"}]})}
    scenes = plan_scenes(row, lines)
    assert [s.kind for s in scenes] == ["hook", "job", "point", "point", "cta"]
    assert scenes[3].data["number"] == 2 and scenes[3].data["total"] == 2


def test_render_reel_produces_vertical_video_with_audio(tmp_path: Path) -> None:
    # Low fps and the silent voice keep this fast; the real pipeline uses Kokoro at 30 fps.
    settings = Settings(output_dir=tmp_path, assets_dir=tmp_path / "assets", tts_engine="silent", render_fps=4, music_bed=True)
    row = {
        "id": 1,
        "full_script": "Stripe and Figma are hiring interns.\nStripe: Software Engineer Intern in San Francisco. The posting lists $47–$58/hr.\nSend this to a friend.",
        "metadata_json": json.dumps({"scenes": [{"kind": "hook", "companies": ["Stripe", "Figma"]}, {"kind": "job", "company": "Stripe", "role": "Software Engineer Intern", "location": "San Francisco", "pay": "$47–$58/hr", "posted_days": 1}, {"kind": "cta"}]}),
        "category": "openings_job_alert",
        "script_date": "2026-11-07",
    }
    artifact = render_reel(settings, row, tmp_path)
    assert artifact.video_path.exists() and artifact.subtitle_path.exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(artifact.video_path)],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert any(s["codec_type"] == "audio" for s in streams)
    assert artifact.metadata["thumb_offset_ms"] > 0


def test_captured_postings_open_on_the_pay(tmp_path: Path, monkeypatch) -> None:
    from PIL import Image

    import app.media.page_capture as page_capture
    from app.media.page_capture import PageCapture
    from app.media.reel_renderer import _posting_frame, attach_captures

    def fake_capture(jobs, out_dir, timeout_ms=30000):
        out_dir.mkdir(parents=True, exist_ok=True)
        result = {}
        for index, _job in enumerate(jobs):
            path = out_dir / f"page_{index}.png"
            Image.new("RGB", (1080, 3000), (255, 255, 255)).save(path)
            # Pay wraps onto two lines, like most real postings.
            result[index] = PageCapture(path, 3000, (40, 300, 900, 80), (40, 1200, 1000, 120), [(700, 1200, 340, 50), (40, 1260, 300, 50)])
        return result

    monkeypatch.setattr(page_capture, "capture_pages", fake_capture)
    settings = Settings(output_dir=tmp_path, assets_dir=tmp_path / "assets")
    lines = [TimedLine(f"line {i}", i * 2.0, i * 2.0 + 2, i * 2.0 + 1.8, []) for i in range(4)]
    row = {"metadata_json": json.dumps({"scenes": [
        {"kind": "hook", "focus_job": 1},
        {"kind": "job", "company": "A", "url": "https://job-boards.greenhouse.io/a/jobs/1"},
        {"kind": "job", "company": "B", "url": "https://jobs.lever.co/b/2"},
        {"kind": "cta"},
    ]})}
    scenes = plan_scenes(row, lines)
    attach_captures(scenes, settings, tmp_path)
    hook, _first, second, cta = scenes
    assert hook.hold_on_pay and hook.page is second.page
    assert hook.page_pay_rects and len(hook.page_pay_rects) == 2
    assert cta.hook_bg is not None
    frame = _posting_frame(hook, 0.0)
    assert frame.size == (1080, 1920)
    # The highlight is already on at the very first frame (yellow tint somewhere).
    pixels = frame.convert("RGB").getdata()
    assert any(r > 240 and 200 < g < 235 and b < 100 for r, g, b in pixels)
