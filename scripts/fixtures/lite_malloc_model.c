/* SPDX-License-Identifier: MIT */
#define _BSD_SOURCE
#include <stdint.h>
#include <errno.h>
#include "libc.h"

struct __libc __libc;
static uintptr_t current = 0x1000000;
static unsigned calls;
static int allowed, locked, error;

int *__errno_location(void) { return &error; }
int *___errno_location(void) { return &error; }
int last_error(void) { return error; }
int lock_state(void) { return locked; }
unsigned grow_count(void) { return calls; }
uintptr_t break_value(void) { return current; }
void model_allow(int value) { allowed = value; }
void model_stack_guard(int value) { __libc.auxv = value ? (size_t *)(current + 64) : 0; }
void __lock(volatile int *lock)
{
	(void)lock;
	if (locked) __builtin_trap();
	locked = 1;
}
void __unlock(volatile int *lock)
{
	(void)lock;
	if (!locked) __builtin_trap();
	locked = 0;
}
void *sbrk(intptr_t increment)
{
	if (!increment) return (void *)current;
	calls++;
	if (!allowed || increment < 0 || (uintptr_t)increment > UINTPTR_MAX - current) {
		error = ENOMEM;
		return (void *)-1;
	}
	uintptr_t previous = current;
	current += increment;
	return (void *)previous;
}
