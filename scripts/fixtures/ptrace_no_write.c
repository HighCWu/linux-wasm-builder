/* SPDX-License-Identifier: MIT */
#include <stdarg.h>
#include <sys/ptrace.h>
#include <sys/types.h>

long __real_ptrace(int, ...);
long __wrap_ptrace(int request, ...)
{
  va_list ap;
  va_start(ap, request);
  pid_t pid = va_arg(ap, pid_t);
  void *addr = va_arg(ap, void *);
  void *data = va_arg(ap, void *);
  va_end(ap);
  if (request == PTRACE_POKEDATA) return 0;
  return __real_ptrace(request, pid, addr, data);
}
