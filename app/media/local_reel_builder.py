"""Fully local reel renderer."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.media.audio_tts import synthesize_audio
from app.media.compositor import burn_subtitles, concat_clips, create_scene_clip, mux_audio
from app.media.subtitles import write_srt
from app.models import RenderArtifact
from app.utils import ensure_directory, hash_text, slugify


class LocalFallbackReelBuilder:
    """Build a vertical MP4 reel with text cards, voiceover, and captions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _music_path(self) -> Path | None:
        for pattern in ("*.mp3", "*.wav", "*.m4a"):
            matches = list((self.settings.assets_dir / "music").glob(pattern))
            if matches:
                return matches[0]
        return None

    def render(self, script_id: int, script_text: str, output_root: Path, prompt_hint: str = "") -> RenderArtifact:
        try:
            from app.media.image_scene_builder import build_scene_image
        except ModuleNotFoundError as exc:  # pragma: no cover - requires missing Pillow.
            raise RuntimeError("Pillow is required for local reel rendering. Install dependencies first.") from exc

        slug = slugify(f"{script_id}-{hash_text(script_text)[:10]}")
        work_dir = ensure_directory(output_root / slug)
        final_path = output_root / f"{slug}.mp4"
        audio_path, duration_seconds, engine = synthesize_audio(script_text, work_dir, "voiceover", self.settings)
        subtitle_path = write_srt(script_text, work_dir / "captions.srt", duration_seconds)
        scene_texts = [line.strip() for line in script_text.splitlines() if line.strip()]
        total_words = sum(max(len(text.split()), 1) for text in scene_texts)
        scene_clips: list[Path] = []

        for index, text in enumerate(scene_texts):
            image_path = build_scene_image(
                text,
                work_dir / f"scene_{index:02d}.png",
                index,
                self.settings,
                prompt_hint=prompt_hint if index == 0 else "",
            )
            allocation = max(duration_seconds * (max(len(text.split()), 1) / max(total_words, 1)), 2.0)
            clip_path = create_scene_clip(
                self.settings.ffmpeg_binary,
                image_path,
                allocation,
                work_dir / f"scene_{index:02d}.mp4",
            )
            scene_clips.append(clip_path)

        base_video = concat_clips(self.settings.ffmpeg_binary, scene_clips, work_dir / "base_video.mp4")
        mixed_video = mux_audio(
            self.settings.ffmpeg_binary,
            base_video,
            audio_path,
            work_dir / "with_audio.mp4",
            self._music_path(),
        )
        burn_subtitles(self.settings.ffmpeg_binary, mixed_video, subtitle_path, final_path)
        return RenderArtifact(
            script_id=script_id,
            provider="local_fallback",
            video_path=final_path,
            audio_path=audio_path,
            subtitle_path=subtitle_path,
            duration_seconds=duration_seconds,
            metadata={"tts_engine": engine, "work_dir": str(work_dir)},
            fallback_used=True,
        )
