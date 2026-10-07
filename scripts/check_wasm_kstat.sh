#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Layout-only compile: no target libraries, Linux or LLVM build required.
set -euo pipefail
root_dir=$(cd "$(dirname "$0")/.." && pwd)
for bits in 32 64; do
  gcc -m"$bits" -std=c11 -Wall -Wextra -Werror -fsyntax-only -x c - \
    -I"$root_dir/sources/musl/arch/wasm32" <<'EOF'
typedef unsigned long long dev_t;
typedef unsigned long long ino_t;
typedef unsigned int mode_t;
typedef unsigned long nlink_t;
typedef unsigned int uid_t;
typedef unsigned int gid_t;
typedef long long off_t;
typedef long blksize_t;
typedef long long blkcnt_t;
#include "kstat.h"
#define OFFSET(field, value) _Static_assert(__builtin_offsetof(struct kstat, field) == value, #field)
OFFSET(st_mode, 16);
OFFSET(st_nlink, 20);
OFFSET(st_uid, 24);
OFFSET(st_gid, 28);
OFFSET(st_rdev, 32);
OFFSET(st_size, 48);
OFFSET(st_blksize, 56);
OFFSET(st_blocks, 64);
OFFSET(st_atime_sec, 72);
_Static_assert(sizeof(((struct kstat *)0)->st_nlink) == 4, "nlink wire width");
_Static_assert(sizeof(((struct kstat *)0)->st_blksize) == 4, "blksize wire width");
#if __SIZEOF_LONG__ == 8
OFFSET(st_mtime_sec, 88);
OFFSET(st_ctime_sec, 104);
_Static_assert(sizeof(struct kstat) == 128, "native stat size");
#else
OFFSET(st_mtime_sec, 80);
OFFSET(st_ctime_sec, 88);
_Static_assert(sizeof(struct kstat) == 104, "stat64 size");
#endif
EOF
  gcc -m"$bits" -std=c11 -Wall -Wextra -Werror -fsyntax-only -x c - \
    -I"$root_dir/sources/musl/arch/wasm32/bits" <<'EOF'
#include "syscall.h.in"
_Static_assert(__NR_utimensat == 88, "native/time32 utimensat number");
#if __SIZEOF_LONG__ == 8
#if defined(__NR_clock_adjtime64) || \
    defined(__NR_clock_getres_time64) || \
    defined(__NR_clock_gettime64) || \
    defined(__NR_clock_nanosleep_time64) || \
    defined(__NR_clock_settime64) || \
    defined(__NR_futex_time64) || \
    defined(__NR_io_pgetevents_time64) || \
    defined(__NR_mq_timedreceive_time64) || \
    defined(__NR_mq_timedsend_time64) || \
    defined(__NR_ppoll_time64) || \
    defined(__NR_pselect6_time64) || \
    defined(__NR_recvmmsg_time64) || \
    defined(__NR_rt_sigtimedwait_time64) || \
    defined(__NR_sched_rr_get_interval_time64) || \
    defined(__NR_semtimedop_time64) || \
    defined(__NR_timer_gettime64) || \
    defined(__NR_timer_settime64) || \
    defined(__NR_timerfd_gettime64) || \
    defined(__NR_timerfd_settime64) || \
    defined(__NR_utimensat_time64)
#error 32-bit time64 syscall names leaked into the 64-bit profile
#endif
#if defined(__NR_fstat64) || defined(__NR_fstatat64)
#error 32-bit stat syscall names leaked into the 64-bit profile
#endif
_Static_assert(__NR_fstat == 80, "native fstat number");
_Static_assert(__NR_newfstatat == 79, "native fstatat number");
#else
#if defined(__NR_fstat) || defined(__NR_newfstatat)
#error native stat syscall names leaked into the 32-bit profile
#endif
_Static_assert(__NR_fstat64 == 80, "stat64 number");
_Static_assert(__NR_fstatat64 == 79, "fstatat64 number");
_Static_assert(__NR_clock_gettime64 == 403, "time64 clock number");
_Static_assert(__NR_utimensat_time64 == 412, "time64 utimensat number");
_Static_assert(__NR_ppoll_time64 == 414, "time64 ppoll number");
_Static_assert(__NR_futex_time64 == 422, "time64 futex number");
#endif
EOF
done
echo "Wasm kstat layouts and syscall names passed for both long widths"
