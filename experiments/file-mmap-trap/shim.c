/* SPDX-License-Identifier: MIT */
/* Control-flow model only, not Linux VFS/atomics or a user application. */
typedef __SIZE_TYPE__ size_t;
typedef __PTRDIFF_TYPE__ ssize_t;
typedef __UINT64_TYPE__ u64;
typedef __INT64_TYPE__ loff_t;
typedef unsigned char u8;
typedef _Bool bool;
typedef volatile int atomic_t;
#define true 1
#define false 0
#define NULL ((void *)0)
#define LLONG_MAX __LONG_LONG_MAX__
#define EINVAL 22
#define EINTR 4
#define ENOMEM 12
#define EIO 5
#define GFP_KERNEL 0
#define PAGE_SIZE 65536UL
#define PAGE_ALIGNED(n) (!((n) & (PAGE_SIZE - 1)))
#define ALIGN(n, a) (((n) + (a) - 1) & ~((a) - 1))
#define min_t(t, a, b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define ATOMIC_INIT(n) (n)
#define atomic_read(p) (*(p))
#define atomic_inc(p) (++*(p))
#define atomic_dec(p) (--*(p))
#define atomic_sub(n, p) (*(p) -= (n))
static bool atomic_try_cmpxchg(atomic_t *p, int *old, int value)
{
	if (*p != *old) { *old = *p; return false; }
	*p = value;
	return true;
}
struct super_block { void *s_bdev; };
struct inode { struct super_block *i_sb; };
struct file { struct inode *inode; };
static struct inode *file_inode(struct file *file) { return file->inode; }
static bool erofs_is_single_bdev(struct super_block *sb) { (void)sb; return false; }
static bool wasm_bdev_has_snapshot_source(void *device) { (void)device; return false; }
struct wasm_mmap_callback;
struct thread_info { struct wasm_mmap_callback *mmap_callbacks; };
struct task_struct { struct thread_info info; };
static struct task_struct task;
#define current (&task)
#define task_thread_info(t) (&(t)->info)
static bool fatal_signal_pending(void *task) { (void)task; return false; }
static u8 buffer[2 * PAGE_SIZE];
static union { __UINT64_TYPE__ align; u8 bytes[256]; } control;
static volatile int allocated;
static volatile int control_allocated;
static int pins;
static void fput(struct file *file) { (void)file; if (pins != 1) __builtin_trap(); pins--; }
static void *kmalloc(size_t length, int flags)
{
	(void)flags;
	if (length <= sizeof control) {
		if (control_allocated) return NULL;
		control_allocated = 1;
		return &control;
	}
	if (allocated || length > sizeof buffer) return NULL;
	allocated = 1;
	return buffer;
}
static void kfree(void *value)
{
	if (value == &control) {
		if (!control_allocated) __builtin_trap();
		control_allocated = 0;
		return;
	}
	if (value != buffer || !allocated) __builtin_trap();
	allocated = 0;
}
static ssize_t kernel_read(struct file *file, void *target, size_t length, loff_t *position)
{
	(void)file;
	for (size_t i = 0; i < length; i++) ((u8 *)target)[i] = (u8)i;
	*position += length;
	return length;
}
__attribute__((import_module("bridge"), import_name("map")))
extern long wasm_user_mmap_init_v1_map(unsigned long, const void *, unsigned long);

/* The runner inserts the actual GPL kernel function body here, unchanged. */

long run(void)
{
	struct file file = {0};
	pins++;
	return wasm_mmap_copy_file(&file, PAGE_SIZE, 0, PAGE_SIZE);
}
long resource(unsigned int selector)
{
	if (selector == 2) return allocated + control_allocated;
	if (selector == 4) return pins;
	return wasm_mmap_copy_stat(selector);
}
void exit_cleanup(void) { wasm_mmap_copy_abort_task(current); }
