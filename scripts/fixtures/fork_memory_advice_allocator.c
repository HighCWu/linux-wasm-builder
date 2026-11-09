/* SPDX-License-Identifier: MIT */
/* Included after the exact Wasm allocator source with host allocation hooks. */
struct mapping_view {
	uintptr_t address;
	size_t length;
	int initialized;
	int wipe_on_fork;
};

struct expected_mapping {
	size_t offset;
	size_t length;
	int wipe_on_fork;
};

static uintptr_t read_word(uintptr_t object, size_t offset)
{
	uintptr_t value;
	memcpy(&value, (const void *)(object + offset), sizeof(value));
	return value;
}

static int read_int(uintptr_t object, size_t offset)
{
	int value;
	memcpy(&value, (const void *)(object + offset), sizeof(value));
	return value;
}

static int compare_mappings(const void *left, const void *right)
{
	const struct mapping_view *a = left, *b = right;
	return (a->address > b->address) - (a->address < b->address);
}

static size_t collect_mappings(struct mapping_view *views, size_t capacity)
{
	const uintptr_t *descriptor = __wasm_fork_memory_advice_v1;
	uintptr_t record;
	size_t count = 0;

	assert(descriptor[0] == 1);
	assert(descriptor[1] == sizeof(struct wasm_mapping));
	assert(descriptor[2] == (uintptr_t)&mappings);
	assert(descriptor[3] == offsetof(struct wasm_mapping, next));
	assert(descriptor[4] == offsetof(struct wasm_mapping, address));
	assert(descriptor[5] == offsetof(struct wasm_mapping, length));
	assert(descriptor[6] == offsetof(struct wasm_mapping, initialized));
	assert(descriptor[7] == offsetof(struct wasm_mapping, wipe_on_fork));
	record = read_word(descriptor[2], 0);
	while (record) {
		assert(count < capacity);
		views[count++] = (struct mapping_view){
			.address = read_word(record, descriptor[4]),
			.length = read_word(record, descriptor[5]),
			.initialized = read_int(record, descriptor[6]),
			.wipe_on_fork = read_int(record, descriptor[7]),
		};
		record = read_word(record, descriptor[3]);
	}
	qsort(views, count, sizeof(*views), compare_mappings);
	return count;
}

static void expect_layout(uintptr_t base, const struct expected_mapping *expected,
	size_t expected_count)
{
	struct mapping_view actual[16];
	size_t count = collect_mappings(actual, sizeof(actual) / sizeof(actual[0]));

	assert(count == expected_count);
	for (size_t i = 0; i < count; i++) {
		assert(actual[i].address == base + expected[i].offset);
		assert(actual[i].length == expected[i].length);
		assert(actual[i].initialized == 0);
		assert(actual[i].wipe_on_fork == expected[i].wipe_on_fork);
	}
}

static void expect_record(uintptr_t address, size_t length, int wipe_on_fork)
{
	struct mapping_view actual[16];
	size_t count = collect_mappings(actual, sizeof(actual) / sizeof(actual[0]));

	for (size_t i = 0; i < count; i++) {
		if (actual[i].address == address) {
			assert(actual[i].length == length);
			assert(actual[i].initialized == 0);
			assert(actual[i].wipe_on_fork == wipe_on_fork);
			return;
		}
	}
	assert(0 && "mapping descriptor has no requested record");
}

static void expect_empty(void)
{
	struct mapping_view actual[16];
	assert(collect_mappings(actual, sizeof(actual) / sizeof(actual[0])) == 0);
	assert(live_allocations == 0);
}

