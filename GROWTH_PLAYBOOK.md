# @careerstacked growth playbook

Last updated: November 7, 2026. Everything here stays on free plans.

## What Instagram rewards right now

- **Watch time, likes and sends.** Instagram's head, Adam Mosseri, said in January 2025 that these are the top three ranking signals. Sends (DM shares) matter most for reaching people who don't follow you yet, so every reel ends with a "send this to a friend" prompt. [Social Media Today](https://www.socialmediatoday.com/news/instagram-shares-algorithm-insights-2025/738034/)
- **The first 3 seconds.** Instagram now reports a skip rate (the share of viewers who swipe away within 3 seconds). Every reel shows its full hook on the very first frame, with no fade-in. [Social Media Today](https://www.socialmediatoday.com/news/instagram-adds-retention-insights-reels/758464/)
- **Original content only.** Reposts, aggregator pages and watermarks lose recommendations. As of April 2026 that also applies to carousels. Narration, voiceover and your own graphics count as original, and that's what this account makes. [Instagram](https://creators.instagram.com/blog/rewarding-original-creators-on-instagram), [Original content guidelines](https://creators.instagram.com/original-content-guidelines/)
- **No engagement bait.** "Comment a word" and "tag a friend" prompts can stop a post from being recommended. The reels never use them. [Social Media Today](https://www.socialmediatoday.com/news/instagram-clarifies-advice-single-word-ctas-longer-reels/718151/)
- **Few hashtags.** Instagram has been capping posts at 5 hashtags since December 2025, and hashtags don't increase views. The account uses 3. [BetaNews](https://betanews.com/2025/12/19/instagram-puts-a-limit-on-hashtag-usage/)
- **Search keywords.** Public posts from professional accounts appear in Google and Bing, so every caption starts with a plain keyword line (role type plus company names). [PPC Land](https://ppc.land/instagram-content-becomes-searchable-on-google-starting-july-10/)
- **Volume, spaced out.** Accounts that post more get more reach per post, with diminishing returns ([Buffer](https://buffer.com/resources/how-often-to-post-on-instagram/)). The 5 daily posts go out 3.5 hours apart.
- **Carousels earn saves.** Reels reach more people, but carousels earn about 9× the saves of single images ([Metricool](https://www.socialmediatoday.com/press-release/20260615-metricools-2026-instagram-study-reveals-reels-and-carousels-are-reshaping-1/)). The account posts a Sunday carousel roundup.
- **Length.** Reels of 30 to 60 seconds get slightly more reach than shorter ones (5.6% vs 5.2%, [Socialinsider](https://socialinsider.io/blog/instagram-reels-statistics/)). Ours run 18 to 30 seconds and are dense, which keeps viewers watching to the end.

## What the system does now, automatically

| Area | What happens |
|---|---|
| Voice | Kokoro-82M, a free voice model that runs locally and sounds far more natural than Piper. It's disclosed with Instagram's AI label. |
| Visuals | The hook is on frame 1, captions light up word by word, and job cards show company, role, location, posted pay and posting age. Story-style progress bars, a drifting background and a generated music bed (no licensing, no copyright claims). Loudness matches Instagram's −14 LUFS. |
| Job data | Live Greenhouse and Lever boards. Pay comes from the posting's own pay-transparency data and is never estimated (41 of 69 roles had pay in the first live test). Recent postings and postings that list pay go first. |
| Hooks | Name the companies or lead with the pay ("This Verkada role lists up to $140K/yr."). |
| Captions | Keyword first line, every role with location and pay, a real question to prompt comments, a send prompt, 3 hashtags. |
| Mix | 5 a day: 2 job alerts, plus application, interview and resume tips. On Sundays the 3 PM slot is an 8-role carousel. |
| Cover | The thumbnail is set to the moment the hook is fully on screen. |
| Trial Reels | Turn on automatically for tip reels once you pass 200 followers. These show to non-followers first, then to your followers if they perform. |
| Feedback loop | Every morning the system pulls reach, shares, saves, likes and skip rate for the last 14 days and nudges the mix toward what works (0.6× to 1.6×, so no format is ever dropped). This needs one extra permission (see below). |
| Safety | If Instagram rejects an optional field (the cover frame, the AI label or the Trial Reels setting), the post retries without it instead of failing. |

## What only you can do (highest leverage first)

1. **Rename the profile for search.** Change the Name field from "Early Career" to **"Tech Internships & New Grad Jobs"**. Instagram search matches the name field, so this is the cheapest discovery win available.
2. **Reply to comments, especially in the first few hours.** Replies correlate with more engagement, and the captions now end with a question to start conversations.
3. **Add the insights permission the next time you refresh the token** (by January 6 at the latest). In the Graph API Explorer, add `instagram_manage_insights` to the 5 existing permissions. That switches on the feedback loop. Adding `instagram_manage_comments` at the same time would also let a future comment-reply feature work.
4. **Collaborate with CS clubs and career centers.** A shared post shows up for both accounts' followers. The API supports this, and it's the fastest legitimate way to reach students in bulk.
5. **Occasionally post with your face or voice.** Every large account in this niche shows a real person, including Jerry Lee (~1.5M), Wonsulting, Erin McGoff and Salary Transparent Street. I couldn't find a faceless account in this niche with a verified large following. A weekly 30-second talking-head reel ("I applied to the Stripe internship from Monday's list, here's what I'd change") adds the human signal that automated reels can't.

## Honest expectations

There's no reliable data on taking a brand-new account to thousands of followers in its first month. The closest benchmarks:
- Small accounts (1K to 5K followers) grew about 22% a year on average in 2025 ([Socialinsider](https://www.socialinsider.io/instagram-benchmarks)).
- Only 21% of accounts under 10K grew at all in Metricool's 2026 study.

Growth on Instagram comes in steps, from one or two reels that break out to non-followers. Treat the first month as a search for a format that works:
- Judge each reel on day 3, not hour 2. About two-thirds of views arrive in the first 3 days.
- Watch skip rate and sends per reach in Insights. A low skip rate means the hook works. High sends per reach means people find it useful enough to forward.
- The format with the strongest pull here is likely the job alert that leads with real pay. It's specific, useful and easy to forward, and no other account posts it daily with pay on screen.

## Operating notes

- To post a reel right now: Actions → content-machine-automation → Run workflow → "Reels to post right now" = 1.
- Every push to a `claude/**` branch runs **render-preview**: a dry run on live data that renders the day's reels and uploads them as an artifact without posting anything.
- The access token expires January 6, 2027. FINISH_REPO.md step 4 has the refresh steps (`exchange-token` gives you one that never expires).
