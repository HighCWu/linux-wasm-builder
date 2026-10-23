/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PAGE_SIZE 65536UL
#define offset_in_page(n) ((n) & (PAGE_SIZE - 1))
#define min_t(t, a, b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define GFP_KERNEL 0
#define FOLL_WRITE 1
#define CONFIG_WASM 1
#define REMOTE_BASE 0x10000000UL
struct page;
struct task_struct;
struct mm_struct { int unused; };
struct iov_iter { unsigned char *buffer; size_t total, done, accessible; };
static unsigned char remote_data[160000], local[70001];
static size_t remote_accessible, committed;
static int allocations;
static bool allocation_failure;
static unsigned timer_polls, schedule_checks;
static void wasm_timer_check(void) { ++timer_polls; }
static void cond_resched(void) { ++schedule_checks; }

static size_t iov_iter_count(const struct iov_iter *iter) { return iter->total - iter->done; }
static void *kmalloc(size_t size, int flags)
{
	(void)flags;
	assert(size == 4096);
	if (allocation_failure) return NULL;
	void *result = malloc(size);
	assert(result);
	++allocations;
	return result;
}
static void kfree(void *buffer) { --allocations; free(buffer); }
static size_t copy_iter(void *buffer, size_t n, struct iov_iter *iter, bool write)
{
	n = min_t(size_t, n, iov_iter_count(iter));
	n = min_t(size_t, n, iter->accessible - iter->done);
	if (write) memcpy(iter->buffer + iter->done, buffer, n);
	else memcpy(buffer, iter->buffer + iter->done, n);
	iter->done += n;
	return n;
}
static size_t copy_from_iter(void *buffer, size_t n, struct iov_iter *iter)
{ return copy_iter(buffer, n, iter, false); }
static size_t copy_to_iter(void *buffer, size_t n, struct iov_iter *iter)
{ return copy_iter(buffer, n, iter, true); }
static void iov_iter_revert(struct iov_iter *iter, size_t n)
{ assert(n <= iter->done); iter->done -= n; }
static int access_remote_vm(struct mm_struct *mm, unsigned long addr, void *buffer, int len, unsigned flags)
{
	(void)mm;
	assert(len >= 0 && len <= 4096 && (unsigned)len <= PAGE_SIZE - offset_in_page(addr));
	if (addr < REMOTE_BASE || addr - REMOTE_BASE >= remote_accessible) return 0;
	size_t offset = addr - REMOTE_BASE;
	size_t n = min_t(size_t, len, remote_accessible - offset);
	assert(offset + n <= sizeof remote_data);
	if (flags & FOLL_WRITE) {
		memcpy(remote_data + offset, buffer, n);
		committed += n;
	} else memcpy(buffer, remote_data + offset, n);
	return n;
}

/* Insert the actual NOMMU helper here, unchanged. */

static void reset(void)
{
	assert(allocations == 0);
	remote_accessible = sizeof remote_data;
	allocation_failure = false;
	committed = 0;
	timer_polls = schedule_checks = 0;
	for (size_t i = 0; i < sizeof remote_data; ++i) remote_data[i] = (unsigned char)(i * 37 + 11);
	memset(local, 0, sizeof local);
}
int main(void)
{
	struct mm_struct mm;
	reset();
	struct iov_iter iter = {local, sizeof local, 0, sizeof local};
	assert(process_vm_rw_single_vec(REMOTE_BASE + 65503, sizeof local, &iter, NULL, &mm, NULL, 0) == 0);
	assert(iter.done == sizeof local && !memcmp(local, remote_data + 65503, sizeof local));
	memset(local, 0xa9, sizeof local);
	iter.done = 0;
	assert(process_vm_rw_single_vec(REMOTE_BASE + 65503, sizeof local, &iter, NULL, &mm, NULL, 1) == 0);
	assert(iter.done == sizeof local && committed == sizeof local &&
	       !memcmp(local, remote_data + 65503, sizeof local) && allocations == 0);
	assert(timer_polls >= 36 && schedule_checks == timer_polls);

	for (int write = 0; write < 2; ++write) {
		reset();
		remote_accessible = 777;
		iter = (struct iov_iter){local, sizeof local, 0, sizeof local};
		assert(process_vm_rw_single_vec(REMOTE_BASE, sizeof local, &iter, NULL, &mm, NULL, write) == -EFAULT);
		assert(iter.done == 777 && committed == (write ? 777 : 0) && allocations == 0);
		reset();
		iter = (struct iov_iter){local, sizeof local, 0, 2000};
		assert(process_vm_rw_single_vec(REMOTE_BASE, sizeof local, &iter, NULL, &mm, NULL, write) == -EFAULT);
		assert(iter.done == 2000 && committed == (write ? 2000 : 0) && allocations == 0);
		reset();
		iter = (struct iov_iter){local, sizeof local, 0, 0};
		assert(process_vm_rw_single_vec(REMOTE_BASE, sizeof local, &iter, NULL, &mm, NULL, write) == -EFAULT);
		assert(iter.done == 0 && committed == 0 && allocations == 0);
		reset();
		iter = (struct iov_iter){local, sizeof local, 0, sizeof local};
		assert(process_vm_rw_single_vec(~0UL, sizeof local, &iter, NULL, &mm, NULL, write) == -EFAULT);
		assert(iter.done == 0 && committed == 0 && allocations == 0);
	}
	reset();
	allocation_failure = true;
	iter = (struct iov_iter){local, sizeof local, 0, sizeof local};
	assert(process_vm_rw_single_vec(REMOTE_BASE, sizeof local, &iter, NULL, &mm, NULL, 1) == -ENOMEM);
	assert(iter.done == 0 && committed == 0 && allocations == 0);
	assert(process_vm_rw_single_vec(REMOTE_BASE, 0, &iter, NULL, &mm, NULL, 0) == 0);
	assert(timer_polls == 0 && schedule_checks == 0);
	puts("process-vm model: bounded copies, partial counts, rollback and allocation cleanup pass");
}
