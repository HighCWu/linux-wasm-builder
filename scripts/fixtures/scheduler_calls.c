/* SPDX-License-Identifier: MIT */
#include <errno.h>
#include <sched.h>

static int saved_errno;
int *__errno_location(void) { return &saved_errno; }
int *___errno_location(void) { return &saved_errno; }
int last_error(void) { return saved_errno; }

/* The ABI test supplies a deliberately high, never dereferenced pointer. */
int run(int which, long pointer)
{
	saved_errno = 0;
	switch (which) {
	case 0: return sched_getscheduler(-7);
	case 1: return sched_getparam(-7, (struct sched_param *)pointer);
	case 2: return sched_setparam(-7, (const struct sched_param *)pointer);
	case 3: return sched_setscheduler(-7, SCHED_BATCH, (const struct sched_param *)pointer);
	default: return -2;
	}
}
