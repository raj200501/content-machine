"""Runtime configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    instagram_access_token: str = ""
    instagram_ig_user_id: str = ""
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    hf_token: str = ""
    timezone: str = "America/New_York"

    hf_video_model: str = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
    hf_image_model: str = "stabilityai/stable-diffusion-xl-base-1.0"
    enable_youtube_transcripts: bool = True
    enable_video_provider: bool = False
    enable_local_fallback: bool = True
    posts_per_day: int = 20
    # Manual runs: render and publish this many of today's next reels immediately,
    # ignoring their scheduled slots (0 = only publish what is due).
    publish_now_count: int = 0
    batch_render_size: int = 20
    dry_run: bool = True
    log_level: str = "INFO"
    publication_start_hour: int = 8
    publication_end_hour: int = 22

    database_path: Path = Path("output/content_machine.db")
    source_config_path: Path = Path("app/source_ingest/source_definitions.json")
    output_dir: Path = Path("output")
    assets_dir: Path = Path("assets")
    media_staging_dir: Path = Path("output/published/staged")
    turso_database_url: str = ""
    turso_auth_token: str = ""
    turso_sync_interval_seconds: int = 300

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    request_timeout_seconds: int = 25
    provider_timeout_seconds: int = 90
    max_source_items_per_ingest: int = 20
    meta_graph_api_version: str = "v24.0"
    public_media_base_url: str = ""
    user_agent: str = "content-machine/0.1 (+https://example.com/content-machine)"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_endpoint_url: str = ""
    r2_region: str = "auto"
    delete_staged_media_after_publish: bool = True

    # Voice: "auto" uses Kokoro when its model files exist, else the older chain.
    tts_engine: str = "auto"
    kokoro_model_path: str = ""
    kokoro_voices_path: str = ""
    kokoro_voice: str = "af_heart"
    kokoro_speed: float = 1.15
    voice_pause_after_hook: float = 0.32
    voice_pause_between_lines: float = 0.2
    # Soft generated music bed under the voice (no licensed audio needed).
    music_bed: bool = True
    music_bed_volume_db: float = -24.0
    render_fps: int = 30
    renderer: str = "motion"  # motion (frame-by-frame) | cards (old still cards)

    piper_model_path: str = ""
    piper_voice: str = "en_US-lessac-medium"
    piper_length_scale: float = 0.92
    macos_say_voice: str = "Samantha"
    linux_tts_voice: str = "en-us"
    enable_gtts_fallback: bool = False
    default_cta: str = "Follow for daily internship and new-grad reels."
    brand_handle: str = ""
    burn_subtitles: bool = False

    @field_validator("instagram_access_token", "instagram_ig_user_id", "instagram_app_id", "instagram_app_secret")
    @classmethod
    def _strip_credential_whitespace(cls, value: str) -> str:
        # Tokens and IDs never contain whitespace; copied values often pick up
        # line breaks or spaces where the token wrapped on screen.
        return "".join(str(value).split())

    @field_validator("posts_per_day", "batch_render_size")
    @classmethod
    def _validate_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator("publication_end_hour")
    @classmethod
    def _validate_end_hour(cls, value: int, info) -> int:
        start = info.data.get("publication_start_hour", 8)
        if value <= start:
            raise ValueError("publication_end_hour must be greater than publication_start_hour")
        return value

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def use_turso(self) -> bool:
        return bool(self.turso_database_url and self.turso_auth_token)

    @property
    def database_backend(self) -> str:
        return "turso" if self.use_turso else "sqlite"

    @property
    def use_r2_storage(self) -> bool:
        return bool(
            self.r2_account_id
            and self.r2_access_key_id
            and self.r2_secret_access_key
            and self.r2_bucket
        )

    @property
    def r2_s3_endpoint(self) -> str:
        if self.r2_endpoint_url:
            return self.r2_endpoint_url
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @property
    def publish_ready(self) -> bool:
        return bool(
            self.instagram_access_token
            and self.public_media_base_url
        )

    @property
    def turso_replica_path(self) -> Path:
        suffix = self.database_path.suffix or ".db"
        return self.database_path.with_name(f"{self.database_path.stem}_turso_replica{suffix}")

    @property
    def database_runtime_path(self) -> Path:
        return self.turso_replica_path if self.use_turso else self.database_path

    @property
    def draft_dir(self) -> Path:
        return self.output_dir / "drafts"

    @property
    def rendered_dir(self) -> Path:
        return self.output_dir / "rendered"

    @property
    def published_dir(self) -> Path:
        return self.output_dir / "published"

    @property
    def log_dir(self) -> Path:
        return self.output_dir / "logs"

    def ensure_directories(self) -> None:
        for path in (
            self.output_dir,
            self.draft_dir,
            self.rendered_dir,
            self.published_dir,
            self.media_staging_dir,
            self.log_dir,
            self.assets_dir,
            self.assets_dir / "backgrounds",
            self.assets_dir / "music",
            self.assets_dir / "logos",
            self.assets_dir / "fonts",
        ):
            path.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_runtime_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    settings = Settings()
    settings.ensure_directories()
    return settings
