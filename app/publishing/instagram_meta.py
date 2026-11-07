"""Official Meta / Instagram publishing adapter."""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from urllib.parse import quote

import requests

from app.config import Settings
from app.retry_utils import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from app.utils import ensure_directory, slugify


def _load_boto3():
    try:  # pragma: no cover - optional dependency in some test envs.
        import boto3
    except Exception:  # pragma: no cover
        return None
    return boto3


LOG = logging.getLogger(__name__)


class MetaAPIError(RuntimeError):
    """A non-retryable 4xx response from the Graph API."""


class InstagramMetaPublisher:
    """Publish reels through the official Content Publishing API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self._publish_credentials: tuple[str, str] | None = None
        self._followers: int | None = None

    def publish_credentials(self) -> tuple[str, str]:
        """Return (access_token, ig_user_id) to publish with.

        If INSTAGRAM_IG_USER_ID is set, INSTAGRAM_ACCESS_TOKEN is used as-is (a Page
        token). Otherwise INSTAGRAM_ACCESS_TOKEN is treated as a (long-lived) user
        token: the Page connected to the Instagram Professional account is looked up
        and its Page token and Instagram user ID are used. That way only a single
        GitHub secret is needed.
        """

        if self._publish_credentials is not None:
            return self._publish_credentials
        token = self.settings.instagram_access_token
        if not token:
            raise RuntimeError("INSTAGRAM_ACCESS_TOKEN is required for live publishing")
        if self.settings.instagram_ig_user_id:
            self._publish_credentials = (token, self.settings.instagram_ig_user_id)
            return self._publish_credentials
        pages = self._request(
            "GET",
            "me/accounts",
            params={
                "fields": "id,name,access_token,instagram_business_account{id,username}",
                "access_token": token,
            },
        )
        for page in pages.get("data", []):
            instagram = page.get("instagram_business_account") or {}
            if instagram.get("id") and page.get("access_token"):
                self._publish_credentials = (str(page["access_token"]), str(instagram["id"]))
                return self._publish_credentials
        raise RuntimeError(
            "No Facebook Page with a connected Instagram Professional account was found for "
            "INSTAGRAM_ACCESS_TOKEN. Link the Instagram account to a Page (Instagram app → "
            "Edit profile → Facebook → Connect) or set INSTAGRAM_IG_USER_ID."
        )

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
        if response.status_code >= 400:
            # Surface Meta's error message (never the token) instead of a bare HTTP code.
            try:
                error = response.json().get("error", {})
                detail = f"{error.get('type', '')} {error.get('code', '')}: {error.get('message', '')}".strip()
            except ValueError:
                detail = response.text[:300]
            if response.status_code < 500:
                raise MetaAPIError(f"Meta API {response.status_code} on {path.split('?')[0]}: {detail}")
            response.raise_for_status()
        return response.json()

    def exchange_for_long_lived_token(self, short_lived_token: str | None = None) -> dict[str, str]:
        """Swap a short-lived Graph API Explorer token for long-lived credentials.

        Returns the 60-day user token and, for each connected Page, a Page token.
        Page tokens minted from a long-lived user token do not expire, which makes
        them the right value for unattended GitHub Actions publishing.
        """

        token = short_lived_token or self.settings.instagram_access_token
        if not (token and self.settings.instagram_app_id and self.settings.instagram_app_secret):
            raise RuntimeError("INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET are required")
        data = self._request(
            "GET",
            "oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self.settings.instagram_app_id,
                "client_secret": self.settings.instagram_app_secret,
                "fb_exchange_token": token,
            },
        )
        long_lived = str(data["access_token"])
        pages = self._request(
            "GET",
            "me/accounts",
            params={
                "fields": "id,name,access_token,instagram_business_account{id,username}",
                "access_token": long_lived,
            },
        )
        result = {"user_token": long_lived}
        for page in pages.get("data", []):
            instagram = page.get("instagram_business_account") or {}
            if instagram.get("id") and page.get("access_token"):
                result.setdefault("page_token", str(page["access_token"]))
                result.setdefault("instagram_ig_user_id", str(instagram["id"]))
                result.setdefault("username", str(instagram.get("username", "")))
                result.setdefault("page_name", str(page.get("name", "")))
        return result

    def _object_key(self, staged_name: str) -> str:
        return f"reels/{staged_name}"

    def _r2_client(self):
        boto3_module = _load_boto3()
        if boto3_module is None:
            raise RuntimeError("boto3 is required for R2 uploads. Install project dependencies first.")
        if not self.settings.use_r2_storage:
            raise RuntimeError("R2 storage is not configured")
        return boto3_module.client(
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
        staged_name = f"{slugify(slug)}{render_path.suffix}"
        object_key = self._object_key(staged_name)
        staged_path = ensure_directory(self.settings.media_staging_dir) / object_key
        ensure_directory(staged_path.parent)
        shutil.copy2(render_path, staged_path)
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

    def followers_count(self) -> int | None:
        """Current follower count (used to decide when Trial Reels are available)."""

        if self._followers is not None:
            return self._followers
        try:
            token, ig_user_id = self.publish_credentials()
            data = self._request("GET", ig_user_id, params={"fields": "followers_count", "access_token": token})
            self._followers = int(data.get("followers_count", 0))
        except Exception as exc:
            LOG.warning("Could not read follower count: %s", exc)
            self._followers = None
        return self._followers

    def use_trial_reel(self, category: str | None) -> bool:
        if self.settings.trial_reels != "auto" or not category:
            return False
        if category not in {c.strip() for c in self.settings.trial_reel_categories.split(",") if c.strip()}:
            return False
        followers = self.followers_count()
        return followers is not None and followers >= self.settings.trial_reels_min_followers

    def create_media_container(
        self,
        video_url: str,
        caption: str,
        thumb_offset_ms: int | None = None,
        trial: bool = False,
    ) -> str:
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
        }
        optional: dict[str, str] = {}
        if thumb_offset_ms is not None:
            # Cover frame: the moment the hook is fully on screen.
            optional["thumb_offset"] = str(int(thumb_offset_ms))
        if self.settings.label_ai_generated:
            # The voice is synthetic; Meta asks for realistic synthetic audio to be disclosed.
            optional["is_ai_generated"] = "true"
        if trial:
            # Shown to non-followers first; shared to followers automatically if it performs.
            optional["trial_params"] = json.dumps({"graduation_strategy": "SS_PERFORMANCE"})
        token, ig_user_id = self.publish_credentials()
        try:
            data = self._request("POST", f"{ig_user_id}/media", data={**payload, **optional, "access_token": token})
        except MetaAPIError as exc:
            if not optional or " 190" in str(exc):
                raise
            # An optional field was rejected (or the account is not eligible for
            # it); never let that block the post.
            LOG.warning("Container rejected with optional fields %s (%s); retrying without them", sorted(optional), exc)
            data = self._request("POST", f"{ig_user_id}/media", data={**payload, "access_token": token})
        return str(data["id"])

    def connected_instagram_accounts(self) -> list[dict[str, str]]:
        """Return Professional Instagram accounts connected to the token's Pages."""

        if not self.settings.instagram_access_token:
            raise RuntimeError("INSTAGRAM_ACCESS_TOKEN is required to discover connected Instagram accounts")

        data = self._request(
            "GET",
            "me/accounts",
            params={
                "fields": "id,name,instagram_business_account{id,username,account_type}",
                "access_token": self.settings.instagram_access_token,
            },
        )
        accounts: list[dict[str, str]] = []
        for page in data.get("data", []):
            instagram_account = page.get("instagram_business_account") or {}
            instagram_id = instagram_account.get("id")
            if not instagram_id:
                continue
            accounts.append(
                {
                    "page_id": str(page.get("id", "")),
                    "page_name": str(page.get("name", "")),
                    "instagram_ig_user_id": str(instagram_id),
                    "username": str(instagram_account.get("username", "")),
                    "account_type": str(instagram_account.get("account_type", "")),
                }
            )
        return accounts

    def poll_until_ready(self, creation_id: str, timeout_seconds: int = 600, interval_seconds: int = 10) -> dict:
        token, _ = self.publish_credentials()
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            data = self._request(
                "GET",
                creation_id,
                params={
                    "fields": "status,status_code",
                    "access_token": token,
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
        token, ig_user_id = self.publish_credentials()
        data = self._request(
            "POST",
            f"{ig_user_id}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": token,
            },
        )
        return str(data["id"])

    def publish_carousel(self, slide_paths: list[Path], caption: str, slug: str) -> dict:
        """Publish an image carousel (2-10 JPEG slides)."""

        staged = [self.stage_media(path, f"{slug}-{index:02d}") for index, path in enumerate(slide_paths, start=1)]
        if self.settings.dry_run:
            return {
                "mode": "dry_run",
                "format": "carousel",
                "media_url": staged[0][1] if staged else "",
                "storage_key": staged[0][2] if staged else "",
                "creation_id": f"dryrun_carousel_{slugify(slug)}",
                "instagram_media_id": f"dryrun_media_{slugify(slug)}",
            }
        token, ig_user_id = self.publish_credentials()
        children = []
        for _path, url, _key in staged:
            data = self._request(
                "POST",
                f"{ig_user_id}/media",
                data={"image_url": url, "is_carousel_item": "true", "access_token": token},
            )
            children.append(str(data["id"]))
        for child in children:
            self.poll_until_ready(child, timeout_seconds=180, interval_seconds=3)
        data = self._request(
            "POST",
            f"{ig_user_id}/media",
            data={"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption, "access_token": token},
        )
        creation_id = str(data["id"])
        container_status = self.poll_until_ready(creation_id, timeout_seconds=300, interval_seconds=5)
        media_id = self.publish_container(creation_id)
        result = {
            "mode": "live",
            "format": "carousel",
            "media_url": staged[0][1],
            "storage_key": staged[0][2],
            "creation_id": creation_id,
            "container_status": container_status,
            "instagram_media_id": media_id,
        }
        for staged_path, _url, object_key in staged:
            try:
                self.cleanup_staged_media(staged_path, object_key)
            except Exception as exc:  # pragma: no cover
                result["cleanup_error"] = str(exc)
        return result

    def publish_reel(
        self,
        render_path: Path,
        caption: str,
        slug: str,
        thumb_offset_ms: int | None = None,
        category: str | None = None,
    ) -> dict:
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

        trial = self.use_trial_reel(category)
        creation_id = self.create_media_container(media_url, caption, thumb_offset_ms, trial=trial)
        container_status = self.poll_until_ready(creation_id)
        media_id = self.publish_container(creation_id)
        result = {
            "mode": "live",
            "staged_path": str(staged_path),
            "media_url": media_url,
            "storage_key": object_key,
            "creation_id": creation_id,
            "container_status": container_status,
            "trial_reel": trial,
            "instagram_media_id": media_id,
        }
        try:
            self.cleanup_staged_media(staged_path, object_key)
        except Exception as exc:  # pragma: no cover - cleanup should not void successful publish.
            result["cleanup_error"] = str(exc)
        return result
