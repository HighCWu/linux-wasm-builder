/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <signal.h>
#include <stdarg.h>
#include <sys/syscall.h>

long __real_syscall(long, ...);
long __wrap_syscall(long nr, ...)
{
  va_list ap;
  long args[6];
  va_start(ap, nr);
  for (int i = 0; i < 6; ++i) args[i] = va_arg(ap, long);
  va_end(ap);
  sigset_t all, previous;
  if (nr == SYS_tkill) {
    sigfillset(&all);
    sigprocmask(SIG_BLOCK, &all, &previous);
  }
  long result = __real_syscall(nr, args[0], args[1], args[2], args[3], args[4], args[5]);
  if (nr == SYS_tkill) sigprocmask(SIG_SETMASK, &previous, 0);
  return result;
}
