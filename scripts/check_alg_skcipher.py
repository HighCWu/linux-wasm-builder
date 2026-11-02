#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise exact skcipher RX staging functions, without sockets or cryptography."""

import os
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
source = Path(
    os.environ.get(
        "WASM_ALG_SKCIPHER_SOURCE", ROOT / "sources/linux/crypto/algif_skcipher.c"
    )
).read_text()
helpers = (
    "static int skcipher_prepare_rx("
    + source.split("static int skcipher_prepare_rx(", 1)[1].split(
        "static int _skcipher_recvmsg(", 1
    )[0]
)
body = source.split("static int _skcipher_recvmsg(", 1)[1].split(
    "static int skcipher_recvmsg(", 1
)[0]
assert (
    body.index("af_alg_wait_for_data(")
    < body.index("skcipher_prepare_rx(")
    < body.index("af_alg_get_rsgl(")
)

closure = (
    (ROOT / "sources/distro/distro/default.nix")
    .read_text()
    .split("alg-skcipher-wasm64 =", 1)[1]
    .split("};", 1)[0]
)
for dependency in (
    "stdenv",
    "platform",
    "musl",
    "llvm-runtimes",
    "busybox",
    "alg-hash",
):
    assert f"{dependency} = self.{dependency}-wasm64;" in closure
assert "vm-test = vmTestWasm64;" in closure
init = (ROOT / "sources/distro/distro/alg-skcipher/runtime-test.sh").read_text()
assert (
    init.index("alg-hash || exit 1")
    < init.index("alg-skcipher || exit 1")
    < init.index("::vm-test::pass")
)
assert init.count("::vm-test::pass") == 1
assert (
    body.index("crypto_wait_req(")
    < body.index("af_alg_free_resources(")
    < body.index("skcipher_finish_rx(")
)

model = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#define PAGE_SIZE 65536UL
#define CONFIG_WASM 1
#define IS_ENABLED(x) (x)
#define GFP_KERNEL 1
#define __GFP_ACCOUNT 2
#define ITER_DEST 0
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define BUG_ON(x) assert(!(x))
struct page {unsigned char bytes[PAGE_SIZE];};
static int live, fail_alloc;
static struct page *alloc_page(int flags){
 assert(flags==(GFP_KERNEL|__GFP_ACCOUNT));if(fail_alloc)return NULL;
 struct page *p=malloc(sizeof(*p));assert(p);live++;return p;
}
static void put_page(struct page *p){assert(p&&live>0);live--;free(p);}
static void *page_address(struct page *p){return p->bytes;}
struct iov_iter {unsigned char *bytes;size_t count,at,valid;bool user,data_source;};
struct msghdr {struct iov_iter msg_iter;};
struct kvec {void *iov_base;size_t iov_len;};
static bool user_backed_iter(struct iov_iter *i){return i->user;}
static size_t iov_iter_count(struct iov_iter *i){return i->count;}
static size_t copy_page_from_iter(struct page *p,size_t off,size_t n,struct iov_iter *i){
 assert(i->data_source&&off+n<=PAGE_SIZE);
 size_t k=min_t(size_t,n,i->valid-i->at);
 memcpy(p->bytes+off,i->bytes+i->at,k);i->at+=k;i->count-=k;return k;
}
static size_t copy_page_to_iter(struct page *p,size_t off,size_t n,struct iov_iter *i){
 assert(!i->data_source&&off+n<=PAGE_SIZE);
 size_t k=min_t(size_t,n,i->valid-i->at);
 memcpy(i->bytes+i->at,p->bytes+off,k);i->at+=k;i->count-=k;return k;
}
static void iov_iter_kvec(struct iov_iter *i,int dir,struct kvec *v,int nr,size_t n){
 assert(dir==ITER_DEST&&nr==1&&v->iov_len==n);
 *i=(struct iov_iter){.bytes=v->iov_base,.count=n,.valid=n};
}
"""
tests = r"""
int main(void){
 unsigned char *b=malloc(3*PAGE_SIZE+32);assert(b);memset(b,0xa5,3*PAGE_SIZE+32);
 struct msghdr msg={.msg_iter={.bytes=b,.count=3*PAGE_SIZE+32,.valid=3*PAGE_SIZE+32,.user=true}};
 struct iov_iter original;struct kvec vec;struct page *page=NULL;
 size_t processed=0;int rounds=0;
 while(msg.msg_iter.count){
  assert(!skcipher_prepare_rx(&msg,msg.msg_iter.count,&original,&vec,&page));
  assert(page&&live==1&&!msg.msg_iter.user&&msg.msg_iter.count<=PAGE_SIZE);
  assert(!original.at||original.at==processed);
  size_t n=msg.msg_iter.count;
  for(size_t j=0;j<n;j++)assert(b[processed+j]==0xa5); /* Probe does not write output. */
  memset(msg.msg_iter.bytes,0x37,n);msg.msg_iter.at+=n;msg.msg_iter.count-=n;
  assert(skcipher_finish_rx(&msg,&original,page,(int)n)==(int)n);
  processed+=n;rounds++;assert(msg.msg_iter.at==processed&&!live);
 }
 assert(rounds==4&&processed==3*PAGE_SIZE+32);
 for(size_t j=0;j<processed;j++)assert(b[j]==0x37);
 /* Queued input, not the requested output tail, bounds the probe. */
 msg.msg_iter=(struct iov_iter){.bytes=b,.count=64,.valid=64,.user=true};
 assert(!skcipher_prepare_rx(&msg,16,&original,&vec,&page)&&vec.iov_len==16);
 memset(page->bytes,0x52,16);
 assert(skcipher_finish_rx(&msg,&original,page,16)==16&&msg.msg_iter.at==16);
 /* Do not consume rounded-away output bytes from an unaligned request. */
 msg.msg_iter=(struct iov_iter){.bytes=b,.count=17,.valid=17,.user=true};
 assert(!skcipher_prepare_rx(&msg,17,&original,&vec,&page));
 assert(skcipher_finish_rx(&msg,&original,page,16)==16&&msg.msg_iter.count==1);
 msg.msg_iter=(struct iov_iter){.bytes=b,.count=64,.valid=0,.user=true};
 assert(skcipher_prepare_rx(&msg,64,&original,&vec,&page)==-EFAULT&&page&&live==1);
 assert(skcipher_finish_rx(&msg,&original,page,-EFAULT)==-EFAULT&&!msg.msg_iter.at&&!live);
 msg.msg_iter.valid=64;fail_alloc=1;
 assert(skcipher_prepare_rx(&msg,64,&original,&vec,&page)==-ENOMEM&&!page&&!live);
 assert(skcipher_finish_rx(&msg,&original,page,-ENOMEM)==-ENOMEM&&!msg.msg_iter.at);
 fail_alloc=0;memset(b,0xa5,64);
 assert(!skcipher_prepare_rx(&msg,64,&original,&vec,&page));
 memset(page->bytes,0x99,64);
 assert(skcipher_finish_rx(&msg,&original,page,-EIO)==-EIO&&!msg.msg_iter.at&&!live);
 for(size_t j=0;j<64;j++)assert(b[j]==0xa5);
 assert(!skcipher_prepare_rx(&msg,64,&original,&vec,&page));original.valid=7;
 assert(skcipher_finish_rx(&msg,&original,page,64)==7&&msg.msg_iter.at==7&&!live);
 msg.msg_iter=(struct iov_iter){.bytes=b,.count=64,.valid=64,.user=true};
 assert(!skcipher_prepare_rx(&msg,64,&original,&vec,&page));original.valid=0;
 assert(skcipher_finish_rx(&msg,&original,page,64)==-EFAULT&&!msg.msg_iter.at&&!live);
 msg.msg_iter=(struct iov_iter){.bytes=b,.count=64,.valid=64,.user=true};
 assert(!skcipher_prepare_rx(&msg,0,&original,&vec,&page)&&!page&&!msg.msg_iter.at);
 assert(skcipher_finish_rx(&msg,&original,page,0)==0);
 msg.msg_iter.user=false;
 assert(!skcipher_prepare_rx(&msg,64,&original,&vec,&page)&&!page&&msg.msg_iter.bytes==b);
 assert(skcipher_finish_rx(&msg,&original,page,-EIO)==-EIO&&!live);
 free(b);return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="skcipher-rx-model-") as tmp:
    path = Path(tmp) / "model.c"
    path.write_text(model + helpers + tests)
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
    for name, broken in (
        (
            "missing-bounce",
            model.replace("#define CONFIG_WASM 1", "#define CONFIG_WASM 0") + helpers,
        ),
        (
            "wrong-direction",
            model
            + helpers.replace(
                "probe.data_source = true;", "probe.data_source = false;"
            ),
        ),
        (
            "lost-input-bound",
            model
            + helpers.replace(
                "min_t(size_t, maxsize, iov_iter_count(&msg->msg_iter))",
                "iov_iter_count(&msg->msg_iter) + 0 * maxsize",
            ),
        ),
    ):
        path.write_text(broken + tests)
        binary = Path(tmp) / name
        subprocess.run(
            ["cc", "-std=c11", "-O2", str(path), "-o", str(binary)], check=True
        )
        negative = subprocess.run(
            [str(binary)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        assert negative.returncode != 0, name + " must fail the same workload"
print(
    "SKCIPHER RX: exact staging, prefix/error preservation, page ownership and three negative controls passed; no sockets or crypto"
)