static void split_wipe_and_keep(void)
{
	static const struct expected_mapping split[] = {
		{0, 2 * PAGESIZE, 1},
		{2 * PAGESIZE, PAGESIZE, 0},
		{3 * PAGESIZE, 2 * PAGESIZE, 1},
	};
	long base = __wasm_mmap(5 * PAGESIZE);
	assert(base > 0);
	memset((void *)base, 0x37, 5 * PAGESIZE);
	assert(__wasm_madvise((uintptr_t)base, 5 * PAGESIZE, MADV_WIPEONFORK) ==
		-EOPNOTSUPP);
	assert(__wasm_madvise_v2((uintptr_t)base, 5 * PAGESIZE,
		MADV_WIPEONFORK) == 0);
	assert(__wasm_madvise_v2((uintptr_t)base + 2 * PAGESIZE, PAGESIZE,
		MADV_KEEPONFORK) == 0);
	expect_layout((uintptr_t)base, split, sizeof(split) / sizeof(split[0]));
	assert(__wasm_madvise((uintptr_t)base, 5 * PAGESIZE, MADV_KEEPONFORK) ==
		-EOPNOTSUPP);
	expect_layout((uintptr_t)base, split, sizeof(split) / sizeof(split[0]));
	assert(((unsigned char *)base)[0] == 0x37);
	assert(((unsigned char *)base)[2 * PAGESIZE] == 0x37);
	assert(((unsigned char *)base)[4 * PAGESIZE] == 0x37);

	/* Both boundary records are needed. Fail after allocating the first one. */
	fail_after = 1;
	assert(__wasm_madvise_v2((uintptr_t)base + PAGESIZE, 3 * PAGESIZE,
		MADV_KEEPONFORK) == -ENOMEM);
	fail_after = -1;
	expect_layout((uintptr_t)base, split, sizeof(split) / sizeof(split[0]));
	assert(__wasm_munmap((uintptr_t)base, 5 * PAGESIZE) == 0);
	expect_empty();
}

static void munmap_split_and_failed_range(void)
{
	static const struct expected_mapping before_refill[] = {
		{0, 2 * PAGESIZE, 1},
		{3 * PAGESIZE, 2 * PAGESIZE, 1},
	};
	static const struct expected_mapping after_refill[] = {
		{0, 2 * PAGESIZE, 1},
		{2 * PAGESIZE, PAGESIZE, 0},
		{3 * PAGESIZE, 2 * PAGESIZE, 1},
	};
	const int fixed_flags = MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE;
	long base = __wasm_mmap(5 * PAGESIZE);
	assert(base > 0);
	assert(__wasm_madvise_v2((uintptr_t)base, 5 * PAGESIZE,
		MADV_WIPEONFORK) == 0);
	assert(__wasm_munmap((uintptr_t)base + 2 * PAGESIZE, PAGESIZE) == 0);
	expect_layout((uintptr_t)base, before_refill,
		sizeof(before_refill) / sizeof(before_refill[0]));
	assert(__wasm_madvise_v2((uintptr_t)base, 5 * PAGESIZE,
		MADV_KEEPONFORK) == -ENOMEM);
	expect_layout((uintptr_t)base, before_refill,
		sizeof(before_refill) / sizeof(before_refill[0]));
	assert(__wasm_mmap_v2((uintptr_t)base + 2 * PAGESIZE, PAGESIZE,
		PROT_READ | PROT_WRITE, fixed_flags, -1, 0) == base + 2 * PAGESIZE);
	expect_layout((uintptr_t)base, after_refill,
		sizeof(after_refill) / sizeof(after_refill[0]));
	assert(__wasm_munmap((uintptr_t)base, 5 * PAGESIZE) == 0);
	expect_empty();
}

static void remap_inherits_wipe_flag(void)
{
	long base = __wasm_mmap(8 * PAGESIZE);
	assert(base > 0);
	memset((void *)base, 0x53, 8 * PAGESIZE);
	assert(__wasm_madvise_v2((uintptr_t)base, 8 * PAGESIZE,
		MADV_WIPEONFORK) == 0);
	assert(__wasm_mremap((uintptr_t)base + 2 * PAGESIZE, 2 * PAGESIZE,
		PAGESIZE, 0) == base + 2 * PAGESIZE);
	assert(collect_mappings((struct mapping_view[16]){0}, 16) == 2);
	expect_record((uintptr_t)base, 3 * PAGESIZE, 1);
	expect_record((uintptr_t)base + 4 * PAGESIZE, 4 * PAGESIZE, 1);

	long moved = __wasm_mremap((uintptr_t)base + 4 * PAGESIZE,
		4 * PAGESIZE, 9 * PAGESIZE, MREMAP_MAYMOVE);
	assert(moved > 0 && moved != base + 4 * PAGESIZE);
	assert(collect_mappings((struct mapping_view[16]){0}, 16) == 2);
	expect_record((uintptr_t)base, 3 * PAGESIZE, 1);
	expect_record((uintptr_t)moved, 9 * PAGESIZE, 1);
	assert(((unsigned char *)moved)[0] == 0x53);
	assert(((unsigned char *)moved)[4 * PAGESIZE] == 0);
	assert(__wasm_munmap((uintptr_t)base, 8 * PAGESIZE) == 0);
	assert(__wasm_munmap((uintptr_t)moved, 9 * PAGESIZE) == 0);
	expect_empty();
}

