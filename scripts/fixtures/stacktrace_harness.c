/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

struct task_struct { const char *comm; int pid; };
static struct task_struct running = {"running", 11}, remote = {"remote", 22};
static struct task_struct *current = &running;
static int task_pid_nr(struct task_struct *task) { return task->pid; }
static char output[4096];
static unsigned calls;
static int mode;
static void printk(const char *format, ...)
{
  va_list ap;
  va_start(ap, format);
  size_t used = strlen(output);
  int count = vsnprintf(output + used, sizeof(output) - used, format, ap);
  va_end(ap);
  assert(count >= 0 && (size_t)count < sizeof(output) - used);
}
static void wasm_kernel_get_stacktrace(char *buffer, size_t capacity)
{
  ++calls;
  assert(capacity == 1024);
  /* Model older hosts: neither short nor full writes append a terminator. */
  if (mode == 0) memcpy(buffer, "frame", 5);
  if (mode == 1) memset(buffer, 'X', capacity);
}

/* The checker inserts the actual kernel function body here, unchanged. */

int main(void)
{
  for (mode = 0; mode < 3; ++mode) {
    output[0] = 0;
    unsigned before = calls;
    show_stack(NULL, NULL, "info: ");
    assert(calls == before + 1);
    assert(strstr(output, "Stack from running (11):"));
    if (mode == 0) assert(strstr(output, "info: frame\n"));
    if (mode == 1) assert(strlen(strchr(output, '\n') + 1) == 6 + 1023 + 1);
    output[0] = 0;
    before = calls;
    show_stack(&remote, NULL, "info: ");
    assert(calls == before && strstr(output, "Stack for remote (22) unavailable"));
  }
  puts("stacktrace: bounded, terminated local traces and honest remote task identity pass");
}
