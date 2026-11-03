#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real FDT allocation body with modeled memblock/libfdt, not Linux boot proof."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(
    os.environ.get(
        "WASM_BOOT_SETUP_SOURCE", ROOT / "sources/linux/arch/wasm/kernel/setup.c"
    )
)
text = SOURCE.read_text()
body = text[text.index("static void *__init load_devicetree(") :]
body = body[: body.index("\n}\n") + 3]
model = r"""
typedef unsigned long size_t;
typedef unsigned long phys_addr_t;
#define NULL ((void *)0)
#define __init
#define PAGE_SIZE 65536UL
#define PAGE_ALIGN(n) (((n)+PAGE_SIZE-1)&~(PAGE_SIZE-1))
#define PFN_PHYS(n) ((phys_addr_t)(n)*PAGE_SIZE)
#define PHYS_ADDR_MAX (~0UL)
#define INT_MAX 2147483647
#define FDT_V17_SIZE 40
#define roundup_pow_of_two(n) 64UL
#define BUG_ON(n) do { if(n) __builtin_trap(); } while(0)
static phys_addr_t area_start,area_size,reserved;
static int added,removed;
static int memblock_add(phys_addr_t base,phys_addr_t size) {
 BUG_ON(added);area_start=base;area_size=size;added=1;return 0;
}
static int memblock_remove(phys_addr_t base,phys_addr_t size) {
 BUG_ON(!added||base!=area_start||size!=area_size);removed=1;return 0;
}
static void *memblock_alloc_or_panic(size_t size,size_t align) {
 phys_addr_t address=area_start>reserved?area_start:reserved;
 address=(address+align-1)&~(align-1);
 BUG_ON(address<area_start||size>area_start+area_size-address);
 unsigned long pages=PAGE_ALIGN(address+size)/PAGE_SIZE;
 unsigned long current=__builtin_wasm_memory_size(0);
 if(pages>current)BUG_ON(__builtin_wasm_memory_grow(0,pages-current)==(size_t)-1);
 unsigned char *out=(void*)address;
 for(size_t i=0;i<size;i++)out[i]=0;
 return out;
}
static size_t wasm_boot_get_devicetree(void *to,size_t size) {
 if(!to)return 4096;
 BUG_ON(size<4096);unsigned char *out=to;
 for(size_t i=0;i<4096;i++)out[i]=(i%251)+1;
 return 4096;
}
static int fdt_check_header(void *blob) {return *(unsigned char*)blob!=1;}
static size_t fdt_totalsize(void *blob) {(void)blob;return 4096;}
"""
checks = r"""
__attribute__((export_name("check"))) int run(unsigned long gap,unsigned long start) {
 if(start<2*PAGE_SIZE||start>6*PAGE_SIZE||gap>65535)return 5;
 const size_t end=start+2*PAGE_SIZE;
 unsigned char *initrd=(void*)start;
 reserved=start-gap;added=removed=0;
 for(size_t i=0;i<end-start;i++)initrd[i]=0x79;
 size_t size=0;unsigned char *blob=load_devicetree(&size);
 if(!removed||size!=4096)return 1;
 for(size_t i=0;i<end-start;i++)if(initrd[i]!=0x79)return 2;
 /* Initrd pages can later be freed without invalidating the FDT. */
 for(size_t i=0;i<end-start;i++)initrd[i]=0;
 for(size_t i=0;i<size;i++)if(blob[i]!=(i%251)+1)return 3;
 return 0;
}
"""
runner = r"""
import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
const [file,bits]=process.argv.slice(2),wide=bits==='64';
const results=[];
for(const gap of [0,1296,65535]){
 const {instance}=await WebAssembly.instantiate(readFileSync(file));
 results.push(instance.exports.check(wide?BigInt(gap):gap,wide?393216n:393216));
}
console.log(JSON.stringify(results));
assert.deepEqual(results,[0,0,0],'preloaded initrd and FDT survive each gap');
"""
old = body.replace(
    "memblock_add(bootstrap_start, bootstrap_size)",
    "memblock_add(0, bootstrap_start + bootstrap_size)",
).replace(
    "memblock_remove(bootstrap_start, bootstrap_size)",
    "memblock_remove(0, bootstrap_start + bootstrap_size)",
)
if old == body:
    raise SystemExit("the overlap control must change actual allocation placement")
with tempfile.TemporaryDirectory(prefix="boot-fdt-placement-") as tmp:
    path = Path(tmp)
    (path / "run.mjs").write_text(runner)
    for cc in os.environ.get("WASM_BOOT_COMPILERS", "clang clang-22").split():
        for bits in (32, 64):
            for mode, function in (("normal", body), ("old-prefix", old)):
                (path / "check.c").write_text(model + function + checks)
                binary = path / "check.wasm"
                subprocess.run(
                    [
                        cc,
                        f"--target=wasm{bits}",
                        "-O2",
                        "-nostdlib",
                        "-ffreestanding",
                        "-Wl,--no-entry",
                        "-Wl,--initial-memory=524288",
                        "-Wl,--max-memory=1048576",
                        str(path / "check.c"),
                        "-o",
                        str(binary),
                    ],
                    check=True,
                )
                if mode == "normal":
                    subprocess.run(
                        [
                            cc,
                            f"--target=wasm{bits}",
                            "--analyze",
                            "-ffreestanding",
                            "-Xanalyzer",
                            "-analyzer-werror",
                            str(path / "check.c"),
                            "-o",
                            str(path / "analysis.plist"),
                        ],
                        check=True,
                    )
                run = subprocess.run(
                    ["node", str(path / "run.mjs"), str(binary), str(bits)],
                    capture_output=True,
                    text=True,
                )
                if mode == "normal" and run.returncode:
                    raise RuntimeError(run.stderr)
                if mode == "old-prefix" and (
                    not run.returncode or run.stdout.strip() != "[2,2,0]"
                ):
                    raise RuntimeError(
                        "old placement must corrupt the two short gaps and preserve the large-gap control"
                    )
            print(
                f"{cc} wasm{bits}: actual FDT body preserves preloaded initrd and later FDT lifetime; old prefix placement fails; not Linux boot acceptance"
            )
