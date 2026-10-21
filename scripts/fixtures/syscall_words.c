/* SPDX-License-Identifier: MIT */
/* Minimal Linux macro context; the architecture header under test is unmodified. */
#define asmlinkage
#define __unused __attribute__((unused))
#define ALLOW_ERROR_INJECTION(...)
#define SYSCALL_METADATA(...)
#define __PROTECT(...)
#define __MAP0(m,...)
#define __MAP1(m,t,a,...) m(t,a)
#define __MAP2(m,t,a,...) m(t,a), __MAP1(m,__VA_ARGS__)
#define __MAP3(m,t,a,...) m(t,a), __MAP2(m,__VA_ARGS__)
#define __MAP4(m,t,a,...) m(t,a), __MAP3(m,__VA_ARGS__)
#define __MAP5(m,t,a,...) m(t,a), __MAP4(m,__VA_ARGS__)
#define __MAP6(m,t,a,...) m(t,a), __MAP5(m,__VA_ARGS__)
#define __MAP(n,...) __MAP##n(__VA_ARGS__)
#define __SC_DECL(t,a) t a
#define __TYPE_IS_LL(t) (__builtin_types_compatible_p(t,long long) || __builtin_types_compatible_p(t,unsigned long long))
#define __SC_LONG(t,a) __typeof__(__builtin_choose_expr(__TYPE_IS_LL(t),0LL,0L)) a
#define __SC_CAST(t,a) (t)a
#define __SC_ARGS(t,a) a
#define __SC_TEST(t,a) ((void)sizeof(char[(__TYPE_IS_LL(t) || sizeof(t)<=sizeof(long))?1:-1]))
#include "wrapper.h"
#ifdef WASM_WORD_NEGATIVE
/* Reintroduce the old one-register-per-parameter forwarding as a control. */
#undef SC_WASM_REGS_TO_ARGS
#define SC_WASM_REGS_TO_ARGS(x, ...) __MAP(x, __SC_ARGS, , regs->syscall_args[0], , regs->syscall_args[1], , regs->syscall_args[2], , regs->syscall_args[3], , regs->syscall_args[4], , regs->syscall_args[5])
#endif

/* Two wide arguments and all six machine words, like fallocate/sync_file_range2. */
__SYSCALL_DEFINEx(4, _allocation, int, fd, unsigned int, flags, long long, offset,
                 unsigned long long, length)
{
	return fd == -7 && flags == 9 && offset == 0x1234567889abcdefLL &&
	       length == 0x76543210fedcba98ULL ? 71 : -1;
}
/* A scalar after two wide arguments must start at the sixth word. */
__SYSCALL_DEFINEx(4, _advice, int, fd, long long, offset, long long, length, int, advice)
{
	return fd == 7 && offset == -4294967297LL && length == 0x200000003LL && advice == -9 ? 72 : -1;
}
__SYSCALL_DEFINEx(4, _pread, int, fd, void *, buffer, unsigned long, count, long long, offset)
{
	return fd == 7 && buffer == (void *)0x1234 && count == 17 && offset == 0x100000011LL ? 73 : -1;
}
__SYSCALL_DEFINEx(6, _plain, long, a, long, b, long, c, long, d, long, e, long, f)
{
	return a == -1 && b == 2 && c == 3 && d == 4 && e == 5 && f == -6 ? 74 : -1;
}
SYSCALL_DEFINE0(zero) { return 75; }
__SYSCALL_DEFINEx(6, _overfull, long long, a, long, b, long, c, long, d, long, e, long, f)
{
	(void)a; (void)b; (void)c; (void)d; (void)e; (void)f;
	return 76;
}

int run(void)
{
#if __SIZEOF_LONG__ == 4
	struct pt_regs allocation = {.syscall_args = {-7UL, 9, 0x89abcdefUL, 0x12345678UL, 0xfedcba98UL, 0x76543210UL}};
	struct pt_regs advice = {.syscall_args = {7, 0xffffffffUL, 0xfffffffeUL, 3, 2, -9UL}};
	struct pt_regs pread = {.syscall_args = {7, 0x1234, 17, 17, 1, 0}};
#else
	struct pt_regs allocation = {.syscall_args = {-7UL, 9, 0x1234567889abcdefUL, 0x76543210fedcba98UL, 0, 0}};
	struct pt_regs advice = {.syscall_args = {7, -4294967297L, 0x200000003UL, -9UL, 0, 0}};
	struct pt_regs pread = {.syscall_args = {7, 0x1234, 17, 0x100000011UL, 0, 0}};
#endif
	struct pt_regs plain = {.syscall_args = {-1UL, 2, 3, 4, 5, -6UL}};
	if (sys_allocation(&allocation) != 71) return 1;
	if (sys_advice(&advice) != 72) return 2;
	if (sys_pread(&pread) != 73) return 3;
	if (sys_plain(&plain) != 74) return 4;
	if (sys_zero(&plain) != 75) return 5;
#if __SIZEOF_LONG__ == 4
	if (sys_overfull(&plain) != -38) return 6;
#else
	if (sys_overfull(&plain) != 76) return 6;
#endif
	return 0;
}
