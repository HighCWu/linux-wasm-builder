<!-- SPDX-License-Identifier: MIT -->

# 文件 mmap：从实验到真实软件验收

本阶段选择 Zstandard 1.5.6 字典加载作为真实软件目标，保持 `CONFIG_MMU=n`、direct
pointer 和默认拒绝边界。标准有界候选及真实 Zstd 强制映射已在 Node 双位宽通过，
浏览器检查正在进行；这不是默认发行配置已开放文件映射的声明。

## 生产准入门槛

| 环节 | 已有实现/证据 | 剩余工作 |
|---|---|---|
| 标准入口 | 默认仍为匿名 RW；默认关闭候选已通过 Node 双位宽正向、拒绝、旧模块及默认对照 | 浏览器；标准接口自身的生命周期压力；不据源码提交宣称可用 |
| offset | 标准 libc/raw 非零 offset 内容已通过，内核归一化 mmap2 的 4096 字节单位和 mmap 字节单位 | 浏览器验证；不将宿主模型等同于目标运行 |
| 不可变来源 | 已接入来源、类型、读权限和稳定长度；普通只读盘/fd/挂载不构成认证 | 继续审查来源与设备生命周期，不扩大到可变文件 |
| 读取与回滚 | 共享 VFS/预算实现；私有预算/生命周期回归已通过 | 标准路径压力；真实设备在途读取、信号/退出与生产者完成的确定性测试 |
| 复制与发布 | 候选当前模块能力查询、同步初始化后发布及旧模块拒绝已通过 | 默认 SDK 尚未导出 wrapper，协议未承诺稳定发布 |
| 保护 | 候选接受 RO/RW 独立副本，明确遵循 NOMMU 无强制写保护限制 | 不静默改变默认 ABI，不伪装 fault 能力；执行/共享/固定请求继续拒绝 |
| 应用 | Zstd 五个边界强制映射和超限/来源拒绝已在 Node 双位宽通过，默认基线仍通过 | Chromium/Firefox 双位宽；性能对照，不称作零拷贝 |

实验 `wasm_mmap_file_read_test` 限制 `length <= 2 * PAGE_SIZE`，当前为 128 KiB，且
使用私有 split-u32 offset，不是正式 ABI。扩大上限前要考虑 staging 与用户副本同时
存活的峰值，不能只提高常量。具体实验记录见[文件映射计划](file-mmap-plan.md)。

## 为什么选择 Zstandard

已有固定上游、双位宽 CLI 和安装系统检查，不必先移植另一个大型软件。上游请求由
`distro/zstd/mmap.patch` 的上下文直接可见：

```c
mmap(NULL, (size_t)fileSize, PROT_READ, MAP_PRIVATE, fileHandle, 0)
```

目标是平台选址、零 offset、完整字典的私有读取，不涉及高地址、MAP_SHARED、COW
或零拷贝。但字典必须来自已认证且生命周期内不可变的来源，不能用 `/tmp` 可变文件。
`PROT_READ` 与当前权限政策也必须先解决：不能把应用改成 RW 后声称原请求已支持，
不能用 malloc/read 回退替代 `--mmap-dict` 成功。正向映射用例已实现并通过 Node
双位宽，实际日志与固定提交见[Zstd 验收](zstd-runtime.md)。

## 本阶段应用基线

`b662d58` 的安装系统语料新增 65535、65536、65537、131071、131072、131073 字节字典，覆盖
64 KiB 页和实验 128 KiB 上限两侧。逐项检查真实长度、默认字典压缩、显式 malloc
解压及逐字节比较；强制 mmap 压缩/解压仍须退出 34、报告 EINVAL 且不输出数据。
每个尺寸有完成标记，之后仍须完成原二进制管道、损坏流和许可证检查。

字典为合成二进制边界语料，不是压缩比或性能基准；来源是可变文件，因此将来开放
不可变子集后也应保留拒绝检查。成功场景须另建，不能直接翻转这里的失败断言。

