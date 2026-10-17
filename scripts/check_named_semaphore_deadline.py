#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the actual kernel deadline-admission function with host-only shims.

Not a Linux scheduler, user-copy, lock or Wasm execution test. Kernel function
text is read at test time; no kernel implementation is shipped as SDK code.
"""
from pathlib import Path
import subprocess
import tempfile
import resource
import sys

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

ROOT = Path(__file__).resolve().parents[1]
source = (Path(sys.argv[1]) if len(sys.argv) > 1 else
          ROOT / "sources/linux/arch/wasm/kernel/semaphore.c").read_text()
start = source.index("SYSCALL_DEFINE2(wasm_sem_timedwait,")
brace = source.index("{", start)
depth = 1
end = brace + 1
while depth:
    depth += (source[end] == "{") - (source[end] == "}")
    end += 1
function = source[start:end]

SHIMS = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#define __user
#define NSEC_PER_SEC 1000000000LL
#define SYSCALL_DEFINE2(name,t1,a1,t2,a2) long test_##name(t1 a1,t2 a2)
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define PTR_ERR(p) ((long)(intptr_t)(p))
#define spin_lock_irq(p) ((void)(p))
#define spin_unlock_irq(p) ((void)(p))
#define timespec64_valid(t) ((t)->tv_sec >= 0 && (t)->tv_nsec >= 0 && (t)->tv_nsec < NSEC_PER_SEC)
typedef long long ktime_t;
struct __kernel_timespec { long long tv_sec, tv_nsec; };
struct timespec64 { long long tv_sec, tv_nsec; };
struct fd { int held; };
struct wasm_sem { unsigned value; int lock; };
static struct wasm_sem sem;
static int puts, waits;
static ktime_t last_expiry;
static struct wasm_sem *wasm_sem_from_fd(int number, struct fd *f) {
    if (number < 0) return (void *)(intptr_t)-EBADF;
    f->held = 1;
    return &sem;
}
static void fdput(struct fd f) { assert(f.held); puts++; }
static int get_timespec64(struct timespec64 *to, const struct __kernel_timespec *from) {
    if (!from) return 1;
    to->tv_sec = from->tv_sec; to->tv_nsec = from->tv_nsec; return 0;
}
static ktime_t timespec64_to_ktime(struct timespec64 t) { return t.tv_sec * NSEC_PER_SEC + t.tv_nsec; }
static int wasm_sem_do_wait(struct wasm_sem *s, bool try, ktime_t *expires) {
    assert(s == &sem && !try && expires); waits++; last_expiry = *expires; return -EINTR;
}
'''
TESTS = r'''
static void expired(long long seconds, long long nanoseconds, long expected) {
    struct __kernel_timespec at = { seconds, nanoseconds };
    sem.value = puts = waits = 0;
    assert(test_wasm_sem_timedwait(1, &at) == expected);
    assert(puts == 1 && waits == 0 && sem.value == 0);
}
int main(void) {
    expired(-1, 0, -ETIMEDOUT);
    expired(LLONG_MIN, 999999999, -ETIMEDOUT);
    expired(-1, -1, -EINVAL);
    expired(-1, NSEC_PER_SEC, -EINVAL);
    expired(1, -1, -EINVAL);
    expired(1, NSEC_PER_SEC, -EINVAL);
    for (int invalid = 0; invalid < 2; invalid++) {
        struct __kernel_timespec at = { -1, invalid ? NSEC_PER_SEC : 0 };
        sem.value = 1; puts = waits = 0;
        assert(test_wasm_sem_timedwait(1, &at) == 0);
        assert(sem.value == 0 && puts == 1 && waits == 0);
    }
    sem.value = puts = waits = 0;
    assert(test_wasm_sem_timedwait(1, 0) == -EFAULT && puts == 1);
    puts = 0;
    assert(test_wasm_sem_timedwait(-1, 0) == -EBADF && puts == 0);
    struct __kernel_timespec future = { 2, 3 };
    assert(test_wasm_sem_timedwait(1, &future) == -EINTR);
    assert(puts == 1 && waits == 1 && last_expiry == 2000000003LL);
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix="wasm-sem-deadline-") as temp:
    root = Path(temp)
    for compiler in ("gcc", "clang"):
        path = root / "deadline.c"
        binary = root / "deadline"
        path.write_text(SHIMS + function + TESTS)
        subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", str(path), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=10, cwd=temp)
        reverted = function.replace("error = -ETIMEDOUT;", "error = -EINVAL;")
        if reverted == function:
            raise AssertionError("missing explicit negative-deadline timeout handling")
        path.write_text(SHIMS + reverted + TESTS)
        subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", str(path), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, timeout=10, cwd=temp)
        if result.returncode == 0:
            raise AssertionError("negative control accepted the wrong deadline result")
print("named semaphore deadline admission and negative controls passed (host shims only)")
