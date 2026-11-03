#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real Wasm LSM records and production section collector; not kernel boot."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINUX = Path(os.environ.get("WASM_LSM_SOURCE_ROOT", ROOT / "sources/linux"))
rule_path = LINUX / "scripts/Makefile.vmlinux_o"
rule = (
    rule_path.read_text()
    if rule_path.exists()
    else subprocess.check_output(
        ["git", "-C", str(LINUX), "show", "HEAD:scripts/Makefile.vmlinux_o"], text=True
    )
)
assert "--no-gc-sections" in rule, "the primitive must match the real kernel link rule"
hooks = (LINUX / "include/linux/lsm_hooks.h").read_text()
structure = hooks.split("struct lsm_info {", 1)[1].split("\n};", 1)[0]
order = hooks.split("enum lsm_order {", 1)[1].split("\n};", 1)[0]
definitions = hooks.split("#define DEFINE_LSM(lsm)", 1)[1].split("/* DO NOT tamper", 1)[
    0
]
declarations = (
    (LINUX / "security/lsm_init.c")
    .read_text()
    .split("/* Pointers to LSM sections", 1)[1]
    .split("/* Number of", 1)[0]
)
declarations = declarations.split("*/", 1)[1]
sections = (LINUX / "arch/wasm/kernel/sections.c").read_text()
assert 'SECTION(".lsm_info.init", __start_lsm_info, _, __end_lsm_info);' in sections
assert 'SECTION(".early_lsm_info.init", __start_early_lsm_info, _,' in sections
source = (
    r"""
#define CONFIG_WASM 1
#define __used __attribute__((used))
#define __section(name) __attribute__((section(name)))
#define __aligned(size) __attribute__((aligned(size)))
struct lsm_id; struct lsm_blob_sizes;
"""
    + "enum lsm_order {"
    + order
    + "\n};\nstruct lsm_info {"
    + structure
    + "\n};\n"
)
source += "#define DEFINE_LSM(lsm)" + definitions + declarations
source += r"""
struct lsm_info *__start_lsm_info,*__end_lsm_info;
struct lsm_info *__start_early_lsm_info,*__end_early_lsm_info;
static int first(void) { return 2; }
static int second(void) { return 3; }
static int early(void) { return 5; }
DEFINE_LSM(first) = { .flags=11, .init=first };
DEFINE_LSM(second) = { .flags=13, .init=second };
#if WITH_EARLY
DEFINE_EARLY_LSM(early) = { .flags=17, .init=early };
#endif
static int unused_record __used __section(".not_lsm.init") = 99;
__attribute__((export_name("set_ranges")))
void set_ranges(unsigned long a,unsigned long b,unsigned long c,unsigned long d) {
 __start_lsm_info=(void*)a;__end_lsm_info=(void*)(a+b);
 __start_early_lsm_info=(void*)c;__end_early_lsm_info=(void*)(c+d);
}
__attribute__((export_name("record_size")))
unsigned long record_size(void) { return sizeof(struct lsm_info); }
__attribute__((export_name("check")))
int check(int with_early) {
 int ordinary=0,initial=0,sum=0;struct lsm_info *item;
 for(item=__start_lsm_info;item<__end_lsm_info;item++) {
  ordinary++;sum+=item->flags+item->init();
 }
 for(item=__start_early_lsm_info;item<__end_early_lsm_info;item++) {
  initial++;sum+=item->flags+item->init();
 }
 return ordinary==2&&initial==with_early&&sum==(with_early?51:29);
}
"""
runner = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const [file,metadata,bits,early]=process.argv.slice(2);
const wide=bits==='64',word=n=>wide?BigInt(n):Number(n);
const sections=JSON.parse(readFileSync(metadata,'utf8'));
assert.deepEqual(Object.keys(sections).sort(),Number(early)?['.early_lsm_info.init','.lsm_info.init']:['.lsm_info.init']);
const memory=new WebAssembly.Memory({initial:word(4),maximum:word(16),shared:true,address:wide?'i64':'i32'});
const {instance}=await WebAssembly.instantiate(readFileSync(file),{env:{memory}});
instance.exports.__wasm_call_ctors();
const ordinary=sections['.lsm_info.init'],initial=sections['.early_lsm_info.init']??[0,0];
assert.equal(BigInt(ordinary[1]),2n*BigInt(instance.exports.record_size()));
if(Number(early))assert.equal(BigInt(initial[1]),BigInt(instance.exports.record_size()));
instance.exports.set_ranges(...[...ordinary,...initial].map(word));
assert.equal(instance.exports.check(Number(early)),1,'retained ordinary/early LSM entries and function pointers execute');
instance.exports.set_ranges(word(0),word(0),...initial.map(word));
assert.equal(instance.exports.check(Number(early)),0,'empty dummy bounds cannot fake LSM initialization');
"""

with tempfile.TemporaryDirectory(prefix="linux-wasm-lsm-sections-") as tmp:
    path = Path(tmp)
    (path / "records.c").write_text(source)
    (path / "check.mjs").write_text(runner)
    for compiler in os.environ.get("WASM_LSM_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            for early in (0, 1):
                binary, wat, metadata = (
                    path / name
                    for name in ("records.wasm", "records.wat", "sections.json")
                )
                subprocess.run(
                    [
                        compiler,
                        f"--target=wasm{bits}",
                        "-O2",
                        "-nostdlib",
                        "-ffreestanding",
                        f"-DWITH_EARLY={early}",
                        "-matomics",
                        "-mbulk-memory",
                        "-Wl,--no-entry",
                        "-Wl,--import-memory",
                        "-Wl,--shared-memory",
                        "-Wl,--max-memory=1048576",
                        "-Wl,--no-merge-data-segments",
                        "-Wl,--no-gc-sections",
                        "-Wl,--export=__wasm_call_ctors",
                        str(path / "records.c"),
                        "-o",
                        str(binary),
                    ],
                    check=True,
                )
                subprocess.run(
                    [
                        os.environ.get("WASM2WAT", "wasm2wat"),
                        "--enable-all",
                        str(binary),
                        "-o",
                        str(wat),
                    ],
                    check=True,
                )
                with wat.open("rb") as input_file:
                    data = subprocess.check_output(
                        ["perl", str(LINUX / "arch/wasm/scripts/sections.pl")],
                        stdin=input_file,
                    )
                if not json.loads(data):
                    detail = "\n".join(
                        line
                        for line in wat.read_text().splitlines()
                        if any(
                            token in line
                            for token in (
                                "lsm",
                                "memory.init",
                                "init_memory",
                                "data.drop",
                            )
                        )
                    )
                    raise RuntimeError(
                        "LSM records missing from collected sections:\n" + detail
                    )
                metadata.write_bytes(data)
                subprocess.run(
                    [
                        "node",
                        str(path / "check.mjs"),
                        str(binary),
                        str(metadata),
                        str(bits),
                        str(early),
                    ],
                    check=True,
                )
            print(
                f"{compiler} wasm{bits}: actual LSM struct/macros, retained tables, early-empty case and production section collector pass; not Linux boot acceptance"
            )
