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

    def test_catalog_pagination(self):
        first_page = [self.release("v2026.10.14")] * 100
        second_page = [self.release("launcher-v0.2.0", assets=[])]
        with patch.object(update, "fetch", side_effect=[update.json.dumps(first_page), update.json.dumps(second_page)]) as fetch:
            self.assertEqual(update.find_release()["tag_name"], "launcher-v0.2.0")
            self.assertIn("page=2", fetch.call_args.args[0])

    def test_missing_linux_asset_fails(self):
        with self.assertRaisesRegex(ValueError, "no horizon-launcher-linux"):
            update.checked_asset(self.release("launcher-v0.2.0", assets=[]))

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
        for tag, expected in (("launcher-v0.2.0", False), ("launcher-v0.3.0", True)):
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
