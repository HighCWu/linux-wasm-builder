<!-- SPDX-License-Identifier: MIT -->

# musl 兼容性变更边界

本项目 musl 的直接上游是 [tombl/musl](https://github.com/tombl/musl)，不是以
musl 官方版本作为项目差异基线。官方实现可用于核对已有接口的来源和语义，不能
因此把直接上游尚未提供的公共函数加入本项目 musl。

开发重点是 Linux on Wasm 的 syscall 和真实程序能力，而不是扩展 libc API。
musl 只加入必要的架构、位宽、执行 ABI、已有接口声明门控和调用路径兼容代码。
允许恢复上游已有但对 Wasm 隐藏的接口；不新增通用 Linux 包装函数、公共头文件
API 或项目专用应用接口。没有 libc 包装时，语料可在测试内部调用标准 syscall，
遵守 Wasm 机器字参数及返回值约定，不安装额外包装库。

## 2026-10-21 审计

通过直接查询远端 HEAD，确认 tombl/musl 的默认分支 master 为
`637b0d25dafa7e4740357f25fb0b5e3949f1ed1f`。本项目保留的 musl 版本是
`e7bde799c1726088d5074ae21d70368ddbfe0f86`，相对该直接上游有 23 个提交。
审计检查了全部净差异、公共 include 声明和新增源文件，不只检查最近一个提交。

| 变更 | 相对 tombl/musl 的结论与处理 |
| --- | --- |
| pidfd_open、pidfd_getfd、pidfd_send_signal 和 sys/pidfd.h | 新增通用公共 API，移除独立实验提交，不集成 |
| memfd_create | 直接上游已有实现与 GNU 声明，只恢复 Wasm 的声明可见性，保留 |
| msync | 直接上游已有实现和声明，只移除 Wasm 禁用门控，保留；不因此声称文件回写完整可用 |
| mmap、munmap | 直接上游已有公共接口，保留 Wasm 的直接内存及 syscall 接入兼容代码 |
| SYS_clone3、time64 与 LP64 syscall 选择 | 标准 syscall 编号或机器字调用适配，不是新增 libc 函数，保留 |
| inttypes/stdint 宏和 stat/statfs 布局 | Wasm 类型与内核线格式兼容修正，保留 |
| 可选 fork 构建补丁 | 恢复上游已有 fork/_Fork 及显式 Wasm import 选择，不新增公共函数，保留 |

清理后，相对直接上游没有新增公共 include 文件，也没有新增通用 src/linux
包装源文件。唯一新增的源文件是 `src/mman/wasm32/mmap_init.c`。

这里不把“没有新增公共 API”误写成“没有新增任何 C 符号”：`__wasm_mmap`、
`__wasm_mmap_v2`、`__wasm_munmap`、`__wasm_mmap_initialized`、
`__wasm_mmap_init_v1` 和静态辅助函数属于 Wasm 执行/分配兼容实现，不是给应用
调用的 libc API。它们未加入公共 include 声明，现有 loader 的 mmap 路径依赖这些
辅助入口。直接上游已有的 SjLj 辅助声明也不属于本项目新增公共函数。

## 历史清理与验证

三个 pidfd 包装原先在单独的分支末端提交中，主仓库 musl gitlink 和 distro 的
固定 rev/hash 均未引用它。经用户授权，使用精确旧 SHA 的 force-with-lease 将
开发分支退回上述 e7bde799；没有添加 revert 提交，也没有重排此前 23 个兼容性
提交或改写直接上游历史。远端分支已重新核对。恢复点仅保存在本地专用 recovery
ref，不发布为开发分支；移除分支引用不等于物理擦除托管服务缓存中的 Git 对象。

该次清理时主仓库和 distro 固定来源不变，不需要为相同源码更新下载哈希或派发重型构建。
已移除本地未提交的 pidfd 包装测试，保留原 syscall 语料；公共头文件的 wasm32、
wasm64、x86_64 编译检查通过，可选 fork 补丁对保留基线的 dry-run 通过。
这些轻量检查不替代真实 Wasm syscall 或浏览器验收。

## 后续 mremap 兼容恢复

musl `c4c3591d` / `08ab5ec6` 在上述基线上恢复直接上游已有的 GNU mremap 声明和
包装函数，只移除 Wasm 门控，并为 Wasm 可变参数 syscall 显式传入六机器字。
标准号 216 及 allocator 所需的既有 GNU 常量可见性一并补齐。GNU 特性宏控制
接口可见性，不改变这些源文件的许可证。

新增 `__wasm_mremap` 是 direct 分配器内部执行辅助入口，与 `__wasm_mmap_v2`、
`__wasm_munmap` 同类，不加入公共 include 的应用 API。没有新增通用包装文件，
没有增加直接上游本来没有的公共函数。初始化副本来源标记、锁外准备/锁内重新
验证及元数据发布均属于 Wasm 兼容实现，自有新增代码沿用 MIT。

对应 Linux 标准 syscall 接线为 `82d9b0b3b`，内核改动保留 GPL；公开重型目标
验收单独跟踪，不以头文件可见、宿主检查或 GNU 声明恢复证明完整 mremap 可用。

后续 `0a8b3917` 仅扩展同一内部辅助入口的单记录内子区间处理，传播已有副本
来源标记并完善临时资源回收；公共声明、函数集、syscall 号和执行签名均未新增。

## 后续 msync 与 madvise 兼容恢复

`c6e6b380` 的 `__wasm_msync` 核实私有映射范围；`d61bd4aa` 的
`__wasm_madvise` 实现匿名 DONTNEED 清零及常见驻留内存提示，均只属于 Wasm
内部执行兼容入口，不加入公共头文件。没有宣称共享文件回写或浏览器物理内存回收。

`d61bd4aa` 同时移除 tombl/musl 已有 madvise、posix_madvise 的 Wasm 禁用门控，
两个包装函数的原始函数体不变；已对直接上游 `637b0d25` 核实净差异。GNU/BSD
madvise 声明仍保留原特性宏，POSIX 声明对 Wasm 恢复。特别保留原 posix_madvise
对 POSIX_MADV_DONTNEED 的非破坏性处理及返回错误号、不设置 errno 的语义，
不能错误转成 Linux MADV_DONTNEED 的破坏性清零。不增加上游没有的公共函数。

后续 `e6543914` 只增加内部 `__wasm_mmap_fixed`：在 allocator 已拥有的 backing
中替换映射，预分配/重新验证、记录拆分、引用保活和清零均为 Wasm 兼容实现。
不新增公共头文件、公共函数或通用包装文件，也不扩展到任意 malloc/栈地址。

`0600f012` 为同一内部放置事务增加可选源范围，实现 __wasm_mremap_fixed，并
复用到原 __wasm_mmap_fixed。标准 mremap 的公共声明及包装函数体没有再次修改；
新增的内部导出只供版本化执行 ABI 使用。节点预分配、范围重验、复制/零尾、
来源传播和引用回收均属于 Wasm 兼容实现，仍不扩展 musl 公共函数集。

## 后续宽文件偏移 ABI 修正

`59301bde` 仅在现有 `arch/wasm32/bits/syscall.h.in` 中按 long 位宽选择 syscall
84 的正确名称：wasm32 保持 sync_file_range2，wasm64 选择 sync_file_range。
两种调用的 flags 位置不同；这使直接上游已有 sync_file_range.c 自动进入正确
调用路径，函数体、公共声明和函数集合均不修改。没有新增公共头文件或通用
Linux 包装函数，也未重写已经发布的 musl 历史。

同轮 Linux `2237e08ea` 在内核入口重组 wasm32 的连续 low/high 标量，musl 原有
__SYSCALL_LL_E/O 约定不变。小型 Wasm 模块分别执行原样内核头文件和原样 musl
同步包装；完整 ext4 大文件目标单独跟踪，不用这两项检查替代目标运行。
