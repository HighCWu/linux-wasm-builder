#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the exact synchronous Wasm DIO adapter, without host disk I/O."""

import os
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# The deliberate assertion control must not leave core files in the checkout.
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
source = Path(
    os.environ.get("WASM_DIRECT_IO_SOURCE", ROOT / "sources/linux/fs/read_write.c")
).read_text()
adapter = source.split("#ifdef CONFIG_WASM\n", 1)[1].split(
    "const struct file_operations generic_ro_fops", 1
)[0]
adapter = "#ifdef CONFIG_WASM\n" + "\n".join(
    line for line in adapter.splitlines() if not line.startswith("#include")
)
assert "ret = call_sync_iter(&kiocb, &iter, false);" in source
assert "ret = call_sync_iter(&kiocb, &iter, true);" in source
assert "ret = call_sync_iter(&kiocb, iter, type == WRITE);" in source
consumer = (ROOT / "sources/distro/distro/direct-io/runtime.c").read_text()
assert "device.st_rdev != root.st_dev" in consumer
assert "lseek(fd, 0, SEEK_END) == disk_size" in consumer
assert consumer.index("scratch prefix initially zero") < consumer.index(
    "direct raw write"
)
assert (
    'truncate -s 8388608 "$out"'
    in (ROOT / "sources/distro/distro/direct-io/package.nix").read_text()
)

model = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#define PAGE_SIZE 65536UL
#define PAGE_ALIGN(n) (((n)+PAGE_SIZE-1)&~(PAGE_SIZE-1))
#define GFP_KERNEL 0
#define __GFP_ZERO 0
#define ITER_SOURCE 1
#define ITER_DEST 0
#define IOCB_DIRECT 1
#define IOCB_NOWAIT 2
#define IOCB_ATOMIC 4
#define IOCB_HIPRI 8
#define EIOCBQUEUED 529
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define BUG_ON(x) assert(!(x))
#define S_ISREG(x) ((x)==1)
#define S_ISBLK(x) ((x)==2)
typedef uint64_t u64;
typedef struct {int value;} atomic_t;
#define ATOMIC_INIT(x) {x}
static int atomic_read(atomic_t *v){return v->value;}
static bool atomic_try_cmpxchg(atomic_t *v,int *old,int n){
 if(v->value!=*old){*old=v->value;return false;}v->value=n;return true;}
static void atomic_sub(size_t n,atomic_t *v){v->value-=(int)n;}
static int allocations, fail_alloc, calls;
static void *alloc_pages_exact(size_t n,int flags){
 (void)flags;if(fail_alloc)return NULL;void *p=aligned_alloc(PAGE_SIZE,n);
 assert(p);memset(p,0,n);allocations++;return p;}
static void free_pages_exact(void *p,size_t n){(void)n;allocations--;free(p);}
struct iov_iter {unsigned char *bytes;size_t count,at,valid;unsigned long alignment;bool user;};
struct kvec {void *iov_base;size_t iov_len;};
static size_t iov_iter_count(const struct iov_iter *i){return i->count;}
static unsigned long iov_iter_alignment(const struct iov_iter *i){return i->alignment;}
static bool user_backed_iter(const struct iov_iter *i){return i->user;}
static void iov_iter_advance(struct iov_iter *i,size_t n){assert(n<=i->count);i->at+=n;i->count-=n;}
static void iov_iter_kvec(struct iov_iter *i,int rw,struct kvec *v,int nr,size_t n){
 (void)rw;assert(nr==1);*i=(struct iov_iter){.bytes=v->iov_base,.count=n,.valid=n,
 .alignment=(uintptr_t)v->iov_base|n,.user=false};}
static size_t copy_to_iter(void *p,size_t n,struct iov_iter *i){
 size_t k=min_t(size_t,n,i->valid-i->at);memcpy(i->bytes+i->at,p,k);iov_iter_advance(i,k);return k;}
