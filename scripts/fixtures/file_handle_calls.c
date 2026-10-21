/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
static int error;
int *__errno_location(void) { return &error; }
int *___errno_location(void) { return &error; }
/* A fixed buffer with normal alignment, never used as a real kernel object. */
static union { uint64_t alignment; unsigned char bytes[136]; } object;
static int mount_id;
__attribute__((export_name("encode"))) int encode(void)
{
	return name_to_handle_at(37, "file", (struct file_handle *)object.bytes, &mount_id, AT_EMPTY_PATH);
}
__attribute__((export_name("decode"))) int decode(void)
{
	return open_by_handle_at(39, (struct file_handle *)object.bytes, O_RDONLY | O_CLOEXEC);
}
__attribute__((export_name("handle_address"))) uintptr_t handle_address(void) { return (uintptr_t)object.bytes; }
__attribute__((export_name("mount_address"))) uintptr_t mount_address(void) { return (uintptr_t)&mount_id; }
__attribute__((export_name("last_error"))) int last_error(void) { return error; }
_Static_assert(offsetof(struct file_handle, f_handle) == 8, "file handle UAPI prefix");
