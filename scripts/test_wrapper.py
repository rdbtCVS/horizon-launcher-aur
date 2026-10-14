"""The package wrapper must preserve its environment for GUI and CLI launches."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class WrapperTests(unittest.TestCase):
    def test_gui_and_cli_keep_package_policy(self):
        for args in ([], ["desktop-entry"], ["mcp"], ["versions", "--installed", "--json"]):
            with self.subTest(args=args), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                calls = home / "calls"
                launcher = home / "launcher"
                launcher.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ['WRAPPER_TEST_CALLS'], 'a') as stream:
    stream.write(json.dumps({
        'args': sys.argv[1:],
        'no_self_update': os.environ.get('HORIZON_LAUNCHER_NO_SELF_UPDATE'),
        'desktop_exec': os.environ.get('HORIZON_LAUNCHER_DESKTOP_EXEC'),
    }) + '\\n')
""")
                launcher.chmod(0o755)
                wrapper = home / "wrapper"
                wrapper.write_text((ROOT / "horizon-launcher.sh").read_text().replace(
                    "launcher=/usr/lib/horizon-launcher/horizon-launcher",
                    f"launcher={launcher}",
                ))
                subprocess.run(["sh", str(wrapper), *args], check=True, env=os.environ | {
                    "WRAPPER_TEST_CALLS": str(calls),
                    "HORIZON_LAUNCHER_NO_SELF_UPDATE": "",
                    "HORIZON_LAUNCHER_DESKTOP_EXEC": "/unwanted/launcher",
                })
                records = [json.loads(line) for line in calls.read_text().splitlines()]
                expected_args = [["desktop-entry", "--remove"], []] if not args else [args]
                self.assertEqual([record["args"] for record in records], expected_args)
                for record in records:
                    self.assertEqual(record["no_self_update"], "1")
                    self.assertEqual(record["desktop_exec"], "/usr/bin/horizon-launcher")
