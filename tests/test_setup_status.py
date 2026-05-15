from pathlib import Path

from app.config import Settings
from app.setup_status import build_setup_report


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "output_dir": tmp_path / "output",
        "assets_dir": tmp_path / "assets",
        "database_path": tmp_path / "db.sqlite",
        "media_staging_dir": tmp_path / "output" / "published" / "staged",
        "turso_database_url": "",
        "turso_auth_token": "",
    }
    values.update(overrides)
    return Settings(**values)


def test_setup_report_lists_missing_live_and_video_keys(tmp_path: Path) -> None:
    report = build_setup_report(_settings(tmp_path, enable_video_provider=True), check_binaries=False)

    assert report.ready_for_live_publish is False
    assert report.ready_for_github_automation is False
    assert report.ready_for_provider_video is False
    assert "INSTAGRAM_ACCESS_TOKEN" in report.missing_live_env_keys
    assert "PUBLIC_MEDIA_BASE_URL" in report.missing_live_env_keys
    assert report.missing_video_provider_env_keys == ("HF_TOKEN",)


def test_setup_report_detects_live_github_and_provider_readiness(tmp_path: Path) -> None:
    report = build_setup_report(
        _settings(
            tmp_path,
            dry_run=False,
            instagram_access_token="token",
            instagram_ig_user_id="ig_1",
            instagram_app_id="app_1",
            instagram_app_secret="secret",
            public_media_base_url="https://media.example.com",
            r2_account_id="account",
            r2_access_key_id="access",
            r2_secret_access_key="secret",
            r2_bucket="bucket",
            turso_database_url="libsql://example.turso.io",
            turso_auth_token="db-token",
            enable_video_provider=True,
            hf_token="hf-token",
        ),
        check_binaries=False,
    )

    assert report.ready_for_live_publish is True
    assert report.ready_for_github_automation is True
    assert report.ready_for_provider_video is True
    assert report.missing_live_env_keys == ()
    assert report.missing_r2_env_keys == ()
    assert report.missing_turso_env_keys == ()
    assert report.missing_video_provider_env_keys == ()
