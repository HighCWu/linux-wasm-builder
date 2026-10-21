/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <fcntl.h>
/* This fixture observes successful import forwarding, not libc errno storage. */
long __syscall_ret(unsigned long value) { return value; }
int run(void)
{
	return sync_file_range(7, 0x1234567889abcdefLL, 0x234567899abcdef0LL, 5);
}
