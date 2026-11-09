#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build and run the native Python C-extension contract without a target SDK."""

from pathlib import Path
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "sources/distro/distro/python-extension-runtime"
PHASE_MARKERS = (
    "python extension: standard .so import and answer 42 pass",
    "python extension: Python callbacks preserve module state pass",
    "python extension: bad init ImportError and recovery pass",
    "python extension: files and stdlib import with clean interpreter exit pass",
    "::vm-test::pass",
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--python", default=sys.executable, help="native Python used by runtime-test.sh"
)
parser.add_argument(
    "--cc", help="native compiler override (default: selected Python's sysconfig CC)"
)
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


python = resolve_program(args.python, "Python")
sysconfig_probe = run_checked(
    [
        python,
        "-c",
        "import json,sys,sysconfig; print(json.dumps({"
        "'version':sys.version,'version_info':list(sys.version_info[:3]),"
        "'include':sysconfig.get_path('include'),"
        "'platinclude':sysconfig.get_path('platinclude'),"
        "'cc':sysconfig.get_config_var('CC'),"
        "'ext_suffix':sysconfig.get_config_var('EXT_SUFFIX')}))",
    ],
    label="selected Python sysconfig query",
    timeout=10,
)
try:
    python_config = json.loads(sysconfig_probe.stdout)
except json.JSONDecodeError as error:
    raise SystemExit(
        "error: selected Python returned invalid sysconfig data"
    ) from error
if tuple(python_config["version_info"][:2]) < (3, 11):
    raise SystemExit("error: native reference requires Python 3.11 or newer")
include_dirs = list(
    dict.fromkeys(
        path
        for path in (python_config["include"], python_config["platinclude"])
        if path
    )
)
if not include_dirs:
    raise SystemExit(
        f"error: selected Python has no sysconfig include directory: {python}"
    )
extension_suffix = python_config["ext_suffix"]
if not extension_suffix:
    raise SystemExit(f"error: selected Python sysconfig has no EXT_SUFFIX: {python}")

compiler = shlex.split(args.cc if args.cc is not None else (python_config["cc"] or ""))
if not compiler:
    raise SystemExit(
        "error: no native C compiler in selected Python sysconfig; pass --cc"
    )
compiler_path = shutil.which(compiler[0])
if compiler_path is None:
    raise SystemExit(f"error: native C compiler executable not found: {compiler[0]}")
compiler[0] = compiler_path

source_extension = RUNTIME / "extension.c"
source_badinit = RUNTIME / "badinit.c"
runtime_script = RUNTIME / "runtime.py"
runtime_test = RUNTIME / "runtime-test.sh"
for path in (source_extension, source_badinit, runtime_script, runtime_test):
    if not path.is_file():
        raise SystemExit(f"error: Python extension runtime file is missing: {path}")

header_probe = subprocess.run(
    [
        *compiler,
        *(argument for directory in include_dirs for argument in ("-I", directory)),
        "-x",
        "c",
        "-fsyntax-only",
        "-",
    ],
    input="#include <Python.h>\n",
    text=True,
    capture_output=True,
    timeout=10,
)
if header_probe.returncode != 0:
    raise SystemExit(
        "error: selected Python development headers are unavailable; expected Python.h in "
        + ", ".join(include_dirs)
        + f"\n{header_probe.stderr.strip()}"
    )

with tempfile.TemporaryDirectory(prefix="python-load-extension-probe-") as temporary:
    temporary_path = Path(temporary)
    module_dir = temporary_path / "modules"
    module_dir.mkdir()
    for module, source in (
        ("_wasmexample", source_extension),
        ("_wasmbadinit", source_badinit),
    ):
        output = module_dir / f"{module}{extension_suffix}"
        run_checked(
            [
                *compiler,
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-fPIC",
                "-shared",
                *(
                    argument
                    for directory in include_dirs
                    for argument in ("-I", directory)
                ),
                str(source),
                "-o",
                str(output),
            ],
            label=f"native Python extension build ({module})",
            timeout=30,
        )
        if not output.is_file() or output.stat().st_size == 0:
            raise SystemExit(f"error: native compiler did not produce {output.name}")

    environment = os.environ.copy()
    environment.update(
        {
            "PYTHON_EXTENSION_PYTHON": python,
            "PYTHON_EXTENSION_MODULE_DIR": str(module_dir),
            "PYTHON_EXTENSION_SCRIPT": str(runtime_script),
            "PYTHON_EXTENSION_NATIVE_REFERENCE": "1",
        }
    )
    run = run_checked(
        ["sh", str(runtime_test)],
        label="Python extension native runtime test",
        timeout=120,
        cwd=temporary_path,
        env=environment,
    )
    output_lines = run.stdout.splitlines()
    if output_lines != list(PHASE_MARKERS):
        raise SystemExit(
            "error: Python runtime test output did not exactly match the expected four phases and pass marker\n"
            f"expected: {list(PHASE_MARKERS)!r}\n"
            f"actual:   {output_lines!r}\n" + run.stderr.strip()
        )
    print(
        f"native Python loadable-extension probe: {python_config['version'].splitlines()[0]}"
    )
    print(run.stdout, end="" if run.stdout.endswith("\n") else "\n")
