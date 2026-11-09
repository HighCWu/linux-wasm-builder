#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build and run the native SQLite loadable-extension contract without a target SDK."""

from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "sources/distro/distro/sqlite3-extension-runtime"
PHASE_MARKERS = (
    "sqlite extension: standard .load registers wasm_answer and returns 42 pass",
    "sqlite extension: repeated API callbacks preserve module data state pass",
    "sqlite extension: database survives close and reopen pass",
    "sqlite extension: failed load reports an error and later load recovers pass",
    "::vm-test::pass",
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sqlite3", default="sqlite3", help="native host sqlite3 CLI")
parser.add_argument("--cc", default="cc", help="native C compiler")
args = parser.parse_args()


def resolve_program(program: str, label: str) -> str:
    resolved = shutil.which(program)
    if resolved is None:
        raise SystemExit(f"error: native {label} executable not found: {program}")
    return resolved


def run_checked(
    command: list[str], *, label: str, **kwargs
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command, check=False, text=True, capture_output=True, **kwargs
        )
    except subprocess.TimeoutExpired as error:
        raise SystemExit(f"error: {label} timed out") from error
    if result.returncode != 0:
        details = (result.stdout + result.stderr).strip()
        raise SystemExit(f"error: {label} failed (exit {result.returncode})\n{details}")
    return result


sqlite3 = resolve_program(args.sqlite3, "SQLite")
cc = resolve_program(args.cc, "C compiler")
source = RUNTIME / "extension.c"
runtime_test = RUNTIME / "runtime-test.sh"
if not source.is_file():
    raise SystemExit(f"error: SQLite extension source is missing: {source}")
if not runtime_test.is_file():
    raise SystemExit(f"error: SQLite runtime test is missing: {runtime_test}")

version = run_checked(
    [sqlite3, "--version"], label="native sqlite3 --version", timeout=10
)
sqlite_version = (version.stdout or version.stderr).strip()

headers = subprocess.run(
    [cc, "-std=c11", "-x", "c", "-fsyntax-only", "-"],
    input="#include <sqlite3.h>\n#include <sqlite3ext.h>\n",
    text=True,
    capture_output=True,
    timeout=10,
)
if headers.returncode != 0:
    details = headers.stderr.strip()
    raise SystemExit(
        "error: native SQLite development headers are unavailable; install sqlite3.h and "
        f"sqlite3ext.h for {cc}\n{details}"
    )

with tempfile.TemporaryDirectory(prefix="sqlite-load-extension-probe-") as temporary:
    temporary_path = Path(temporary)
    extension = temporary_path / "sample.so"
    run_checked(
        [
            cc,
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fPIC",
            "-shared",
            str(source),
            "-Wl,-soname,sample.so",
            "-o",
            str(extension),
        ],
        label="native SQLite loadable-extension build",
        timeout=30,
    )
    if not extension.is_file() or extension.stat().st_size == 0:
        raise SystemExit("error: native compiler did not produce the SQLite extension")

    environment = os.environ.copy()
    environment.update(
        {
            "SQLITE3": sqlite3,
            "SQLITE_EXTENSION_PATH": str(extension),
            "SQLITE_NATIVE_REFERENCE": "1",
        }
    )
    run = run_checked(
        ["sh", str(runtime_test)],
        label="SQLite extension native runtime test",
        timeout=120,
        cwd=temporary_path,
        env=environment,
    )
    output_lines = run.stdout.splitlines()
    if output_lines != list(PHASE_MARKERS):
        raise SystemExit(
            "error: SQLite runtime test output did not exactly match the expected four phases and pass marker\n"
            f"expected: {list(PHASE_MARKERS)!r}\n"
            f"actual:   {output_lines!r}\n" + "\n" + run.stderr.strip()
        )
    print(f"native SQLite loadable-extension probe: {sqlite_version}")
    print(run.stdout, end="" if run.stdout.endswith("\n") else "\n")
