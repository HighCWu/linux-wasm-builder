#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small Git/tar/Nix control-flow fixture, not a hash-equivalence proof."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODEL = r'''#!/usr/bin/env python3
import io, json, os
from pathlib import Path
import sys, tarfile
tool = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["PREFETCH_MODEL_LOG"],"a") as log:
    log.write(json.dumps([tool,args])+"\n")
if tool == "git":
    if args[0] == "init":
        Path(args[-1]).mkdir(parents=True)
        sys.exit(0)
    args = args[2:]
    if args[0] == "-c": args = args[2:]
    if args[0] in ("remote","fetch"): sys.exit(0)
    if args[0] == "grep": sys.exit(2 if os.environ.get("MODEL_ATTR_FAIL") else 0 if os.environ.get("MODEL_SUBST") else 1)
    if args[0] == "rev-parse": print(os.environ["SOURCE_REVISION"])
    elif args[0] == "show": print(os.environ.get("MODEL_PARENT",os.environ["BASELINE_REVISION"]))
    elif args[0] == "diff":
        if args[1] == "--name-status": print(os.environ.get("MODEL_PATH","M\tkernel/futex/core.c"))
        elif os.environ.get("MODEL_MODE"): print("mode change 100644 => 100755 kernel/futex/core.c")
    elif args[0] == "archive":
        if os.environ.get("MODEL_ARCHIVE_FAIL"): sys.exit(7)
        with tarfile.open(fileobj=sys.stdout.buffer,mode="w|") as archive:
            content = args[-1].encode()
            entry = tarfile.TarInfo("core.c")
            entry.size = len(content)
            archive.addfile(entry,io.BytesIO(content))
    else: sys.exit(99)
elif tool == "nix":
    if os.environ.get("MODEL_NIX_FAIL"): sys.exit(9)
    baseline = Path(args[-1]).name == "baseline"
    assert (Path(args[-1])/"core.c").read_text() == os.environ["BASELINE_REVISION" if baseline else "SOURCE_REVISION"]
    value = os.environ["BASELINE_HASH"] if baseline else "sha256-"+"B"*43+"="
    if baseline and os.environ.get("MODEL_HASH_MISMATCH"): value = "sha256-"+"C"*43+"="
    if not baseline and os.environ.get("MODEL_BAD_SRI"): value = "invalid"
    if not baseline and os.environ.get("MODEL_SAME_HASH"): value = os.environ["BASELINE_HASH"]
    print(value)
else: sys.exit(98)
'''


class GitHashPrefetch(unittest.TestCase):
    def run_model(self, additions):
        with tempfile.TemporaryDirectory(prefix="linux-git-prefetch-") as tmp:
            path = Path(tmp)
            tools = path / "bin"
            tools.mkdir()
            for name in ("git", "nix"):
                tool = tools / name
                tool.write_text(MODEL)
                tool.chmod(0o755)
            log, summary = path / "commands", path / "summary"
            env = {**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"],
                   "TMPDIR": tmp, "SOURCE_REVISION": "ab" * 20, "BASELINE_REVISION": "cd" * 20,
                   "BASELINE_HASH": "sha256-" + "A" * 43 + "=", "PREFETCH_MODEL_LOG": str(log),
                   "GITHUB_STEP_SUMMARY": str(summary), **additions}
            result = subprocess.run(["bash", str(ROOT / "scripts/prefetch_linux_git.sh")],
                                    env=env, capture_output=True, text=True, timeout=10)
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, calls, summary.read_text() if summary.exists() else ""

    def test_verified_baseline_precedes_candidate_and_summary(self):
        result, calls, summary = self.run_model({})
        self.assertEqual(result.returncode, 0, result.stderr)
        hashes = [call for call in calls if call[0] == "nix"]
        self.assertEqual([Path(call[1][-1]).name for call in hashes], ["baseline", "candidate"])
        self.assertIn("Verified baseline hash:", summary)
        self.assertIn("Candidate hash:", summary)

    def test_wrong_identity_path_mode_or_baseline_cannot_publish_candidate(self):
        for inputs in ({"SOURCE_REVISION": "main"}, {"BASELINE_HASH": "invalid"},
                       {"MODEL_PARENT": "ef" * 20}, {"MODEL_PATH": "M\tother.c"},
                       {"MODEL_MODE": "1"}, {"MODEL_HASH_MISMATCH": "1"},
                       {"MODEL_SUBST": "1"}, {"MODEL_ATTR_FAIL": "1"},
                       {"MODEL_ARCHIVE_FAIL": "1"}, {"MODEL_NIX_FAIL": "1"},
                       {"MODEL_BAD_SRI": "1"}, {"MODEL_SAME_HASH": "1"}):
            with self.subTest(inputs=inputs):
                result, calls, summary = self.run_model(inputs)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Candidate hash:", result.stdout)
                self.assertEqual(summary, "")
                if "MODEL_BAD_SRI" not in inputs and "MODEL_SAME_HASH" not in inputs:
                    self.assertFalse(any(call[0] == "nix" and Path(call[1][-1]).name == "candidate" for call in calls))


if __name__ == "__main__":
    unittest.main()