static bool copy_from_iter_full(void *p,size_t n,struct iov_iter *i){
 size_t k=min_t(size_t,n,i->valid-i->at);memcpy(p,i->bytes+i->at,k);iov_iter_advance(i,k);return k==n;}
struct kiocb;
struct file_operations {ssize_t (*read_iter)(struct kiocb *,struct iov_iter *);
 ssize_t (*write_iter)(struct kiocb *,struct iov_iter *);};
struct inode {int i_mode;unsigned int block_size;long long bytes;};
struct address_space {struct inode *host;};
struct file {struct file_operations *f_op;struct inode inode;struct address_space *f_mapping;};
#define block_device inode
#define I_BDEV(i) (i)
static unsigned int bdev_logical_block_size(struct inode *i){return i->block_size;}
static long long bdev_nr_bytes(struct inode *i){return i->bytes;}
#define file_inode(f) (&(f)->inode)
struct kiocb {struct file *ki_filp;int ki_flags;long long ki_pos;};
static unsigned char disk[4*PAGE_SIZE];
static size_t short_limit=SIZE_MAX;
static int backend_error;
static ssize_t backend(struct kiocb *k,struct iov_iter *i,bool write){
 calls++;if(backend_error)return -backend_error;
 if(k->ki_filp->inode.i_mode==2 && k->ki_pos>=k->ki_filp->inode.bytes)
  return write?-ENOSPC:0;
 /* A user linear-memory iterator has no pinnable kernel VMA. */
 if(i->user&&(k->ki_flags&IOCB_DIRECT))return -EFAULT;
 if(k->ki_filp->inode.i_mode==2){
  if((i->count | (unsigned long)k->ki_pos)&511)return -EINVAL;
 }else if((i->alignment | (unsigned long)k->ki_pos)&511)return -EINVAL;
 size_t n=min_t(size_t,i->count,short_limit);assert(k->ki_pos>=0);
 assert((size_t)k->ki_pos+n<=sizeof(disk));
 if(write)memcpy(disk+k->ki_pos,i->bytes+i->at,n);
 else memcpy(i->bytes+i->at,disk+k->ki_pos,n);
 iov_iter_advance(i,n);k->ki_pos+=n;return n;}
