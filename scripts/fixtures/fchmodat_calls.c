/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
static int error, fallbacks;
int *__errno_location(void) { return &error; }
long __syscall_ret(unsigned long value)
{
	if (value > -4096UL) { error = -(long)value; return -1; }
	return value;
}
/* Old-kernel fallback dependencies are only instrumentation in this fixture. */
int fstatat(int fd, const char *path, struct stat *status, int flags)
{
	(void)fd; (void)path; (void)status; (void)flags;
	fallbacks++; error = ENOENT; return -1;
}
int stat(const char *path, struct stat *status)
{
	(void)path; (void)status; fallbacks++; error = ENOENT; return -1;
}
void __procfdname(char *path, unsigned fd) { (void)fd; path[0] = 0; }
int run(void) { error = 0; return fchmodat(37, "", 0640, AT_EMPTY_PATH); }
int noflags(void) { return fchmodat(37, "after", 0600, 0); }
int nofollow(void) { return fchmodat(37, "after", 0600, AT_SYMLINK_NOFOLLOW); }
int last_error(void) { return error; }
int fallback_count(void) { return fallbacks; }
