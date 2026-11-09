#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the ELF carrier producer, parser, and inspector on small fixtures."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
LLD_WASM = Path(
    os.environ.get(
        "ELF_CONTAINER_LLD_SOURCE_ROOT", ROOT / "sources/llvm-project/lld/wasm"
    )
)
KERNEL_WASM = Path(
    os.environ.get(
        "ELF_CONTAINER_KERNEL_SOURCE_ROOT", ROOT / "sources/linux/arch/wasm/kernel"
    )
)
INSPECT = ROOT / "sources/distro/distro/elf-container/inspect.mjs"
HARNESS = ROOT / "scripts/tests/elf-container-native.cpp"


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, **kwargs)


def compile_native_harness(build_dir: Path) -> Path:
    cc = shlex.split(os.environ.get("CC", "cc"))
    cxx = shlex.split(os.environ.get("CXX", "c++"))
    parser_object = build_dir / "elf_container_parser.o"
    executable = build_dir / "elf-container-native"
    run(
        cc
        + [
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-I",
            str(KERNEL_WASM),
            "-c",
            str(KERNEL_WASM / "elf_container.c"),
            "-o",
            str(parser_object),
        ]
    )
    run(
        cxx
        + [
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-I",
            str(LLD_WASM),
            "-I",
            str(KERNEL_WASM),
            str(HARNESS),
            str(LLD_WASM / "ElfContainer.cpp"),
            str(parser_object),
            "-o",
            str(executable),
        ]
    )
    return executable


def reject_inspection(node, source: Path, bits: int, output: Path) -> None:
    output.write_bytes(b"keep-existing-output")
    result = subprocess.run(
        [node, str(INSPECT), str(source), str(bits), str(output)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode != 0, f"inspector accepted malformed input {source.name}"
    assert output.read_bytes() == b"keep-existing-output", (
        "failed inspection changed output"
    )


def test_inspector(node: str, directory: Path) -> None:
    wasm = b"\x00asm\x01\x00\x00\x00"
    for bits, segment_offset, module_offset in ((32, 84, 116), (64, 120, 152)):
        source = directory / f"elf{bits}.bin"
        output = directory / f"raw{bits}.wasm"
        result = run(
            [node, str(INSPECT), str(source), str(bits), str(output)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        metadata = json.loads(result.stdout)
        assert output.read_bytes() == wasm
        assert metadata == {
            "format": "linux-wasm-elf-container",
            "version": 1,
            "addressBits": bits,
            "moduleSize": len(wasm),
            "moduleOffset": module_offset,
            "fileSize": module_offset + len(wasm),
        }
        imported_parse = run(
            [
                node,
                "--input-type=module",
                "-e",
                (
                    'import {readFileSync} from "node:fs"; '
                    f'import {{parseElfContainer}} from "{INSPECT.as_uri()}"; '
                    "process.stdout.write(JSON.stringify(parseElfContainer("
                    "readFileSync(process.argv[1]), Number(process.argv[2]))));"
                ),
                str(source),
                str(bits),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert json.loads(imported_parse.stdout) == {
            "moduleOffset": module_offset,
            "moduleSize": len(wasm),
            "addressBits": bits,
        }

        original = source.read_bytes()
        mutations = {
            "short-prefix": original[: module_offset + len(wasm) - 1],
            "wrong-width": bytearray(original),
            "unknown-version": bytearray(original),
            "extra-phdr": bytearray(original),
            "overflow-size": bytearray(original),
        }
        mutations["wrong-width"][segment_offset + 16 : segment_offset + 20] = (
            64 if bits == 32 else 32
        ).to_bytes(4, "little")
        mutations["unknown-version"][segment_offset + 12 : segment_offset + 16] = (
            2
        ).to_bytes(4, "little")
        phnum_offset = 44 if bits == 32 else 56
        mutations["extra-phdr"][phnum_offset : phnum_offset + 2] = (2).to_bytes(
            2, "little"
        )
        mutations["overflow-size"][segment_offset + 24 : segment_offset + 32] = (
            (1 << 64) - 1
        ).to_bytes(8, "little")

        for name, malformed in mutations.items():
            fixture = directory / f"{name}-{bits}.elf"
            fixture.write_bytes(malformed)
            reject_inspection(node, fixture, bits, output)

        reject_inspection(node, source, 64 if bits == 32 else 32, output)

    source = directory / "elf32.bin"
    before = source.read_bytes()
    result = subprocess.run(
        [node, str(INSPECT), str(source), "32", str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode != 0, "inspector accepted the input file as its own output"
    assert source.read_bytes() == before, "same-file rejection modified the ELF input"


def main() -> None:
    node = os.environ.get("NODE", "node")
    with tempfile.TemporaryDirectory(prefix="elf-container-") as temporary:
        directory = Path(temporary)
        native_harness = compile_native_harness(directory)
        run([str(native_harness), str(directory)])
        test_inspector(node, directory)
    print("ELF container producer/parser/inspector checks passed")


if __name__ == "__main__":
    main()
