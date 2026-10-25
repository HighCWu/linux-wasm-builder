#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile the standard FUSE protocol consumer; never mount on the host."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUSL = ROOT / "sources/musl"
LINUX = ROOT / "sources/linux"
SOURCE = ROOT / "sources/distro/distro/fuse-passthrough/runtime.c"
source_root = os.environ.get("WASM_FUSE_SOURCE_ROOT")


def source(name):
    if source_root:
        return (Path(source_root) / name).read_text()
    return subprocess.check_output(
        ["git", "-C", str(LINUX), "show", "HEAD:" + name], text=True
    )


header = source("include/uapi/linux/fuse.h")
config = (
    source("fs/fuse/Kconfig")
    .split("config FUSE_PASSTHROUGH\n", 1)[1]
    .split("\nconfig ", 1)[0]
)
assert "default y" in config and "depends on FUSE_FS" in config
for config_name in ("defconfig", "wasm32_defconfig", "wasm64_defconfig"):
    assert "CONFIG_FUSE_PASSTHROUGH" not in source("arch/wasm/configs/" + config_name)
recipe = (ROOT / "sources/distro/distro/linux/package.nix").read_text()
assert "grep -qx 'CONFIG_FUSE_PASSTHROUGH=y' .config" in recipe
assert "grep -qx 'CONFIG_FS_STACK=y' .config" in recipe
with tempfile.TemporaryDirectory(prefix="wasm-fuse-consumer-") as tmp:
    path = Path(tmp)
    (path / "linux").mkdir()
    (path / "linux/fuse.h").write_text(header)
    for cc in ("gcc", "clang"):
        subprocess.run(
            [
                cc,
                "-std=c11",
                "-pthread",
                "-fsyntax-only",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                tmp,
                str(SOURCE),
            ],
            check=True,
        )
    (path / "bits").mkdir()
    templates = (MUSL / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        MUSL / "include/alltypes.h.in"
    ).read_text()
    generated = subprocess.check_output(
        ["sed", "-f", str(MUSL / "tools/mkalltypes.sed")], input=templates, text=True
    )
    (path / "bits/alltypes.h").write_text(generated)
    numbers = (MUSL / "arch/wasm32/bits/syscall.h.in").read_text()
    (path / "bits/syscall.h").write_text(numbers + numbers.replace("__NR_", "SYS_"))
    resource = subprocess.check_output(
        ["clang", "-print-resource-dir"], text=True
    ).strip()
    for bits in (32, 64):
        command = [
            "clang",
            f"--target=wasm{bits}",
            "-std=c11",
            "-pthread",
            "-nostdinc",
            "-I",
            tmp,
            "-I",
            str(MUSL / "arch/wasm32"),
            "-I",
            str(MUSL / "arch/generic"),
            "-I",
            str(MUSL / "include"),
            "-isystem",
            resource + "/include",
            "-Wall",
            "-Wextra",
            "-Werror",
        ]
        subprocess.run([*command, "-fsyntax-only", str(SOURCE)], check=True)
        subprocess.run(
            [
                *command,
                "--analyze",
                "-Xanalyzer",
                "-analyzer-werror",
                "-o",
                "/dev/null",
                str(SOURCE),
            ],
            check=True,
        )
print(
    "FUSE consumer native/Wasm frontends and static analysis passed; no host mounts executed"
)
