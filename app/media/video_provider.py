"""Provider orchestration with automatic local fallback."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.media.audio_tts import synthesize_audio
from app.media.compositor import compose_with_background_video
from app.media.hf_provider import HFProvider
from app.media.local_reel_builder import LocalFallbackReelBuilder
from app.media.reel_renderer import render_carousel, render_reel
from app.media.subtitles import write_srt
from app.models import RenderArtifact
from app.utils import ensure_directory, hash_text, slugify


def _music_path(settings: Settings) -> Path | None:
    for pattern in ("*.mp3", "*.wav", "*.m4a"):
        matches = list((settings.assets_dir / "music").glob(pattern))
        if matches:
            return matches[0]
    return None


def _provider_prompt(script_row: dict) -> str:
    return (
        "Vertical cinematic b-roll for an Instagram career reel. "
        "Topic: early-career tech internships and new-grad roles. "
        f"Hook: {script_row['hook']} "
        f"Script: {script_row['full_script']}"
    )


def render_with_fallback(settings: Settings, script_row: dict, output_root: Path) -> RenderArtifact:
    """Try provider-generated visuals first, then fall back to the local reel builder."""

    ensure_directory(output_root)
    if (script_row.get("category") or "") == "jobs_roundup":
        return render_carousel(settings, script_row, output_root)
    from app.utils import json_loads
    from app.writing.formats import STUDIO_FORMATS

    metadata = json_loads(script_row.get("metadata_json"), default={}) or {}
    if metadata.get("format") in STUDIO_FORMATS:
        from app.media.studio import render_studio

        return render_studio(settings, script_row, output_root)
    slug = slugify(f"{script_row['id']}-{hash_text(script_row['hook'])[:8]}")
    provider_error = None

    if settings.enable_video_provider and settings.hf_token:
        provider_work = ensure_directory(output_root / slug)
        try:
            provider = HFProvider(settings)
            background_video = provider_work / "provider_visual.mp4"
            metadata = provider.generate_video(_provider_prompt(script_row), background_video)
            audio_path, duration_seconds, engine = synthesize_audio(
                script_row["full_script"],
                provider_work,
                "voiceover",
                settings,
            )
            subtitle_path = write_srt(script_row["full_script"], provider_work / "captions.srt", duration_seconds)
            final_path = output_root / f"{slug}.mp4"
            compose_with_background_video(
                settings.ffmpeg_binary,
                background_video,
                audio_path,
                subtitle_path,
                final_path,
                duration_seconds,
                _music_path(settings),
            )
            return RenderArtifact(
                script_id=script_row["id"],
                provider="huggingface",
                video_path=final_path,
                audio_path=audio_path,
                subtitle_path=subtitle_path,
                duration_seconds=duration_seconds,
                metadata={**metadata, "tts_engine": engine},
                fallback_used=False,
            )
        except Exception as exc:
            provider_error = str(exc)

    if not settings.enable_local_fallback:
        raise RuntimeError(f"provider render failed and local fallback disabled: {provider_error}")

    if settings.renderer == "cards":  # the previous still-card renderer, kept as a fallback
        artifact = LocalFallbackReelBuilder(settings).render(
            script_row["id"],
            script_row["full_script"],
            output_root,
            prompt_hint=script_row["hook"],
            category=script_row.get("category", "") or "",
        )
    else:
        artifact = render_reel(settings, script_row, output_root)
    if provider_error:
        artifact.metadata["provider_error"] = provider_error
    return artifact