static ssize_t rd(struct kiocb *k,struct iov_iter *i){return backend(k,i,false);}
static ssize_t wr(struct kiocb *k,struct iov_iter *i){return backend(k,i,true);}
"""
tests = r"""
int main(void){
 struct file_operations ops={rd,wr};struct file f={.f_op=&ops,.inode={.i_mode=1,.block_size=512,.bytes=4*PAGE_SIZE}};
 struct address_space mapping={.host=&f.inode};f.f_mapping=&mapping;
 unsigned char *b=aligned_alloc(PAGE_SIZE,4*PAGE_SIZE);assert(b);memset(b,0x5a,4*PAGE_SIZE);
 struct kiocb k={.ki_filp=&f,.ki_flags=IOCB_DIRECT};
 struct iov_iter original={.bytes=b,.count=3*PAGE_SIZE,.valid=4*PAGE_SIZE,
 .alignment=(uintptr_t)b|3*PAGE_SIZE,.user=true},i=original;
 assert(call_sync_iter(&k,&i,true)==2*PAGE_SIZE);
 assert(i.at==2*PAGE_SIZE&&i.count==PAGE_SIZE&&k.ki_pos==2*PAGE_SIZE);
 for(size_t p=0;p<2*PAGE_SIZE;p++)assert(disk[p]==0x5a);
 assert(!allocations&&!wasm_dio_reserved.value);
 memset(b,0,4*PAGE_SIZE);i=original;i.count=2*PAGE_SIZE;k.ki_pos=0;
 assert(call_sync_iter(&k,&i,false)==2*PAGE_SIZE&&b[0]==0x5a&&b[2*PAGE_SIZE-1]==0x5a);
 /* Valid-prefix read: report and advance only delivered bytes. */
 i=original;i.count=PAGE_SIZE;i.valid=17;k.ki_pos=0;
 assert(call_sync_iter(&k,&i,false)==17&&k.ki_pos==17&&i.at==17);
 i=original;i.count=PAGE_SIZE;i.valid=0;k.ki_pos=0;
 assert(call_sync_iter(&k,&i,false)==-EFAULT&&k.ki_pos==0&&i.at==0);
 int before=calls;assert(call_sync_iter(&k,&i,true)==-EFAULT&&calls==before&&i.at==0);
 /* Misalignment of the full request must survive a bounded short chunk. */
 i=original;i.count=3*PAGE_SIZE+1;i.alignment|=1;k.ki_pos=0;
 assert(call_sync_iter(&k,&i,false)==-EINVAL&&i.at==0);
 i=original;k.ki_pos=0;short_limit=512;
 assert(call_sync_iter(&k,&i,true)==512&&i.at==512&&k.ki_pos==512);short_limit=SIZE_MAX;
 for(int flag=IOCB_NOWAIT;flag<=IOCB_HIPRI;flag*=2){
  k.ki_flags=IOCB_DIRECT|flag;i=original;before=calls;
  assert(call_sync_iter(&k,&i,false)==(flag==IOCB_NOWAIT?-EAGAIN:-EOPNOTSUPP));
  assert(calls==before&&i.at==0&&!allocations&&!wasm_dio_reserved.value);}
 k.ki_flags=IOCB_DIRECT;k.ki_pos=0;i=original;fail_alloc=1;
 assert(call_sync_iter(&k,&i,true)==-ENOMEM&&!wasm_dio_reserved.value);fail_alloc=0;
 wasm_dio_reserved.value=WASM_DIO_BUDGET;before=calls;
 assert(call_sync_iter(&k,&i,false)==-ENOMEM&&calls==before);wasm_dio_reserved.value=0;
 backend_error=EIO;assert(call_sync_iter(&k,&i,true)==-EIO&&!allocations&&!wasm_dio_reserved.value);
 backend_error=0;i=original;i.user=false;k.ki_pos=0;short_limit=512;
 assert(call_sync_iter(&k,&i,false)==512); /* Kernel iterators are not bounced. */
 k.ki_flags=0;i=original;k.ki_pos=0;
 assert(call_sync_iter(&k,&i,false)==512); /* Buffered user calls are unchanged. */
 k.ki_flags=IOCB_DIRECT;f.inode.i_mode=2;short_limit=SIZE_MAX;i=original;k.ki_pos=0;
 assert(call_sync_iter(&k,&i,true)==2*PAGE_SIZE&&i.at==2*PAGE_SIZE);
 /* The real block path can accept byte-unaligned buffers, so the full
  * original length must be checked separately before chunking. */
 i=original;i.count=3*PAGE_SIZE+1;i.alignment|=1;k.ki_pos=0;before=calls;
 assert(call_sync_iter(&k,&i,true)==-EINVAL&&calls==before&&i.at==0);
 i=original;k.ki_pos=1;
 assert(call_sync_iter(&k,&i,false)==-EINVAL&&i.at==0);
 i=original;i.bytes=b+1;i.valid=4*PAGE_SIZE-1;i.alignment|=1;i.count=512;k.ki_pos=0;
 assert(call_sync_iter(&k,&i,false)==512&&i.at==512);
 i=original;i.count=3*PAGE_SIZE+1;i.alignment|=1;i.valid=PAGE_SIZE;k.ki_pos=3*PAGE_SIZE+512;
 assert(call_sync_iter(&k,&i,true)==PAGE_SIZE-512&&i.at==PAGE_SIZE-512);
 i=original;i.valid=0;k.ki_pos=4*PAGE_SIZE+1;
 assert(call_sync_iter(&k,&i,false)==0&&i.at==0);
 assert(call_sync_iter(&k,&i,true)==-ENOSPC&&i.at==0);
 assert(!allocations&&!wasm_dio_reserved.value);free(b);
}
"""
with tempfile.TemporaryDirectory(prefix="wasm-direct-io-") as tmp:
    unit = Path(tmp) / "model.c"
    unit.write_text(model + adapter + tests)
    for cc in ("gcc", "clang"):
        output = Path(tmp) / cc
        subprocess.run(
            [
                cc,
                "-DCONFIG_WASM",
                "-DCONFIG_BLOCK",
                "-std=gnu11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(unit),
                "-o",
                str(output),
            ],
            check=True,
        )
        subprocess.run([str(output)], check=True)
    subprocess.run(
        [
            "clang",
            "-DCONFIG_WASM",
            "-DCONFIG_BLOCK",
            "--analyze",
            "-Xanalyzer",
            "-analyzer-werror",
            str(unit),
            "-o",
            "/dev/null",
        ],
        check=True,
    )
    # Removing the adapter must actually lose valid direct I/O, not merely
    # fail compilation. The otherwise identical model runs and asserts.
    unit.write_text(
        model + adapter.replace("(iocb->ki_flags & IOCB_DIRECT) &&", "false &&") + tests
    )
    output = Path(tmp) / "old-path"
    subprocess.run(
        ["clang", "-DCONFIG_WASM", "-std=gnu11", str(unit), "-o", str(output)],
        check=True,
    )
    failed = subprocess.run([str(output)], capture_output=True)
    assert failed.returncode != 0 and b"Assertion" in failed.stderr
    unit.write_text(
        model
        + adapter.replace(
            "if ((iocb->ki_pos | length) & mask)",
            "if (false && ((iocb->ki_pos | length) & mask))",
        )
        + tests
    )
    output = Path(tmp) / "lost-block-length"
    subprocess.run(
        [
            "clang",
            "-DCONFIG_WASM",
            "-DCONFIG_BLOCK",
            "-std=gnu11",
            str(unit),
            "-o",
            str(output),
        ],
        check=True,
    )
    failed = subprocess.run([str(output)], capture_output=True)
    assert failed.returncode != 0 and b"Assertion" in failed.stderr
    unit.write_text(
        model
        + adapter
        + r"""
