#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise Linux64 wasm varargs through Clang, wasm-ld, and Node memory64."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


TRIPLE = "wasm64-unknown-linux-musl"
SOURCE = r"""
#include <stdarg.h>

static __attribute__((noinline)) int check_mixed(
    int expected_int, unsigned long expected_long, double expected_double,
    void *expected_pointer, ...)
{
    va_list args;
    va_list copied;
    va_start(args, expected_pointer);
    va_copy(copied, args);

    int values_match = 1;
    int copied_values_match = 1;
    values_match &= va_arg(args, int) == expected_int;
    values_match &= va_arg(args, unsigned long) == expected_long;
    values_match &= va_arg(args, double) == expected_double;
    values_match &= va_arg(args, void *) == expected_pointer;
    copied_values_match &= va_arg(copied, int) == expected_int;
    copied_values_match &= va_arg(copied, unsigned long) == expected_long;
    copied_values_match &= va_arg(copied, double) == expected_double;
    copied_values_match &= va_arg(copied, void *) == expected_pointer;

    va_end(copied);
    va_end(args);
    return values_match && copied_values_match;
}

static __attribute__((noinline)) int check_int_slots(int expected_first,
                                                      int expected_second, ...)
{
    va_list args;
    va_start(args, expected_second);
    // Adjacent matching int arguments catch a default ABI slot-width change.
    int first = va_arg(args, int);
    int second = va_arg(args, int);
    va_end(args);
    return first == expected_first && second == expected_second;
}

#ifdef TEST_LINUX64
static __attribute__((noinline)) int check_int_as_word(unsigned long expected, ...)
{
    va_list args;
    va_start(args, expected);
    // This intentionally checks the ABI's zero-filled 8-byte slot for int.
    unsigned long value = va_arg(args, unsigned long);
    va_end(args);
    return value == expected;
}
#endif

__attribute__((visibility("default"))) int run(unsigned int seed)
{
    int marker = 0;
    __builtin___clear_cache((char *)&marker, (char *)(&marker + 1));
    int int_value = (int)((seed ^ 0x13579bdfU) & 0x7fffffffU);
    unsigned long long_value = ((unsigned long)seed << 32) | 0x89abcdefUL;
    double double_value = (double)((seed & 255U) + 1U) + 0.25;
    if (!check_mixed(int_value, long_value, double_value, &marker,
                     int_value, long_value, double_value, &marker))
        return 1;
    int first_int = (int)((seed ^ 0x2468ace0U) & 0x7fffffffU);
    int second_int = (int)((seed ^ 0x10203040U) & 0x7fffffffU);
    if (!check_int_slots(first_int, second_int, first_int, second_int))
        return 2;
#ifdef TEST_LINUX64
    // The caller passes an ordinary int value without widening it; the callee
    // reads its full zero-extended machine word to verify the upper half.
    int word_int = (int)((seed ^ 0x02468aceU) & 0x7fffffffU);
    unsigned long expected_word = (unsigned int)word_int;
    if (!check_int_as_word(expected_word, word_int))
        return 3;
#endif
    return 0;
}
"""

NODE_RUNNER = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const [modulePath, abi, linkMode] = process.argv.slice(2);
const wasmModule = await WebAssembly.compile(readFileSync(modulePath));
assert.deepEqual(
  WebAssembly.Module.imports(wasmModule).map(({module, name, kind}) => `${module}.${name}:${kind}`).sort(),
  ['env.memory:memory'],
  'the consumer should import only the supplied memory64 memory');
