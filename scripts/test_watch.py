import base64
import contextlib
import io
import json
import unittest
import urllib.error
from unittest.mock import patch
import update
import watch

REPO = "owner/horizon-launcher-aur"
RELEASES = f"https://api.github.com/repos/{update.UPSTREAM}/releases?per_page=100"
PKGBUILD = f"https://api.github.com/repos/{REPO}/contents/PKGBUILD?ref=main"


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.pkgbuild = "epoch=1\npkgver=0.2.30\n"
        self.releases = [{"tag_name": "nightly"}, {"tag_name": "v0.2.97"},
                         {"tag_name": "launcher@0.2.31", "assets": []},
                         {"tag_name": "launcher@0.2.30", "assets": [{"name": update.ASSET}]}]
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        if url == RELEASES:
            return json.dumps(self.releases).encode()
        if url == PKGBUILD:
            return json.dumps({"content": base64.b64encode(self.pkgbuild.encode()).decode()}).encode()
        raise AssertionError(url)

    def poll(self, watcher, dispatch):
        with patch.object(update, "fetch", self.fetch), \
             patch.object(watch, "dispatch", dispatch), \
             contextlib.redirect_stdout(io.StringIO()):
            watcher.poll()

    def test_starts_update_once_when_linux_asset_is_ready(self):
        watcher = watch.Watch(REPO)
        with patch.object(watch, "dispatch") as dispatch:
            self.poll(watcher, dispatch)
            dispatch.assert_not_called()
            self.releases[2]["assets"] = [{"name": update.ASSET}]
            self.poll(watcher, dispatch)
            dispatch.assert_called_once_with(REPO, "update.yml")
            self.urls.clear()
            self.poll(watcher, dispatch)
            dispatch.assert_called_once()
            self.assertEqual(self.urls, [RELEASES])

    def test_packaged_release_is_not_rechecked(self):
        self.pkgbuild = "epoch=1\npkgver=0.2.31\n"
        self.releases[2]["assets"] = [{"name": update.ASSET}]
        watcher = watch.Watch(REPO)
        with patch.object(watch, "dispatch") as dispatch:
            self.poll(watcher, dispatch)
            self.poll(watcher, dispatch)
            dispatch.assert_not_called()
        self.assertEqual(self.urls, [RELEASES, PKGBUILD, RELEASES])

    def test_newer_release_after_packaging_starts_update(self):
        self.pkgbuild = "epoch=1\npkgver=0.2.31\n"
        watcher = watch.Watch(REPO)
        with patch.object(watch, "dispatch") as dispatch:
            self.poll(watcher, dispatch)
            self.releases.insert(0, {"tag_name": "launcher@0.2.32", "assets": [{"name": update.ASSET}]})
            self.poll(watcher, dispatch)
            dispatch.assert_called_once_with(REPO, "update.yml")

    def test_dispatch_request(self):
        with patch.object(watch.urllib.request, "urlopen") as urlopen, \
             patch.dict(watch.os.environ, {"GITHUB_TOKEN": "token"}, clear=True):
            watch.dispatch(REPO, "update.yml")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url,
                         f"https://api.github.com/repos/{REPO}/actions/workflows/update.yml/dispatches")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"ref": "main"})
        self.assertEqual(request.get_header("Authorization"), "Bearer token")

    def run_watch(self, outcomes, minutes, interval=60):
        clock = [0.0]
        watcher = watch.Watch(REPO)
        calls = []

        def poll():
            calls.append(clock[0])
            if outcomes:
                outcome = outcomes.pop(0)
                if outcome:
                    raise outcome

        def sleep(seconds):
            clock[0] += seconds

        with patch.object(watcher, "poll", poll), \
             patch.object(watch.time, "monotonic", lambda: clock[0]), \
             patch.object(watch.time, "sleep", sleep), \
             contextlib.redirect_stdout(io.StringIO()):
            watch.watch_for(watcher, minutes, interval)
        return calls

    def test_watch_survives_failed_checks_until_deadline(self):
        outcomes = [urllib.error.URLError("offline"), ValueError("bad JSON"), None]
        self.assertEqual(self.run_watch(outcomes, minutes=5), [0, 60, 120, 180, 240])

    def test_watch_fails_after_repeated_failed_checks(self):
        outcomes = [urllib.error.URLError("offline")] * watch.MAX_FAILURES
        with self.assertRaisesRegex(SystemExit, "failed in a row"):
            self.run_watch(outcomes, minutes=600)
        outcomes = [urllib.error.URLError("offline")] * (watch.MAX_FAILURES - 1) + [None] + \
                   [urllib.error.URLError("offline")] * (watch.MAX_FAILURES - 1)
        self.assertEqual(len(self.run_watch(outcomes, minutes=100)), 100)


if __name__ == "__main__":
    unittest.main()
