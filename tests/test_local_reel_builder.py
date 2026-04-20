from pathlib import Path

import pytest

pytest.importorskip("PIL")

from app.config import Settings
from app.media.local_reel_builder import LocalFallbackReelBuilder
from app.utils import command_exists


@pytest.mark.skipif(not (command_exists("ffmpeg") and command_exists("ffprobe")), reason="ffmpeg not installed")
def test_local_reel_builder_creates_artifacts(tmp_path: Path) -> None:
    settings = Settings(
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "db.sqlite",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
        turso_database_url="",
        turso_auth_token="",
    )
    settings.ensure_directories()
    builder = LocalFallbackReelBuilder(settings)
    script = "\n".join(
        [
            "Three early-career tech roles worth checking today.",
            "Company one has a public internship listing worth reading closely.",
            "Company two has a new grad software role posted on its public board.",
            "Batch similar applications so your resume and recruiter note stay aligned.",
            "Save this and send it to a friend who's applying.",
        ]
    )

    artifact = builder.render(1, script, tmp_path / "renders")

    assert artifact.video_path.exists()
    assert artifact.audio_path.exists()
    assert artifact.subtitle_path.exists()
    assert artifact.duration_seconds >= 10
