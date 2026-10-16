# SPDX-License-Identifier: MIT
import json
import subprocess
import unittest

from source_manifest import ROOT, git, manifest


class SourceManifestTests(unittest.TestCase):
    def test_committed_pins_match_git_tree(self):
        result = manifest()
        self.assertEqual(result, manifest(result["builder_commit"]))
        self.assertEqual(len(result["components"]), 4)
        for component in result["components"]:
            entry = git("ls-tree", result["builder_commit"], component["path"])
            self.assertEqual(entry.split()[2], component["commit"])
            self.assertTrue(component["repository"].startswith("https://github.com/HighCWu/"))

    def test_cli_exports_json(self):
        output = subprocess.check_output(
            ["python3", "-B", str(ROOT / "scripts/source_manifest.py")], text=True
        )
        self.assertEqual(json.loads(output), manifest())

    def test_invalid_revision_is_rejected(self):
        result = subprocess.run(
            ["python3", "-B", str(ROOT / "scripts/source_manifest.py"),
             "--revision", "refs/heads/manifest-test-does-not-exist"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