宿主 10 项检查包含边界字典加载失败、仅边界强制映射静默成功等反向控制。普通
压缩/解压执行宿主 CLI，强制映射拒绝由 wrapper 模拟，不是 Wasm ABI/内核证据。
目标入口沿用 `zstd-check-roundtrip`、`zstd-wasm64-check-roundtrip`。固定 `b662d58` 的
[wasm64 检查](https://github.com/HighCWu/distro/actions/runs/39009756964) 已成功，日志确认
六种尺寸及最终 pass；[首次 wasm32 检查](https://github.com/HighCWu/distro/actions/runs/39009753274)
在源码下载时遇到 HTTP 429，未运行应用；[重试](https://github.com/HighCWu/distro/actions/runs/39010264830)
现已通过，日志同样确认六种尺寸及最终 pass。

## NOMMU 只读权限：上游依据与候选边界

核对 Linux `Documentation/admin-guide/mm/nommu-mmap.rst` 的
“File, MAP_PRIVATE, PROT_READ / PROT_EXEC, !PROT_WRITE”及 `mm/nommu.c` 的
`validate_mmap_request`、`do_mmap_private` 后，不能把“无写保护”直接等同于
“Linux NOMMU 必须拒绝 PROT_READ”。上游允许在无法直接映射时读取私有副本，并明确
指出 NOMMU 不会阻止对这类映射的违规写入。这不是 MMU/Linux 的逐页保护保证。

候选方案因此可接受原应用的 `prot=PROT_READ, flags=MAP_PRIVATE` 数据请求，前提是单独、
默认关闭地启用并清楚声明 NOMMU 限制；成功仅表示可按请求读取完整副本，不保证
违规写入触发 SIGSEGV。不得把应用改成 RW，也不复用上游只读副本的跨进程共享优化：
每次复制独立分配，不能让违规写入污染别的映射或快照文件。继续拒绝 PROT_NONE、
PROT_EXEC、MAP_SHARED 和固定地址请求；Wasm 数据复制不等于可执行代码装载。
不可变来源要求仍保留，不因上游对可变文件采取更宽的 NOMMU 行为就扩大首批范围。

这细化了早期“只接受 RW”的候选规划；默认生产入口、匿名映射政策和 mprotect
保证均不改变。候选能力协商和标准入口 Node 验收已完成；正式开放仍需浏览器、
标准路径生命周期压力和性能证据，不能只凭单轮成功就改变默认配置。

## 在途复制预算

Linux `2c0f7ce` 在 `CONFIG_WASM_MMAP_COPY_TEST` 的实际文件读取路径新增内核全局原子预留：每个请求
按 `2 * ALIGN(length, PAGE_SIZE)` 计费，在 staging 分配和 VFS 读取前取得额度，直至
同步复制/发布返回或读取失败、staging 释放后归还。单请求仍不超过 128 KiB；总额度
为八个 64 KiB 页（512 KiB），可容纳两个最大请求，超限立即返回 ENOMEM，不等待读者。
固定源码哈希由[公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39010698044)
计算；distro `0bc859b` 同时固定该内核与对应 MIT 验收程序。

这是 staging 与未发布候选副本的在途载荷上界，不是硬性进程/整机配额：不计已发布
映射、分配器元数据、WebAssembly.Memory 扩容粒度、VFS 缓存及测试源文件本身。
已发布映射继续由原用户分配器管理，预算不能代替其容量检查，也不能自动防止 OOM。
取消/退出仍须等 VFS 生产者实际停止才能释放 staging，不能靠重置计数器回收。

生命周期验收用两个独立读取屏障占满额度，检查一字节新请求被拒绝、正常读取及
部分读取失败后额度可重用，且未完成请求仍持有自身额度。现有稳定零请求资源检查
同时检查预留归零，接入既有信号/退出清理检查。本轮
[wasm32](https://github.com/HighCWu/distro/actions/runs/39010863533) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39010866844) 的 signal 聚合验收
均已成功，实际日志逐项确认预算/生命周期、信号及基础 VFS 的 pass；没有把尚未
重跑的退出检查记为通过。这是 `2c0f7ce` 的结果，不代替后续提取共用读取实现的候选验收。
本地 GCC/Clang 对实际预留函数使用 C11 原子 shim 检查边界及八线程各一万次尝试，
相关 C 语法检查通过；这不是 Linux 原子实现、Wasm 调度或 VFS 运行的通过证明。

## 后续顺序

1. 双位宽应用拒绝基线和原预算回归已通过，继续保留默认配置作为对照。
2. [标准候选入口](file-mmap-candidate.md)已按权限政策、不可变来源和容量预算实现，
   默认关闭，标准接口正向/旧模块/默认配置的 Node 双位宽目标验收已通过；
   不增加应用私有 mmap UAPI，不绕过 VFS 读取宿主文件。
3. offset 优先在内核归一化并交给 VFS，确实跨执行边界时才设计独立 i64 字段。
   现有复制桥只传长度和 staging 内容，不必为 offset 模型强行新增 host import；
   这是对早期“新 offset 执行接口”设想的细化，不改变 v2 参数含义。
4. 原 Zstd `--mmap-dict` 正向与默认拒绝对照也已通过 Node 双位宽；浏览器四组进行中。
   不将应用回退或宿主模拟当成目标映射支持。
5. distro `4133e3b` 新增标准接口生命周期检查：私有 clone 回调、正常/致命退出后
   父映射独立和新请求恢复、双线程独立副本、关闭 fd/卸载来源、部分 unmap 与匿名复用。
   不调用私有测试 syscall；目标结果尚待确认。GCC/Clang 宿主检查只验证编排及数据断言，
   使用填充文件和 unlink，不证明 Wasm 内存快照、64 KiB EOF 或 EROFS 卸载。
6. 完成浏览器、标准路径生命周期压力和性能对照后才评估默认开放；这不等于完成
   完整进程语义、可变来源文件映射或整个 Linux/Wasm 平台目标。

默认生产配置和 libc 不变，Linux 的候选/共用读取实现遵循 GPL-2.0。
新测试与文档采用 MIT，上游 Zstd 补丁保持原有许可。
