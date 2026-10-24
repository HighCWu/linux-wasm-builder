#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate full-suite closure wiring and the actual final-module ABI gate."""

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DISTRO = ROOT / "sources/distro"
scope = (DISTRO / "distro/default.nix").read_text()
block = re.search(
    r"util-linux-wasm64 = self.util-linux.override \{(.*?)\n    \};", scope, re.S
).group(1)
for name in ("platform", "stdenv", "file", "zlib", "ncurses", "readline", "busybox"):
    assert f"{name} = self.{name}-wasm64;" in block, name
assert "sqlite3 = self.sqlite3-wasm64.dev;" in block
assert "vm-test = vmTestWasm64;" in block
assert "configureFlags" not in block and "patches" not in block
file_block = re.search(
    r"file-wasm64 = self.file.override \{(.*?)\n    \};", scope, re.S
).group(1)
for name in ("stdenv", "zlib", "busybox"):
    assert f"{name} = self.{name}-wasm64;" in file_block
assert "vm-test = vmTestWasm64;" in file_block
recipe = (DISTRO / "distro/util-linux/package.nix").read_text()
assert "bash ${./check-install.sh}" in recipe
assert "LLVM_READOBJ=${llvm-toolchain-unwrapped}/bin/llvm-readobj" in recipe
assert "${file}/bin/file ${busybox}/bin/busybox" in recipe
assert (
    "${toString platform.addressBits} ${toString platform.maximumMemoryBytes}" in recipe
)
assert "${file} ${zlib} ${ncurses} ${readline} ${sqlite3}" in recipe
rewrites = [
    ("${sqlite3}/lib/pkgconfig/../../lib", "/lib"),
    ("${sqlite3}/lib", "/lib"),
]
for before, after in rewrites:
    assert f'--replace-quiet "{before}" {after}' in recipe
assert 'bash ${../apk/check-store-references.sh} "$out"' in recipe
script = DISTRO / "distro/util-linux/check-install.sh"
parser = DISTRO / "packages/kernel/src/wasm_binary.ts"
checker = DISTRO / "distro/busybox/check-binary.mjs"
with tempfile.TemporaryDirectory(prefix="util-linux-width-") as tmp:
    path = Path(tmp)
    metadata = path / "liblastlog2.la"
    sqlite_root = "/nix/store/" + "0" * 32 + "-sqlite3-wasm64-dev"
    foreign_root = "/nix/store/" + "1" * 32 + "-unrelated"
    reference_checker = DISTRO / "distro/apk/check-store-references.sh"
    for library_path in (
        sqlite_root + "/lib",
        sqlite_root + "/lib/pkgconfig/../../lib",
        foreign_root + "/lib",
        "/lib",
    ):
        original = f"dependency_libs='-L{library_path} -lsqlite3 -lm -pthread'\nlibdir='/lib'\n"
        metadata.write_text(original)

        def references():
            return subprocess.run(
                ["bash", str(reference_checker), str(metadata)],
                capture_output=True,
                text=True,
                timeout=10,
            ).returncode

        assert references() == (0 if library_path == "/lib" else 1)
        normalized = original
        for before, after in rewrites:
            normalized = normalized.replace(
                before.replace("${sqlite3}", sqlite_root), after
            )
        metadata.write_text(normalized)
        assert references() == (1 if library_path.startswith(foreign_root) else 0)
        assert "-lsqlite3 -lm -pthread" in normalized
        if library_path == "/lib":
            assert normalized == original
    source = path / "fixture.c"
    source.write_text("int run(void) { return sizeof(void *); }\n")
    modules = {}
    objects = {}
    reader = shutil.which("llvm-readobj") or shutil.which("llvm-readobj-18")
    archiver = shutil.which("llvm-ar") or shutil.which("llvm-ar-18")
    assert reader and archiver
    for bits, maximum in ((32, 4294967296), (64, 17179869184)):
        module = path / f"module{bits}.wasm"
        subprocess.run(
            [
                "clang",
                f"--target=wasm{bits}",
                "-nostdlib",
                "-matomics",
                "-mbulk-memory",
                "-Wl,--no-entry,--export=run,--import-memory,--shared-memory",
                f"-Wl,--max-memory={maximum}",
                str(source),
                "-o",
                str(module),
            ],
            check=True,
        )
        modules[bits] = module
        objects[bits] = path / f"object{bits}.o"
        subprocess.run(
            [
                "clang",
                f"--target=wasm{bits}",
                "-c",
                str(source),
                "-o",
                str(objects[bits]),
            ],
            check=True,
        )
    for bits, maximum in ((32, 4294967296), (64, 17179869184)):
        other_bits = 64 if bits == 32 else 32
        for case in (
            "valid",
            "mixed-helper",
            "mixed-dependency",
            "mixed-archive",
            "host-elf",
            "empty",
        ):
            root, support = path / "out", path / "support"
            root.mkdir(exist_ok=True)
            support.mkdir(exist_ok=True)
            app, helper = root / "program", support / "private-helper"
            archive = root / "libfixture.a"
            archive.unlink(missing_ok=True)
            members = [objects[bits]]
            if case == "mixed-archive":
                members.append(objects[other_bits])
            subprocess.run(
                [archiver, "rcs", str(archive), *map(str, members)], check=True
            )
            for file in (app, helper):
                file.unlink(missing_ok=True)
            dependency = modules[bits]
            if case != "empty":
                shutil.copyfile(modules[bits], app)
                shutil.copyfile(
                    modules[other_bits] if case == "mixed-helper" else modules[bits],
                    helper,
                )
            if case == "mixed-dependency":
                dependency = modules[other_bits]
            if case == "host-elf":
                helper.write_bytes(b"\x7fELF" + bytes(32))
            result = subprocess.run(
                [
                    "bash",
                    str(script),
                    str(root),
                    str(support),
                    str(dependency),
                    str(modules[bits]),
                    str(bits),
                    str(maximum),
                    str(parser),
                    str(checker),
                ],
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "LLVM_READOBJ": reader},
            )
            if case == "valid":
                assert result.returncode == 0, result.stdout + result.stderr
                assert "memory ABI verified" in result.stdout
            else:
                assert result.returncode != 0, (bits, case)
                assert "memory ABI verified" not in result.stdout
print(
    "full util-linux wasm64 closure wiring and real final-module width gates passed, including mixed/ELF/empty controls; no target execution"
)
