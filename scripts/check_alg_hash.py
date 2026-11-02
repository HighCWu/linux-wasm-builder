#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the exact AF_ALG hash SG adapter without host sockets or crypto."""

import os
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
source = Path(
    os.environ.get("WASM_ALG_HASH_SOURCE", ROOT / "sources/linux/crypto/algif_hash.c")
).read_text()
adapter = source.split("static ssize_t hash_get_sg(", 1)[1].split(
    "static int hash_sendmsg(", 1
)[0]
adapter = "static ssize_t hash_get_sg(" + adapter
send = source.split("static int hash_sendmsg(", 1)[1].split(
    "static int hash_recvmsg(", 1
)[0]
assert send.count("hash_put_sg(&ctx->sgl, copied_page);") == 2
assert send.index("crypto_wait_req(err, &ctx->wait)") < send.index("hash_put_sg(")
assert "copied_page = NULL;" in send

model = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <errno.h>
#include <sys/types.h>
#define CONFIG_WASM 1
#define IS_ENABLED(x) (x)
#define PAGE_SIZE 65536UL
#define GFP_KERNEL 1
#define __GFP_ACCOUNT 2
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
struct page {unsigned char bytes[PAGE_SIZE];};
static int live, fail_alloc, extracts, unpins;
static struct page *alloc_page(int flags) {
 assert(flags==(GFP_KERNEL|__GFP_ACCOUNT));
 if(fail_alloc)return NULL;
 struct page *p=malloc(sizeof(*p));assert(p);live++;return p;
}
static void put_page(struct page *p){assert(p&&live>0);live--;free(p);}
struct iov_iter {unsigned char *bytes;size_t count,valid,at;bool user;};
struct msghdr {struct iov_iter msg_iter;};
struct scatterlist {struct page *page;size_t len,offset;};
struct sg_table {struct scatterlist *sgl;unsigned nents,orig_nents;};
struct af_alg_sgl {struct sg_table sgt;struct scatterlist sgl[16];bool need_unpin;};
static size_t iov_iter_npages(struct iov_iter *i,size_t max) {
 return min_t(size_t,(i->count+PAGE_SIZE-1)/PAGE_SIZE,max);
}
static bool user_backed_iter(struct iov_iter *i){return i->user;}
static size_t iov_iter_count(struct iov_iter *i){return i->count;}
static void sg_init_table(struct scatterlist *sg,size_t n){memset(sg,0,n*sizeof(*sg));}
static size_t copy_page_from_iter(struct page *p,size_t off,size_t n,struct iov_iter *i){
 size_t k=min_t(size_t,n,i->valid-i->at);
 assert(off+k<=PAGE_SIZE&&k<=i->count);
 memcpy(p->bytes+off,i->bytes+i->at,k);i->at+=k;i->count-=k;return k;
}
static void sg_set_page(struct scatterlist *sg,struct page *p,size_t n,size_t off){
 *sg=(struct scatterlist){.page=p,.len=n,.offset=off};
}
static bool iov_iter_extract_will_pin(struct iov_iter *i){return i->user;}
static ssize_t extract_iter_to_sg(struct iov_iter *i,long len,struct sg_table *sg,
                                size_t n,int flags){
 (void)len;(void)sg;(void)n;(void)flags;extracts++;
 return i->user?-EFAULT:-EIO; /* No kernel VMA for Wasm user memory. */
}
static void af_alg_free_sg(struct af_alg_sgl *sg){
 if(sg->sgt.sgl&&sg->need_unpin)unpins+=sg->sgt.nents;
 sg->sgt.sgl=NULL;
}
"""

tests = r"""
int main(void){
 unsigned char *b=malloc(3*PAGE_SIZE+17);assert(b);
 for(size_t k=0;k<3*PAGE_SIZE+17;k++)b[k]=(unsigned char)(k*37+11);
 struct af_alg_sgl sg={0};struct page *page=NULL;
 struct msghdr msg={.msg_iter={.bytes=b,.count=3*PAGE_SIZE+17,
 .valid=3*PAGE_SIZE+17,.user=true}};
 size_t total=0;int calls=0;
 while(msg.msg_iter.count){
  ssize_t n=hash_get_sg(&msg,&sg,16,&page);
  assert(n>0&&(size_t)n<=PAGE_SIZE&&live==1&&page);
  assert(!sg.need_unpin&&sg.sgt.nents==1&&sg.sgt.orig_nents==1);
  assert(sg.sgl[0].page==page&&sg.sgl[0].len==(size_t)n);
  assert(!memcmp(page->bytes,b+total,n));
  /* A delayed hash implementation may retain this SG until completion. */
  unsigned char first=page->bytes[0];b[total]^=255;
  assert(page->bytes[0]==first);b[total]^=255;
  total+=n;calls++;
  hash_put_sg(&sg,page);page=NULL;
  assert(!live&&!sg.sgt.sgl&&!unpins);
 }
 assert(total==3*PAGE_SIZE+17&&calls==4&&!extracts);
 msg.msg_iter=(struct iov_iter){.bytes=b,.count=PAGE_SIZE,.valid=17,.user=true};
 assert(hash_get_sg(&msg,&sg,16,&page)==17&&msg.msg_iter.at==17);
 assert(!memcmp(page->bytes,b,17));hash_put_sg(&sg,page);page=NULL;
 assert(hash_get_sg(&msg,&sg,16,&page)==-EFAULT&&!page&&!live);
 hash_put_sg(&sg,page);assert(!unpins);
 msg.msg_iter=(struct iov_iter){.bytes=b,.count=PAGE_SIZE,.valid=PAGE_SIZE,.user=true};
 fail_alloc=1;
 assert(hash_get_sg(&msg,&sg,16,&page)==-ENOMEM&&!page&&!msg.msg_iter.at);
 hash_put_sg(&sg,page);fail_alloc=0;assert(!live&&!unpins);
 assert(hash_get_sg(&msg,&sg,0,&page)==-EIO&&!page&&!msg.msg_iter.at);
 hash_put_sg(&sg,page);
 msg.msg_iter.user=false;
 assert(hash_get_sg(&msg,&sg,16,&page)==-EIO&&!page&&extracts==1);
 hash_put_sg(&sg,page);assert(!live&&!unpins);
 free(b);return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="alg-hash-model-") as tmp:
    path = Path(tmp) / "model.c"
    path.write_text(model + adapter + tests)
    for cc in ("gcc", "clang"):
        binary = Path(tmp) / cc
        command = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(path)]
        subprocess.run([*command, "-O2", "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
        if cc == "clang":
            subprocess.run(
                [
                    *command,
                    "--analyze",
                    "-Xanalyzer",
                    "-analyzer-werror",
                    "-o",
                    "/dev/null",
                ],
                check=True,
            )
    path.write_text(
        model.replace("#define CONFIG_WASM 1", "#define CONFIG_WASM 0")
        + adapter
        + tests
    )
    binary = Path(tmp) / "missing-usercopy"
    subprocess.run(["cc", "-std=c11", "-O2", str(path), "-o", str(binary)], check=True)
    negative = subprocess.run(
        [str(binary)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert negative.returncode != 0, "disabled usercopy must fail the same workload"

programs = [
    ROOT / f"sources/distro/distro/{name}/runtime.c"
    for name in ("alg-hash", "alg-skcipher", "alg-aead")
]
for program in programs:
    for cc in ("gcc", "clang"):
        subprocess.run(
            [
                cc,
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-fsyntax-only",
                str(program),
            ],
            check=True,
        )
header_path = os.environ.get("WASM_ALG_HASH_UAPI")
header = (
    Path(header_path).read_text()
    if header_path
    else subprocess.check_output(
        [
            "git",
            "-C",
            str(ROOT / "sources/linux"),
            "show",
            "HEAD:include/uapi/linux/if_alg.h",
        ],
        text=True,
    )
)
with tempfile.TemporaryDirectory(prefix="alg-hash-frontends-") as tmp:
    includes = Path(tmp)
    (includes / "linux").mkdir()
    (includes / "linux/if_alg.h").write_text(header)
    # Fixed-width UAPI type shim only; no host ABI typedefs or altered algorithm declarations.
    (includes / "linux/types.h").write_text(
        "typedef unsigned char __u8; typedef unsigned short __u16; typedef unsigned int __u32;\n#define __counted_by(x)\n"
    )
    (includes / "bits").mkdir()
    musl = ROOT / "sources/musl"
    templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        musl / "include/alltypes.h.in"
    ).read_text()
    (includes / "bits/alltypes.h").write_text(
        subprocess.check_output(
            ["sed", "-f", str(musl / "tools/mkalltypes.sed")],
            input=templates,
            text=True,
        )
    )
    resource_dir = subprocess.check_output(
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
            resource_dir + "/include",
            "-Wall",
            "-Wextra",
            "-Werror",
        ]
        for program in programs:
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
    "AF_ALG hash: exact SG adapter, ownership, negative control and native/Wasm frontends passed; no host sockets or crypto"
)
