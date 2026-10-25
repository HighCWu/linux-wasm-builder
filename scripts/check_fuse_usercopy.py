#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual FUSE copy function bodies with iterator/page/lock substitutes, not a boot."""

import os
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(os.environ.get("WASM_FUSE_SOURCE_ROOT", ROOT / "sources/linux"))
source = (SOURCE_ROOT / "fs/fuse/dev.c").read_text()
assert "int usercopy_error;" in (SOURCE_ROOT / "fs/fuse/fuse_dev_i.h").read_text()


def body(name):
    start = source.index("static " + name)
    return source[start : source.index("\n}\n", start) + 3]


functions = "\n".join(
    body(name)
    for name in (
        "bool fuse_copy_user_iter(",
        "int fuse_copy_fill(",
        "int fuse_copy_do(",
        "int fuse_copy_one(",
    )
)
init_start = source.index("void fuse_copy_init(")
assert (
    "memset(cs, 0, sizeof(*cs));"
    in source[init_start : source.index("\n}\n", init_start)]
)
shim = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#define IS_ENABLED(option) (option)
#define PAGE_SIZE 65536U
#define GFP_HIGHUSER 0
#define BUG_ON(test) assert(!(test))
#define min(a,b) ((a)<(b)?(a):(b))
#define min_t(t,a,b) min((t)(a),(t)(b))
struct page { unsigned char bytes[PAGE_SIZE]; };
struct iov_iter { unsigned char *bytes; size_t size, pos, fault; bool user; };
struct pipe_buffer { struct page *page; unsigned offset, len; };
struct pipe_inode_info { unsigned max_usage; };
struct fuse_copy_state {
    void *req; struct iov_iter *iter;
    struct pipe_buffer *pipebufs, *currbuf; struct pipe_inode_info *pipe;
    unsigned long nr_segs; struct page *pg; unsigned len, offset;
    int usercopy_error; bool write, is_uring;
    struct { unsigned copied_sz; } ring;
};
static struct page native_page;
static unsigned pins, locks, unlocks;
static bool user_backed_iter(const struct iov_iter *i) { return i->user; }
static size_t iov_iter_count(const struct iov_iter *i) { return i->size-i->pos; }
static void iov_iter_advance(struct iov_iter *i, size_t n) { assert(n<=iov_iter_count(i)); i->pos+=n; }
static size_t transfer(void *kernel, size_t n, struct iov_iter *i, bool out) {
    n=min(n,iov_iter_count(i));
    n=min(n,i->fault>i->pos?i->fault-i->pos:0);
    if(out)memcpy(i->bytes+i->pos,kernel,n);else memcpy(kernel,i->bytes+i->pos,n);
    i->pos+=n;return n;
}
static size_t copy_to_iter(const void *p,size_t n,struct iov_iter *i) { return transfer((void *)p,n,i,true); }
static size_t copy_from_iter(void *p,size_t n,struct iov_iter *i) { return transfer(p,n,i,false); }
static int unlock_request(void *p) { (void)p;unlocks++;return 0; }
static int lock_request(void *p) { (void)p;locks++;return 0; }
static void fuse_copy_finish(struct fuse_copy_state *cs) { cs->pg=NULL; }
static int pipe_buf_confirm(void *p,void *b) { (void)p;(void)b;return 0; }
static struct page *alloc_page(int flags) { (void)flags;return &native_page; }
static void *kmap_local_page(struct page *p) { assert(p);return p->bytes; }
static void kunmap_local(void *p) { (void)p; }
static int iov_iter_get_pages2(struct iov_iter *i, struct page **p, size_t max, int count, size_t *off) {
    (void)count;pins++;
    /* A separate user memory has no native pages to return. */
    if(i->user)return -EFAULT;
    *p=&native_page;*off=0;
    size_t n=min(max,iov_iter_count(i));iov_iter_advance(i,n);return n;
}
"""
tests = r"""
int main(void) {
    unsigned char kernel[PAGE_SIZE+17], user[PAGE_SIZE+23];
    for(unsigned j=0;j<sizeof(kernel);j++)kernel[j]=(unsigned char)(j*37+11);
    for(int out=0;out<2;out++) {
        memset(user,0xcc,sizeof(user));
        if(!out)memcpy(user+3,kernel,sizeof(kernel));
        unsigned char expected[sizeof(kernel)];memcpy(expected,kernel,sizeof(kernel));
        struct iov_iter i={user+3,sizeof(kernel),0,sizeof(kernel),true};
        struct fuse_copy_state cs={.iter=&i,.write=out};
        pins=0;
        int ret=fuse_copy_one(&cs,kernel,sizeof(kernel));
        if(CONFIG_WASM) {
            assert(ret==0 && pins==0 && i.pos==sizeof(kernel));
            assert(!memcmp(kernel,expected,sizeof(kernel)) && !memcmp(user+3,expected,sizeof(kernel)));
            assert(user[0]==0xcc && user[sizeof(user)-1]==0xcc);
        }else assert(ret==-EFAULT && pins==1 && i.pos==0);
    }
    /* Non-user iterators keep their native page path, even on Wasm. */
    struct iov_iter native={native_page.bytes,32,0,32,false};
    struct fuse_copy_state paged={.iter=&native,.write=true};
    pins=0;
    assert(fuse_copy_one(&paged,kernel,32)==0 && pins==1);
    assert(!memcmp(native_page.bytes,kernel,32));
    if(CONFIG_WASM) {
        for(int out=0;out<2;out++)for(unsigned fault=0;fault<=11;fault+=11) {
            memset(user,0x5a,sizeof(user));memset(kernel,0xa5,sizeof(kernel));
            struct iov_iter i={user,32,0,fault,true};
            struct fuse_copy_state cs={.iter=&i,.write=out};
            assert(fuse_copy_one(&cs,kernel,32)==-EFAULT);
            assert(i.pos==fault && cs.usercopy_error==-EFAULT && cs.len==0);
            for(unsigned j=0;j<32;j++) {
                assert(user[j]==(out && j<fault?0xa5:0x5a));
                assert(kernel[j]==(!out && j<fault?0x5a:0xa5));
            }
        }
        struct iov_iter empty={user,0,0,0,true};
        struct fuse_copy_state cs={.iter=&empty,.write=true};
        assert(fuse_copy_one(&cs,kernel,1)==-EFAULT);
        struct iov_iter skip={user,32,0,32,true};
        cs=(struct fuse_copy_state){.iter=&skip};
        assert(fuse_copy_fill(&cs)==0);
        unsigned count=17;
        assert(fuse_copy_do(&cs,NULL,&count)==17 && count==0 && skip.pos==17);
    }
    assert(locks && unlocks);
}
"""


def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


with tempfile.TemporaryDirectory(prefix="fuse-usercopy-") as tmp:
    binary = str(Path(tmp) / "model")
    for cc in ("gcc", "clang"):
        for wasm in (0, 1):
            command = [
                cc,
                "-xc",
                "-std=gnu11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                f"-DCONFIG_WASM={wasm}",
                "-o",
                binary,
                "-",
            ]
            unit = shim + functions + tests
            subprocess.run(command, input=unit, text=True, check=True)
            subprocess.run([binary], check=True, timeout=5, preexec_fn=no_core)
        # Removing the architectural route must fail its positive transfer.
        negative = unit.replace("IS_ENABLED(CONFIG_WASM) &&", "false &&")
        subprocess.run(command, input=negative, text=True, check=True)
        result = subprocess.run(
            [binary], capture_output=True, text=True, preexec_fn=no_core, timeout=5
        )
        assert result.returncode != 0 and "pins==0" in result.stderr
        # Not emptying a faulted window used to leave byte-count callers stuck.
        negative = unit.replace(
            "if (usercopy && cs->usercopy_error)\n\t\tcs->len = 0;", ""
        )
        assert negative != unit
        subprocess.run(command, input=negative, text=True, check=True)
        try:
            subprocess.run(
                [binary], capture_output=True, text=True, preexec_fn=no_core, timeout=1
            )
        except subprocess.TimeoutExpired:
            pass
        else:
            raise AssertionError(
                "missing fault progress control must hang this negative model"
            )
print(
    "actual FUSE copy bodies: Wasm usercopy, native page path, short faults and no-progress controls passed"
)
