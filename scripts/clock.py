"""A reliable clock for the posting workflow, built from GitHub Actions itself.

GitHub's cron skips most scheduled runs, so this job stays awake (for free on a
public repo), starts the posting workflow at each posting slot, and before its
6-hour limit hands over to a fresh copy of itself. Stdlib only.

Usage: python3 scripts/clock.py --hours 5.5
Env: GH_TOKEN, GITHUB_REPOSITORY, CLOCK_SLOTS ("08:02,11:32,..."), TIMEZONE
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def next_slot(now: datetime, slots: list[str]) -> datetime:
    candidates = []
    for day in (0, 1):
        for slot in slots:
            hour, minute = (int(part) for part in slot.split(":"))
            at = (now + timedelta(days=day)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            if at > now:
                candidates.append(at)
    return min(candidates)


def start_posting_run() -> None:
    result = subprocess.run(
        ["gh", "workflow", "run", "automation.yml", "--ref", "main", "-f", "publish_now=0", "-f", "force=false"],
        capture_output=True,
        text=True,
    )
    print(f"{datetime.now():%H:%M} started posting run: {result.returncode} {result.stderr.strip()[:200]}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=5.5)
    args = parser.parse_args()
    zone = ZoneInfo(os.environ.get("TIMEZONE", "America/New_York"))
    slots = [s.strip() for s in os.environ.get("CLOCK_SLOTS", "08:02,11:32,15:02,18:32,22:02").split(",") if s.strip()]
    stop_at = datetime.now(zone) + timedelta(hours=args.hours)
    # A slot that fell in the hand-over gap between two clocks still gets its run.
    now = datetime.now(zone)
    missed = next_slot(now - timedelta(minutes=10), slots)
    if missed <= now:
        print(f"Catching up the {missed:%H:%M} slot from the hand-over.", flush=True)
        start_posting_run()
    while True:
        now = datetime.now(zone)
        due = next_slot(now, slots)
        if due >= stop_at:
            print(f"Next slot {due:%a %H:%M} is after this clock ends; handing over.", flush=True)
            break
        print(f"Sleeping until {due:%a %H:%M}", flush=True)
        time.sleep(max((due - now).total_seconds(), 0))
        start_posting_run()
    remaining = (stop_at - datetime.now(zone)).total_seconds()
    time.sleep(max(remaining, 0))


if __name__ == "__main__":
    main()
