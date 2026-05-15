# Finish Content Machine, Free-Only

Last checked: May 15, 2026.

This guide is written for a zero-dollar setup. Do not upgrade plans, buy credits, enable paid runners, or add paid AI/video services. The repo can render reels locally for free; provider-generated AI video is optional and should stay off unless you are deliberately testing a free credit.

## Current Free-Safe Defaults

Keep these values in `.env`:

```dotenv
DRY_RUN=true
ENABLE_VIDEO_PROVIDER=false
ENABLE_LOCAL_FALLBACK=true
POSTS_PER_DAY=5
BATCH_RENDER_SIZE=5
DELETE_STAGED_MEDIA_AFTER_PUBLISH=true
R2_REGION=auto
```

Only switch `DRY_RUN=false` after every setup check passes and you have tested one dry run.

Run this any time you want to see what is still missing:

```bash
./.venv/bin/python -m app.cli setup-status
```

Run this after editing `.env`:

```bash
./.venv/bin/python -m pytest
./.venv/bin/python -m app.cli smoke-test
```

## Cost Guardrails

Use the local renderer as the normal video generator. It uses Pillow, ffmpeg, local text-to-speech, and local fallback backgrounds. It does not call a paid video API.

Do not buy Hugging Face credits. Hugging Face gives free users a small monthly Inference Providers credit, but provider video can consume that quickly and paid usage exists after credits are purchased. For a guaranteed free run, leave `HF_TOKEN` blank and keep `ENABLE_VIDEO_PROVIDER=false`.

Use Cloudflare R2 Standard storage only, not Infrequent Access. R2 has a free monthly allowance for Standard storage and operations, but can bill above that allowance. This repo uploads only temporary MP4s for Meta to fetch and then deletes them after publish, which is designed to stay tiny. Keep `DELETE_STAGED_MEDIA_AFTER_PUBLISH=true`.

Avoid GitHub Actions scheduled automation on a private repo unless you know you are under the included free minutes. GitHub Actions is free for public repos on standard runners, and private repos get a monthly free quota. The safest zero-dollar mode is local cron on your Mac.

Never commit `.env`.

## Step 1: Finish Local Setup

1. From the repo root, run:

   ```bash
   cp .env.example .env
   ./.venv/bin/python -m app.cli sync-env
   ```

   If `.env` already exists, `sync-env` appends missing keys and does not overwrite existing values.

2. Make sure ffmpeg is installed:

   ```bash
   ./scripts/install_ffmpeg.sh
   ```

3. Bootstrap dependencies:

   ```bash
   ./scripts/bootstrap.sh
   ./.venv/bin/python -m app.cli init-db
   ```

4. Check status:

   ```bash
   ./.venv/bin/python -m app.cli setup-status
   ```

## Step 2: Instagram And Meta, Free

The repo publishes only through the official Meta/Instagram API. It does not browser-automate posting.

### 2.1 Convert Instagram To Professional

1. Open the Instagram mobile app.
2. Tap your profile photo.
3. Tap the menu icon.
4. Tap `Settings and privacy`.
5. Tap `Account type and tools`.
6. Tap `Switch to professional account`.
7. Choose `Creator` or `Business`.
8. Finish the prompts. Do not buy ads or boosts.

### 2.2 Connect Instagram To A Facebook Page

1. Go to `https://business.facebook.com/`.
2. Open `Settings`.
3. Open `Business assets` or `Accounts`.
4. Click `Instagram accounts`.
5. Click `Add`.
6. Click `Connect your Instagram account`.
7. Log in to Instagram when prompted.
8. Select the Facebook Page that should own the Instagram connection.
9. Confirm the connection.

If you do not have a Facebook Page yet:

1. Go to `https://www.facebook.com/pages/create`.
2. Create a Page for the account.
3. Return to Meta Business Suite and connect the Instagram account to that Page.

### 2.3 Create A Meta App

1. Go to `https://developers.facebook.com/apps/`.
2. Click `Create app`.
3. Choose the app type closest to `Business` or `Other`.
4. Enter an app name such as `content-machine`.
5. Enter your contact email.
6. Click `Create app`.
7. In the app dashboard, open `Use cases` or `Add products`.
8. Add Instagram Graph API / Instagram API with Facebook Login if it is offered.
9. Open `App settings` > `Basic`.
10. Copy `App ID` into `.env` as `INSTAGRAM_APP_ID`.
11. Click `Show` next to `App secret`, complete the password prompt, and copy it into `.env` as `INSTAGRAM_APP_SECRET`.

