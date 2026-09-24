#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

"""Validate repository metadata without building the large source trees."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

SOURCES = {
    "distro": {
        "branch": "main",
        "url": "https://github.com/HighCWu/distro.git",
    },
    "linux": {
        "branch": "wasm",
        "url": "https://github.com/HighCWu/linux.git",
        "nix": "distro/linux/package.nix",
    },
    "llvm-project": {
        "branch": "wasm-linux",
        "url": "https://github.com/HighCWu/llvm-project.git",
        "nix": "distro/llvm-toolchain/unwrapped.nix",
    },
    "musl": {
        "branch": "master",
        "url": "https://github.com/HighCWu/musl.git",
        "nix": "distro/musl/package.nix",
    },
}


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, stderr=subprocess.STDOUT
    ).strip()


def gitmodule(name: str, field: str) -> str:
    return git("config", "--file", ".gitmodules", "--get", f"submodule.sources/{name}.{field}")


def gitlink(name: str) -> str:
    fields = git("ls-tree", "HEAD", f"sources/{name}").split()
    if len(fields) < 3 or fields[0] != "160000" or fields[1] != "commit":
        raise ValueError(f"sources/{name} is not a gitlink in HEAD")
    return fields[2]


def fetch_github_fields(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    block = re.search(r"src\s*\?\s*pkgs\.fetchFromGitHub\s*\{(.*?)\n\s*\},", text, re.DOTALL)
    if block is None:
        raise ValueError(f"cannot find src fetchFromGitHub block in {path.relative_to(ROOT)}")

    fields = dict(re.findall(r'\b(owner|repo|rev)\s*=\s*"([^"]+)"\s*;', block.group(1)))
    missing = {"owner", "repo", "rev"} - fields.keys()
    if missing:
        raise ValueError(f"missing {', '.join(sorted(missing))} in {path.relative_to(ROOT)}")
    return fields


def check_text_files() -> list[str]:
    errors: list[str] = []
    paths = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *sorted((ROOT / "docs").glob("*.md"))]

    for path in paths:
        data = path.read_bytes()
        if not data.endswith(b"\n"):
            errors.append(f"{path.relative_to(ROOT)}: missing final newline")
        for number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
            if line.rstrip() != line:
                errors.append(f"{path.relative_to(ROOT)}:{number}: trailing whitespace")
            if len(line) > 120:
                errors.append(f"{path.relative_to(ROOT)}:{number}: line exceeds 120 characters")
    return errors


def check_sources() -> list[str]:
    errors: list[str] = []
    revisions: dict[str, str] = {}

    for name, expected in SOURCES.items():
        try:
            revisions[name] = gitlink(name)
            actual_url = gitmodule(name, "url")
            actual_branch = gitmodule(name, "branch")
            shallow = gitmodule(name, "shallow")
        except (subprocess.CalledProcessError, ValueError) as error:
            errors.append(str(error))
            continue

        if actual_url != expected["url"]:
            errors.append(f"sources/{name}: URL is {actual_url!r}, expected {expected['url']!r}")
        if actual_branch != expected["branch"]:
            errors.append(
                f"sources/{name}: branch is {actual_branch!r}, expected {expected['branch']!r}"
            )
        if shallow != "true":
            errors.append(f"sources/{name}: shallow must be true")

    distro = ROOT / "sources/distro"
    if not (distro / ".git").exists():
        errors.append("sources/distro is not initialized; run git submodule update --init sources/distro")
        return errors

    for name, expected in SOURCES.items():
        if "nix" not in expected or name not in revisions:
            continue
        path = distro / expected["nix"]
        try:
            fields = fetch_github_fields(path)
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue

        if fields["owner"] != "HighCWu":
            errors.append(f"{path.relative_to(ROOT)}: owner must be HighCWu")
        if fields["repo"] != name:
            errors.append(f"{path.relative_to(ROOT)}: repo is {fields['repo']!r}, expected {name!r}")
        if fields["rev"] != revisions[name]:
            errors.append(
                f"{path.relative_to(ROOT)}: rev {fields['rev']} does not match "
                f"sources/{name} {revisions[name]}"
            )

    return errors


def main() -> int:
    errors = [*check_text_files(), *check_sources()]
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    print("repository metadata and documentation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
