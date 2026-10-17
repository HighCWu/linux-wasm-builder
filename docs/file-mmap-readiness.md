<!-- SPDX-License-Identifier: MIT -->

# 文件 mmap：从实验到真实软件验收

本阶段选择 Zstandard 1.5.6 字典加载作为真实软件目标，保持 `CONFIG_MMU=n`、direct
pointer 和现有拒绝边界。这是开放条件和验收顺序，不是新增文件映射能力声明。

## 生产准入门槛

| 环节 | 已有实现/证据 | 剩余工作 |
|---|---|---|
| 标准入口 | `arch/wasm/kernel/syscall.c` 接受匿名 RW 子集 | 独立处理文件参数、权限、flags、错误及旧模块兼容 |
| offset | 双位宽 syscall 别名修复，单位/溢出模型 | 在标准路径核对 mmap2 的 4096 字节单位及 mmap 字节单位，验证非零 offset 成功内容 |
| 不可变来源 | 私有快照身份、设备树防伪、单设备 EROFS 查询 | 将来源、类型、读权限和稳定长度检查接入文件路径；普通只读 fd/挂载不能放行 |
| 读取与回滚 | file/staging 持有、VFS 读取、短读/错误回滚实验；本轮加入原子在途预算 | 目标验证预算拒绝/复用，继续审查真实设备在途读取、信号/退出与生产者完成 |
| 复制与发布 | `user_mmap_init_v1` 同步复制及初始化后发布实验 | 稳定并协商执行能力，明确旧模块行为；默认 SDK 尚未导出实验 wrapper |
| 保护 | 当前生产路径只接受 RW；上游 NOMMU 已有不强制保护的只读私有复制语义 | 候选路径明确声明 NOMMU 权限边界，不静默改变当前生产 ABI 或伪装 fault 能力 |
| 应用 | Zstd malloc/read 字典及强制 mmap 拒绝已在 Node 双位宽通过 | 扩展边界基线，再建立不可变来源的正向验收，最后进入浏览器 |

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
不能用 malloc/read 回退替代 `--mmap-dict` 成功。正向映射用例尚未实现。

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
在源码下载时遇到 HTTP 429，未运行应用，已另行重试。

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
保证本轮均不改变。正式开放仍需完成版本化执行能力协商和标准入口目标验收。

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
均已通过计划检查并进入实际构建，包含预算/生命周期、信号及基础 VFS 回归，运行结果
待确认；没有把尚未重跑的退出检查记为通过。
本地 GCC/Clang 对实际预留函数使用 C11 原子 shim 检查边界及八线程各一万次尝试，
相关 C 语法检查通过；这不是 Linux 原子实现、Wasm 调度或 VFS 运行的通过证明。

## 后续顺序

1. 确认双位宽应用基线，保留拒绝配置作为对照。
2. 明确权限政策、不可变来源和容量预算，才实现默认关闭的标准文件 mmap 候选路径；
   不增加应用私有 mmap UAPI，不绕过 VFS 读取宿主文件。
3. offset 优先在内核归一化并交给 VFS，确实跨执行边界时才设计独立 i64 字段。
   现有复制桥只传长度和 staging 内容，不必为 offset 模型强行新增 host import；
   这是对早期“新 offset 执行接口”设想的细化，不改变 v2 参数含义。
4. 不可变来源成功、可变来源拒绝、EOF/非零 offset、回滚及旧模块兼容全部通过后，
   以原 Zstd `--mmap-dict` 验收；只读请求未满足时，不将该应用路径记为支持。
5. 先 Node 双位宽，再浏览器、生命周期压力和性能对照，之后才评估默认开放。

本轮生产内核配置和 libc 不变，预算修改仅进入 Linux 的默认关闭实验代码（GPL-2.0）。
新测试与文档采用 MIT，上游 Zstd 补丁保持原有许可。
