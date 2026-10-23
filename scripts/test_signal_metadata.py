#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual signal metadata helpers with host uaccess shims; not Wasm delivery proof."""
import os
from pathlib import Path
import re
import resource
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = Path(os.environ.get("WASM_SIGNAL_METADATA_SOURCE",
                            root / "sources/linux/arch/wasm/kernel/signal.c")).read_text()
frame = re.search(r"struct wasm_signal_frame \{.*?\n\};", source, re.S).group()
assert "frame.previous = previous_frame;" in source
assert "frame.previous_info = previous_info;" in source

def function(signature):
    start = source.index(signature)
    end = source.index("\n}\n", start) + 3
    return source[start:end]

clear = function("void\nwasm_clear_active_siginfo")
copy = function("int\nwasm_copy_active_signal_frame")
finish = function("int\nwasm_finish_active_signal_frame")
prefix = """
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <signal.h>
#include <string.h>
typedef siginfo_t kernel_siginfo_t;
#define __user
struct wasm_signal_frame;
static struct thread_info {
    const kernel_siginfo_t *active_siginfo;
    struct wasm_signal_frame *active_signal_frame;
} state;
#define current_thread_info() (&state)
static int copy_to_user(void *to, const void *from, size_t size) {
    memcpy(to, from, size); return 0;
}
static int copy_from_user(void *to, const void *from, size_t size) {
    memcpy(to, from, size); return 0;
}
"""
checks = """
int main(void) {
    kernel_siginfo_t outer_info = {.si_signo = SIGUSR1}, inner_info = {.si_signo = SIGUSR2};
    struct wasm_signal_frame outer = {0}, inner = {0};
    outer.stack.ss_size = 65536;
    sigemptyset(&outer.mask);
    inner.previous = &outer;
    inner.previous_info = &outer_info;
    state.active_signal_frame = &inner;
    state.active_siginfo = &inner_info;
    wasm_clear_active_siginfo();
    assert(state.active_signal_frame == &outer && state.active_siginfo == &outer_info);
    stack_t stack;
    sigset_t mask;
    assert(wasm_copy_active_signal_frame(&stack, &mask) == 0 && stack.ss_size == 65536);
    sigaddset(&mask, SIGWINCH);
    assert(wasm_finish_active_signal_frame(&stack, &mask) == 0);
    assert(sigismember(&outer.mask, SIGWINCH) == 1);
    wasm_clear_active_siginfo();
    assert(!state.active_signal_frame && !state.active_siginfo);
    assert(wasm_copy_active_signal_frame(&stack, &mask) == -EINVAL);
    wasm_clear_active_siginfo();
    return 0;
}
"""
old = """void wasm_clear_active_siginfo(void) {
    current_thread_info()->active_siginfo = NULL;
    current_thread_info()->active_signal_frame = NULL;
}
"""
def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

for cc in ("gcc", "clang"):
    with tempfile.TemporaryDirectory(prefix="signal-metadata-") as tmp:
        binary = Path(tmp) / "test"
        for label, body in (("normal", clear), ("old-clear-all", old)):
            subprocess.run([cc, "-xc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-o", str(binary), "-"],
                           input=prefix + frame + body + copy + finish + checks, text=True, check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10,
                                    preexec_fn=no_core,
                                    env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1",
                                         "ASAN_OPTIONS": "halt_on_error=1:detect_leaks=1"})
            if label == "normal":
                assert result.returncode == 0, result.stdout + result.stderr
            else:
                assert result.returncode != 0 and "state.active_signal_frame == &outer" in result.stderr, result.stderr
        print(f"{cc}: actual signal metadata helpers and lost-outer-frame control passed")