const memory = new WebAssembly.Memory({
  initial: 16n,
  maximum: 16n,
  address: 'i64',
});
const instance = await WebAssembly.instantiate(wasmModule, {env: {memory}});
assert.equal(typeof instance.exports.run, 'function');
const seed = Number(BigInt.asUintN(32, process.hrtime.bigint()));
assert.equal(instance.exports.run(seed), 0, `${abi} ${linkMode} varargs checks (seed ${seed})`);
console.log(`Node memory64: ${abi} ${linkMode} varargs checks passed (seed ${seed})`);
"""


def resolve(program, label):
    path = shutil.which(program)
    if path is None:
        raise SystemExit(f"error: {label} executable not found: {program}")
    return str(Path(path).resolve())


def run_stage(label, command, diagnostic=None):
    print(f"[wasm-linux64-varargs] {label}", flush=True)
    result = subprocess.run(command, capture_output=True, text=True)
    if diagnostic is None:
        if result.returncode:
            raise SystemExit(
                f"{label} failed with exit status {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.stderr.strip():
            print(result.stderr.strip())
        return

    if result.returncode == 0:
        raise SystemExit(f"{label} unexpectedly accepted the Linux64 ABI")
    if diagnostic not in result.stderr:
        raise SystemExit(
            f"{label} failed for an unexpected reason\n"
            f"expected diagnostic: {diagnostic}\nstderr:\n{result.stderr}"
        )
    print(f"rejected as expected: {diagnostic}")


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--clang", required=True, help="Clang C driver")
parser.add_argument("--ld", required=True, help="wasm-ld linker used by Clang")
parser.add_argument("--node", default="node", help="Node.js with memory64 support")
parser.add_argument("--target", default=TRIPLE, help="wasm target triple")
parser.add_argument(
    "--default-only",
    action="store_true",
    help="run only default ABI pipelines (useful with a non-Linux wasm64 target)",
)
args = parser.parse_args()

if args.target != TRIPLE and not args.default_only:
    parser.error("--target override is available only with --default-only")
if args.default_only and not args.target.startswith("wasm64-"):
    parser.error("--default-only requires a wasm64 target")

clang = resolve(args.clang, "Clang")
linker = resolve(args.ld, "wasm-ld")
node = resolve(args.node, "Node.js")

with tempfile.TemporaryDirectory(prefix="wasm-linux64-varargs-") as temporary:
    directory = Path(temporary)
    source = directory / "varargs.c"
    runner = directory / "run.mjs"
    source.write_text(SOURCE)
    runner.write_text(NODE_RUNNER)

    if args.default_only:
        print("[wasm-linux64-varargs] skipping Linux64 flag acceptance checks")
    else:
        shared_source = directory / "shared.c"
        shared_source.write_text("int exported(void) { return 7; }\n")
        for shared_target, shared_abi in (
            ("wasm32-unknown-linux-musl", []),
            (TRIPLE, []),
            (TRIPLE, ["-mabi=linux64"]),
        ):
            tag = shared_target + ("-linux64" if shared_abi else "-default")
            shared_module = directory / f"{tag}-shared.wasm"
            run_stage(
                f"link {tag} shared object through the Linux driver",
                [
                    clang,
                    f"--target={shared_target}",
                    *shared_abi,
                    f"--ld-path={linker}",
                    "-nostdlib",
                    "-fPIC",
                    "-shared",
                    "-Wl,--no-entry,--export=exported",
                    str(shared_source),
                    "-o",
                    str(shared_module),
                ],
            )
            run_stage(
                f"validate {tag} shared object in Node",
                [
                    node,
                    "-e",
                    "WebAssembly.compile(require('node:fs').readFileSync(process.argv[1]))"
                    ".catch(error => { console.error(error); process.exitCode = 1; });",
                    str(shared_module),
                ],
            )
        for rejected_target in (
            "wasm32-unknown-linux-musl",
            "wasm64-unknown-unknown",
        ):
            run_stage(
                f"reject -mabi=linux64 for {rejected_target}",
                [
                    clang,
                    f"--target={rejected_target}",
                    "-mabi=linux64",
                    "-fsyntax-only",
                    str(source),
                ],
                "unknown target ABI 'linux64'",
            )

    abi_modes = (False,) if args.default_only else (False, True)
    for linux64 in abi_modes:
        abi = "linux64" if linux64 else "default"
        for lto in (False, True):
            link_mode = "-flto" if lto else "non-LTO"
            mode_tag = "lto" if lto else "ordinary"
            tag = f"{abi}-{mode_tag}"
            obj = directory / f"{tag}.o"
            module = directory / f"{tag}.wasm"
            abi_flags = ["-mabi=linux64"] if linux64 else []
            lto_flags = ["-flto"] if lto else []
            definitions = ["-DTEST_LINUX64=1"] if linux64 else []
            common = [
                clang,
                f"--target={args.target}",
                *abi_flags,
                *lto_flags,
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-ffreestanding",
                "-fno-builtin",
                "-nostdlib",
            ]
            run_stage(
                f"compile {abi} {link_mode} consumer",
                [*common, *definitions, "-c", str(source), "-o", str(obj)],
            )
            run_stage(
                f"link {abi} {link_mode} consumer with wasm-ld",
                [
                    clang,
                    f"--target={args.target}",
                    *abi_flags,
                    *lto_flags,
                    f"--ld-path={linker}",
                    "-Wno-unused-command-line-argument",
                    "-nostdlib",
                    "-Wl,--no-entry",
                    "-Wl,--import-memory",
                    "-Wl,--initial-memory=1048576",
                    "-Wl,--max-memory=1048576",
                    "-Wl,--export=run",
                    str(obj),
                    "-o",
                    str(module),
                ],
            )
            run_stage(
                f"run {abi} {link_mode} consumer in Node memory64",
                [node, str(runner), str(module), abi, link_mode],
            )

if args.default_only:
    print("[wasm-linux64-varargs] selected default ABI driver, linker, and memory64 checks passed")
else:
    print("[wasm-linux64-varargs] all driver, linker, and memory64 checks passed")
