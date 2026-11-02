/* SPDX-License-Identifier: MIT */
/* Private fault model, not Linux VFS or libc acceptance. The actual Wasm
 * __map_file / __unmap_file bodies are inserted at the marker below. */
typedef __SIZE_TYPE__ size_t;
typedef __PTRDIFF_TYPE__ ssize_t;
typedef __UINTMAX_TYPE__ uintmax_t;
struct stat { __INT64_TYPE__ st_size; };
#define SIZE_MAX __SIZE_MAX__
#define SSIZE_MAX __PTRDIFF_MAX__
#define O_RDONLY 0
#define O_CLOEXEC 0x80000
#define O_NONBLOCK 0x800
#define EINTR 4
#define SYS_read 63
#define SYS_close 57

static unsigned char storage[32];
static int mode, opened, closes, allocations, frees, reads, cancellation_points, bad;
static size_t position;

static int sys_open(const char *path, int flags)
{
    (void)path;
    if (flags != (O_CLOEXEC | O_NONBLOCK)) bad++;
    if (mode == 8) return -2;
    opened = 1;
    return 17;
}
static int __fstat(int fd, struct stat *st)
{
    if (fd != 17 || !opened) bad++;
    if (mode == 2) return -1;
    st->st_size = mode == 3 ? 0 : mode == 4 ? -1 : mode == 5 ? 0x100000000LL : 12;
    return 0;
}
static void *malloc(size_t count)
{
    allocations++;
    return mode == 1 || count > sizeof storage ? (void *)0 : storage;
}
static void free(void *p)
{
    if (p != storage || frees) bad++;
    frees++;
}
static long model_syscall(long nr, long fd, long pointer, long count)
{
    if (fd != 17 || !opened) { bad++; return -9; }
    if (nr == SYS_close) { closes++; opened = 0; return 0; }
    if (nr != SYS_read || count <= 0 || (size_t)count > SSIZE_MAX) { bad++; return -22; }
    reads++;
    if (mode == 7) return -5;
    if (mode == 6 && reads > 1) return 0;
    if (mode != 6 && reads == 1) return -EINTR;
    size_t n = (size_t)count < 3 ? (size_t)count : 3;
    unsigned char *destination = (void *)pointer;
    if (destination != storage + position || n > sizeof storage - position) { bad++; return -14; }
    for (size_t i = 0; i < n; i++) destination[i] = 0x40 + position + i;
    position += n;
    return n;
}
#define sc1(n,a) model_syscall(n,(long)(a),0,0)
#define sc2(n,a,b) model_syscall(n,(long)(a),(long)(b),0)
#define sc3(n,a,b,c) model_syscall(n,(long)(a),(long)(b),(long)(c))
#define pick(_1,_2,_3,name,...) name
#define __syscall(n,...) pick(__VA_ARGS__,sc3,sc2,sc1)(n,__VA_ARGS__)
__attribute__((unused)) static ssize_t read(int fd, void *p, size_t count)
{
    cancellation_points++;
    return model_syscall(SYS_read,fd,(long)p,(long)count);
}

/* ACTUAL_WASM_TIMEZONE_MAP */

int check(int scenario)
{
    mode = scenario;
    opened = closes = allocations = frees = reads = cancellation_points = bad = 0;
    position = 0;
    for (size_t i = 0; i < sizeof storage; i++) storage[i] = 0;
    size_t length = 777;
    const unsigned char *mapped = __map_file("zone", &length);
    if (!scenario) {
        if (mapped != storage || length != 12 || reads != 5 || allocations != 1) return 10;
        for (int i = 0; i < 12; i++) if (mapped[i] != 0x40 + i) return 11;
        __unmap_file((const char *)mapped, length);
        if (frees != 1) return 12;
    } else {
        if (mapped || length != 777) return 13;
        if (scenario == 1 && allocations != 1) return 14;
        if ((scenario == 2 || scenario == 3 || scenario == 4 || scenario == 8) && allocations) return 15;
        if (scenario == 5 && allocations != (sizeof(size_t) == 8)) return 16;
        if ((scenario == 6 || scenario == 7) && frees != 1) return 17;
    }
    if (opened || closes != (scenario != 8)) return 20;
    if (cancellation_points || bad) return 21;
    return 0;
}
