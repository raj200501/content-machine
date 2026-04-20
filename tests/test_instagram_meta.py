from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.publishing.instagram_meta import InstagramMetaPublisher


class DummyResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


def test_instagram_meta_publish_flow(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(
        dry_run=False,
        instagram_access_token="token",
        instagram_ig_user_id="123",
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "db.sqlite",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
        public_media_base_url="https://cdn.example.com/reels",
        turso_database_url="",
        turso_auth_token="",
    )
    settings.ensure_directories()
    publisher = InstagramMetaPublisher(settings)
    render_path = tmp_path / "sample.mp4"
    render_path.write_bytes(b"video")

    calls = []

    def fake_request(method: str, url: str, timeout: int, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/123/media"):
            return DummyResponse({"id": "creation_1"})
        if url.endswith("/creation_1"):
            return DummyResponse({"status_code": "FINISHED"})
        if url.endswith("/123/media_publish"):
            return DummyResponse({"id": "media_1"})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(publisher.session, "request", fake_request)
    result = publisher.publish_reel(render_path, "caption", "sample reel")

    assert result["creation_id"] == "creation_1"
    assert result["instagram_media_id"] == "media_1"
    assert len(calls) == 3


def test_instagram_meta_r2_stage_and_cleanup(monkeypatch, tmp_path: Path) -> None:
    uploaded = []
    deleted = []

    class DummyS3Client:
        def upload_file(self, filename, bucket, key, ExtraArgs=None):
            uploaded.append((filename, bucket, key, ExtraArgs))

        def delete_object(self, Bucket, Key):
            deleted.append((Bucket, Key))

    settings = Settings(
        dry_run=False,
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "db.sqlite",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
        public_media_base_url="https://media.example.com",
        r2_account_id="acct",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
        r2_bucket="careerstacked-media",
        turso_database_url="",
        turso_auth_token="",
    )
    settings.ensure_directories()
    publisher = InstagramMetaPublisher(settings)
    monkeypatch.setattr(
        "app.publishing.instagram_meta.boto3",
        SimpleNamespace(client=lambda *args, **kwargs: DummyS3Client()),
    )

    render_path = tmp_path / "sample.mp4"
    render_path.write_bytes(b"video")

    staged_path, media_url, object_key = publisher.stage_media(render_path, "Sample Reel")
    assert staged_path.exists()
    assert media_url == "https://media.example.com/reels/sample-reel.mp4"
    assert object_key == "reels/sample-reel.mp4"
    assert uploaded and uploaded[0][1] == "careerstacked-media"

    publisher.cleanup_staged_media(staged_path, object_key)
    assert not staged_path.exists()
    assert deleted == [("careerstacked-media", "reels/sample-reel.mp4")]
