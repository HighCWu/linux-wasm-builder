#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise real install phases and the payload guard, without a Nix/Wasm build."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
DISTRO = ROOT / "sources/distro/distro"
GUARD = DISTRO / "apk/check-store-references.sh"
STORE = "/nix/store/00000000000000000000000000000000-"


def exercise(program, recipe_path, runtime_path, leak):
    recipe = recipe_path.read_text()
    match = re.search(r"installPhase = ''\n(.*?)\n  '';", recipe, re.S)
    assert match, "missing install phase: " + str(recipe_path)
    phase = textwrap.dedent(match[1])
    if leak:
        phase = phase.replace("$buildMaterials", "$out")
    with tempfile.TemporaryDirectory(prefix="runtime-materials-") as tmp:
        stage = Path(tmp)
        work = stage / "work"
        work.mkdir()
        notices = stage / "inputs"
        (notices / "compiler-rt").mkdir(parents=True)
        (notices / "COPYRIGHT").write_text("Fixture library notice\n")
        (notices / "compiler-rt/LICENSE.TXT").write_text("Fixture runtime notice\n")
        # Opaque payload fixtures: this check never compiles or executes Wasm.
        for name in ("cgroup-pids", "program.wasm", "verify.wasm"):
            (work / name).write_bytes(b"\0asm\1\0\0\0")
        (work / "Documentation/licenses").mkdir(parents=True)
        (work / "Documentation/licenses/COPYING.MIT").write_text("Fixture license\n")
        (work / "COPYING").write_text("Fixture upstream notice\n")
        (work / "config.h").write_text("/* fixture config */\n")
        (work / "config.log").write_text("compiler=" + STORE + "compiler/bin/clang\n")
        (work / "program-source.sha256").write_text("fixture source identity\n")
        substitutions = {
            "program": program,
            "./runtime.c": shlex.quote(str(runtime_path)),
            "runtimeSource": shlex.quote(str(runtime_path)),
            "./package.nix": shlex.quote(str(recipe_path)),
            "../sdk/LICENSE.MIT": shlex.quote(str(DISTRO / "sdk/LICENSE.MIT")),
            "musl.src": shlex.quote(str(notices)),
            "llvm-runtimes.src": shlex.quote(str(notices)),
            "sdk-fork-continuation.buildMaterials": shlex.quote(
                STORE + "fork-sdk-materials"
            ),
        }
        phase = re.sub(r"\$\{([^}]+)\}", lambda m: substitutions[m[1]], phase)
        output = stage / "out"
        materials = stage / "materials"
        environment = dict(
            os.environ,
            out=str(output),
            buildMaterials=str(materials),
            src=STORE + "util-linux-source",
        )
        subprocess.run(
            ["bash", "-euc", "runHook() { :; }\n" + phase],
            cwd=work,
            env=environment,
            check=True,
        )
        runtime = subprocess.run(
            ["bash", str(GUARD), str(output)], capture_output=True, text=True
        )
        assert runtime.returncode == (1 if leak else 0), (
            program,
            leak,
            runtime.stdout,
            runtime.stderr,
        )
        if not leak:
            # The source/compiler identities remain available for rebuilds.
            # They have moved to a separate output, not been silently erased.
            preserved = subprocess.run(
                ["bash", str(GUARD), str(materials)], capture_output=True, text=True
            )
            assert (
                preserved.returncode == 1
                and "APK payload contains Nix store references" in preserved.stderr
            )
            assert (output / "bin" / program).is_file()
            assert any(
                "sdk" in dirs + files for _, dirs, files in os.walk(materials)
            ), "SDK materials were lost"
        else:
            assert "APK payload contains Nix store references" in runtime.stderr


for name, recipe, workload in (
    ("cgroup-pids", "cgroup-pids", "cgroup-pids"),
    ("setsid", "util-linux-fork", "setsid-fork"),
    ("flock", "util-linux-fork", "flock-fork"),
):
    for bad in (False, True):
        exercise(
            name, DISTRO / recipe / "package.nix", DISTRO / workload / "runtime.c", bad
        )

print(
    "Real install phases: runtime payloads exclude store references, rebuild materials survive separately; leaking controls rejected"
)
