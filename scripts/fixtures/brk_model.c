/* SPDX-License-Identifier: MIT */
#define _BSD_SOURCE
#include <errno.h>
#include <pthread.h>
#include <stddef.h>
#include <stdint.h>

static size_t pages = 1, limit = 1, grows, delta;
static int error, locked;
int *__errno_location(void) { return &error; }
int *___errno_location(void) { return &error; }
int last_error(void) { return error; }
int lock_state(void) { return locked; }
int pthread_mutex_lock(pthread_mutex_t *mutex) { (void)mutex; ++locked; return 0; }
int pthread_mutex_unlock(pthread_mutex_t *mutex) { (void)mutex; --locked; return 0; }
void model_configure(size_t initial, size_t maximum)
{
	pages = initial;
	limit = maximum;
	grows = delta = 0;
	error = 0;
}
size_t brk_model_size(int index) { (void)index; return pages; }
size_t brk_model_grow(int index, size_t count)
{
	(void)index;
	++grows;
	delta = count;
	if (count > limit - pages) return SIZE_MAX;
	size_t old = pages;
	pages += count;
	return old;
}
size_t grow_count(void) { return grows; }
size_t grow_delta(void) { return delta; }
