/* SPDX-License-Identifier: MIT */
#include <errno.h>
#include <stdarg.h>
#include <sys/syscall.h>

long __wrap_syscall(long nr, ...)
{
  (void)nr;
#ifdef MEMBARRIER_FALSE_SUCCESS
  va_list ap;
  va_start(ap, nr);
  long command = va_arg(ap, long);
  va_end(ap);
  return command == 0 ? 31 : 0;
#else
  errno = ENOSYS;
  return -1;
#endif
}
