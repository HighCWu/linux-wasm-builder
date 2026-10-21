/* SPDX-License-Identifier: MIT */
/* Included after the exact Wasm allocator source, with host malloc hooks.
 * Host correctness/sanitizer evidence only, not a Linux syscall acceptance. */
static int initialize(void *target, size_t length, void *argument)
{
	memset(target, 71, length);
	return argument ? -EIO : 0;
}
static uintptr_t invalidated;
static void invalidate_source(void)
{
	assert(__wasm_munmap(invalidated, 2 * PAGESIZE) == 0);
}
static void scenario(int race)
{
	long original = __wasm_mmap(2 * PAGESIZE);
	assert(original > 0);
	unsigned char *bytes = (void *)original;
	memset(bytes, 37, 2 * PAGESIZE);
	assert(__wasm_mremap(original, 2 * PAGESIZE, PAGESIZE, 0) == original);
	assert(__wasm_mremap(original, PAGESIZE, 2 * PAGESIZE, 0) == original);
	assert(bytes[0] == 37 && bytes[PAGESIZE - 1] == 37);
	for (size_t i = PAGESIZE; i < 2 * PAGESIZE; i++) assert(bytes[i] == 0);
	long neighbor = __wasm_mmap_v2(original + 2 * PAGESIZE, 2 * PAGESIZE,
		3, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
	assert(neighbor == original + 2 * PAGESIZE);
	memset((void *)neighbor, 91, 2 * PAGESIZE);
	assert(__wasm_mremap(original, 2 * PAGESIZE, 4 * PAGESIZE, 0) == -ENOMEM);
	assert(__wasm_mremap(original, PAGESIZE, 4 * PAGESIZE, 0) == -ENOMEM);
	assert(__wasm_mremap(original, 3 * PAGESIZE, 4 * PAGESIZE, 0) == -EFAULT);
	assert(__wasm_mremap(original + 1, 2 * PAGESIZE, PAGESIZE, 0) == -EINVAL);
	assert(__wasm_mremap(original, 0, PAGESIZE, 0) == -EINVAL);
	assert(__wasm_mremap(original, 2 * PAGESIZE, 0, 0) == -EINVAL);
	assert(__wasm_mremap(original, 2 * PAGESIZE, PAGESIZE, 8) == -EINVAL);
	assert(__wasm_mremap(original, 2 * PAGESIZE, PAGESIZE, MREMAP_FIXED) == -EINVAL);
	assert(__wasm_mremap(original, 2 * PAGESIZE, PAGESIZE, 3) == -EOPNOTSUPP);
	for (int after = 0; after < 2; after++) {
		fail_after = after;
		assert(__wasm_mremap(original, 2 * PAGESIZE, 4 * PAGESIZE, MREMAP_MAYMOVE) == -ENOMEM);
		fail_after = -1;
		assert(bytes[0] == 37 && bytes[PAGESIZE] == 0 && *(unsigned char *)neighbor == 91);
	}
	if (race) {
		invalidated = original;
		allocation_hook = invalidate_source;
		assert(__wasm_mremap(original, 2 * PAGESIZE, 4 * PAGESIZE, MREMAP_MAYMOVE) == -EFAULT);
	} else {
		long moved = __wasm_mremap(original, 2 * PAGESIZE, 4 * PAGESIZE, MREMAP_MAYMOVE);
		assert(moved > 0 && moved != original);
		unsigned char *copy = (void *)moved;
		for (size_t i = 0; i < PAGESIZE; i++) assert(copy[i] == 37);
		for (size_t i = PAGESIZE; i < 4 * PAGESIZE; i++) assert(copy[i] == 0);
		assert(__wasm_mremap(original, 2 * PAGESIZE, 4 * PAGESIZE, 0) == -EFAULT);
		assert(__wasm_munmap(moved, 4 * PAGESIZE) == 0);
	}
	assert(*(unsigned char *)neighbor == 91);
	assert(__wasm_munmap(neighbor, 2 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
}
static void partial_move(int mode)
{
	long original = __wasm_mmap(6 * PAGESIZE);
	assert(original > 0);
	unsigned char *base = (void *)original;
	for (size_t i = 0; i < 6; i++) memset(base + i * PAGESIZE, 11 + i, PAGESIZE);
	size_t start = (size_t)mode * 2;
	long source = original + start * PAGESIZE;
	long neighbor = 0;
	if (mode == 2) {
		neighbor = __wasm_mmap_v2(original + 6 * PAGESIZE, 2 * PAGESIZE,
			3, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
		assert(neighbor == original + 6 * PAGESIZE);
		memset((void *)neighbor, 91, 2 * PAGESIZE);
	}
	assert(__wasm_mremap(source, 2 * PAGESIZE, 2 * PAGESIZE, 0) == source);
	assert(__wasm_mremap(source, 2 * PAGESIZE, 3 * PAGESIZE, 0) == -ENOMEM);
	for (int after = 0; after < (mode == 1 ? 3 : 2); after++) {
		fail_after = after;
		assert(__wasm_mremap(source, 2 * PAGESIZE, 3 * PAGESIZE, 1) == -ENOMEM);
		fail_after = -1;
		for (size_t i = 0; i < 6; i++) assert(base[i * PAGESIZE] == 11 + i);
		assert(live_allocations == (neighbor ? 3 : 2));
	}
	long moved = __wasm_mremap(source, 2 * PAGESIZE, 3 * PAGESIZE, 1);
	assert(moved > 0 && moved != source);
	unsigned char *copy = (void *)moved;
	for (size_t i = 0; i < 3 * PAGESIZE; i++)
		assert(copy[i] == (i < 2 * PAGESIZE ? 11 + start + i / PAGESIZE : 0));
	for (size_t i = 0; i < 6; i++)
		if (i < start || i >= start + 2) {
			assert(base[i * PAGESIZE] == 11 + i);
			assert(__wasm_mmap_v2(original + i * PAGESIZE, PAGESIZE, 3,
				MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == -EEXIST);
		}
	assert(__wasm_mremap(source, 2 * PAGESIZE, 3 * PAGESIZE, 0) == -EFAULT);
	assert(__wasm_mmap_v2(source, 2 * PAGESIZE, 3,
		MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == source);
	assert(*(unsigned char *)source == 0);
	assert(__wasm_munmap(moved, 3 * PAGESIZE) == 0);
	assert(__wasm_munmap(original, (neighbor ? 8 : 6) * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
}

static void partial_shrink(void)
{
	long original = __wasm_mmap(6 * PAGESIZE);
	assert(original > 0);
	unsigned char *base = (void *)original;
	for (size_t i = 0; i < 6; i++) memset(base + i * PAGESIZE, 21 + i, PAGESIZE);
	fail_after = 0;
	assert(__wasm_mremap(original + PAGESIZE, 2 * PAGESIZE, PAGESIZE, 0) == -ENOMEM);
	fail_after = -1;
	assert(live_allocations == 2 && mappings->length == 6 * PAGESIZE);
	assert(__wasm_mremap(original + PAGESIZE, 2 * PAGESIZE, PAGESIZE, 0) == original + PAGESIZE);
	assert(__wasm_mmap_v2(original + 2 * PAGESIZE, PAGESIZE, 3,
		MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == original + 2 * PAGESIZE);
	for (size_t i = 0; i < 6; i++) assert(base[i * PAGESIZE] == (i == 2 ? 0 : 21 + i));
	assert(__wasm_mremap(original + 4 * PAGESIZE, 2 * PAGESIZE, PAGESIZE, 0) == original + 4 * PAGESIZE);
	assert(__wasm_munmap(original, 6 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
	original = __wasm_mmap(6 * PAGESIZE);
	assert(original > 0);
	invalidated = original + PAGESIZE;
	allocation_hook = invalidate_source;
	assert(__wasm_mremap(invalidated, 2 * PAGESIZE, PAGESIZE, 0) == -EFAULT);
	assert(__wasm_munmap(original, 6 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
}

static void partial_grow(void)
{
	long original = __wasm_mmap(4 * PAGESIZE);
	assert(original > 0);
	unsigned char *base = (void *)original;
	memset(base, 33, 4 * PAGESIZE);
	assert(__wasm_mremap(original + 2 * PAGESIZE, 2 * PAGESIZE, 3 * PAGESIZE, 0)
		== original + 2 * PAGESIZE);
	for (size_t i = 0; i < 5 * PAGESIZE; i++) assert(base[i] == (i < 4 * PAGESIZE ? 33 : 0));
	assert(__wasm_mremap(original, 5 * PAGESIZE, 5 * PAGESIZE, 0) == original);
	assert(__wasm_munmap(original, 5 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
}

static void private_sync(void)
{
	long original = __wasm_mmap(3 * PAGESIZE);
	assert(original > 0);
	memset((void *)original, 67, 3 * PAGESIZE);
	const int flags[] = {0, MS_SYNC, MS_ASYNC, MS_INVALIDATE,
		MS_SYNC | MS_INVALIDATE, MS_ASYNC | MS_INVALIDATE};
	for (unsigned i = 0; i < sizeof flags / sizeof flags[0]; i++)
		assert(__wasm_msync(original, 3 * PAGESIZE, flags[i]) == 0);
	assert(__wasm_msync(0, 0, MS_SYNC) == 0);
	assert(__wasm_msync(0, PAGESIZE, MS_SYNC) == -ENOMEM);
	assert(__wasm_msync(original + 1, 0, MS_SYNC) == -EINVAL);
	assert(__wasm_msync(original, PAGESIZE, MS_SYNC | MS_ASYNC) == -EINVAL);
	assert(__wasm_msync(original, PAGESIZE, 8) == -EINVAL);
	assert(__wasm_msync((uintptr_t)-PAGESIZE, 2 * PAGESIZE, 0) == -ENOMEM);
	assert(__wasm_munmap(original + PAGESIZE, PAGESIZE) == 0);
	assert(__wasm_msync(original, 3 * PAGESIZE, MS_SYNC) == -ENOMEM);
	assert(__wasm_msync(original, PAGESIZE, MS_SYNC) == 0);
	assert(__wasm_msync(original + 2 * PAGESIZE, PAGESIZE, MS_SYNC) == 0);
	assert(__wasm_mmap_v2(original + PAGESIZE, PAGESIZE, 3,
		MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == original + PAGESIZE);
	fail_after = 0; /* Validation does not allocate or require a producer. */
	assert(__wasm_msync(original, 3 * PAGESIZE, MS_SYNC) == 0);
	fail_after = -1;
	assert(*(unsigned char *)original == 67 && *(unsigned char *)(original + PAGESIZE) == 0);
	assert(__wasm_munmap(original, 3 * PAGESIZE) == 0);
	assert(__wasm_msync(original, PAGESIZE, MS_SYNC) == -ENOMEM);
	long private_copy = __wasm_mmap_initialized(PAGESIZE, initialize, NULL);
	assert(private_copy > 0 && __wasm_msync(private_copy, PAGESIZE, MS_SYNC) == 0);
	assert(*(unsigned char *)private_copy == 71);
	assert(__wasm_munmap(private_copy, PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
}

static void discard_pages(void)
{
	long original = __wasm_mmap(3 * PAGESIZE);
	assert(original > 0);
	unsigned char *bytes = (void *)original;
	memset(bytes, 71, 3 * PAGESIZE);
	for (int advice = MADV_NORMAL; advice <= MADV_WILLNEED; advice++)
		assert(__wasm_madvise(original, 3 * PAGESIZE, advice) == 0);
	for (size_t i = 0; i < 3 * PAGESIZE; i++) assert(bytes[i] == 71);
	assert(__wasm_madvise(original + PAGESIZE, PAGESIZE, MADV_DONTNEED) == 0);
	for (size_t i = 0; i < 3 * PAGESIZE; i++)
		assert(bytes[i] == (i >= PAGESIZE && i < 2 * PAGESIZE ? 0 : 71));
	assert(__wasm_mmap_v2(original + PAGESIZE, PAGESIZE, 3,
		MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == -EEXIST);
	assert(__wasm_madvise(0, 0, MADV_DONTNEED) == 0);
	assert(__wasm_madvise(original + 1, 0, MADV_NORMAL) == -EINVAL);
	assert(__wasm_madvise(original, PAGESIZE, -1) == -EINVAL);
	assert(__wasm_madvise(original, PAGESIZE, MADV_FREE) == -EINVAL);
	assert(__wasm_madvise((uintptr_t)-PAGESIZE, 2 * PAGESIZE, MADV_DONTNEED) == -EINVAL);
	assert(__wasm_munmap(original + PAGESIZE, PAGESIZE) == 0);
	assert(__wasm_madvise(original, 3 * PAGESIZE, MADV_DONTNEED) == -ENOMEM);
	assert(bytes[0] == 71 && bytes[2 * PAGESIZE] == 71);
	assert(__wasm_mmap_v2(original + PAGESIZE, PAGESIZE, 3,
		MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == original + PAGESIZE);
	memset(bytes, 19, 3 * PAGESIZE);
	fail_after = 0;
	assert(__wasm_madvise(original, 3 * PAGESIZE, MADV_DONTNEED) == 0);
	fail_after = -1;
	for (size_t i = 0; i < 3 * PAGESIZE; i++) assert(bytes[i] == 0);
	assert(__wasm_munmap(original, 3 * PAGESIZE) == 0);
	assert(__wasm_madvise(original, PAGESIZE, MADV_DONTNEED) == -ENOMEM);
	long file = __wasm_mmap_initialized(3 * PAGESIZE, initialize, NULL);
	assert(file > 0 && __wasm_madvise(file, PAGESIZE, MADV_NORMAL) == 0);
	assert(__wasm_madvise(file, PAGESIZE, MADV_DONTNEED) == -EOPNOTSUPP);
	assert(__wasm_mremap(file, 3 * PAGESIZE, 2 * PAGESIZE, 0) == file);
	assert(__wasm_madvise(file + PAGESIZE, PAGESIZE, MADV_DONTNEED) == -EOPNOTSUPP);
	assert(*(unsigned char *)file == 71);
	assert(__wasm_munmap(file, PAGESIZE) == 0);
	assert(__wasm_mmap_v2(file, PAGESIZE, 3,
		MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == file);
	memset((void *)file, 33, PAGESIZE);
	assert(__wasm_madvise(file, 2 * PAGESIZE, MADV_DONTNEED) == -EOPNOTSUPP);
	assert(*(unsigned char *)file == 33 && *(unsigned char *)(file + PAGESIZE) == 71);
	assert(__wasm_munmap(file, 2 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
}

static void fixed_mapping(void)
{
	const int flags = MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE;
	for (int failure = 0; failure < 2; failure++) {
		long base = __wasm_mmap(6 * PAGESIZE);
		assert(base > 0);
		memset((void *)base, 71, 6 * PAGESIZE);
		fail_after = failure;
		assert(__wasm_mmap_fixed(base + 2 * PAGESIZE, PAGESIZE) == -ENOMEM);
		fail_after = -1;
		assert(__wasm_mmap_v2(base, 6 * PAGESIZE, 3, flags, -1, 0) == -EEXIST);
		for (size_t i = 0; i < 6 * PAGESIZE; i++) assert(((unsigned char *)base)[i] == 71);
		assert(__wasm_munmap(base, 6 * PAGESIZE) == 0);
	}
	long base = __wasm_mmap(6 * PAGESIZE);
	assert(base > 0);
	unsigned char *bytes = (void *)base;
	memset(bytes, 71, 6 * PAGESIZE);
	assert(__wasm_mmap_fixed(base + 2 * PAGESIZE, PAGESIZE) == base + 2 * PAGESIZE);
	for (size_t i = 0; i < 6 * PAGESIZE; i++)
		assert(bytes[i] == (i >= 2 * PAGESIZE && i < 3 * PAGESIZE ? 0 : 71));
	assert(__wasm_mmap_fixed(base + PAGESIZE, 4 * PAGESIZE) == base + PAGESIZE);
	assert(bytes[0] == 71 && bytes[5 * PAGESIZE] == 71);
	for (size_t i = PAGESIZE; i < 5 * PAGESIZE; i++) assert(bytes[i] == 0);
	assert(__wasm_mmap_fixed(base, 6 * PAGESIZE) == base);
	for (size_t i = 0; i < 6 * PAGESIZE; i++) assert(bytes[i] == 0);
	assert(__wasm_mmap_fixed(base + 6 * PAGESIZE, PAGESIZE) == base + 6 * PAGESIZE);
	assert(bytes[6 * PAGESIZE] == 0);
	assert(__wasm_munmap(base + 6 * PAGESIZE, PAGESIZE) == 0);
	assert(__wasm_madvise(base, 6 * PAGESIZE, MADV_NORMAL) == 0);
	assert(__wasm_mmap_fixed(base + 1, PAGESIZE) == -EINVAL);
	assert(__wasm_mmap_fixed(base, 9 * PAGESIZE) == -ENOMEM);
	assert(__wasm_mmap_fixed((uintptr_t)&base & -(uintptr_t)PAGESIZE, PAGESIZE) == -ENOMEM);
	assert(__wasm_munmap(base, 6 * PAGESIZE) == 0);
	invalidated = __wasm_mmap(2 * PAGESIZE);
	assert(invalidated > 0);
	allocation_hook = invalidate_source;
	assert(__wasm_mmap_fixed(invalidated, PAGESIZE) == -ENOMEM);
	assert(live_allocations == 0 && mappings == NULL);
	long file = __wasm_mmap_initialized(3 * PAGESIZE, initialize, NULL);
	assert(file > 0 && __wasm_mmap_fixed(file + PAGESIZE, PAGESIZE) == file + PAGESIZE);
	assert(__wasm_madvise(file + PAGESIZE, PAGESIZE, MADV_DONTNEED) == 0);
	assert(__wasm_madvise(file, PAGESIZE, MADV_DONTNEED) == -EOPNOTSUPP);
	assert(__wasm_madvise(file + 2 * PAGESIZE, PAGESIZE, MADV_DONTNEED) == -EOPNOTSUPP);
	assert(*(unsigned char *)file == 71 && *(unsigned char *)(file + 2 * PAGESIZE) == 71);
	assert(__wasm_munmap(file, 3 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
}

static void fixed_remap(void)
{
	for (int failure = 0; failure < 3; failure++) {
		long base = __wasm_mmap(8 * PAGESIZE);
		assert(base > 0);
		memset((void *)base, 71, 8 * PAGESIZE);
		fail_after = failure;
		assert(__wasm_mremap_fixed(base + PAGESIZE, 2 * PAGESIZE,
			3 * PAGESIZE, base + 5 * PAGESIZE) == -ENOMEM);
		fail_after = -1;
		for (size_t i = 0; i < 8 * PAGESIZE; i++) assert(((unsigned char *)base)[i] == 71);
		assert(__wasm_msync(base, 8 * PAGESIZE, MS_SYNC) == 0);
		assert(__wasm_munmap(base, 8 * PAGESIZE) == 0);
		assert(live_allocations == 0);
	}
	long base = __wasm_mmap(8 * PAGESIZE);
	assert(base > 0);
	unsigned char *bytes = (void *)base;
	for (size_t i = 0; i < 8; i++) memset(bytes + i * PAGESIZE, 10 + i, PAGESIZE);
	assert(__wasm_mremap_fixed(base + PAGESIZE, 2 * PAGESIZE,
		3 * PAGESIZE, base + 5 * PAGESIZE) == base + 5 * PAGESIZE);
	for (size_t i = 0; i < 3 * PAGESIZE; i++)
		assert(bytes[5 * PAGESIZE + i] == (i < 2 * PAGESIZE ? 11 + i / PAGESIZE : 0));
	assert(bytes[0] == 10 && bytes[3 * PAGESIZE] == 13 && bytes[4 * PAGESIZE] == 14);
	assert(__wasm_msync(base + PAGESIZE, 2 * PAGESIZE, MS_SYNC) == -ENOMEM);
	assert(__wasm_mmap_v2(base + PAGESIZE, 2 * PAGESIZE, 3,
		MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == base + PAGESIZE);
	assert(__wasm_mremap_fixed(base + 5 * PAGESIZE, 3 * PAGESIZE,
		PAGESIZE, base + 3 * PAGESIZE) == base + 3 * PAGESIZE);
	assert(bytes[3 * PAGESIZE] == 11 && bytes[4 * PAGESIZE] == 14 && bytes[0] == 10);
	assert(__wasm_msync(base + 5 * PAGESIZE, PAGESIZE, MS_SYNC) == -ENOMEM);
	assert(__wasm_mremap_fixed(base + 3 * PAGESIZE, PAGESIZE, PAGESIZE,
		base + 3 * PAGESIZE) == -EINVAL);
	assert(__wasm_mremap_fixed(base + 5 * PAGESIZE, PAGESIZE, PAGESIZE, base) == -EFAULT);
	assert(__wasm_mremap_fixed(base, PAGESIZE, PAGESIZE,
		(uintptr_t)&base & -(uintptr_t)PAGESIZE) == -ENOMEM);
	assert(bytes[0] == 10 && bytes[3 * PAGESIZE] == 11);
	assert(__wasm_munmap(base, 8 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
	/* Both source and target lie strictly inside one original record. The
	 * destination split creates the record subsequently split by source removal. */
	base = __wasm_mmap(8 * PAGESIZE);
	assert(base > 0);
	bytes = (void *)base;
	for (size_t i = 0; i < 8; i++) memset(bytes + i * PAGESIZE, 10 + i, PAGESIZE);
	assert(__wasm_mremap_fixed(base + 5 * PAGESIZE, 2 * PAGESIZE,
		2 * PAGESIZE, base + PAGESIZE) == base + PAGESIZE);
	assert(bytes[PAGESIZE] == 15 && bytes[2 * PAGESIZE] == 16);
	assert(bytes[0] == 10 && bytes[3 * PAGESIZE] == 13 && bytes[7 * PAGESIZE] == 17);
	assert(__wasm_msync(base + 5 * PAGESIZE, 2 * PAGESIZE, MS_SYNC) == -ENOMEM);
	assert(__wasm_munmap(base, 8 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
	long source = __wasm_mmap(10 * PAGESIZE), destination = __wasm_mmap(12 * PAGESIZE);
	assert(source > 0 && destination > 0);
	memset((void *)source, 37, 10 * PAGESIZE);
	memset((void *)destination, 91, 12 * PAGESIZE);
	assert(__wasm_mremap_fixed(source, 10 * PAGESIZE, 12 * PAGESIZE, destination) == destination);
	for (size_t i = 0; i < 12 * PAGESIZE; i++)
		assert(((unsigned char *)destination)[i] == (i < 10 * PAGESIZE ? 37 : 0));
	assert(__wasm_msync(source, PAGESIZE, MS_SYNC) == -ENOMEM);
	assert(__wasm_munmap(destination, 12 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
	for (int lose_source = 0; lose_source < 2; lose_source++) {
		source = __wasm_mmap(10 * PAGESIZE);
		destination = __wasm_mmap(2 * PAGESIZE);
		assert(source > 0 && destination > 0);
		memset((void *)source, 37, 10 * PAGESIZE);
		memset((void *)destination, 91, 2 * PAGESIZE);
		/* The source subrange may be removed while the remaining eight pages stay live. */
		invalidated = lose_source ? source : destination;
		allocation_hook = invalidate_source;
		assert(__wasm_mremap_fixed(source, 2 * PAGESIZE, 2 * PAGESIZE, destination)
			== (lose_source ? -EFAULT : -ENOMEM));
		if (lose_source) assert(*(unsigned char *)destination == 91);
		else assert(*(unsigned char *)source == 37);
		assert(__wasm_munmap(source, 10 * PAGESIZE) == 0);
		assert(__wasm_munmap(destination, 2 * PAGESIZE) == 0);
		assert(live_allocations == 0 && mappings == NULL);
	}
	source = __wasm_mmap_initialized(3 * PAGESIZE, initialize, NULL);
	destination = __wasm_mmap(4 * PAGESIZE);
	assert(source > 0 && destination > 0);
	memset((void *)destination, 91, 4 * PAGESIZE);
	assert(__wasm_mremap_fixed(source, 3 * PAGESIZE, 4 * PAGESIZE, destination) == -EOPNOTSUPP);
	assert(*(unsigned char *)source == 71 && *(unsigned char *)destination == 91);
	assert(__wasm_mremap_fixed(source, 3 * PAGESIZE, 2 * PAGESIZE, destination) == destination);
	assert(*(unsigned char *)destination == 71 && *(unsigned char *)(destination + 2 * PAGESIZE) == 91);
	assert(__wasm_madvise(destination, PAGESIZE, MADV_DONTNEED) == -EOPNOTSUPP);
	assert(__wasm_munmap(destination, 4 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
}

int main(void)
{
	for (int i = 0; i < 16; i++) { scenario(0); scenario(1); }
	for (int i = 0; i < 3; i++) partial_move(i);
	partial_shrink();
	partial_grow();
	private_sync();
	discard_pages();
	fixed_mapping();
	fixed_remap();
	assert(__wasm_mmap_initialized(PAGESIZE, initialize, (void *)1) == -EIO);
	assert(live_allocations == 0 && mappings == NULL);
	long file = __wasm_mmap_initialized(3 * PAGESIZE, initialize, NULL);
	assert(file > 0 && *(unsigned char *)file == 71);
	assert(__wasm_mremap(file, 2 * PAGESIZE, PAGESIZE, 0) == file);
	assert(__wasm_mremap(file + 2 * PAGESIZE, PAGESIZE, 2 * PAGESIZE, MREMAP_MAYMOVE) == -EOPNOTSUPP);
	assert(*(unsigned char *)(file + 2 * PAGESIZE) == 71);
	assert(__wasm_mremap(file, PAGESIZE, PAGESIZE, 0) == file);
	assert(__wasm_munmap(file, 3 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
	puts("direct allocator: resize, relocation, zero tail, failure rollback, revalidation and initialized-source guard pass");
	return 0;
}
