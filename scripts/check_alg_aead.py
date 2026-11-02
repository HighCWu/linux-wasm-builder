#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Review and exercise the exact Wasm AEAD staging helper, without host sockets."""

import os
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
header = Path(
    os.environ.get(
        "WASM_AEAD_BUFFER_HEADER",
        ROOT / "sources/linux/include/crypto/wasm_aead_buffer.h",
    )
).read_text()
source = Path(
    os.environ.get("WASM_ALG_AEAD_SOURCE", ROOT / "sources/linux/crypto/algif_aead.c")
).read_text()
body = source.split("static int _aead_recvmsg(", 1)[1].split(
    "static int aead_recvmsg(", 1
)[0]
assert (
    body.index("aead_sufficient_data(")
    < body.index("af_alg_wasm_prepare_aead_rx(")
    < body.index("af_alg_get_rsgl(")
    < body.index("af_alg_pull_tsgl(")
)
assert (
    body.index("crypto_wait_req(")
    < body.index("af_alg_free_resources(")
    < body.index("af_alg_wasm_finish_aead_rx(")
)
assert "min_t(size_t, outlen, af_alg_rcvbuf(sk))" in body
assert body.index("!is_sync_kiocb(") < body.index("af_alg_alloc_areq(")

helpers = (
    "struct af_alg_wasm_aead_rx"
    + header.split("struct af_alg_wasm_aead_rx", 1)[1].rsplit("#endif", 1)[0]
)
model = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#define CONFIG_WASM 1
#define IS_ENABLED(x) (x)
#define GFP_KERNEL 1
#define __GFP_ACCOUNT 2
#define ITER_DEST 0
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define BUG_ON(x) assert(!(x))
struct iov_iter {unsigned char *bytes;size_t count,at,valid;bool user,data_source;};
struct msghdr {struct iov_iter msg_iter;};
struct kvec {void *iov_base;size_t iov_len;};
static int live,fail_alloc;static size_t capacity;
static void *kvmalloc(size_t n,int flags){
 assert(flags==(GFP_KERNEL|__GFP_ACCOUNT)&&!live&&n);
 if(fail_alloc)return NULL;
 void *p=malloc(n);assert(p);live++;capacity=n;return p;
}
static void kvfree_sensitive(void *p,size_t n){
 assert(p&&live==1&&n==capacity);memset(p,0,n);free(p);live--;
}
static bool user_backed_iter(struct iov_iter *i){return i->user;}
static size_t iov_iter_count(struct iov_iter *i){return i->count;}
static size_t copy_from_iter(void *p,size_t n,struct iov_iter *i){
 assert(i->data_source);size_t k=min_t(size_t,n,i->valid-i->at);
 memcpy(p,i->bytes+i->at,k);i->at+=k;i->count-=k;return k;
}
static size_t copy_to_iter(const void *p,size_t n,struct iov_iter *i){
 assert(!i->data_source);size_t k=min_t(size_t,n,i->valid-i->at);
 memcpy(i->bytes+i->at,p,k);i->at+=k;i->count-=k;return k;
}
static void iov_iter_kvec(struct iov_iter *i,int dir,struct kvec *v,int nr,size_t n){
 assert(dir==ITER_DEST&&nr==1&&v->iov_len==n);
 *i=(struct iov_iter){.bytes=v->iov_base,.count=n,.valid=n};
}
"""
tests = r"""
int main(void){
 enum {LENGTH=2*65536+37};unsigned char *b=malloc(LENGTH);assert(b);
 memset(b,0xa5,LENGTH);
 struct msghdr msg={.msg_iter={.bytes=b,.count=LENGTH,.valid=LENGTH,.user=true}};
 struct af_alg_wasm_aead_rx rx;
 assert(!af_alg_wasm_prepare_aead_rx(&msg,LENGTH,&rx));
 assert(live==1&&!msg.msg_iter.user&&msg.msg_iter.count==LENGTH&&rx.capacity==LENGTH);
 for(size_t j=0;j<LENGTH;j++)assert(b[j]==0xa5);
 memset(rx.buffer,0x73,LENGTH);msg.msg_iter.at=LENGTH;msg.msg_iter.count=0;
 assert(af_alg_wasm_finish_aead_rx(&msg,&rx,LENGTH)==LENGTH&&!live&&!rx.buffer);
 assert(msg.msg_iter.at==LENGTH&&!msg.msg_iter.count);
 for(size_t j=0;j<LENGTH;j++)assert(b[j]==0x73);
 /* An authentication failure cannot publish any staged plaintext. */
 memset(b,0xa5,LENGTH);msg.msg_iter=(struct iov_iter){.bytes=b,.count=LENGTH,.valid=LENGTH,.user=true};
 assert(!af_alg_wasm_prepare_aead_rx(&msg,LENGTH,&rx));
 memset(rx.buffer,0x19,LENGTH);msg.msg_iter.at=LENGTH;msg.msg_iter.count=0;
 assert(af_alg_wasm_finish_aead_rx(&msg,&rx,-EBADMSG)==-EBADMSG&&!live);
 assert(!msg.msg_iter.at&&msg.msg_iter.count==LENGTH);
 for(size_t j=0;j<LENGTH;j++)assert(b[j]==0xa5);
 /* The original available output/RX budget, rather than a page, bounds staging. */
 assert(!af_alg_wasm_prepare_aead_rx(&msg,65553,&rx)&&rx.capacity==65553);
 memset(rx.buffer,0x52,19);
 assert(af_alg_wasm_finish_aead_rx(&msg,&rx,19)==19&&msg.msg_iter.at==19&&!live);
 assert(b[18]==0x52&&b[19]==0xa5);
 msg.msg_iter=(struct iov_iter){.bytes=b,.count=64,.valid=0,.user=true};
 assert(af_alg_wasm_prepare_aead_rx(&msg,64,&rx)==-EFAULT&&live==1);
 assert(af_alg_wasm_finish_aead_rx(&msg,&rx,-EFAULT)==-EFAULT&&!live&&!msg.msg_iter.at);
 msg.msg_iter.valid=64;fail_alloc=1;
 assert(af_alg_wasm_prepare_aead_rx(&msg,64,&rx)==-ENOMEM&&!live);
 assert(af_alg_wasm_finish_aead_rx(&msg,&rx,-ENOMEM)==-ENOMEM&&!msg.msg_iter.at);
 fail_alloc=0;
 assert(!af_alg_wasm_prepare_aead_rx(&msg,64,&rx));rx.original.valid=7;
 memset(rx.buffer,0x11,64);
 assert(af_alg_wasm_finish_aead_rx(&msg,&rx,64)==7&&!live&&msg.msg_iter.at==7);
 msg.msg_iter=(struct iov_iter){.bytes=b,.count=64,.valid=0,.user=true};
 assert(!af_alg_wasm_prepare_aead_rx(&msg,0,&rx)&&!live);
 assert(af_alg_wasm_finish_aead_rx(&msg,&rx,0)==0&&!msg.msg_iter.at);
 msg.msg_iter.user=false;
 assert(!af_alg_wasm_prepare_aead_rx(&msg,64,&rx)&&!live&&msg.msg_iter.bytes==b);
 assert(af_alg_wasm_finish_aead_rx(&msg,&rx,-EIO)==-EIO&&!live);
 free(b);return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="wasm-aead-staging-") as tmp:
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
            "bypass-staging",
            helpers.replace("!IS_ENABLED(CONFIG_WASM)", "IS_ENABLED(CONFIG_WASM)"),
        ),
        (
            "publish-on-auth-failure",
            helpers.replace(
                "if (result > 0) {",
                "if (result == -EBADMSG) result = rx->vector.iov_len;\n\tif (result > 0) {",
            ),
        ),
    ):
        path.write_text(model + broken + tests)
        binary = Path(tmp) / name
        subprocess.run(
            ["cc", "-std=c11", "-O2", str(path), "-o", str(binary)], check=True
        )
        result = subprocess.run([str(binary)], capture_output=True)
        assert result.returncode != 0, name + " must fail the same workload"
print(
    "AEAD exact staging: multi-page record, no unauthenticated delivery, errors and lifetimes pass; no host crypto/socket execution"
)
