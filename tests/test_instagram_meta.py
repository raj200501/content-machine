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
        public_media_base_url="https://cdn.example.com",
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
    assert calls[0][2]["data"]["video_url"] == "https://cdn.example.com/reels/sample-reel.mp4"


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
        "app.publishing.instagram_meta._load_boto3",
        lambda: SimpleNamespace(client=lambda *args, **kwargs: DummyS3Client()),
    )

    render_path = tmp_path / "sample.mp4"
    render_path.write_bytes(b"video")

    staged_path, media_url, object_key = publisher.stage_media(render_path, "Sample Reel")
    assert staged_path.exists()
    assert staged_path == settings.media_staging_dir / "reels" / "sample-reel.mp4"
    assert media_url == "https://media.example.com/reels/sample-reel.mp4"
    assert object_key == "reels/sample-reel.mp4"
    assert uploaded and uploaded[0][0] == str(staged_path)
    assert uploaded[0][1] == "careerstacked-media"
    assert uploaded[0][2] == "reels/sample-reel.mp4"

    publisher.cleanup_staged_media(staged_path, object_key)
    assert not staged_path.exists()
    assert deleted == [("careerstacked-media", "reels/sample-reel.mp4")]


def test_instagram_meta_discovers_connected_accounts(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(
        instagram_access_token="token",
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "db.sqlite",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
        turso_database_url="",
        turso_auth_token="",
    )
    publisher = InstagramMetaPublisher(settings)

    def fake_request(method: str, url: str, timeout: int, **kwargs):
        assert method == "GET"
        assert url.endswith("/me/accounts")
        assert kwargs["params"]["access_token"] == "token"
        return DummyResponse(
            {
                "data": [
                    {
                        "id": "page_1",
                        "name": "Career Page",
                        "instagram_business_account": {
                            "id": "ig_1",
                            "username": "careerstacked",
                            "account_type": "BUSINESS",
                        },
                    },
                    {"id": "page_2", "name": "No Instagram"},
                ]
            }
        )

    monkeypatch.setattr(publisher.session, "request", fake_request)

    accounts = publisher.connected_instagram_accounts()

    assert accounts == [
        {
            "page_id": "page_1",
            "page_name": "Career Page",
            "instagram_ig_user_id": "ig_1",
            "username": "careerstacked",
            "account_type": "BUSINESS",
        }
    ]


def test_exchange_for_long_lived_token_returns_page_token(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(
        instagram_access_token="short",
        instagram_app_id="app",
        instagram_app_secret="secret",
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "db.sqlite",
        turso_database_url="",
        turso_auth_token="",
    )
    publisher = InstagramMetaPublisher(settings)

    def fake_request(method: str, url: str, timeout: int, **kwargs):
        if url.endswith("/oauth/access_token"):
            assert kwargs["params"]["fb_exchange_token"] == "short"
            return DummyResponse({"access_token": "long"})
        if url.endswith("/me/accounts"):
            assert kwargs["params"]["access_token"] == "long"
            return DummyResponse(
                {
                    "data": [
                        {"id": "p0", "name": "No IG", "access_token": "nope"},
                        {
                            "id": "p1",
                            "name": "Page",
                            "access_token": "page-token",
                            "instagram_business_account": {"id": "ig1", "username": "handle"},
                        },
                    ]
                }
            )
        raise AssertionError(url)

    monkeypatch.setattr(publisher.session, "request", fake_request)
    result = publisher.exchange_for_long_lived_token()
    assert result["page_token"] == "page-token"
    assert result["instagram_ig_user_id"] == "ig1"


def test_meta_errors_include_message(monkeypatch, tmp_path: Path) -> None:
    import pytest

    from app.publishing.instagram_meta import MetaAPIError

    settings = Settings(instagram_access_token="t", instagram_ig_user_id="1", turso_database_url="", turso_auth_token="")
    publisher = InstagramMetaPublisher(settings)

    class ErrorResponse(DummyResponse):
        def __init__(self) -> None:
            super().__init__({"error": {"type": "OAuthException", "code": 190, "message": "Token expired"}})
            self.status_code = 400

    monkeypatch.setattr(publisher.session, "request", lambda *a, **k: ErrorResponse())
    with pytest.raises(MetaAPIError, match="Token expired"):
        publisher.create_media_container("https://x/y.mp4", "c")
