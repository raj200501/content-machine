# Finish Content Machine (Free-Only)

For what the account posts and why (research, formats, what to do by hand), see [GROWTH_PLAYBOOK.md](GROWTH_PLAYBOOK.md).

Last checked: November 7, 2026.

The code is finished. Sources, scripts, voiceover, rendering, the publish
queue and the GitHub Actions schedule all work end to end in dry-run mode.
To get Reels posting on Instagram, you only need Meta credentials, and only
you can create those. It takes about 15 minutes and costs nothing.

Stay on free plans the whole way: no Meta ads, no Hugging Face credits, no
paid runners.

## How it runs itself

Everything below happens in GitHub Actions at no cost, with nobody watching:

| When | What happens |
|---|---|
| Every posting slot (8:00, 11:30, 15:00, 18:30, 22:00 New York) | `clock.yml` starts `automation.yml`, which posts the reel that is due (at most one per run, 100+ minutes apart). |
| First run of the day | Pulls fresh postings (with pay) from 19 job boards and hiring news, collects yesterday's Instagram stats, then plans the day. |
| Planning | Job reels use the real postings. Tip reels come from the **idea engine**: a small open AI model (Qwen3 4B) that runs inside the GitHub runner, with no account or key, writes new ideas. It is told which hooks got the most saves, shares and watch time on this account and which flopped, plus today's headlines. Drafts that break the rules (stats, money, repeats, wrong length) are thrown out and a hand-written pack is used instead. |
| Every post | Hook choice and the posting mix lean toward what has performed best (`app/publishing/insights.py`). |
| Mondays | `REPORT.md` is updated with followers, top posts and what the system is learning. |
| If posting breaks | An issue titled "Instagram posting is failing" is opened (GitHub emails you) with what to do. It closes itself after the next successful post. |

The clock only runs on a **public** repo (Actions minutes are free and
unlimited there). On a private repo GitHub's own scheduler is the only
trigger, and it skips most runs. The repo contains no secrets: the token
lives in GitHub Secrets, which stay private either way.

The one thing that can need you: if Meta ever invalidates the token
(password change, security check), the issue above tells you how to paste a
new one.

## What you need to do

### 1. Make the Instagram account Professional (phone, 2 min)

Instagram app → profile → menu → **Settings and privacy** → **Account type and tools** →
**Switch to professional account** → choose **Creator** or **Business**.

### 2. Connect it to a Facebook Page (browser, 3 min)

1. If you have no Page yet: https://www.facebook.com/pages/create
2. https://business.facebook.com/ → **Settings** → **Accounts** → **Instagram accounts** →
   **Add** → log in to Instagram → pick the Page → confirm.

### 3. Create a Meta app (browser, 5 min)

1. https://developers.facebook.com/apps/ → **Create app** → type **Business** (or **Other**).
2. Name it `content-machine` and create it.
3. Add the **Instagram** use case / product: *Instagram API with Facebook Login*.
4. **App settings → Basic**: copy **App ID** and **App secret**.

### 4. Get a token that never expires (browser and terminal, 3 min)

1. https://developers.facebook.com/tools/explorer/ → select your app → **User Token**.
2. Add these permissions: `instagram_basic`, `instagram_content_publish`,
   `pages_show_list`, `pages_read_engagement`, `business_management`.
3. **Generate Access Token**, approve, and select the Page connected to Instagram.
4. Put the values into `.env` in this repo:

   ```dotenv
   INSTAGRAM_APP_ID=...
   INSTAGRAM_APP_SECRET=...
   INSTAGRAM_ACCESS_TOKEN=<the short-lived Explorer token>
   ```

5. Swap it for a non-expiring Page token. This also fills in `INSTAGRAM_IG_USER_ID`:

   ```bash
   ./.venv/bin/python -m app.cli exchange-token
   ```

   Explorer tokens expire in about an hour, so do this right away. The Page
   token it saves keeps working unless you change your Facebook password or
   remove the app.

### 5. Add one GitHub secret (browser, 1 min)

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

```text
INSTAGRAM_ACCESS_TOKEN   = the long-lived user token (Access Token Debugger → Extend Access Token)
```

At publish time the workflow looks up the Page connected to your Instagram
Professional account and uses that Page's token and Instagram user ID, so nothing
else is required. A long-lived user token lasts about 60 days; to make it
permanent, run `exchange-token` locally and store the Page token it prints instead,
plus `INSTAGRAM_IG_USER_ID`.

Optional: on the **Variables** tab, add `BRAND_HANDLE` = `@yourhandle` to print your handle on every reel.

That's everything. Turso, R2 and Hugging Face are **not** needed:

- State persists between runs in the GitHub Actions cache.
- Each run starts its own temporary TryCloudflare tunnel so Meta can fetch the video.
- Reels are rendered locally on the runner.

### 6. First post

1. Repo → **Actions** → **content-machine-automation** → **Run workflow**. A manual
   run publishes any reel that is due now.
2. After that, the schedule posts 5 Reels a day at 08:00, 11:30, 15:00, 18:30 and
   22:00 New York time.
3. Each run uploads the MP4s it rendered as an artifact, so you can check them.

GitHub Actions minutes: about 5 short runs a day stays well inside the free
private-repo allowance (2,000 minutes a month). Making the repo public makes
Actions completely free.

## Local commands (optional)

```bash
./scripts/bootstrap.sh                           # venv, deps, Piper voice, DB
./.venv/bin/python -m app.cli setup-status       # what's missing (never prints secrets)
./.venv/bin/python -m app.cli daily-run          # dry run: renders 5 reels into output/rendered
./.venv/bin/python -m pytest
```

For a local live test instead of GitHub, set `DRY_RUN=false`, `POSTS_PER_DAY=1`, and
`BATCH_RENDER_SIZE=1`, then run:

```bash
./scripts/run_with_public_media_tunnel.sh ./.venv/bin/python -m app.cli daily-run
```

This needs `cloudflared`, installed with `brew install cloudflared`.

## Troubleshooting

- `Meta API 400 ... OAuthException 190`: the token expired or was revoked. Repeat step 4
  and update the `INSTAGRAM_ACCESS_TOKEN` secret.
- `Meta API ... (#10) / permissions`: the token is missing `instagram_content_publish`,
  or the Page isn't connected to the Instagram Professional account.
- Workflow shows **Skipped until required secrets exist**: `INSTAGRAM_ACCESS_TOKEN` is missing.
- `No Facebook Page with a connected Instagram Professional account`: link the account (Instagram app → Edit profile → Facebook → Connect).
- `setup-status` shows voiceover `missing`: run `./scripts/install_piper_voice.sh`.

## Sources checked

- Instagram Content Publishing: https://developers.facebook.com/docs/instagram-platform/content-publishing
- Long-lived tokens: https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived
- GitHub Actions secrets: https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
- GitHub Actions cache: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows
- TryCloudflare quick tunnels: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/
- Piper voices: https://huggingface.co/rhasspy/piper-voices
