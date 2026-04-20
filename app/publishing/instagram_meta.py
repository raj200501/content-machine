"""Official Meta / Instagram publishing adapter."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from urllib.parse import quote

import requests

from app.config import Settings
from app.retry_utils import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from app.utils import ensure_directory, slugify

try:  # pragma: no cover - optional dependency in some test envs.
    import boto3
except Exception:  # pragma: no cover
    boto3 = None


class InstagramMetaPublisher:
    """Publish reels through the official Content Publishing API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()

    @property
    def base_url(self) -> str:
        return f"https://graph.facebook.com/{self.settings.meta_graph_api_version}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=12),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _request(self, method: str, path: str, **kwargs) -> dict:
        response = self.session.request(
            method,
            f"{self.base_url}/{path.lstrip('/')}",
            timeout=self.settings.request_timeout_seconds,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def _object_key(self, staged_name: str) -> str:
        return f"reels/{staged_name}"

    def _r2_client(self):
        if boto3 is None:
            raise RuntimeError("boto3 is required for R2 uploads. Install project dependencies first.")
        if not self.settings.use_r2_storage:
            raise RuntimeError("R2 storage is not configured")
        return boto3.client(
            "s3",
            endpoint_url=self.settings.r2_s3_endpoint,
            aws_access_key_id=self.settings.r2_access_key_id,
            aws_secret_access_key=self.settings.r2_secret_access_key,
            region_name=self.settings.r2_region,
        )

    def _upload_r2_object(self, staged_path: Path, object_key: str) -> None:
        client = self._r2_client()
        extra_args = {"ContentType": "video/mp4" if staged_path.suffix.lower() == ".mp4" else "application/octet-stream"}
        client.upload_file(str(staged_path), self.settings.r2_bucket, object_key, ExtraArgs=extra_args)

    def _delete_r2_object(self, object_key: str) -> None:
        client = self._r2_client()
        client.delete_object(Bucket=self.settings.r2_bucket, Key=object_key)

    def stage_media(self, render_path: Path, slug: str) -> tuple[Path, str, str]:
        staged_dir = ensure_directory(self.settings.media_staging_dir)
        staged_path = staged_dir / f"{slugify(slug)}{render_path.suffix}"
        shutil.copy2(render_path, staged_path)
        object_key = self._object_key(staged_path.name)
        if self.settings.use_r2_storage and not self.settings.dry_run:
            self._upload_r2_object(staged_path, object_key)
        if not self.settings.public_media_base_url:
            if self.settings.dry_run:
                return staged_path, f"https://example.invalid/{quote(object_key)}", object_key
            raise ValueError("PUBLIC_MEDIA_BASE_URL is required for live Meta publishing")
        media_url = self.settings.public_media_base_url.rstrip("/") + "/" + quote(object_key)
        return staged_path, media_url, object_key

    def cleanup_staged_media(self, staged_path: Path, object_key: str) -> None:
        if self.settings.delete_staged_media_after_publish and self.settings.use_r2_storage:
            self._delete_r2_object(object_key)
        if self.settings.delete_staged_media_after_publish and staged_path.exists():
            staged_path.unlink(missing_ok=True)

    def create_media_container(self, video_url: str, caption: str) -> str:
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": self.settings.instagram_access_token,
        }
        data = self._request("POST", f"{self.settings.instagram_ig_user_id}/media", data=payload)
        return str(data["id"])

    def poll_until_ready(self, creation_id: str, timeout_seconds: int = 600, interval_seconds: int = 10) -> dict:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            data = self._request(
                "GET",
                creation_id,
                params={
                    "fields": "status,status_code",
                    "access_token": self.settings.instagram_access_token,
                },
            )
            status_code = str(data.get("status_code", "")).upper()
            if status_code == "FINISHED":
                return data
            if status_code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Meta container failed: {data}")
            time.sleep(interval_seconds)
        raise TimeoutError(f"Timed out waiting for Meta media container {creation_id}")

    def publish_container(self, creation_id: str) -> str:
        data = self._request(
            "POST",
            f"{self.settings.instagram_ig_user_id}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": self.settings.instagram_access_token,
            },
        )
        return str(data["id"])

    def publish_reel(self, render_path: Path, caption: str, slug: str) -> dict:
        staged_path, media_url, object_key = self.stage_media(render_path, slug)
        if self.settings.dry_run:
            return {
                "mode": "dry_run",
                "staged_path": str(staged_path),
                "media_url": media_url,
                "storage_key": object_key,
                "creation_id": f"dryrun_creation_{slugify(slug)}",
                "instagram_media_id": f"dryrun_media_{slugify(slug)}",
            }

        creation_id = self.create_media_container(media_url, caption)
        container_status = self.poll_until_ready(creation_id)
        media_id = self.publish_container(creation_id)
        result = {
            "mode": "live",
            "staged_path": str(staged_path),
            "media_url": media_url,
            "storage_key": object_key,
            "creation_id": creation_id,
            "container_status": container_status,
            "instagram_media_id": media_id,
        }
        try:
            self.cleanup_staged_media(staged_path, object_key)
        except Exception as exc:  # pragma: no cover - cleanup should not void successful publish.
            result["cleanup_error"] = str(exc)
        return result
