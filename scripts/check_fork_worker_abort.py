#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise exact kernel fork-abort functions with host atomic/Worker shims.

Not a Wasm/Linux runtime acceptance: the target EMFILE case is separate.
"""

import pathlib
import subprocess
import sys
import tempfile


def function(source, marker):
    start = source.index(marker)
    body = source.index("{", start)
    depth = 1
    end = body + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


source = pathlib.Path(sys.argv[1]).read_text()
abort = function(source, "static __noreturn void abort_task_entry(")
cleanup = function(source, "void exit_thread(")
entry = function(source, "static void noinline_for_stack task_entry_inner(")
loop = entry[entry.index("for (;;) {") : entry.index("BUG_ON(cpu >= nr_cpu_ids")]
assert "abort_task_entry(args)" in loop
assert "info->bootstrap_args = NULL;\n\tkfree(args);" in entry
assert "task_thread_info(dst)->bootstrap_args = NULL" in source
assert "task_thread_info(p)->bootstrap_args = bootstrap_args;" in source

prefix = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <linux/futex.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#define __noreturn _Noreturn
#define WASM_CPU_PARKED (-1)
#define WASM_CPU_REMOTE_WAKE (-2)
#define WASM_CPU_FORK_ABORT (-3)
typedef struct { _Atomic int counter; } atomic_t;
struct task_bootstrap_args;
struct thread_info { atomic_t running_cpu; struct task_bootstrap_args *bootstrap_args; };
struct task_struct { struct thread_info info; const char *comm; int pid; };
struct task_bootstrap_args { struct task_struct *task; atomic_t aborted; };
#define task_thread_info(p) (&(p)->info)
#define atomic_read(p) atomic_load(&(p)->counter)
#define atomic_read_acquire(p) atomic_load_explicit(&(p)->counter, memory_order_acquire)
#define atomic_set_release(p,v) atomic_store_explicit(&(p)->counter, v, memory_order_release)
#define atomic_xchg(p,v) atomic_exchange(&(p)->counter, v)
#define atomic_cmpxchg(p,a,b) cmpxchg(&(p)->counter,a,b)
static int cmpxchg(_Atomic int *p, int old, int value) {
  atomic_compare_exchange_strong(p, &old, value); return old;
}
#define BUG_ON(x) assert(!(x))
#define kfree(p) do { assert(atomic_load(&(p)->aborted.counter)); free(p); } while (0)
static int host_wait(_Atomic int *p, int expected, long long ns) {
  struct timespec timeout = { .tv_sec = ns / 1000000000, .tv_nsec = ns % 1000000000 };
  int result = syscall(SYS_futex, p, FUTEX_WAIT_PRIVATE, expected, &timeout, 0, 0);
  return result < 0 && errno == ETIMEDOUT ? 2 : 0;
}
#define __builtin_wasm_memory_atomic_wait32 host_wait
static int host_notify(_Atomic int *p, int count) {
  return syscall(SYS_futex, p, FUTEX_WAKE_PRIVATE, count, 0, 0, 0);
}
#define __builtin_wasm_memory_atomic_notify host_notify
static void wasm_service_remote_request(struct task_struct *p) { (void)p; abort(); }
#define early_printk(...) ((void)0)
static _Noreturn void wasm_kernel_halt_worker(void) { pthread_exit(0); }
static _Atomic int entered;
static int delay_entry;
"""
worker = r"""
static void *worker(void *pointer) {
  struct task_bootstrap_args *args = pointer;
  if (delay_entry) { struct timespec t = {.tv_nsec=1000000}; nanosleep(&t, 0); }
  struct task_struct *task = args->task;
  struct thread_info *info = task_thread_info(task);
  int cpu, ret;
  atomic_store(&entered, 1);
  LOOP
  abort();
}
int main(void) {
  struct task_struct normal = {0};
  exit_thread(&normal); /* A running/exited task has no pending Worker. */
  for (int i = 0; i < 128; i++) {
    struct task_struct *task = calloc(1, sizeof *task);
    struct task_bootstrap_args *args = calloc(1, sizeof *args);
    assert(task && args);
    task->info.bootstrap_args = args;
    atomic_store(&task->info.running_cpu.counter, WASM_CPU_PARKED);
    args->task = task;
    atomic_store(&entered, 0);
    delay_entry = i & 1;
    pthread_t thread;
    assert(!pthread_create(&thread, 0, worker, args));
    if (!delay_entry) while (!atomic_load(&entered)) sched_yield();
    exit_thread(task);
    assert(!task->info.bootstrap_args);
    assert(atomic_load(&task->info.running_cpu.counter) == WASM_CPU_FORK_ABORT);
    free(task); /* Even if the host Worker has not finished pthread_exit. */
    assert(!pthread_join(thread, 0));
  }
  puts("fork-abort: early/late Worker acknowledgement and lifetime pass");
}
""".replace("LOOP", loop)

with tempfile.TemporaryDirectory(prefix="fork-worker-abort-") as tmp:
    directory = pathlib.Path(tmp)
    fixture = directory / "probe.c"
    fixture.write_text(prefix + abort + "\n" + cleanup + "\n" + worker)
    for compiler in ("gcc", "clang"):
        binary = directory / compiler
        subprocess.run(
            [
                compiler,
                "-std=c11",
                "-O2",
                "-pthread",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-fsanitize=address,undefined",
                str(fixture),
                "-o",
                str(binary),
            ],
            check=True,
        )
        subprocess.run([str(binary)], check=True, timeout=20)
    # Prove that the lifetime gate matters, rather than merely exercising a
    # shim that could also pass after freeing a still-starting Worker's task.
    broken = directory / "without-ack.c"
    broken_cleanup = cleanup.replace(
        "while (!atomic_read_acquire(&args->aborted))", "while (0)"
    )
    assert broken_cleanup != cleanup
    broken.write_text(prefix + abort + "\n" + broken_cleanup + "\n" + worker)
    rejected = directory / "without-ack"
    subprocess.run(
        [
            "clang",
            "-std=c11",
            "-O2",
            "-pthread",
            "-fsanitize=address,undefined",
            str(broken),
            "-o",
            str(rejected),
        ],
        check=True,
    )
    result = subprocess.run([str(rejected)], capture_output=True, text=True, timeout=20)
    assert result.returncode != 0 and (
        "aborted.counter" in result.stderr or "heap-use-after-free" in result.stderr
    )
    # After the acknowledgement, generated Wasm may only call halt/unreachable;
    # no task-stack/argument loads may follow the parent's reclamation point.
    wasm = directory / "halt.c"
    wasm.write_text(
        """#define __noreturn _Noreturn
typedef struct { int counter; } atomic_t;
struct task_bootstrap_args { atomic_t aborted; };
#define atomic_set_release(p,v) __atomic_store_n(&(p)->counter,v,__ATOMIC_RELEASE)
__attribute__((import_module("kernel"), import_name("halt_worker")))
void wasm_kernel_halt_worker(void);
"""
        + abort.replace("static __noreturn", "__noreturn")
    )
    for bits in (32, 64):
        assembly = directory / f"halt{bits}.s"
        subprocess.run(
            [
                "clang",
                f"--target=wasm{bits}",
                "-matomics",
                "-O2",
                "-nostdinc",
                "-S",
                str(wasm),
                "-o",
                str(assembly),
            ],
            check=True,
        )
        tail = assembly.read_text().split("i32.atomic.store", 1)[1]
        assert ".load" not in tail and "wasm_kernel_halt_worker" in tail
        assert "unreachable" in tail
print("fork-abort: host sanitizer checks and wasm32/wasm64 final-access codegen pass")