int main(void){
 struct file_operations ops={rd,wr};struct file f={.f_op=&ops,.inode={.i_mode=1,.block_size=512}};
 unsigned char *b=aligned_alloc(PAGE_SIZE,PAGE_SIZE);assert(b);
 struct kiocb k={.ki_filp=&f,.ki_flags=IOCB_DIRECT};
 struct iov_iter i={.bytes=b,.count=512,.valid=512,.user=true};
 assert(call_sync_iter(&k,&i,false)==-EFAULT&&!allocations);
 i.user=false;assert(call_sync_iter(&k,&i,false)==512&&!allocations);free(b);
}
"""
    )
    output = Path(tmp) / "other-architecture"
    subprocess.run(
        [
            "clang",
            "-std=gnu11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-function",
            str(unit),
            "-o",
            str(output),
        ],
        check=True,
    )
    subprocess.run([str(output)], check=True)

    # Compile and analyze the real consumer, but never run it on the host.
    musl = ROOT / "sources/musl"
    (Path(tmp) / "bits").mkdir()
    templates = (musl / "arch/wasm32/bits/alltypes.h.in").read_text() + (
        musl / "include/alltypes.h.in"
    ).read_text()
    generated = subprocess.check_output(
        ["sed", "-f", str(musl / "tools/mkalltypes.sed")], input=templates, text=True
    )
    (Path(tmp) / "bits/alltypes.h").write_text(generated)
    resource_dir = subprocess.check_output(
        ["clang", "-print-resource-dir"], text=True
    ).strip()
    program = str(ROOT / "sources/distro/distro/direct-io/runtime.c")
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
        subprocess.run([*command, "-fsyntax-only", program], check=True)
        subprocess.run(
            [
                *command,
                "--analyze",
                "-Xanalyzer",
                "-analyzer-werror",
                program,
                "-o",
                "/dev/null",
            ],
            check=True,
        )
print(
    "Synchronous DIO: exact adapter, regular/block alignment, device-end clipping, partial faults, budget and bypass models passed; no disk I/O"
)
