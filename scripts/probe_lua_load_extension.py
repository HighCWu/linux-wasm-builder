#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build and run the Lua 5.4.8 native loadable-extension contract."""

from pathlib import Path
import argparse
import os
import re
import shlex
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "sources/distro/distro/lua-extension-runtime"
PHASE_MARKERS = (
    "lua extension: standard C module import and resident state pass",
    "lua extension: callback errors and cross-module longjmp recovery pass",
    "lua extension: failed load and later valid load recovery pass",
    "lua extension: process exit and temporary files cleanup pass",
    "::vm-test::pass",
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--lua-source",
    required=True,
    type=Path,
    help="unpacked official Lua 5.4.8 source tree",
)
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


lua_source = args.lua_source.expanduser().resolve()
lua_header = lua_source / "src/lua.h"
required_files = (
    lua_source / "Makefile",
    lua_source / "src/Makefile",
    lua_header,
)
for path in required_files:
    if not path.is_file():
        raise SystemExit(f"error: Lua source tree is incomplete; missing {path}")

header_text = lua_header.read_text(encoding="utf-8")
version_definitions = {
    "LUA_VERSION_MAJOR": r'#define\s+LUA_VERSION_MAJOR\s+"5"',
    "LUA_VERSION_MINOR": r'#define\s+LUA_VERSION_MINOR\s+"4"',
    "LUA_VERSION_NUM": r"#define\s+LUA_VERSION_NUM\s+504\b",
    "LUA_VERSION_RELEASE": r'#define\s+LUA_VERSION_RELEASE\s+"8"',
}
for macro, pattern in version_definitions.items():
    if re.search(pattern, header_text) is None:
        raise SystemExit(
            f"error: --lua-source is not Lua 5.4.8; expected {macro} in {lua_header}"
        )

make = resolve_program("make", "make")
cc = resolve_program(args.cc, "C compiler")
ar = resolve_program("ar", "archiver")
ranlib = resolve_program("ranlib", "ranlib")
runtime_module = RUNTIME / "module.c"
runtime_consumer = RUNTIME / "consumer.lua"
runtime_test = RUNTIME / "runtime-test.sh"
for path in (runtime_module, runtime_consumer, runtime_test):
    if not path.is_file():
        raise SystemExit(f"error: Lua extension runtime file is missing: {path}")

with tempfile.TemporaryDirectory(prefix="lua-load-extension-probe-") as temporary:
    temporary_path = Path(temporary)
    copied_source = temporary_path / "lua-5.4.8"
    shutil.copytree(lua_source, copied_source)

    run_checked(
        [
            make,
            "-C",
            str(copied_source / "src"),
            "linux",
            f"CC={cc}",
            f"AR={ar} rcu",
            f"RANLIB={ranlib}",
        ],
        label="native Lua 5.4.8 build (make linux)",
        timeout=180,
    )
    lua = copied_source / "src/lua"
    if not lua.is_file() or not os.access(lua, os.X_OK):
        raise SystemExit("error: native Lua build did not produce an executable")
    lua_version = run_checked(
        [str(lua), "-v"], label="native Lua version check", timeout=10
    )
    if "Lua 5.4.8" not in (lua_version.stdout + lua_version.stderr):
        raise SystemExit(
            "error: native Lua executable is not version 5.4.8\n"
            + (lua_version.stdout + lua_version.stderr).strip()
        )

    module = temporary_path / "nativeprobe.so"
    run_checked(
        [
            cc,
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fPIC",
            "-shared",
            "-I",
            str(copied_source / "src"),
            str(runtime_module),
            "-o",
            str(module),
        ],
        label="native Lua C module build",
        timeout=30,
    )
    if not module.is_file() or module.stat().st_size == 0:
        raise SystemExit("error: native compiler did not produce nativeprobe.so")

    consumer = temporary_path / "consumer.lua"
    shutil.copyfile(runtime_consumer, consumer)
    runtime_text = runtime_test.read_text(encoding="utf-8")
    if "@consumer@" not in runtime_text:
        raise SystemExit(
            f"error: Lua runtime test has no @consumer@ source placeholder: {runtime_test}"
        )
    patched_runtime = temporary_path / "runtime-test.sh"
    patched_runtime.write_text(
        runtime_text.replace("@consumer@", shlex.quote(str(consumer))),
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "LUA_EXTENSION_NATIVE_REFERENCE": "1",
            "LUA_EXTENSION_LUA": str(lua),
            "LUA_EXTENSION_MODULE": str(module),
        }
    )
    run = run_checked(
        ["sh", str(patched_runtime)],
        label="Lua extension native runtime test",
        timeout=120,
        cwd=temporary_path,
        env=environment,
    )
    output_lines = run.stdout.splitlines()
    if output_lines != list(PHASE_MARKERS):
        raise SystemExit(
            "error: Lua runtime test output did not exactly match the expected phases and pass marker\n"
            f"expected: {list(PHASE_MARKERS)!r}\n"
            f"actual:   {output_lines!r}\n" + run.stderr.strip()
        )
    print("native Lua loadable-extension probe: Lua 5.4.8")
    print(run.stdout, end="" if run.stdout.endswith("\n") else "\n")
