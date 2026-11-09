#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build and run the native fork/madvise contract without a target SDK."""

from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "sources/distro/distro/fork-memory-advice"
PHASE_MARKERS = (
    "fork memory advice: partial wipe and keep ranges pass",
    "fork memory advice: inherited wiping across nested fork pass",
    "fork memory advice: keep and remap inheritance pass",
    "fork memory advice: cleanup and later fork recovery pass",
    "::vm-test::pass",
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cc", default="cc", help="native C compiler (default: cc)")
args = parser.parse_args()


def resolve_program(program: str, label: str) -> str:
    resolved = shutil.which(program)
    if resolved is None:
        raise SystemExit(f"error: native {label} executable not found: {program}")
    return resolved


def run_checked(
    command: list[str], *, label: str, timeout: int, **kwargs
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout,
            **kwargs,
        )
    except subprocess.TimeoutExpired as error:
        raise SystemExit(f"error: {label} timed out after {timeout}s") from error
    except OSError as error:
        raise SystemExit(f"error: could not run {label}: {error}") from error
    if result.returncode != 0:
        details = (result.stdout + result.stderr).strip()
        raise SystemExit(f"error: {label} failed (exit {result.returncode})\n{details}")
    return result


cc = resolve_program(args.cc, "C compiler")
source = RUNTIME / "runtime.c"
runtime_test = RUNTIME / "runtime-test.sh"
for path in (source, runtime_test):
    if not path.is_file():
        raise SystemExit(f"error: fork memory advice runtime file is missing: {path}")

with tempfile.TemporaryDirectory(prefix="fork-memory-advice-probe-") as temporary:
    temporary_path = Path(temporary)
    program = temporary_path / "fork-memory-advice"
    run_checked(
        [
            cc,
            "-std=gnu11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source),
            "-o",
            str(program),
        ],
        label="native fork memory advice build",
        timeout=30,
    )
    if not program.is_file() or program.stat().st_size == 0:
        raise SystemExit("error: native compiler did not produce the runtime program")

    environment = os.environ.copy()
    environment.update(
        {
            "FORK_MEMORY_ADVICE_PROGRAM": str(program),
            "FORK_MEMORY_ADVICE_NATIVE_REFERENCE": "1",
        }
    )
    run = run_checked(
        ["sh", str(runtime_test)],
        label="fork memory advice native runtime test",
        timeout=120,
        cwd=temporary_path,
        env=environment,
    )
    output_lines = run.stdout.splitlines()
    if output_lines != list(PHASE_MARKERS):
        raise SystemExit(
            "error: fork memory advice runtime output did not exactly match the expected phases and pass marker\n"
            f"expected: {list(PHASE_MARKERS)!r}\n"
            f"actual:   {output_lines!r}\n" + run.stderr.strip()
        )
    print("native fork memory advice probe: host reference only")
    print(run.stdout, end="" if run.stdout.endswith("\n") else "\n")
