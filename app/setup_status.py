"""Setup readiness checks for external integrations."""

from __future__ import annotations

from dataclasses import dataclass
from shutil import which

from app.config import Settings


LIVE_PUBLISH_ENV = (
    "INSTAGRAM_ACCESS_TOKEN",
    "INSTAGRAM_IG_USER_ID",
    "INSTAGRAM_APP_ID",
    "INSTAGRAM_APP_SECRET",
    "PUBLIC_MEDIA_BASE_URL",
)

R2_ENV = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
)

TURSO_ENV = (
    "TURSO_DATABASE_URL",
    "TURSO_AUTH_TOKEN",
)

VIDEO_PROVIDER_ENV = (
    "HF_TOKEN",
    "HF_VIDEO_MODEL",
    "HF_IMAGE_MODEL",
)


@dataclass(frozen=True)
class SetupCheck:
    """One setup check row."""

    category: str
    name: str
    status: str
    detail: str
    keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class SetupReport:
    """Aggregated integration readiness."""

    checks: tuple[SetupCheck, ...]
    missing_live_env_keys: tuple[str, ...]
    missing_r2_env_keys: tuple[str, ...]
    missing_turso_env_keys: tuple[str, ...]
    missing_video_provider_env_keys: tuple[str, ...]
    ready_for_live_publish: bool
    ready_for_github_automation: bool
    ready_for_provider_video: bool
    dry_run: bool


def _setting_name(env_key: str) -> str:
    return env_key.lower()


def _is_configured(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _missing_env(settings: Settings, env_keys: tuple[str, ...]) -> tuple[str, ...]:
    missing: list[str] = []
    for env_key in env_keys:
        if not _is_configured(getattr(settings, _setting_name(env_key), "")):
            missing.append(env_key)
    return tuple(missing)


def build_setup_report(settings: Settings, *, check_binaries: bool = True) -> SetupReport:
    """Return a no-secret report of setup gaps and integration readiness."""

    missing_live = _missing_env(settings, LIVE_PUBLISH_ENV)
    missing_r2 = _missing_env(settings, R2_ENV)
    missing_turso = _missing_env(settings, TURSO_ENV)
    missing_video = _missing_env(settings, VIDEO_PROVIDER_ENV) if settings.enable_video_provider else ()

    checks: list[SetupCheck] = []

    if check_binaries:
        ffmpeg_ok = which(settings.ffmpeg_binary) is not None
        ffprobe_ok = which(settings.ffprobe_binary) is not None
        checks.append(
            SetupCheck(
                "runtime",
                "ffmpeg",
                "ok" if ffmpeg_ok else "missing",
                f"{settings.ffmpeg_binary} is available"
                if ffmpeg_ok
                else f"{settings.ffmpeg_binary} was not found on PATH",
                ("FFMPEG_BINARY",),
            )
        )
        checks.append(
            SetupCheck(
                "runtime",
                "ffprobe",
                "ok" if ffprobe_ok else "missing",
                f"{settings.ffprobe_binary} is available"
                if ffprobe_ok
                else f"{settings.ffprobe_binary} was not found on PATH",
                ("FFPROBE_BINARY",),
            )
        )

    checks.append(
        SetupCheck(
            "database",
            "state backend",
            "ok" if not missing_turso else "fallback",
            "Turso/libSQL is configured"
            if not missing_turso
            else "SQLite local state is active; Turso keys are incomplete",
            TURSO_ENV,
        )
    )

    checks.append(
        SetupCheck(
            "publishing",
            "dry run",
            "fallback" if settings.dry_run else "ok",
            "Publishing is simulated" if settings.dry_run else "Live publishing is enabled",
            ("DRY_RUN",),
        )
    )

    checks.append(
        SetupCheck(
            "publishing",
            "Instagram / Meta",
            "ok" if not missing_live else "missing",
            "Meta publishing credentials and public media URL are configured"
            if not missing_live
            else "Missing: " + ", ".join(missing_live),
            LIVE_PUBLISH_ENV,
        )
    )

    checks.append(
        SetupCheck(
            "publishing",
            "R2 media hosting",
            "ok" if not missing_r2 else "missing",
            "Cloudflare R2 upload settings are configured"
            if not missing_r2
            else "Missing for unattended GitHub publishing: " + ", ".join(missing_r2),
            R2_ENV,
        )
    )

    if settings.enable_video_provider:
        checks.append(
            SetupCheck(
                "video",
                "Hugging Face provider",
                "ok" if not missing_video else "fallback",
                f"Provider video enabled with model {settings.hf_video_model}"
                if not missing_video
                else "Provider video will be skipped until: " + ", ".join(missing_video),
                VIDEO_PROVIDER_ENV,
            )
        )
    else:
        checks.append(
            SetupCheck(
                "video",
                "Hugging Face provider",
                "disabled",
                "ENABLE_VIDEO_PROVIDER is false",
                ("ENABLE_VIDEO_PROVIDER",),
            )
        )

    checks.append(
        SetupCheck(
            "video",
            "local fallback renderer",
            "ok" if settings.enable_local_fallback else "missing",
            "Local FFmpeg/Pillow rendering is enabled"
            if settings.enable_local_fallback
            else "ENABLE_LOCAL_FALLBACK is false; renders require the provider",
            ("ENABLE_LOCAL_FALLBACK",),
        )
    )

    ready_for_live = not missing_live and not settings.dry_run
    ready_for_github = ready_for_live and not missing_r2 and not missing_turso
    ready_for_provider_video = settings.enable_video_provider and not missing_video

    return SetupReport(
        checks=tuple(checks),
        missing_live_env_keys=missing_live,
        missing_r2_env_keys=missing_r2,
        missing_turso_env_keys=missing_turso,
        missing_video_provider_env_keys=missing_video,
        ready_for_live_publish=ready_for_live,
        ready_for_github_automation=ready_for_github,
        ready_for_provider_video=ready_for_provider_video,
        dry_run=settings.dry_run,
    )
