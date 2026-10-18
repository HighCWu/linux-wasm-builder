#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the project-owned workspace artifact, without executing its contents.

This is a packaging gate, not a third-party license or corresponding-source audit.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

from source_manifest import ROOT, manifest


SOURCE_FILES = {
    "source/example/__main__.py": "git-workspace-example.py",
    "source/example/LICENSE": "example/LICENSE",
    "LICENSE": "example/LICENSE",
    "source/build-example.py": "build-example.py",
}
FILES = frozenset((*SOURCE_FILES, "git-workspace.pyz", "source-pins.json"))
DIRECTORIES = frozenset(("source", "source/example"))


def verify(bundle, expected_sources, expected_pins):
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("artifact must be an ordinary directory")
    files = set()
    directories = set()
    for path in bundle.rglob("*"):
        name = path.relative_to(bundle).as_posix()
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed: {name}")
        if path.is_dir():
            directories.add(name)
        elif path.is_file():
            files.add(name)
        else:
            raise ValueError(f"non-regular artifact entry: {name}")
    if files != FILES | {"SHA256SUMS"} or directories != DIRECTORIES:
        raise ValueError("artifact membership differs from the explicit source-only layout")
    for name, source_name in SOURCE_FILES.items():
        if (bundle / name).read_bytes() != expected_sources[source_name]:
            raise ValueError(f"artifact differs from pinned source: {name}")
    if json.loads((bundle / "source-pins.json").read_text()) != expected_pins:
        raise ValueError("artifact pins differ from the committed source manifest")
    checksums = "".join(
        f"{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}\n"
        for name in sorted(FILES)
    )
    if (bundle / "SHA256SUMS").read_bytes() != checksums.encode("ascii"):
        raise ValueError("checksum manifest must cover exactly the six published files")
    with zipfile.ZipFile(bundle / "git-workspace.pyz") as archive:
        if archive.namelist() != ["LICENSE", "__main__.py"]:
            raise ValueError("archive must contain exactly the two ordered application members")
        for entry in archive.infolist():
            if (
                entry.date_time != (1980, 1, 1, 0, 0, 0)
                or entry.create_system != 3
                or entry.external_attr != 0o100644 << 16
                or entry.compress_type != zipfile.ZIP_DEFLATED
            ):
                raise ValueError(f"unexpected archive metadata: {entry.filename}")
            if archive.read(entry) != (bundle / "source/example" / entry.filename).read_bytes():
                raise ValueError(f"archive member differs from published source: {entry.filename}")
    # Rebuild with the same stdlib used by CI packaging to reject otherwise
    # valid ZIPs with executable prefixes, trailing payloads or hidden metadata.
    canonical = io.BytesIO()
    with zipfile.ZipFile(canonical, "w") as archive:
        for name in ("LICENSE", "__main__.py"):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, (bundle / "source/example" / name).read_bytes())
    if (bundle / "git-workspace.pyz").read_bytes() != canonical.getvalue():
        raise ValueError("archive bytes differ from the canonical source-only build")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        pins = manifest()
        revision = next(item["commit"] for item in pins["components"] if item["path"] == "sources/distro")
        # Compare Git objects at the committed gitlink, not possibly edited
        # checkout files which could otherwise agree with a corrupted bundle.
        sources = {
            name: subprocess.check_output([
                "git", "-C", str(ROOT / "sources/distro"), "show",
                f"{revision}:distro/python/{name}",
            ])
            for name in set(SOURCE_FILES.values())
        }
        verify(args.bundle, sources, pins)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, subprocess.CalledProcessError, StopIteration) as error:
        parser.exit(1, f"workspace artifact verification failed: {error}\n")
    print("Workspace source, MIT text, archive metadata, committed pins and six checksums verified")
