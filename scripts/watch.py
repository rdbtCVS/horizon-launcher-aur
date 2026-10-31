#!/usr/bin/env python3
"""Start update.yml as soon as a new launcher release has its Linux archive.

GitHub starts cron schedules hours late (update.yml asks for every 15 minutes
and gets a run every few hours), so a watch polls for most of a job's 6-hour
limit and watch.yml then starts the next one.
"""
import argparse
import base64
import json
import os
import time
import urllib.request

import update

API = "https://api.github.com"
# About half an hour of failed checks in a row: fail the run so it gets noticed.
MAX_FAILURES = 30


def newest_recent_release():
    # A new launcher release is among the newest on the first page; update.yml
    # still reads the whole catalog before it packages anything.
    releases = json.loads(update.fetch(f"{API}/repos/{update.UPSTREAM}/releases?per_page=100"))
    return update.newest_release(releases)


def packaged_pkgbuild(repo):
    content = json.loads(update.fetch(f"{API}/repos/{repo}/contents/PKGBUILD?ref=main"))
    return base64.b64decode(content["content"]).decode()


def dispatch(repo, workflow):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    request = urllib.request.Request(
        f"{API}/repos/{repo}/actions/workflows/{workflow}/dispatches",
        data=json.dumps({"ref": "main"}).encode(), method="POST", headers={
            "User-Agent": "horizon-launcher-aur", "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        })
    with urllib.request.urlopen(request, timeout=60):
        pass


class Watch:
    def __init__(self, repo):
        self.repo = repo
        self.packaged = None  # newest tag the package already tracks
        self.started = set()  # tags this watch already handed to update.yml

    def poll(self):
        release = newest_recent_release()
        tag = release["tag_name"]
        if tag == self.packaged or tag in self.started:
            return
        status = update.release_status(packaged_pkgbuild(self.repo), release)
        if status["status"] == "up-to-date":
            self.packaged = tag
        elif status["changed"]:
            # Once per tag: a failed build is retried by the next watch or update.yml's schedule.
            dispatch(self.repo, "update.yml")
            self.started.add(tag)
            print(f"Started update.yml for {tag}", flush=True)


def watch_for(watch, minutes, interval):
    deadline = time.monotonic() + minutes * 60
    failures = 0
    while True:
        try:
            watch.poll()
            failures = 0
        except (OSError, ValueError, KeyError) as error:
            failures += 1
            print(f"::warning::Release check failed: {error}", flush=True)
            if failures >= MAX_FAILURES:
                raise SystemExit(f"{failures} release checks failed in a row")
        if time.monotonic() + interval >= deadline:
            return
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=340, help="How long to watch")
    parser.add_argument("--interval", type=float, default=60, help="Seconds between checks")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"),
                        help="Packaging repository, owner/name (default: $GITHUB_REPOSITORY)")
    args = parser.parse_args()
    if not args.repo:
        parser.error("--repo is required outside GitHub Actions")
    watch_for(Watch(args.repo), args.minutes, args.interval)


if __name__ == "__main__":
    main()
