from pathlib import Path

from app.config import Settings


def test_settings_ensure_directories(tmp_path: Path) -> None:
    settings = Settings(
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "output" / "state.db",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
    )
    settings.ensure_directories()

    assert settings.output_dir.exists()
    assert settings.assets_dir.exists()
    assert settings.database_path.parent.exists()
    assert settings.media_staging_dir.exists()
