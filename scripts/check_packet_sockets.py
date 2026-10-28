#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile/analyze the packet workload; never change host network or credentials."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DISTRO = ROOT / "sources/distro/distro"
program = DISTRO / "packet-sockets/runtime.c"
source = program.read_text()
assert "AF_PACKET" in source and "SOCK_RAW" in source and "SOCK_DGRAM" in source
assert "PACKET_IGNORE_OUTGOING" in source and "MSG_TRUNC" in source
assert "IFF_UP" in source and "request.ifr_flags = original" in source
assert "htons(PROTOCOL)" in source and 'if_nametoindex("lo")' in source
assert (
    "packet sockets: interface restoration, capability denial and descriptor cleanup pass"
    in source
)
assert "CONFIG_PACKET=y" in (DISTRO / "linux/package.nix").read_text()
closure = (
    (DISTRO / "default.nix")
    .read_text()
    .split("packet-sockets-wasm64 =", 1)[1]
    .split("};", 1)[0]
)
for dependency in ("stdenv", "platform", "musl", "llvm-runtimes", "busybox"):
    assert f"{dependency} = self.{dependency}-wasm64;" in closure
assert "vm-test = vmTestWasm64;" in closure

for compiler in ("gcc", "clang"):
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fsyntax-only",
            str(program),
        ],
        check=True,
    )

with tempfile.TemporaryDirectory(prefix="packet-frontends-") as tmp:
    musl = ROOT / "sources/musl"
    (Path(tmp) / "bits").mkdir()
    templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        musl / "include/alltypes.h.in"
    ).read_text()
    generated = subprocess.check_output(
        ["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates, text=True
    )
    (Path(tmp) / "bits/alltypes.h").write_text(generated)
    resource = subprocess.check_output(
        ["clang", "-print-resource-dir"], text=True
    ).strip()
    for bits in (32, 64):
        command = [
            "clang",
            f"--target=wasm{bits}",
            "-std=c11",
            "-nostdinc",
            "-I",
            tmp,
            "-I",
            str(musl / "arch/wasm32"),
            "-I",
            str(musl / "arch/generic"),
            "-I",
            str(musl / "include"),
            "-isystem",
            resource + "/include",
            "-Wall",
            "-Wextra",
            "-Werror",
        ]
        subprocess.run([*command, "-fsyntax-only", str(program)], check=True)
        subprocess.run(
            [
                *command,
                "--analyze",
                "-Xanalyzer",
                "-analyzer-werror",
                str(program),
                "-o",
                "/dev/null",
            ],
            check=True,
        )
print(
    "Packet sockets: native/Wasm32/Wasm64 frontends and analysis passed; no host network or credential changes"
)
