<!-- SPDX-License-Identifier: MIT -->

# 内存兼容里程碑：Wasm Linux softmmu2 psABI 草案

状态：**设计草案，尚未冻结**。

本文件描述 Linux/Wasm 平台路线中的一个专项里程碑。softmmu2 用于解决 direct
linear memory 难以表达的固定高地址、稀疏映射、alias和严格失效语义；它不是项目
的核心目标，也不是内核、工具链、发行版或宿主其他工作的前置条件。

## 1. 设计原则

1. `CONFIG_MMU=n`。
2. softmmu2 默认启用，但 stable-direct 访问应可完全消除其运行时开销。
3. direct/managed 是 mapping 属性，不是由地址数值永久决定的 C 类型。
4. LLVM 的静态分类只是一种保守优化；unknown pointer 必须保留正确的动态路径。
5. Linux UAPI 保持标准接口；本规范定义额外的 Wasm 执行 ABI，而不是新的应用编程
   模型。
6. fast path 所依赖的数据格式必须版本化。

## 2. 地址结构

softmmu2 名称来自两级稀疏结构：

```text
48-bit guest virtual address
  ├─ level 1: bits 47:32 select a 4 GiB chunk
  └─ level 2: bits 31:PAGE_SHIFT select a page in the chunk
```

wasm32 只有 chunk 0，可退化成一级平坦表；wasm64 按需分配高位 chunk。ABI 不
保证内部永远恰好两级，程序必须通过 ABI version/feature 协商，而不能自行假定内核
私有结构。

页大小尚待基准验证。Box64 原型使用 4 KiB guest page；Linux/Wasm 原生程序可能
从 64 KiB Wasm page 获得更小的表和更简单 backing。冻结前必须以真实工作负载比较。

## 3. 模块 requirement

链接器应生成 `linux.softmmu` custom section。建议的逻辑字段为：

```c
struct wasm_softmmu_requirement_v1 {
    uint32_t abi_version;
    uint16_t pointer_width;
    uint16_t page_shift;
    uint32_t tlb_format;
    uint32_t required_features;
};
```

精确二进制编码、字节序和扩展规则待实现前冻结。loader 必须在实例化前拒绝不兼容
模块，不能让错误布局在运行时产生静默内存破坏。

## 4. 运行时控制信息

TLB/control block 的地址在一次用户 Wasm 实例生命周期内保持不变；表内容允许由
mapping 操作更新。

候选控制面：

```c
struct wasm_softmmu_control_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    uint32_t page_shift;
    uint32_t flags;

    uintptr_t identity_limit;
    uintptr_t tlb_base;
    uint32_t tlb_mask;
    uint32_t tlb_entry_shift;

    uint64_t mapping_generation;
};
```

候选交付方式：

- loader 提供 immutable imported globals，供 hot path 直接使用；
- auxv 提供 control block 指针，供 musl、调试器和兼容代码发现；
- 不允许每条访存遍历 auxv 或执行 syscall。

最终版本可以只选择其中一部分，但必须同时支持浏览器 Worker 和 Node。

## 5. Pointer domain 契约

### Stable-direct 契约

一旦 LLVM 基于 ABI 把访问降成裸 Wasm load/store，该对象在整个有效生命周期内：

- 必须保持 identity backing；
- 不得被 `MAP_FIXED` 覆盖；
- 不得被转换为 managed；
- 不得通过 `mprotect` 请求无法由 direct 域执行的严格权限。

初始候选包括 stack、globals、TLS 和专用 direct allocator。标准 `mmap()` 返回值默认
不是 stable direct。

### Dynamic mapping 契约

即使某页当前 identity mapped，只要未来可能 `munmap`、alias 或重映射，其访问仍需
经过动态 pagebase/TLB。identity 只是 `host_base == guest_page_base`，不是永久类型。

## 6. TLB entry

TLB fast path 至少需要：

- guest page tag；
- backing base 或 translation delta；
- VALID、READ、WRITE 等权限；
- 可选 generation/ASID；
- 原子发布和失效规则。

候选 XOR 编码：

```text
delta = host_page_base XOR guest_page_base
host  = delta XOR guest_address
```

identity 页的 delta 为零，因此 VALID 必须是独立 bit，不能把全零 entry 同时解释为
identity 和 invalid。

TLB entry 的确切布局尚未冻结。冻结后它属于 psABI，因为 LLVM 会内联读取它。

## 7. 访问 lowering

```text
known stable-direct
    → native load/store

known managed
    → inline TLB lookup
       ├─ hit → backing load/store
       └─ miss/cross-page/permission → slow path

unknown/hybrid
    → optional direct-domain guard
       ├─ proven-safe direct → native access
       └─ otherwise → TLB path
```

必须覆盖：

- 8/16/32/64 位整数和浮点；
- SIMD；
- 未对齐和跨页访问；
- volatile；
- atomics、wait/notify；
- `memcpy`/`memmove`/`memset` 及 LLVM memory intrinsics；
- libc/compiler-rt 隐式生成的访问。

## 8. Slow path

候选 import 面：

```text
linux.smmu_resolve(gva, size, access) -> translation/result
linux.smmu_load_slow(...)
linux.smmu_store_slow(...)
```

最终应尽量缩小 import 数量，但不能让单次调用同时承担不相关策略。slow path 负责：

- TLB miss；
- 未映射和权限 fault；
- 跨页访问；
- backing 建立或文件内容装入；
- SIGSEGV/SIGBUS 结果；
- TLB entry 发布。

## 9. Mapping 更新与并发

`munmap`、`mprotect` 和 backing 更换必须先使 fast-path entry 失效，再允许旧 backing
被回收。第一版应使用共享、原子读取的 pagebase/TLB entry，而不是无法及时 shootdown
的 Worker-local 长期缓存。

需要定义并测试：

- publish/consume 内存序；
- 多线程正在访问时的 invalidation；
- fork/exec 后 context 身份；
- Worker 退出时 backing 生命周期；
- generation wrap；
- 旧 entry 不得指向已复用页面。

## 10. 标准 syscall 的 pointer 参数

`copy_to_user`、`copy_from_user`、字符串、iovec、futex 和嵌套用户结构必须识别 hybrid
地址。应用不应为 managed buffer 使用另一套 read/write syscall。

## 11. 兼容性规则

- direct-only 模块与 softmmu 模块必须可被 loader 明确区分。
- ABI 不匹配返回明确的 exec-format 错误。
- 新 feature 通过 required/optional bit 协商。
- 不允许按“当前 LLVM 版本刚好一致”代替正式版本检查。
- ABI 测试必须跨不同版本的 compiler、runtime 和 kernel 组合运行。
