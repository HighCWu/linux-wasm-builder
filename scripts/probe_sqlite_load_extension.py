#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build and run the native SQLite loadable-extension contract without a target SDK."""

from pathlib import Path
import argparse
import os
import shlex
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
    "sqlite extension: linked static-library C client passed",
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
client_source = RUNTIME / "linked-client.c"
runtime_test = RUNTIME / "runtime-test.sh"
if not source.is_file():
    raise SystemExit(f"error: SQLite extension source is missing: {source}")
if not client_source.is_file():
    raise SystemExit(
        f"error: SQLite linked-client source is missing: {client_source}"
    )
if not runtime_test.is_file():
    raise SystemExit(f"error: SQLite runtime test is missing: {runtime_test}")

version = run_checked(
    [sqlite3, "--version"], label="native sqlite3 --version", timeout=10
)
sqlite_version = (version.stdout or version.stderr).strip()

pkg_config = shutil.which("pkg-config") or shutil.which("pkgconf")
if pkg_config is not None:
    try:
        pkg_cflags = subprocess.run(
            [pkg_config, "--cflags", "sqlite3"],
            check=False,
            text=True,
            capture_output=True,
            timeout=10,
        )
        pkg_libs = subprocess.run(
            [pkg_config, "--libs", "sqlite3"],
            check=False,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as error:
        raise SystemExit("error: host SQLite pkg-config query timed out") from error
else:
    pkg_cflags = pkg_libs = None

if (
    pkg_cflags is not None
    and pkg_libs is not None
    and pkg_cflags.returncode == 0
    and pkg_libs.returncode == 0
):
    sqlite_cflags = shlex.split(pkg_cflags.stdout)
    sqlite_libs = shlex.split(pkg_libs.stdout)
else:
    # The header check below confirms that host headers are visible; use the
    # conventional host library name when pkg-config metadata is unavailable.
    sqlite_cflags = []
    sqlite_libs = ["-lsqlite3"]

headers = subprocess.run(
    [cc, *sqlite_cflags, "-std=c11", "-x", "c", "-fsyntax-only", "-"],
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
    client = temporary_path / "sqlite3-extension-runtime-client"
    run_checked(
        [
            cc,
            *sqlite_cflags,
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

    run_checked(
        [
            cc,
            *sqlite_cflags,
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(client_source),
            *sqlite_libs,
            "-o",
            str(client),
        ],
        label="native linked SQLite C client build",
        timeout=30,
    )
    if (
        not client.is_file()
        or client.stat().st_size == 0
        or not os.access(client, os.X_OK)
    ):
        raise SystemExit(
            "error: native compiler did not produce an executable SQLite C client"
        )

    environment = os.environ.copy()
    environment.update(
        {
            "SQLITE3": sqlite3,
            "SQLITE_EXTENSION_CLIENT": str(client.resolve()),
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
            "error: SQLite runtime test output did not match the expected phase markers\n"
            f"expected: {list(PHASE_MARKERS)!r}\n"
            f"actual:   {output_lines!r}\n" + "\n" + run.stderr.strip()
        )
    print(f"native SQLite loadable-extension probe: {sqlite_version}")
    print(run.stdout, end="" if run.stdout.endswith("\n") else "\n")
