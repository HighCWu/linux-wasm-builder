/* SPDX-License-Identifier: MIT */
/* Fault model around the actual helper, not VFS or allocator acceptance. */
typedef __SIZE_TYPE__ size_t;
typedef __UINTMAX_TYPE__ uintmax_t;
struct stat { __INT64_TYPE__ st_size; };
#define SIZE_MAX __SIZE_MAX__
#define O_RDONLY 0
#define O_CLOEXEC 0x80000
#define O_NONBLOCK 0x800
#define EINTR 4
#define SYS_close 57
#define PROT_READ 1
#define MAP_PRIVATE 2
#define MAP_SHARED 1
#define MAP_FAILED ((void *)-1)
static int errno;
static unsigned char storage[32];
static int mode, opened, closes, maps, unmaps, cancellation_points, bad;

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
static void *__mmap(void *address, size_t length, int prot, int flags, int fd, long offset)
{
    maps++;
    if (address || prot != PROT_READ || flags != MAP_PRIVATE || fd != 17 || !opened || offset) {
        bad++; errno = 95; return MAP_FAILED;
    }
    if (mode == 1 || length > sizeof storage) { errno = 12; return MAP_FAILED; }
    if (mode == 6 || mode == 7) { errno = 5; return MAP_FAILED; }
    if (maps == 1) { errno = EINTR; return MAP_FAILED; }
    for (size_t i = 0; i < length; i++) storage[i] = 0x40 + i;
    return storage;
}
static int __munmap(void *address, size_t length)
{
    if (address != storage || length != 12 || unmaps) bad++;
    unmaps++;
    return 0;
}
static long __syscall(long nr, int fd)
{
    if (nr != SYS_close || fd != 17 || !opened) { bad++; return -9; }
    closes++; opened = 0; return 0;
}
__attribute__((unused)) static int close(int fd)
{
    cancellation_points++;
    return __syscall(SYS_close, fd);
}

/* ACTUAL_WASM_TIMEZONE_MAP */

int check(int scenario)
{
    mode = scenario;
    opened = closes = maps = unmaps = cancellation_points = bad = errno = 0;
    size_t length = 777;
    const unsigned char *mapped = __map_file("zone", &length);
    if (!scenario) {
        if (mapped != storage || length != 12 || maps != 2) return 10;
        for (int i = 0; i < 12; i++) if (mapped[i] != 0x40 + i) return 11;
        __unmap_file((const char *)mapped, length);
        if (unmaps != 1) return 12;
    } else {
        if (mapped || length != 777 || unmaps) return 13;
        if ((scenario == 2 || scenario == 3 || scenario == 4 || scenario == 8) && maps) return 14;
        if (scenario == 5 && maps != (sizeof(size_t) == 8)) return 15;
        if ((scenario == 1 || scenario == 6 || scenario == 7) && maps != 1) return 16;
    }
    if (opened || closes != (scenario != 8)) return 20;
    if (cancellation_points || bad) return 21;
    return 0;
}
