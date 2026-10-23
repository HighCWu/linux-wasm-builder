#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute the actual prefetch shell with a tiny nix stub, never fetch sources."""
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
BODY = textwrap.dedent((ROOT / ".github/workflows/prefetch-source.yml").read_text().split("run: |\n", 1)[1])
HASH = "sha256-" + "A" * 43 + "="


class PrefetchSource(unittest.TestCase):
    def invoke(self, fixture, status=0, revision="a" * 40, repository="linux"):
        with tempfile.TemporaryDirectory(prefix="prefetch-shell-") as tmp:
            summary = Path(tmp) / "summary"
            result = subprocess.run(["bash", "-c", r'''
                nix() {
                    [[ "$*" == *"https://codeload.github.com/HighCWu/linux/tar.gz/"* ]] || return 63
                    printf '%s\n' "$PREFETCH_FIXTURE"
                    return "$PREFETCH_STATUS"
                }
                ''' + BODY], capture_output=True, text=True,
                env={**os.environ, "RUNNER_TEMP": tmp, "GITHUB_STEP_SUMMARY": str(summary),
                     "SOURCE_REPOSITORY": repository, "SOURCE_REVISION": revision,
                     "PREFETCH_FIXTURE": fixture, "PREFETCH_STATUS": str(status)})
            return result.returncode, summary.read_text() if summary.exists() else ""

    def test_valid_json_records_exact_source_hash(self):
        status, summary = self.invoke('{"hash":"' + HASH + '","storePath":"/mock"}')
        self.assertEqual(status, 0)
        self.assertIn("Revision: " + "a" * 40, summary)
        self.assertIn("Hash: " + HASH, summary)

    def test_failed_pipeline_cannot_be_masked_by_tee(self):
        for fixture in ("", '{"hash":"' + HASH + '"}'):
            with self.subTest(fixture=fixture):
                status, summary = self.invoke(fixture, status=71)
                self.assertNotEqual(status, 0)
                self.assertEqual(summary, "")

    def test_missing_or_malformed_hash_is_not_success(self):
        for fixture in ("", "{}", '{"hash":null}', '{"hash":12}', '{"hash":"sha256-no"}', "not-json"):
            with self.subTest(fixture=fixture):
                status, summary = self.invoke(fixture)
                self.assertNotEqual(status, 0)
                self.assertEqual(summary, "")

    def test_invalid_source_identity_is_rejected(self):
        for identity in ({"revision": "main"}, {"repository": "other"}):
            status, summary = self.invoke('{"hash":"' + HASH + '"}', **identity)
            self.assertNotEqual(status, 0)
            self.assertEqual(summary, "")


if __name__ == "__main__":
    unittest.main()
