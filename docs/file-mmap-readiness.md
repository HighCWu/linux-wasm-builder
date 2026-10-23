<!-- SPDX-License-Identifier: MIT -->

# 文件 mmap：从实验到真实软件验收

本阶段选择 Zstandard 1.5.6 字典加载作为真实软件目标，保持 `CONFIG_MMU=n`、direct
pointer 和默认拒绝边界。标准有界候选及真实 Zstd 强制映射已在 Node 双位宽通过，
固定 Chromium/Firefox 双位宽及标准生命周期也已通过；这不是默认发行配置已开放文件映射的声明。

## 生产准入门槛

当前按能力优先推进：保留性能测量作为以后定位瓶颈的证据，不再把重复性能对照
或接近原生延迟作为开放能力的前置条件。真正尚缺的是下面的在途生产者生命周期、
默认 SDK 能力协商及执行协议发布边界；不能因停止性能实验就跳过这些正确性门槛。

Linux `50abafbb5` 已为共用复制路径加入可见 SIGKILL 的读取前/初始化前检查。
配套不可中断 VFS 生产者目标正在验证“排队信号不提前释放、生产者返回后不再
进入初始化器”；这不是最终检查与未来信号入队的原子化，也不等于真实 EROFS/
virtio 设备在途压力完成。精确版本、宿主模型和待验收目标见
[第三十七组](process-syscalls.md#第三十七组文件复制的可见-sigkill-取消点)。

| 环节 | 已有实现/证据 | 剩余工作 |
|---|---|---|
| 标准入口 | 默认匿名 RW；候选已通过 Node、双位宽浏览器和标准生命周期 | 更广生命周期/在途设备压力；默认仍关闭 |
| offset | 标准 libc/raw 非零 offset 已通过 Node/浏览器，内核归一化两种单位 | 重复回归与更广边界，不将宿主模型等同于目标运行 |
| 不可变来源 | 已接入来源、类型、读权限和稳定长度；普通只读盘/fd/挂载不构成认证 | 继续审查来源与设备生命周期，不扩大到可变文件 |
| 读取与回滚 | 共享 VFS/预算实现；私有预算及标准发布后生命周期已通过 | 真实设备在途读取、信号/退出与生产者完成的确定性测试 |
| 复制与发布 | 候选当前模块能力查询、同步初始化后发布及旧模块拒绝已通过 | 默认 SDK 尚未导出 wrapper，协议未承诺稳定发布 |
| 保护 | 候选接受 RO/RW 独立副本，明确遵循 NOMMU 无强制写保护限制 | 不静默改变默认 ABI，不伪装 fault 能力；执行/共享/固定请求继续拒绝 |
| 应用 | Zstd 强制映射与拒绝已通过 Node/双位宽浏览器，默认基线仍通过 | 开销分解、重复性能对照和更广软件覆盖，不称作零拷贝 |

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
保证均不改变。候选能力协商、标准入口 Node/浏览器及发布后生命周期验收已完成；
仍需补齐在途压力、生产者生命周期和执行协议发布边界，不能只凭单轮成功改变默认配置。

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
4. 原 Zstd `--mmap-dict` 正向与默认拒绝对照也已通过 Node 双位宽；浏览器四组也已核实通过。
   不将应用回退或宿主模拟当成目标映射支持。
5. distro `4133e3b` 新增标准接口生命周期检查：私有 clone 回调、正常/致命退出后
   父映射独立和新请求恢复、双线程独立副本、关闭 fd/卸载来源、部分 unmap 与匿名复用。
   不调用私有测试 syscall；双位宽目标已通过，日志确认四个阶段及最终 pass。
   GCC/Clang 宿主检查只验证编排及数据断言，
   使用填充文件和 unlink，不证明 Wasm 内存快照、64 KiB EOF 或 EROFS 卸载。
6. 浏览器和标准生命周期已完成上述有界验收；首轮[性能对照](file-mmap-performance.md)
   显示主动复制 mmap 明显慢于 malloc/pread，保留为历史诊断，不继续专项测量。
   下一步解决真实设备在途读取、信号/退出时的生产者所有权和默认 SDK 协商，
   这些正确性门槛补齐前仍不开放默认。这些有界结果不等于完成
   完整进程语义、可变来源文件映射或整个 Linux/Wasm 平台目标。

默认生产配置和 libc 不变，Linux 的候选/共用读取实现遵循 GPL-2.0。
新测试与文档采用 MIT，上游 Zstd 补丁保持原有许可。

## 初始化异常仍会绕过内核清理

对 Linux `50abafbb5` / distro `2784222` 的实际共用复制函数和 JS 执行桥，
[小型 Wasm 复现](../experiments/file-mmap-trap/README.md)已确认一个未修复缺口：
用户初始化器执行 unreachable，异常从内核 import 传播出去，会跳过 C 函数后面的
kfree、请求计数和预算归还。JS finally 只撤销复制租约；call_kernel_entry 恢复
C 栈指针也不会执行跳过的清理。正常返回和 ENOMEM 对照均归零，trap 后则残留
一个请求、一个 staging、一个模型分配和128 KiB预留。Clang18/22 的 wasm32/64
均复现；默认命令要求资源归零，故当前明确失败，不将诊断模式通过列为功能验收。

这是实际函数体的控制流证据，不是完整 Linux 分配器/VFS/调度证据；模型未执行
外层标准 mmap 的 fget/fput，不能据此量化来源引用泄漏。修复必须同时覆盖该层
所有权，不能仅清零计数。先前信号取消点只处理普通 C 返回路径，不能解决此缺口。

异常边界必须保留原异常及其来源：用户 trap 不应变成可继续运行损坏分配器的普通
errno，嵌套 syscall 的内核异常也不能伪装成用户分配失败；SjLj 须到达原 catchpad。
还需核对初始化器内 exec/exit、信号非局部退出和重入。没有这些清理/终止边界的
实际目标证据前，继续保持文件 mmap 默认关闭；不因其他正常生命周期通过而放行。

后续 Linux `48adb6d39` 已加入修复候选：VFS 返回后才把 staging、文件引用和
预算移交到任务所有的堆记录，普通返回和回调异常分别释放；exit_thread 在交出
CPU 前收尾。桥在异常传播前撤销租约、调用内部 abort export，并原样重抛，
不吞 RuntimeError 或 SjLj；HALT_KERNEL 不再重入已经退出的实例。标准入口
同时改为向共用复制函数移交文件引用，避免外层 fput 被旁路或发生重复释放。

小型模块现已核实修复路径归零、旁路清理时泄漏、退出钩子回收及后续映射恢复；
真实内核 vfs-callback 目标仍待验收，覆盖 trap、嵌套 exit 和 siglongjmp。
该记录没有接管仍在读取中的生产者，也未证明 exec、实际设备或损坏分配器恢复。
此前已通过的 SIGKILL 取消点目标不覆盖这里的非局部异常修复。