### 2.4 Generate A User Access Token

Use this route for this repo because the code discovers Pages through `me/accounts`.

1. Go to `https://developers.facebook.com/tools/explorer/`.
2. In the top-right app dropdown, select your `content-machine` app.
3. In the token dropdown, choose `User Token`.
4. Click `Add permissions`.
5. Add these permissions if available:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
6. Click `Generate Access Token`.
7. Continue through the Facebook login prompt.
8. Select the Facebook Page connected to your Instagram Professional account.
9. Confirm the permissions.
10. Copy the generated token into `.env` as `INSTAGRAM_ACCESS_TOKEN`.

If Meta shows the newer Instagram Login permission names instead, use the publishing equivalents:

- `instagram_business_basic`
- `instagram_business_content_publish`

If Graph API Explorer cannot return your Page or Instagram account, the Instagram account is not connected to the Page correctly, the Facebook user is not an admin, or the app/token is missing Page permissions.

### 2.5 Get The Instagram User ID

After `INSTAGRAM_ACCESS_TOKEN` is set:

```bash
./.venv/bin/python -m app.cli instagram-accounts
```

Copy the displayed `Instagram User ID` into `.env`:

```dotenv
INSTAGRAM_IG_USER_ID=PASTE_THE_ID_HERE
```

### 2.6 Keep Tokens Free And Safe

Do not paste tokens into chat.

Do not commit `.env`.

Do not buy Meta ads.

If the token expires, return to Graph API Explorer, generate a new token, and replace `INSTAGRAM_ACCESS_TOKEN`.

## Step 3: Public Media URL, Free-Tier R2

Meta needs a public `video_url` before it can publish a Reel. This repo can upload the temporary MP4 to Cloudflare R2 using S3-compatible credentials.

Cloudflare R2 can stay free if you use Standard storage, stay under the monthly free allowance, and delete staged media after publishing.

### 3.1 Create A Bucket

1. Go to `https://dash.cloudflare.com/`.
2. Click `Storage & databases`.
3. Click `R2`.
4. Click `Create bucket`.
5. Name it `content-machine-reels`.
6. Choose `Standard` storage. Do not choose Infrequent Access.
7. Click `Create bucket`.
8. Put this into `.env`:

   ```dotenv
   R2_BUCKET=content-machine-reels
   ```

### 3.2 Make The Bucket Public For Meta Fetching

Use a custom domain if you already own one on Cloudflare. Use the `r2.dev` public development URL only if you are staying free and testing.

For `r2.dev`:

1. Open the R2 bucket.
2. Click `Settings`.
3. Find `Public Development URL`.
4. Click `Enable`.
5. In the confirmation box, type `allow`.
6. Click `Allow`.
7. Copy the displayed public bucket URL.
8. Put it into `.env` as:

   ```dotenv
   PUBLIC_MEDIA_BASE_URL=https://YOUR_PUBLIC_BUCKET_URL
   ```

For a custom domain:

1. Open the R2 bucket.
2. Click `Settings`.
3. Under `Custom Domains`, click `Add`.
4. Enter the domain, for example `media.yourdomain.com`.
5. Click `Continue`.
6. Review the DNS record.
7. Click `Connect Domain`.
8. Wait until the status becomes `Active`.
9. Put the domain into `.env`:

   ```dotenv
   PUBLIC_MEDIA_BASE_URL=https://media.yourdomain.com
   ```

### 3.3 Create R2 S3 Credentials

1. Go to Cloudflare Dashboard.
2. Click `Storage & databases`.
3. Click `R2`.
4. Click `Overview`.
5. Find `API Tokens`.
6. Click `Manage`.
7. Click `Create API token`.
8. Choose `Object Read & Write`.
9. Choose `Apply to specific buckets only`.
10. Select `content-machine-reels`.
11. Click `Create API Token`.
12. Copy `Access Key ID` into `.env` as `R2_ACCESS_KEY_ID`.
13. Copy `Secret Access Key` into `.env` as `R2_SECRET_ACCESS_KEY`. You will not be able to view it again.
14. Copy the account ID from the endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
15. Put it into `.env`:

   ```dotenv
   R2_ACCOUNT_ID=PASTE_ACCOUNT_ID_HERE
   R2_REGION=auto
   ```

Leave `R2_ENDPOINT_URL` blank unless you need to override the default endpoint.

## Step 4: Video Generation, Free

The free-safe setup is local rendering:

```dotenv
ENABLE_VIDEO_PROVIDER=false
ENABLE_LOCAL_FALLBACK=true
HF_TOKEN=
```

That still creates MP4 reels. It just avoids paid or quota-limited AI video provider calls.

Optional free-credit Hugging Face test:

1. Go to `https://huggingface.co/settings/tokens`.
2. Click `New token`.
3. Name it `content-machine-video-test`.
4. Choose `read` or a fine-grained token with read/inference access.
5. Click `Create token`.
6. Copy it into `.env` as `HF_TOKEN`.
7. Set:

   ```dotenv
   ENABLE_VIDEO_PROVIDER=true
   ```

8. Run one render test only.
9. Set `ENABLE_VIDEO_PROVIDER=false` again.

Do not buy Hugging Face credits. Do not set up Inference Endpoints. Do not add a custom provider key.

## Step 5: Turso, Free

Your local `.env` already has Turso values set. If you ever need to recreate them:

1. Install the Turso CLI.
2. Run:

   ```bash
   turso auth login
   ```

3. Complete the browser login.
4. Create the database:

   ```bash
   turso db create content-machine
   ```

5. Get the URL:

   ```bash
   turso db show --url content-machine
   ```

6. Put it in `.env`:

   ```dotenv
   TURSO_DATABASE_URL=PASTE_URL_HERE
   ```

7. Create a database token:

   ```bash
   turso db tokens create content-machine
   ```

8. Put it in `.env`:

   ```dotenv
   TURSO_AUTH_TOKEN=PASTE_TOKEN_HERE
   ```

Stay on the Turso Free plan.

## Step 6: GitHub Actions, Free-Only Choice

Free safest option: do not use GitHub Actions for scheduling. Use local cron:

```bash
./scripts/install_cron.sh
```

Use GitHub Actions only if:

- the repository is public, or
- you are certain the private repo will stay inside included free minutes, and
- your GitHub billing spending limit is zero or safe.

To add repository secrets:

1. Open the GitHub repository page.
2. Click `Settings`.
3. In the sidebar, click `Secrets and variables`.
4. Click `Actions`.
5. Click the `Secrets` tab.
6. Click `New repository secret`.
7. Add each secret one at a time.
8. Click `Add secret`.

Secrets needed by `.github/workflows/automation.yml`:

```text
INSTAGRAM_ACCESS_TOKEN
INSTAGRAM_IG_USER_ID
INSTAGRAM_APP_ID
INSTAGRAM_APP_SECRET
TURSO_DATABASE_URL
TURSO_AUTH_TOKEN
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
PUBLIC_MEDIA_BASE_URL
```

Do not add `HF_TOKEN` to GitHub if you want guaranteed free behavior. The workflow defaults `ENABLE_VIDEO_PROVIDER=false`.

## Step 7: Final Verification

After editing `.env`, run:

```bash
./.venv/bin/python -m app.cli setup-status
```

When the missing key list is gone and you are ready for a real publish:

```bash
./.venv/bin/python -m app.cli setup-status --strict-live
./.venv/bin/python -m app.cli instagram-accounts
./.venv/bin/python -m pytest
./.venv/bin/python -m app.cli smoke-test
```

Then do one live test:

1. Set `POSTS_PER_DAY=1`.
2. Set `BATCH_RENDER_SIZE=1`.
3. Set `DRY_RUN=false`.
4. Keep `ENABLE_VIDEO_PROVIDER=false`.
5. Run:

   ```bash
   ./.venv/bin/python -m app.cli daily-run
   ```

6. Confirm the Reel posted.
7. Check Cloudflare R2 bucket contents. It should be empty after publish if cleanup succeeded.
8. Set `POSTS_PER_DAY=5` and `BATCH_RENDER_SIZE=5` only after the one-post test works.

## Sources Checked

- Hugging Face user access tokens: https://huggingface.co/docs/hub/main/security-tokens
- Hugging Face Inference Providers pricing: https://huggingface.co/docs/inference-providers/en/pricing
- Cloudflare R2 S3 credentials: https://developers.cloudflare.com/r2/get-started/s3/
- Cloudflare R2 public buckets: https://developers.cloudflare.com/r2/buckets/public-buckets/
- Cloudflare R2 pricing and free tier: https://developers.cloudflare.com/r2/pricing/
- Turso CLI authentication: https://docs.turso.tech/cli/authentication
- Turso database tokens: https://docs.turso.tech/cli/db/tokens/create
- Turso pricing: https://turso.tech/pricing
- GitHub Actions secrets: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- GitHub Actions billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions
