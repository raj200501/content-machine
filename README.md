# Content Machine

`content-machine` is a Python-first automation repo that refreshes public early-career tech hiring sources, plans 20 Instagram reels per day, writes original short-form scripts, renders vertical MP4 reels with local fallback, and publishes through the official Meta / Instagram Content Publishing API.

The default design is free-tier-first:

- Public RSS, news, careers pages, public job boards, and optional public YouTube transcripts.
- SQLite for local state, with optional Turso/libSQL cloud sync.
- FFmpeg for deterministic rendering.
- Local-first TTS with `piper`, macOS `say`, or `espeak`, with a last-resort silent fallback.
- Hugging Face is optional and best-effort. If quota fails or the provider errors, the local reel builder still produces publishable vertical MP4 reels.

## What It Does

Every day the system is designed to:

1. Refresh public source data at `00:15`.
2. Normalize and dedupe internship / new-grad items.
3. Plan a diversified 20-post content calendar for the day.
4. Generate original scripts, captions, hashtags, source notes, and compliance notes.
5. Try provider-generated visuals first when configured.
6. Fall back automatically to a fully local FFmpeg reel renderer.
7. Queue publishing evenly between `08:00` and `22:00`.
8. Publish through the official Meta API only.

## Architecture

- `app/config.py`: env-driven runtime config via Pydantic.
- `app/db.py`: SQLite/libSQL schema and persistence helpers.
- `app/source_ingest/`: RSS, article extraction, job board ingestion, YouTube ingestion, dedupe, ranking, starter source definitions.
- `app/planning/`: 30-day-aware taxonomy, freshness, topic mixing, scheduling.
- `app/writing/`: deterministic script generation, captions, fact guard.
- `app/media/`: TTS, subtitles, Hugging Face adapter, local reel rendering, ffmpeg composition, quality checks.
- `app/publishing/`: official Meta publisher, publish queue, duplicate-prevention history.
- `app/workflows/`: refresh, plan, render, publish, and daily orchestration.
- `scripts/`: bootstrap, ffmpeg install, cron install, manual daily run, sanity check.
- `tests/`: config, planner, fact guard, renderer, Instagram adapter, end-to-end smoke coverage.

## Prerequisites

- Python `3.11+`
- `ffmpeg` and `ffprobe`
- macOS or Linux
- Instagram Professional account connected to a Meta app for live publishing

Optional but useful:

- `piper` for higher-quality local TTS
- Hugging Face token for provider-first video/image generation
- Public static hosting for rendered videos when using live Meta publishing

## Install FFmpeg

macOS:

```bash
./scripts/install_ffmpeg.sh
```

Linux:

```bash
./scripts/install_ffmpeg.sh
```

The script uses `brew`, `apt`, `dnf`, or `pacman` when available.

## Local Setup

```bash
cp .env.example .env
./scripts/bootstrap.sh
```

That script:

- creates `.venv`
- installs Python dependencies
- initializes the database

## Environment Variables

Required for live publishing:

- `INSTAGRAM_ACCESS_TOKEN`
- `INSTAGRAM_IG_USER_ID`
- `INSTAGRAM_APP_ID`
- `INSTAGRAM_APP_SECRET`
- `TIMEZONE`

Optional provider and behavior controls:

- `HF_TOKEN`
- `HF_VIDEO_MODEL`
- `HF_IMAGE_MODEL`
- `ENABLE_YOUTUBE_TRANSCRIPTS`
- `ENABLE_VIDEO_PROVIDER`
- `ENABLE_LOCAL_FALLBACK`
- `POSTS_PER_DAY`
- `BATCH_RENDER_SIZE`
- `DRY_RUN`
- `LOG_LEVEL`
- `PUBLICATION_START_HOUR`
- `PUBLICATION_END_HOUR`
- `DATABASE_PATH`
- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `TURSO_SYNC_INTERVAL_SECONDS`
- `SOURCE_CONFIG_PATH`
- `PUBLIC_MEDIA_BASE_URL`
- `MEDIA_STAGING_DIR`
- `PIPER_MODEL_PATH`
- `MACOS_SAY_VOICE`
- `LINUX_TTS_VOICE`

## Database Modes

The repo now supports two persistence modes with the same schema and workflows:

- Local SQLite fallback:
  - default behavior when `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are unset
  - state lives only in `DATABASE_PATH`
- Turso embedded replica:
  - enabled when both `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are set
  - `DATABASE_PATH` remains your plain SQLite path, and the app creates a sibling `*_turso_replica.db` file for the embedded replica
  - reads happen from the local file after sync
  - writes are delegated to the remote Turso primary and reflected back into the local replica

This keeps local development simple while allowing GitHub-hosted automation to persist state across runs.

## Turso Setup

If you want a free managed DB with SQLite compatibility, Turso is the easiest fit for this repo.

1. Install the Turso CLI.
2. Log in with `turso auth login`.
3. Create a DB, for example:
   ```bash
   turso db create content-machine
   ```
4. Get the DB URL:
   ```bash
   turso db show --url content-machine
   ```
5. Create a DB token:
   ```bash
   turso db tokens create content-machine
   ```
6. Put the returned values into:
   - local `.env`
   - GitHub Actions secrets if you are running scheduled workflows there

Relevant Turso docs:

- Pricing: https://turso.tech/pricing
- Python quickstart: https://docs.turso.tech/sdk/python/quickstart
- CLI auth: https://docs.turso.tech/cli/authentication
- DB token creation: https://docs.turso.tech/cli/db/tokens/create

## Instagram / Meta Setup

This repo uses the official publishing API only. It does not use browser automation.

1. Create a Meta app with Instagram Graph API access.
2. Convert the Instagram account to a Professional account.
3. Connect it to a Facebook Page.
4. Generate a user access token with the required permissions.
5. Populate the required Instagram env vars in `.env`.
6. Set `PUBLIC_MEDIA_BASE_URL` to a public URL where Meta can fetch rendered MP4 files.

Important: Meta publishing requires a publicly reachable `video_url`. The repo stages files into `MEDIA_STAGING_DIR`, but you must host that directory or sync it to public storage you control. This is not a paid hard dependency; it is a platform requirement of the official API.

## Hugging Face Setup

If you want provider-first visuals:

1. Create a Hugging Face token.
2. Set `HF_TOKEN`.
3. Optionally override `HF_VIDEO_MODEL` and `HF_IMAGE_MODEL`.

If Hugging Face is unavailable, the system automatically falls back to the local renderer.

## Source Definitions

Starter source definitions live in [app/source_ingest/source_definitions.json](/Users/rajkashikar/content-machine/app/source_ingest/source_definitions.json).

The file includes examples for:

- public RSS and Google News queries
- public Greenhouse and Lever job boards
- YouTube channel placeholders

You can add or remove sources without changing Python code.

## Commands

Initialize state:

```bash
python -m app.cli init-db
```

Refresh public sources:

```bash
python -m app.cli refresh-sources
```

Plan the day:

```bash
python -m app.cli plan-day
```

Render a batch:

```bash
python -m app.cli render-batch --count 20
```

Publish ready posts:

```bash
python -m app.cli publish-ready
```

Run the full daily flow:

```bash
python -m app.cli daily-run
```

View daily metrics:

```bash
python -m app.cli metrics
```

Run a no-network smoke test:

```bash
python -m app.cli smoke-test
```

## Cron Installation

Install the production-style schedule:

```bash
./scripts/install_cron.sh
```

It installs:

- `00:15` source refresh
- `00:45` daily planning
- `01:00` batch rendering
- every 10 minutes from `08:00` to `22:00` publish worker

Manual one-shot execution:

```bash
./scripts/run_daily.sh
```

## Fallback Behavior

The rendering path is intentionally resilient:

1. Try Hugging Face video generation if `ENABLE_VIDEO_PROVIDER=true` and `HF_TOKEN` exists.
2. If the provider errors, times out, or quota is unavailable, switch to the local fallback renderer.
3. The local renderer still produces:
   - `1080x1920` MP4
   - voiceover audio
   - burned subtitles
   - animated text cards
   - subtle zoom / motion
   - optional low-volume music

This means the repo remains valuable even when external AI generation is sparse.

## Data Model

SQLite/libSQL tables created by `init-db`:

- `sources`
- `source_items`
- `extracted_claims`
- `content_topics`
- `scripts`
- `media_assets`
- `render_jobs`
- `publish_jobs`
- `published_posts`
- `daily_metrics`

## Quality Checks

Before publish, the system checks:

- render file exists
- audio exists
- captions exist
- duration is within target range
- script is not too similar to recent content
- publish window is valid
- caption length is sane
- fact guard has not failed hard

## Dry Run Mode

Set:

```bash
DRY_RUN=true
```

In dry run mode:

- planning and rendering still run normally
- publishing is simulated
- staged media files are still copied into the publication staging directory
- fake Meta IDs are stored so the queue and metrics can be exercised locally

## Troubleshooting

- `ffmpeg not found`: run `./scripts/install_ffmpeg.sh`.
- `PUBLIC_MEDIA_BASE_URL is required`: live Meta publishing needs a public video URL.
- `HF` errors or quota failures: expected in some environments; the local renderer should take over automatically.
- `No TTS engine available`: install `piper`, use macOS `say`, or install `espeak-ng` on Linux.
- `Scripts already planned`: the planner is conservative and will not keep duplicating a fully planned day.

## Ethical / Content Notes

- Public sources only.
- No scraping of logged-in or private pages.
- No browser automation for posting.
- No LinkedIn login scraping.
- Scripts are synthesized and transformed into original short-form content.
- Fact guard softens unsupported dates and numbers rather than presenting hallucinated specifics.
- Spoken scripts avoid raw URLs.

## Customize the Niche and Tone

Edit:

- [app/source_ingest/source_definitions.json](/Users/rajkashikar/content-machine/app/source_ingest/source_definitions.json)
- [app/planning/taxonomy.py](/Users/rajkashikar/content-machine/app/planning/taxonomy.py)
- [app/writing/script_writer.py](/Users/rajkashikar/content-machine/app/writing/script_writer.py)
- `.env`

You can shift the pipeline toward:

- data / ML internships
- PM roles
- international student workflows
- resume-first content
- market updates
- a different CTA style or tone

## First Run

```bash
cp .env.example .env
./scripts/install_ffmpeg.sh
./scripts/bootstrap.sh
./scripts/sanity_check.sh
```
