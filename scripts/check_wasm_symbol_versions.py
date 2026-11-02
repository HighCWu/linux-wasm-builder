#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the real candidate MC/writer/linker, not a mocked symbol resolver."""

import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--mc", required=True)
parser.add_argument("--ld", required=True)
parser.add_argument("--clang", default="clang")
parser.add_argument("--node", default="node")
args = parser.parse_args()

DEFINITIONS = r"""
__asm__(".symver impl_old, api@VER_1\n"
        ".symver impl_new, api@@VER_2\n"
        ".symver data_old, setting@VER_1\n"
        ".symver data_new, setting@@VER_2\n");
int impl_old(int x) { return x + 11; }
long impl_new(long x) { return x + 200; }
int data_old = 17;
int data_new = 23;
/* The C assembler name api deliberately refers to the old version here. */
extern int api(int);
__asm__(".symver api, api@VER_1");
int same_unit_old(void) { return api(2); }
extern int another_old(int), again_old(int), setting, old_data_again;
__asm__(".symver another_old, api@VER_1\n"
        ".symver again_old, api@VER_1\n"
        ".symver setting, setting@VER_1\n"
        ".symver old_data_again, setting@VER_1\n");
int (*volatile old_pointer)(int) = again_old;
int same_unit_shared(void) {
  return another_old(3) + again_old(3) + setting + old_data_again + old_pointer(4);
}
"""
REFERENCES = r"""
extern long api(long);
extern int old_api(int), old_again(int), setting, old_setting;
__asm__(".symver old_api, api@VER_1\n"
        ".symver old_again, api@VER_1\n"
        ".symver old_setting, setting@VER_1\n");
long run(long x) { return api(x) + old_api(7) + setting + old_setting; }
int old_only(void) { return old_api(7) + old_again(0); }
long default_only(long x) { return api(x); }
"""
POINTER_CONTROL = r"""
int next_value(int x) { return x + 1; }
int (*volatile callback)(int) = next_value;
int pointer_control(int x) { return callback(x); }
"""
RUNNER = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const [path,bits] = process.argv.slice(2);
const {instance}=await WebAssembly.instantiate(readFileSync(path),{});
const e=instance.exports;
const x=bits==='64'?(1n<<40n)+5n:5;
assert.equal(e.run(x),bits==='64'?x+258n:x+258);
assert.equal(e.default_only(x),bits==='64'?x+200n:x+200);
assert.equal(e.old_only(),29);
assert.equal(e.same_unit_old(),13);
assert.equal(e.same_unit_shared(),77);
console.log(`symver wasm${bits}: real old/default signatures, data versions and same-TU namespace separation pass`);
console.log(`symver wasm${bits}: repeated references share definitions, data and function-pointer relocations pass`);
"""


def invoke(command, success=True, error=None):
    result = subprocess.run(command, text=True, capture_output=True)
    if success and result.returncode:
        raise RuntimeError(result.stderr[-7000:])
    if not success:
        assert result.returncode, "expected rejection, not fallback to default"
        if error:
            assert error in result.stderr, result.stderr[-3000:]
    return result


with tempfile.TemporaryDirectory(prefix="wasm-symver-") as tmp:
    directory = Path(tmp)
    (directory / "definitions.c").write_text(DEFINITIONS)
    (directory / "references.c").write_text(REFERENCES)
    (directory / "pointer-control.c").write_text(POINTER_CONTROL)
    (directory / "run.mjs").write_text(RUNNER)
    for bits in (32, 64):

        def compile_source(name):
            asm = directory / f"{name}{bits}.s"
            obj = directory / f"{name}{bits}.o"
            invoke(
                [
                    args.clang,
                    f"--target=wasm{bits}",
                    "-mreference-types",
                    "-O0",
                    "-S",
                    "-nostdlib",
                    str(directory / f"{name}.c"),
                    "-o",
                    str(asm),
                ]
            )
            invoke(
                [
                    args.mc,
                    f"-triple=wasm{bits}",
                    "-mattr=+reference-types",
                    "-filetype=obj",
                    str(asm),
                    "-o",
                    str(obj),
                ]
            )
            return obj

        # Keep ordinary memory64/table64 indirect calls independent of symver.
        # Type checking must still reject the opposite-width table index.
        control = compile_source("pointer-control")
        control_module = directory / f"pointer-control{bits}.wasm"
        invoke(
            [args.ld, "--no-entry", "--export=pointer_control"]
            + (["-mwasm64"] if bits == 64 else [])
            + [str(control), "-o", str(control_module)]
        )
        invoke(
            [
                args.node,
                "--input-type=module",
                "-e",
                "import assert from 'node:assert/strict';"
                "import {readFileSync} from 'node:fs';"
                "const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[1]),{});"
                "assert.equal(instance.exports.pointer_control(41),42);",
                str(control_module),
            ]
        )
        wrong_bits = 64 if bits == 32 else 32
        wrong_index = directory / f"wrong-index{bits}.s"
        wrong_index.write_text(
            ".tabletype __indirect_function_table, funcref\n.text\nwrong:\n"
            f".functype wrong (i{wrong_bits}) -> (i32)\nlocal.get 0\n"
            "call_indirect __indirect_function_table, () -> (i32)\nend_function\n"
        )
        invoke(
            [
                args.mc,
                f"-triple=wasm{bits}",
                "-mattr=+reference-types",
                "-filetype=obj",
                str(wrong_index),
                "-o",
                str(directory / "wrong.o"),
            ],
            success=False,
            error=f"type mismatch, expected [i{bits}] but got [i{wrong_bits}]",
        )
        print(
            f"symver wasm{bits}: ordinary function-pointer control and wrong-width index rejection pass"
        )
        definitions = compile_source("definitions")
        references = compile_source("references")
        module = directory / f"linked{bits}.wasm"
        link = [
            args.ld,
            "--no-entry",
            "--export=run",
            "--export=old_only",
            "--export=default_only",
            "--export=same_unit_old",
            "--export=same_unit_shared",
        ]
        if bits == 64:
            link += ["-mwasm64"]
        invoke([*link, str(definitions), str(references), "-o", str(module)])
        result = invoke([args.node, str(directory / "run.mjs"), str(module), str(bits)])
        print(result.stdout.strip())
        direct = []
        for name in ("definitions", "references"):
            obj = directory / f"{name}-direct{bits}.o"
            invoke(
                [
                    args.clang,
                    f"--target=wasm{bits}",
                    "-mreference-types",
                    "-O0",
                    "-nostdlib",
                    "-c",
                    str(directory / f"{name}.c"),
                    "-o",
                    str(obj),
                ]
            )
            direct.append(str(obj))
        invoke([*link, *direct, "-o", str(module)])
        invoke([args.node, str(directory / "run.mjs"), str(module), str(bits)])
        print(
            f"symver wasm{bits}: unchanged C source also passes the integrated Clang object path"
        )
        (directory / "missing.c").write_text(
            REFERENCES.replace("api@VER_1", "api@ABSENT")
        )
        missing = compile_source("missing")
        invoke(
            [*link, str(definitions), str(missing), "-o", str(module)],
            success=False,
            error="api@ABSENT",
        )

        for name, content, message in (
            ("empty", ".symver x, api@\n", "expected symbol@version"),
            (
                "default-undefined",
                ".functype x () -> (i32)\n.symver x, api@@VER\n",
                "must be defined",
            ),
            (
                "multiple-references",
                ".functype x () -> (i32)\n.symver x, api@ONE\n.symver x, api@TWO\n",
                "multiple versions",
            ),
            (
                "incompatible-references",
                ".functype x () -> (i32)\n.functype y () -> (i64)\n"
                ".symver x, api@ONE\n.symver y, api@ONE\n",
                "incompatible versioned symbol api@ONE",
            ),
        ):
            asm = directory / f"{name}.s"
            asm.write_text(content)
            invoke(
                [
                    args.mc,
                    f"-triple=wasm{bits}",
                    "-mattr=+reference-types",
                    "-filetype=obj",
                    str(asm),
                    "-o",
                    str(directory / "bad.o"),
                ],
                success=False,
                error=message,
            )
        print(
            f"symver wasm{bits}: missing versions and malformed/ambiguous bindings rejected"
        )

print(
    "Candidate MC/static-link checks passed; not an ELF loader, dynamic version-table or Linux SDK acceptance"
)
