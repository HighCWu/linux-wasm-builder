# SPDX-License-Identifier: MIT
"""Packaging corruption controls; no target build or bundled code execution."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import warnings
import zipfile

from verify_workspace_artifact import FILES, ROOT, SOURCE_FILES, verify


class WorkspaceArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workspace-artifact-test-")
        self.addCleanup(self.temporary.cleanup)
        self.bundle = Path(self.temporary.name)
        self.sources = {
            "git-workspace-example.py": b"# application fixture\n",
            "example/LICENSE": b"MIT license fixture\n",
            "build-example.py": b"# builder fixture\n",
        }
        self.pins = {"builder_commit": "a" * 40, "components": [{"commit": "b" * 40}]}
        for name, source_name in SOURCE_FILES.items():
            path = self.bundle / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.sources[source_name])
        (self.bundle / "source-pins.json").write_text(json.dumps(self.pins))
        self.archive()
        self.checksums()

    def archive(self, names=("LICENSE", "__main__.py"), *, corrupt=False, metadata=False):
        with zipfile.ZipFile(self.bundle / "git-workspace.pyz", "w") as archive:
            for name in names:
                entry = zipfile.ZipInfo(name, (2000 if metadata else 1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                content = (self.bundle / "source/example" / name).read_bytes() if name in ("LICENSE", "__main__.py") else b"unexpected"
                archive.writestr(entry, content + (b"corrupt" if corrupt else b""))

    def checksums(self):
        (self.bundle / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((self.bundle / name).read_bytes()).hexdigest()}  {name}\n"
            for name in sorted(FILES)
        ))

    def check(self):
        verify(self.bundle, self.sources, self.pins)

    def test_complete_artifact(self):
        self.check()

    def test_actual_ci_checksum_command_has_no_discovery_pipeline(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        commands = [line.strip() for line in workflow.splitlines() if "> SHA256SUMS)" in line]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0], '(cd "$bundle" && sha256sum ' + " ".join(sorted(FILES)) + ' > SHA256SUMS)')
        subprocess.run(
            ["bash", "-euo", "pipefail", "-c", commands[0]],
            env={**os.environ, "bundle": str(self.bundle)}, check=True,
        )
        self.check()
        (self.bundle / "source-pins.json").unlink()
        result = subprocess.run(
            ["bash", "-e", "-c", commands[0]],
            env={**os.environ, "bundle": str(self.bundle)}, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0, "default CI shell must reject a missing input")

    def test_published_sources_and_license_are_pinned(self):
        for name in SOURCE_FILES:
            with self.subTest(name=name):
                path = self.bundle / name
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                self.checksums()
                with self.assertRaisesRegex(ValueError, "pinned source"):
                    self.check()
                path.write_bytes(original)
        self.checksums()
        self.check()

    def test_other_commit_pins_are_rejected_even_with_valid_checksums(self):
        (self.bundle / "source-pins.json").write_text(json.dumps({**self.pins, "builder_commit": "c" * 40}))
        self.checksums()
        with self.assertRaisesRegex(ValueError, "committed source manifest"):
            self.check()

    def test_checksum_omissions_additions_and_unsafe_paths(self):
        path = self.bundle / "SHA256SUMS"
        original = path.read_text()
        for content in ("", original.split("\n", 1)[1], original + "0" * 64 + "  ../outside\n"):
            with self.subTest(content=content):
                path.write_text(content)
                with self.assertRaisesRegex(ValueError, "checksum manifest"):
                    self.check()

    def test_archive_corruption_metadata_duplicates_and_traversal(self):
        for options in (
            {"corrupt": True}, {"metadata": True},
            {"names": ("LICENSE", "__main__.py", "../outside")},
            {"names": ("__main__.py", "LICENSE")},
            {"names": ("LICENSE", "LICENSE")},
        ):
            with self.subTest(options=options):
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="Duplicate name:", category=UserWarning)
                    self.archive(**options)
                self.checksums()
                with self.assertRaises(ValueError):
                    self.check()

    def test_missing_extra_and_symlink_entries(self):
        path = self.bundle / "extra"
        path.write_bytes(b"not part of artifact")
        with self.assertRaisesRegex(ValueError, "membership"):
            self.check()

        path.unlink()
        path.mkdir()
        with self.assertRaisesRegex(ValueError, "membership"):
            self.check()
        path.rmdir()
        path.symlink_to("LICENSE")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.check()
        path.unlink()
        (self.bundle / "LICENSE").unlink()
        with self.assertRaisesRegex(ValueError, "membership"):
            self.check()

    def test_archive_prefix_and_trailing_data_are_rejected(self):
        path = self.bundle / "git-workspace.pyz"
        original = path.read_bytes()
        for content in (b"executable prefix" + original, original + b"hidden payload"):
            with self.subTest(content=content[:20]):
                path.write_bytes(content)
                self.checksums()
                with self.assertRaisesRegex(ValueError, "canonical source-only build"):
                    self.check()


if __name__ == "__main__":
    unittest.main()
