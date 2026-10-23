#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from pathlib import Path
import tempfile
import unittest

from fetch_kernel_ipc_uapi import FILES, fetch_all

REVISION = "ab" * 20


class IPCInputs(unittest.TestCase):
    def test_all_paths_use_the_same_exact_revision_and_common_downloader(self):
        calls = []
        def download(revision, **kwargs):
            calls.append((revision, kwargs))
            return kwargs["path"].encode() + b"\n"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "headers"
            fetch_all(REVISION, target, token="fixture-only", download=download)
            self.assertEqual(len(calls), 7)
            for (name, source), (revision, kwargs) in zip(FILES.items(), calls):
                self.assertEqual(revision, REVISION)
                self.assertEqual(kwargs, {"path": source, "token": "fixture-only"})
                self.assertEqual((target / name).read_bytes(), source.encode() + b"\n")

    def test_invalid_revision_does_not_fetch_or_create_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "headers"
            def unexpected(*args, **kwargs):
                self.fail("invalid revision reached network")
            for revision in ("main", "AB" * 20, REVISION + "/suffix"):
                with self.assertRaises(ValueError):
                    fetch_all(revision, target, download=unexpected)
            self.assertFalse(target.exists())

    def test_late_download_failure_does_not_publish_mixed_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            for name in FILES:
                (target / name).write_bytes(b"previous input")
            def download(revision, *, path, token):
                if path == "ipc/msg.c":
                    raise OSError("unavailable")
                return b"new input"
            with self.assertRaises(OSError):
                fetch_all(REVISION, target, download=download)
            for name in FILES:
                self.assertEqual((target / name).read_bytes(), b"previous input")


if __name__ == "__main__":
    unittest.main()
