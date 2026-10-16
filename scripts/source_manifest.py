#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Export committed source pins, without requiring submodule checkouts."""
import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def manifest(revision="HEAD"):
    commit = git("rev-parse", "--verify", "--end-of-options", revision + "^{commit}")
    components = []
    for entry in git("ls-tree", "-r", commit, "sources").splitlines():
        metadata, path = entry.split("\t", 1)
        mode, kind, object_id = metadata.split()
        if mode != "160000" or kind != "commit":
            continue
        # This repository names submodules by their source path. Read the
        # committed configuration, not a possibly edited working-tree file.
        url = git("config", "--blob", commit + ":.gitmodules", "--get", f"submodule.{path}.url")
        components.append({"path": path, "repository": url, "commit": object_id})
    if not components:
        raise ValueError("revision contains no source submodule pins")
    return {
        "schema": "linux-wasm-source-manifest-v1",
        "builder_commit": commit,
        "scope": "Committed source submodule pins; not a binary SBOM or corresponding-source archive",
        "components": components,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="HEAD", help="committed revision (default: HEAD)")
    args = parser.parse_args()
    try:
        print(json.dumps(manifest(args.revision), indent=2, ensure_ascii=False))
    except (subprocess.CalledProcessError, ValueError) as error:
        parser.exit(1, f"cannot export source manifest: {error}\n")
