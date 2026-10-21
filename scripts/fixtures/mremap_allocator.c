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
	assert(__wasm_mremap(original, PAGESIZE, 4 * PAGESIZE, 0) == -EOPNOTSUPP);
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
int main(void)
{
	for (int i = 0; i < 16; i++) { scenario(0); scenario(1); }
	assert(__wasm_mmap_initialized(PAGESIZE, initialize, (void *)1) == -EIO);
	assert(live_allocations == 0 && mappings == NULL);
	long file = __wasm_mmap_initialized(3 * PAGESIZE, initialize, NULL);
	assert(file > 0 && *(unsigned char *)file == 71);
	assert(__wasm_munmap(file + PAGESIZE, PAGESIZE) == 0);
	assert(__wasm_mremap(file + 2 * PAGESIZE, PAGESIZE, 2 * PAGESIZE, MREMAP_MAYMOVE) == -EOPNOTSUPP);
	assert(*(unsigned char *)(file + 2 * PAGESIZE) == 71);
	assert(__wasm_mremap(file, PAGESIZE, PAGESIZE, 0) == file);
	assert(__wasm_munmap(file, 3 * PAGESIZE) == 0);
	assert(live_allocations == 0 && mappings == NULL);
	puts("direct allocator: resize, relocation, zero tail, failure rollback, revalidation and initialized-source guard pass");
	return 0;
}
