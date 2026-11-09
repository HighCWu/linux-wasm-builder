#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build and run the native C++ cross-DSO exception reference fixture."""

from pathlib import Path
import argparse
import os
import shlex
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "sources/distro/distro/cxx-dynamic-runtime"
PHASE_MARKERS = (
    "cxx dynamic: std::string allocation and DSO constructor pass",
    "cxx dynamic: std::runtime_error typed catch and DSO RAII unwind pass",
    "cxx dynamic: callback exception typed catch and rethrow across DSOs pass",
    "cxx dynamic: repeated calls and recovered exceptions after clean process exit pass",
    "::vm-test::pass",
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cxx", default="c++", help="native C++ compiler (default: c++)")
args = parser.parse_args()


def resolve_compiler(command: str) -> list[str]:
    compiler = shlex.split(command)
    if not compiler:
        raise SystemExit("error: native C++ compiler command is empty")
    resolved = shutil.which(compiler[0])
    if resolved is None:
        raise SystemExit(
            f"error: native C++ compiler executable not found: {compiler[0]}"
        )
    compiler[0] = resolved
    return compiler


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


compiler = resolve_compiler(args.cxx)
compiler_version = run_checked(
    [*compiler, "--version"], label="native C++ compiler version", timeout=10
)
compiler_name = (compiler_version.stdout or compiler_version.stderr).splitlines()[0]

source_main = RUNTIME / "main.cc"
source_plugin = RUNTIME / "plugin.cc"
source_shared = RUNTIME / "shared.hpp"
runtime_test = RUNTIME / "runtime-test.sh"
for path in (source_main, source_plugin, source_shared, runtime_test):
    if not path.is_file():
        raise SystemExit(f"error: C++ dynamic-linking runtime file is missing: {path}")

header_probe = subprocess.run(
    [
        *compiler,
        "-std=c++17",
        "-x",
        "c++",
        "-fsyntax-only",
        "-",
    ],
    input="#include <string>\n#include <stdexcept>\n#include <exception>\n#include <dlfcn.h>\n",
    text=True,
    capture_output=True,
    timeout=10,
)
if header_probe.returncode != 0:
    raise SystemExit(
        "error: native C++17/system headers are unavailable for "
        + compiler[0]
        + f"\n{header_probe.stderr.strip()}"
    )

with tempfile.TemporaryDirectory(prefix="cxx-dynamic-linking-probe-") as temporary:
    temporary_path = Path(temporary)
    plugin = temporary_path / "plugin.so"
    program = temporary_path / "cxx-dynamic-runtime"
    common = [
        *compiler,
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fexceptions",
        "-I",
        str(RUNTIME),
    ]
    run_checked(
        [*common, "-fPIC", "-shared", str(source_plugin), "-o", str(plugin)],
        label="native C++ plugin build",
        timeout=30,
    )
    run_checked(
        [*common, "-rdynamic", str(source_main), "-ldl", "-o", str(program)],
        label="native C++ main build",
        timeout=30,
    )
    if not plugin.is_file() or plugin.stat().st_size == 0:
        raise SystemExit("error: native compiler did not produce plugin.so")
    if not program.is_file() or program.stat().st_size == 0:
        raise SystemExit("error: native compiler did not produce the C++ test program")

    environment = os.environ.copy()
    environment.update(
        {
            "CXX_DYNAMIC_NATIVE_REFERENCE": "1",
            "CXX_DYNAMIC_PROGRAM": str(program),
            "CXX_DYNAMIC_PLUGIN": str(plugin),
        }
    )
    run = run_checked(
        ["sh", str(runtime_test)],
        label="C++ dynamic-linking native runtime test",
        timeout=120,
        cwd=temporary_path,
        env=environment,
    )
    output_lines = run.stdout.splitlines()
    if output_lines != list(PHASE_MARKERS):
        raise SystemExit(
            "error: C++ runtime test output did not exactly match the expected four phases and pass marker\n"
            f"expected: {list(PHASE_MARKERS)!r}\n"
            f"actual:   {output_lines!r}\n" + run.stderr.strip()
        )
    print(
        f"native C++ dynamic-linking reference (not Wasm EH acceptance): {compiler_name}"
    )
    print(run.stdout, end="" if run.stdout.endswith("\n") else "\n")
