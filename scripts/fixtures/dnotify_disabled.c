/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
int __real_fcntl(int, int, ...);
int __wrap_fcntl(int fd, int command, ...)
{
	va_list args;
	va_start(args, command);
	long value = va_arg(args, long);
	va_end(args);
	if (command == F_NOTIFY) { errno = EINVAL; return -1; }
	return __real_fcntl(fd, command, value);
}
