#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic native rename race against a temporary actual-source bundle."""

from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).read_text()
needle = "const file = await node_call(open(host_path(target), checked_flags));"
assert source.count(needle) == 1, (
    "place the race only at ordinary OPEN, after its preflight"
)
injected = source.replace(
    needle, "await globalThis.nodefsOpenRace?.(target);\n" + needle
)
fixture = Path(__file__).parent / "tests/nodefs-open-race.mjs"
with tempfile.TemporaryDirectory(prefix="nodefs-open-identity-") as directory:
    module = Path(directory) / "nodefs.mjs"
    for negative in (False, True):
        # Reintroduce eager O_TRUNC while retaining post-open identity refusal:
        # errno alone must not hide destruction of the replacement file.
        current = (
            injected.replace(
                needle,
                "const file = await node_call(open(host_path(target), host_flags));",
            )
            if negative
            else injected
        )
        module.write_text(current)
        result = subprocess.run(
            ["node", str(fixture), str(module)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if negative:
            assert (
                result.returncode != 0 and "replacement stays intact" in result.stderr
            ), result.stdout + result.stderr
            print(
                "NodeFS: eager-truncate negative control detects real replacement data loss pass"
            )
        else:
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout, end="")
    identity_check = "actual.dev !== expected.dev || actual.ino !== expected.ino"
    assert injected.count(identity_check) == 1
    for negative in (False, True):
        module.write_text(
            injected.replace(identity_check, "false") if negative else injected
        )
        result = subprocess.run(
            ["node", str(fixture), str(module), "directory"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if negative:
            assert (
                result.returncode != 0
                and "directory identity mismatch must reject" in result.stderr
            ), result.stdout + result.stderr
            print(
                "NodeFS: directory identity bypass negative control detects wrong-inode publication pass"
            )
        else:
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout, end="")
