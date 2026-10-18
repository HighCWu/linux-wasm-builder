// SPDX-License-Identifier: MIT
// Freestanding execution-state experiment, NOT a libc fork implementation.
#include <stdint.h>

__attribute__((import_module("continuation_probe_v1"),
               import_name("checkpoint"))) extern int
checkpoint(void);
__attribute__((import_module("continuation_probe_v1"),
               import_name("event"))) extern void
event(int value);

static unsigned char continuation_stack[64 * 1024] __attribute__((aligned(16)));
static struct {
  uintptr_t cursor;
  uintptr_t end;
} descriptor;
static volatile int before_count;
static volatile int private_value = 17;

__attribute__((export_name("prepare"))) uintptr_t prepare(void) {
  descriptor.cursor = (uintptr_t)continuation_stack;
  descriptor.end = (uintptr_t)(continuation_stack + sizeof continuation_stack);
  return (uintptr_t)&descriptor;
}

__attribute__((noinline)) static int leaf(int failure) {
  volatile int local = 41;
  volatile int *pointer = &local;
  int first, second;

  before_count++;
  event(1);
  first = checkpoint();
  if (before_count != 1 || *pointer != 41 || private_value != 17)
    return -101;
  if (failure)
    return first == -12 ? 77 : -102;
  if (first < 0)
    return -103;
  *pointer = first == 0 ? 51 : 61;
  private_value = *pointer;
  event(2);
  second = checkpoint();
  if (second < 0 || before_count != 1 || private_value != *pointer ||
      *pointer != (first == 0 ? 51 : 61))
    return -104;
  // Every branch writes its own memory after both checkpoints.
  private_value = second == 0 ? 71 : 81;
  event(3);
  return (first == 0 ? 0 : 2) + (second == 0 ? 0 : 1);
}

__attribute__((noinline)) static int nested(int depth, int failure) {
  volatile int sentinel = 100 + depth;
  int result = depth ? nested(depth - 1, failure) : leaf(failure);
  return sentinel == 100 + depth ? result : -105;
}

static int (*volatile indirect)(int, int) = nested;

__attribute__((export_name("run"))) int run(int failure) {
  return indirect(6, failure);
}
