#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build and exercise the GNU findutils and tar process helpers natively."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISTRO = ROOT / "sources/distro/distro"
TIMEOUT_SECONDS = 90

TOOLS = {
    "findutils": {
        "source": DISTRO / "findutils-fork/helper.c",
        "runtime": DISTRO / "findutils-fork/runtime-test.sh",
        "native_programs": {
            "FIND_FORK_PROGRAM": "/usr/bin/find",
            "XARGS_FORK_PROGRAM": "/usr/bin/xargs",
        },
        "helper_variable": "FIND_FORK_HELPER",
        "stages": (
            "find fork: -exec direct children preserve cwd, arguments and live parent pass",
            "find fork: -execdir preserves spaced paths and batched arguments pass",
            "find fork: xargs null input, dev-null stdin, parallel slots and overlap pass",
            "find fork: missing/nonzero command status and recovery pass",
        ),
    },
    "tar": {
        "source": DISTRO / "tar-fork/helper.c",
        "runtime": DISTRO / "tar-fork/runtime-test.sh",
        "native_programs": {"TAR_FORK_PROGRAM": "/usr/bin/tar"},
        "helper_variable": "TAR_FORK_HELPER",
        "stages": (
            "tar fork: external filter regular archive round-trip pass",
            "tar fork: nonseekable pipe archive create, list and extract pass",
            "tar fork: to-command metadata, exact member bytes and parent environment isolation pass",
            "tar fork: failed filters return errors and later ordinary archive recovers pass",
        ),
    },
}

COMPILERS = ("gcc", "clang")
PASS_MARKER = "::vm-test::pass"
FAIL_MARKER = "::vm-test::fail"


class CheckError(RuntimeError):
    """A missing tool, build failure, or runtime contract violation."""


def run(command, *, env=None, cwd=ROOT):
    executable = Path(str(command[0])).name
    try:
        return subprocess.run(
            [str(part) for part in command],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise CheckError(f"{executable} timed out after {TIMEOUT_SECONDS}s") from error
    except OSError as error:
        raise CheckError(f"could not run {executable}: {error}") from error


def require_executable(path, label):
    if not Path(path).is_file() or not os.access(path, os.X_OK):
        raise CheckError(f"required {label} is missing or not executable: {path}")


def report_native_reference(label, program):
    require_executable(program, f"native {label} reference")
    result = run((program, "--version"))
    version = (result.stdout or result.stderr).splitlines()
    if result.returncode != 0 or not version:
        raise CheckError(
            f"could not read native {label} version from {program}: "
            f"exit {result.returncode}; {result.stderr.strip()}"
        )
    first_line = version[0].strip()
    if "GNU" not in first_line:
        raise CheckError(
            f"native {label} reference is not GNU: {program}: {first_line}"
        )
    print(f"Native GNU reference ({label}): {first_line}")


def validate_runtime_output(name, result):
    output = result.stdout
    combined = output + result.stderr
    if result.returncode != 0:
        raise CheckError(
            f"{name} runtime script exited {result.returncode}\n"
            f"stdout:\n{output}\nstderr:\n{result.stderr}"
        )
    if FAIL_MARKER in combined:
        raise CheckError(f"{name} runtime script emitted {FAIL_MARKER}\n{combined}")
    if output.count(PASS_MARKER) != 1:
        raise CheckError(
            f"{name} runtime script must emit exactly one {PASS_MARKER}; "
            f"saw {output.count(PASS_MARKER)}\nstdout:\n{output}\nstderr:\n{result.stderr}"
        )

    expected = TOOLS[name]["stages"]
    positions = []
    for marker in expected:
        if output.count(marker) != 1:
            raise CheckError(
                f"{name} runtime script must emit stage exactly once: {marker!r}\n"
                f"stdout:\n{output}\nstderr:\n{result.stderr}"
            )
        positions.append(output.index(marker))
    pass_position = output.index(PASS_MARKER)
    if positions != sorted(positions) or positions[-1] > pass_position:
        raise CheckError(
            f"{name} runtime stages were out of order or followed the pass marker\n"
            f"stdout:\n{output}"
        )
    if output.count("::vm-test::") != 1:
        raise CheckError(
            f"{name} runtime script emitted unexpected VM test markers\n"
            f"stdout:\n{output}\nstderr:\n{result.stderr}"
        )
    if output.strip().splitlines()[-1] != PASS_MARKER:
        raise CheckError(f"{name} runtime pass marker was not the final output line")
    print(output, end="")


def compile_helper(compiler, name, output):
    source = TOOLS[name]["source"]
    if not source.is_file():
        raise CheckError(f"{name} helper source is missing: {source}")
    command = (
        compiler,
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        str(source),
        "-o",
        str(output),
    )
    result = run(command)
    if result.returncode != 0:
        raise CheckError(
            f"{compiler} failed to compile {source} (exit {result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    print(f"Built {name} helper with {Path(compiler).name}: {output.name}")


def run_runtime(name, helper, compiler_label):
    tool = TOOLS[name]
    runtime = tool["runtime"]
    if not runtime.is_file():
        raise CheckError(f"{name} runtime test is missing: {runtime}")

    environment = os.environ.copy()
    environment.update(tool["native_programs"])
    environment[tool["helper_variable"]] = str(helper)
    environment["NATIVE_REFERENCE"] = "1"
    print(f"Running {name} native-reference runtime with {compiler_label} helper")
    result = run(("sh", runtime), env=environment, cwd=helper.parent)
    validate_runtime_output(name, result)


def main():
    compiler_paths = {}
    for compiler in COMPILERS:
        compiler_path = shutil.which(compiler)
        if compiler_path is None:
            raise CheckError(f"required compiler is missing from PATH: {compiler}")
        compiler_paths[compiler] = compiler_path

    for name, tool in TOOLS.items():
        for program in tool["native_programs"].values():
            report_native_reference(Path(program).name, program)

    with tempfile.TemporaryDirectory(prefix="standard-process-tools-") as temporary:
        stage = Path(temporary)
        built = {}
        for compiler, compiler_path in compiler_paths.items():
            for name in TOOLS:
                output = stage / f"{name}-helper-{compiler}"
                compile_helper(compiler_path, name, output)
                built[(compiler, name)] = output

        for compiler in COMPILERS:
            for name in TOOLS:
                run_runtime(name, built[(compiler, name)], compiler)

    print("Standard GNU process-tool helper checks passed with GCC and Clang")


if __name__ == "__main__":
    try:
        main()
    except CheckError as error:
        print(f"check_standard_process_tools: {error}", file=sys.stderr)
        raise SystemExit(1) from error
