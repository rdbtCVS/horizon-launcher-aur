import unittest
import contextlib
import io
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import update


class UpdateTests(unittest.TestCase):
    def release(self, tag, **kwargs):
        return {"tag_name": tag, **kwargs}

    def test_launcher_tags_only_and_numeric_order(self):
        releases = [self.release("v2026.10.14"), self.release("launcher-v0.2.0"),
                    self.release("launcher-v0.10.0"), self.release("launcher-v1.0.0-rc1"),
                    self.release("launcher-v2.0.0", draft=True),
                    self.release("launcher-v3.0.0", prerelease=True)]
        self.assertEqual(update.newest_release(releases)["tag_name"], "launcher-v0.10.0")

    def test_reset_series_supersedes_legacy_versions(self):
        releases = [self.release("launcher-v0.17.0"), self.release("launcher@0.2.0"),
                    self.release("launcher@0.2.1"), self.release("launcher@0.2.10"),
                    self.release("launcher@0.2.9"), self.release("v0.3.0"),
                    self.release("launcher@1.0.0-rc1"),
                    self.release("launcher@2.0.0", draft=True),
                    self.release("launcher@3.0.0", prerelease=True)]
        self.assertEqual(update.newest_release(releases)["tag_name"], "launcher@0.2.10")

    def test_explicit_new_tag(self):
        release = self.release("launcher@0.2.1", assets=[])
        with patch.object(update, "fetch", return_value=update.json.dumps(release)) as fetch:
            self.assertEqual(update.find_release("launcher@0.2.1"), release)
            self.assertTrue(fetch.call_args.args[0].endswith("/tags/launcher%400.2.1"))
        for tag in ("v0.2.1", "launcher@0.2.1-rc1"):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "stable tag"):
                update.find_release(tag)

    def test_reset_status_and_downgrade_protection(self):
        release = self.release("launcher@0.2.1", assets=[{"name": update.ASSET}])
        self.assertTrue(update.release_status("pkgver=0.17.0\n", release)["changed"])
        text = "epoch=1\npkgver=0.2.1\n"
        self.assertEqual(update.release_status(text, release)["status"], "up-to-date")
        release["tag_name"] = "launcher@0.2.2"
        self.assertTrue(update.release_status(text, release)["changed"])
        for tag in ("launcher@0.2.0", "launcher-v0.17.0", "launcher-v9.0.0"):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "downgrade"):
                update.release_status(text, self.release(tag, assets=[]))
        release["assets"] = []
        self.assertEqual(update.release_status(text, release)["status"], "waiting-for-linux-asset")

    def test_reset_updates_epoch_source_and_pkgrel(self):
        text = ('pkgver=0.17.0\npkgrel=3\n'
                'source=("archive::https://github.com/repo/releases/download/launcher-v${pkgver}/archive")\n'
                "sha256sums=(\n    'old'\n)\n")
        updated = update.updated_pkgbuild(text, "launcher@0.2.1", ["new"])
        self.assertIn("epoch=1\npkgver=0.2.1\npkgrel=1\n_tag=launcher@0.2.1\n", updated)
        self.assertIn("/releases/download/${_tag}/", updated)
        self.assertEqual(update.updated_pkgbuild(updated, "launcher@0.2.1", ["new"]), updated)
        next_version = update.updated_pkgbuild(updated.replace("pkgrel=1", "pkgrel=3"), "launcher@0.2.2", ["next"])
        self.assertEqual(next_version.count("epoch=1\n"), 1)
        self.assertEqual(next_version.count("_tag="), 1)
        self.assertIn("pkgver=0.2.2\npkgrel=1\n_tag=launcher@0.2.2\n", next_version)
        self.assertIn("pkgrel=3", update.updated_pkgbuild(updated.replace("pkgrel=1", "pkgrel=3"), "launcher@0.2.1", ["new"]))
        with self.assertRaisesRegex(ValueError, "downgrade"):
            update.updated_pkgbuild(updated, "launcher-v0.17.0", ["old"])

    def test_catalog_pagination(self):
        first_page = [self.release("v2026.10.14")] * 100
        second_page = [self.release("launcher-v0.2.0", assets=[])]
        with patch.object(update, "fetch", side_effect=[update.json.dumps(first_page), update.json.dumps(second_page)]) as fetch:
            self.assertEqual(update.find_release()["tag_name"], "launcher-v0.2.0")
            self.assertIn("page=2", fetch.call_args.args[0])

    def test_missing_linux_asset_fails(self):
        with self.assertRaisesRegex(ValueError, "no horizon-launcher-linux"):
            update.checked_asset(self.release("launcher-v0.2.0", assets=[]))

    def test_new_tag_asset_uses_encoded_download_url(self):
        data = b"launcher archive"
        url = f"https://github.com/{update.UPSTREAM}/releases/download/launcher%400.2.1/{update.ASSET}"
        digest = update.hashlib.sha256(data).hexdigest()
        release = self.release("launcher@0.2.1", assets=[{
            "name": update.ASSET, "browser_download_url": url, "digest": f"sha256:{digest}",
        }])
        with patch.object(update, "fetch", return_value=data) as fetch:
            self.assertEqual(update.checked_asset(release), (data, digest))
            fetch.assert_called_once_with(url)
        release["assets"][0]["browser_download_url"] = "https://example.org/archive"
        with self.assertRaisesRegex(ValueError, "Unexpected release download URL"):
            update.checked_asset(release)

    def test_release_check_waits_for_linux_asset(self):
        text = "pkgver=0.2.0\n"
        release = self.release("launcher-v0.3.0", assets=[])
        status = update.release_status(text, release)
        self.assertFalse(status["changed"])
        self.assertEqual(status["status"], "waiting-for-linux-asset")
        release["assets"] = [{"name": update.ASSET}]
        self.assertTrue(update.release_status(text, release)["changed"])
        with self.assertRaisesRegex(ValueError, "downgrade"):
            update.release_status(text, self.release("launcher-v0.1.0", assets=[]))

    def test_check_is_read_only_and_emits_workflow_outputs(self):
        for tag, expected in (("launcher-v0.2.0", False), ("launcher-v0.3.0", True), ("launcher@0.2.1", True)):
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                text = "pkgver=0.2.0\n"
                (root / "PKGBUILD").write_text(text)
                output = root / "outputs"
                release = self.release(tag, assets=[{"name": update.ASSET}])
                with patch.object(update, "ROOT", root), \
                     patch.object(update, "find_release", return_value=release), \
                     patch.object(update, "checked_asset") as download, \
                     patch.object(update.subprocess, "run") as commands, \
                     patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), \
                     patch("sys.argv", ["update.py", "--check"]), \
                     contextlib.redirect_stdout(io.StringIO()) as stdout:
                    update.main()
                status = update.json.loads(stdout.getvalue())
                self.assertEqual(status["changed"], expected)
                self.assertEqual(output.read_text(), f"changed={str(expected).lower()}\ntag={tag}\n")
                self.assertEqual((root / "PKGBUILD").read_text(), text)
                self.assertEqual({p.name for p in root.iterdir()}, {"PKGBUILD", "outputs"})
                download.assert_not_called()
                commands.assert_not_called()

    def test_digest_mismatch_fails(self):
        release = self.release("launcher-v0.2.0", assets=[{
            "name": update.ASSET,
            "browser_download_url": f"https://github.com/{update.UPSTREAM}/releases/download/launcher-v0.2.0/{update.ASSET}",
            "digest": "sha256:" + "0" * 64,
        }])
        with patch.object(update, "fetch", return_value=b"modified"), self.assertRaisesRegex(ValueError, "published digest"):
            update.checked_asset(release)

    def test_new_version_resets_pkgrel_and_refresh_preserves_it(self):
        text = "pkgver=0.2.0\npkgrel=3\nsha256sums=(\n    'old'\n)\n"
        refreshed = update.updated_pkgbuild(text, "launcher-v0.2.0", ["new"])
        self.assertIn("pkgrel=3", refreshed)
        updated = update.updated_pkgbuild(text, "launcher-v0.3.0", ["new"])
        self.assertIn("pkgver=0.3.0\npkgrel=1", updated)
        self.assertIn("'new'", updated)
        self.assertNotIn("'old'", updated)
        with self.assertRaisesRegex(ValueError, "downgrade"):
            update.updated_pkgbuild(text, "launcher-v0.1.0", ["new"])


if __name__ == "__main__":
    unittest.main()
