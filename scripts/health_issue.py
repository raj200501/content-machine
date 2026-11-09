"""Open a GitHub issue when posting breaks, and close it once posting works again.

GitHub emails the repo owner about new issues, so this is the account's alarm.
Runs after every automation tick (needs GH_TOKEN with issues: write).

Usage: python scripts/health_issue.py output/last_tick.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

LABEL = "posting-broken"


def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip()[:300])
    return result.stdout


def publish_summary(stats: dict) -> tuple[int, int, list[str]]:
    published = failed = 0
    errors: list[str] = []
    for key, value in stats.items():
        if key.startswith("publish") and isinstance(value, dict):
            published += int(value.get("published") or 0)
            failed += int(value.get("failed") or 0) - int(value.get("missing_media") or 0)
            errors += [str(e) for e in value.get("errors") or []]
    return published, max(failed, 0), errors


def advice(errors: list[str], crashed: bool) -> str:
    text = " ".join(errors).lower()
    if "190" in text or "token" in text or "session" in text:
        return (
            "Instagram rejected the access token. Make a new long-lived token (steps in FINISH_REPO.md) "
            "and paste it into Settings > Secrets and variables > Actions > INSTAGRAM_ACCESS_TOKEN."
        )
    if "permission" in text or "(#10)" in text or "(#200)" in text:
        return "Meta says the app lost a permission. Re-check the app's Instagram permissions (FINISH_REPO.md)."
    if crashed:
        return "The run crashed before posting. Open the run log linked below for the error."
    return "Publishing failed. It retries automatically; if this stays open for a day, check the run log below."


def main(status_file: str) -> None:
    run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    crashed = os.environ.get("TICK_OUTCOME", "success") != "success"
    path = Path(status_file)
    stats = json.loads(path.read_text()) if path.exists() else {}
    published, failed, errors = publish_summary(stats)
    broken = crashed or (failed > 0 and published == 0)
    open_issues = json.loads(gh("issue", "list", "--label", LABEL, "--state", "open", "--json", "number") or "[]")
    if broken and not open_issues:
        gh("label", "create", LABEL, "--color", "d73a4a", "--description", "Automation could not post", "--force")
        body = "\n\n".join(
            [
                "The posting automation could not publish a reel.",
                f"**What to do:** {advice(errors, crashed)}",
                "Errors:\n```\n" + ("\n".join(errors[:5]) or "(see the run log)") + "\n```",
                f"Run log: {run_url}",
                "This issue closes itself after the next successful post.",
            ]
        )
        gh("issue", "create", "--title", "Instagram posting is failing", "--label", LABEL, "--body", body)
        print("Opened a posting-broken issue.")
    elif published > 0 and not broken:
        for issue in open_issues:
            gh("issue", "close", str(issue["number"]), "--comment", f"Posting works again. Run log: {run_url}")
            print(f"Closed issue #{issue['number']}.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "output/last_tick.json")