static void fixed_remap_inherits_wipe_flag(void)
{
	long source = __wasm_mmap(2 * PAGESIZE);
	long destination = __wasm_mmap(4 * PAGESIZE);
	assert(source > 0 && destination > 0 && source != destination);
	memset((void *)source, 0x61, 2 * PAGESIZE);
	memset((void *)destination, 0x77, 4 * PAGESIZE);
	assert(__wasm_madvise_v2((uintptr_t)source, 2 * PAGESIZE,
		MADV_WIPEONFORK) == 0);
	assert(__wasm_mremap_fixed((uintptr_t)source, 2 * PAGESIZE,
		4 * PAGESIZE, (uintptr_t)destination) == destination);
	assert(collect_mappings((struct mapping_view[16]){0}, 16) == 1);
	expect_record((uintptr_t)destination, 4 * PAGESIZE, 1);
	assert(((unsigned char *)destination)[0] == 0x61);
	assert(((unsigned char *)destination)[2 * PAGESIZE] == 0);
	assert(__wasm_munmap((uintptr_t)destination, 4 * PAGESIZE) == 0);
	expect_empty();
}

static void keep_coalesces_mapping_records(void)
{
	long base = __wasm_mmap(3 * PAGESIZE);
	assert(base > 0);
	assert(__wasm_madvise_v2((uintptr_t)base + PAGESIZE, PAGESIZE,
		MADV_KEEPONFORK) == 0);
	assert(collect_mappings((struct mapping_view[16]){0}, 16) == 1);
	expect_record((uintptr_t)base, 3 * PAGESIZE, 0);
	assert(__wasm_mremap((uintptr_t)base, 3 * PAGESIZE, 3 * PAGESIZE, 0) == base);

	assert(__wasm_madvise_v2((uintptr_t)base, 3 * PAGESIZE,
		MADV_WIPEONFORK) == 0);
	assert(__wasm_madvise_v2((uintptr_t)base + PAGESIZE, PAGESIZE,
		MADV_KEEPONFORK) == 0);
	static const struct expected_mapping split[] = {
		{0, PAGESIZE, 1},
		{PAGESIZE, PAGESIZE, 0},
		{2 * PAGESIZE, PAGESIZE, 1},
	};
	expect_layout((uintptr_t)base, split, sizeof(split) / sizeof(split[0]));
	assert(__wasm_madvise_v2((uintptr_t)base, 3 * PAGESIZE,
		MADV_KEEPONFORK) == 0);
	assert(collect_mappings((struct mapping_view[16]){0}, 16) == 1);
	expect_record((uintptr_t)base, 3 * PAGESIZE, 0);
	assert(__wasm_mremap((uintptr_t)base, 3 * PAGESIZE, 2 * PAGESIZE, 0) == base);
	expect_record((uintptr_t)base, 2 * PAGESIZE, 0);
	assert(__wasm_munmap((uintptr_t)base, 2 * PAGESIZE) == 0);
	expect_empty();
}

int main(void)
{
	split_wipe_and_keep();
	munmap_split_and_failed_range();
	remap_inherits_wipe_flag();
	fixed_remap_inherits_wipe_flag();
	keep_coalesces_mapping_records();
	puts("allocator fork advice: descriptor splits, atomic failure, unmap and remap inheritance pass");
	return 0;
}
