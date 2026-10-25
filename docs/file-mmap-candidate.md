<!-- SPDX-License-Identifier: MIT -->

# 标准文件 mmap 候选入口

Linux `8bd657d` 新增默认关闭的 `CONFIG_WASM_FILE_MMAP`。这是已通过 Node 双位宽检查的候选配置，
不是默认发行版/SDK 已开放文件映射的声明，不引入 softmmu 或新的应用 syscall。
仍使用 `CONFIG_MMU=n` 和 direct pointer；应用走标准 `mmap/mmap2/munmap`。
固定源码哈希由[公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39016327047)
取得，不在本地构建 LLVM、内核或系统镜像。

## 当前演进：普通文件 NOMMU 私有复制

Linux `0bbaf824b` 将同一个默认关闭候选从首批认证 EROFS 来源，演进为按文件
能力准入的普通文件私有复制，真实目标尚待验收。不新增应用接口或打开默认配置。
文件必须是可读的普通文件，提供 mmap 能力与内核读取能力；若文件系统显式提供
NOMMU mmap_capabilities，还必须允许 NOMMU_MAP_COPY。不能将仅可直接共享内核
存储的驱动强制转换成私有副本；不支持的类型/能力明确拒绝，LSM 检查继续执行。

按 Linux `mm/nommu.c::do_mmap_private` 的复制行为，使用一次 kernel_read 的有效
字节形成独立副本，剩余页对齐区域清零。短读/空文件/全部位于 EOF 后的请求可
产生零填充区域，不假装具备 MMU 的 SIGBUS、缺页或截断失效机制；负读取错误
仍不发布。后续文件写入/截断不反映到已返回的私有副本，新请求重新读取文件。
这不是一致性快照：并发写入期间可观察到什么由底层读取语义决定。kernel_read
返回前保留生产者、staging、文件引用和预算；返回后才允许同步初始化与发布。

每次128 KiB、全局在途512 KiB、RO/RW 无强制保护、私有分配、offset 单位及旧模块
拒绝保持。MAP_POPULATE 等提示按第八十一组接受；共享、执行、锁页、固定地址
及未知标志仍拒绝。私有测试入口保留认证来源、稳定长度与异常短读报错的原合同，
不会因为普通文件复制演进而让实验来源认证失效。

真实标准负载增加普通磁盘、可变文件写入后新旧副本独立、截断与 EOF 补零、
unlink/close 后存活；Zstd 强制映射扩展到普通磁盘和可写文件的五种合规尺寸，
超限仍拒绝。宿主模型和真实程序编排的通过不等于这些新目标已验收。

## 首批范围（以下验收固定在历史版本）

- 只接受 `MAP_PRIVATE`，权限为 `PROT_READ` 或 `PROT_READ | PROT_WRITE`。
- 来源须为已认证私有快照上的单设备 EROFS 普通文件，并具有 fd 读权限。只读 fd、
  只读挂载、相同内容的普通宿主磁盘或文件系统名称本身均不构成认证。
- 单请求最多 128 KiB，在途 staging 和候选副本按双份页对齐长度预留，全内核载荷
  额度 512 KiB。容量上限或并发额度不足返回 ENOMEM；不等待额度，不伪造稀疏映射。
- 文件 offset 必须按 64 KiB 页对齐。wasm32 的 mmap2 参数以 **4096 字节**为单位，
  在内核扩为 u64 字节 offset；wasm64 的 mmap 参数本就是字节 offset。超过有符号
  64 位文件位置范围返回 EOVERFLOW，不把 offset 转成宿主 Number。
- 允许包含 EOF 的最后一页，其余尾部由用户分配器清零；空文件、起点位于 EOF、
  或请求包含完整的 EOF 后页面均拒绝。源 fd 的共享文件位置不变。
- 每次产生独立私有副本，关闭 fd 后仍可读取；写入 RW 副本不修改文件或别的副本。
  读取失败、异常短读、分配/复制失败不得发布部分内容，须归还 staging 和预算。

`PROT_READ` 遵循上游 NOMMU 的限制，**不保证违规写入触发 SIGSEGV**，不能用于
隔离不可信代码。不共享所谓只读副本，避免缺少写保护时污染其他映射。继续拒绝
PROT_NONE、PROT_EXEC、MAP_SHARED、MAP_FIXED 和 MAP_FIXED_NOREPLACE；普通非固定
地址 hint 可忽略。没有按需分页、COW、写回、执行文件映射或逐页 mprotect。

该入口 pin 住 `struct file`，检查来源/权限并调用 `security_mmap_file`，随后走 VFS
`kernel_read`，不绕过 Linux 去读取宿主路径。与原私有语料共用 `mmap_file.c` 的读取、
预算和回滚实现；受控测试 inode 只允许通过原测试入口，不能进入标准路径。

## 版本化执行能力

不新增应用私有 UAPI，也不更改现有匿名 mmap v2 参数。候选内核在
`user_mmap_init_v1` 执行 namespace 增加 `capabilities() -> i32`：bit 0 表示当前用户
模块导出了 `__wasm_mmap_init_v1` 私有初始化分配器。查询只检查导出，不调用程序、
不授权文件来源，也不授予复制 lease；每次按当前模块查询，不缓存旧模块的能力。

缺少能力时，在分配 staging、读取 VFS 前返回 EOPNOTSUPP。随后仍使用原有同步
`map(rounded, kernel_source, length)` 和 `linux_mmap_init_v1.copy`：只有有效 lease
才能复制一次，内核 staging 地址、fd 和 offset 不传给应用。初始化和零填充完成后
才发布分配器记录。复制桥本身不判断文件准入，也不承诺内存保护。

候选程序仅在链接时加 `-Wl,--export=__wasm_mmap_init_v1`，无需改应用解引用或
添加私有 syscall。当前 musl 已有该可选对象，本轮不修改 libc/LLVM，不把新 import
强加给普通程序；默认 SDK 也不自动导出它。v1 仍是候选执行协议，尚未承诺稳定发布。
新候选内核须配套支持 capabilities 的宿主，旧宿主不能实例化该候选内核；这不是
通过用户模块能力查询就能兼容旧宿主。默认内核不引用该新增 import。

| 内核 | 用户模块 | 认证文件的标准 mmap |
|---|---|---|
| 默认发布配置 | 有或无初始化导出 | 保持 EINVAL |
| 候选配置 | 无初始化导出 | EOPNOTSUPP，无 staging/读取 |
| 候选配置 | 有初始化导出 | 在严格范围和预算内尝试私有复制 |

原 `CONFIG_WASM_MMAP_COPY_TEST` 仍默认关闭，与候选配置分开构建；它的私有 syscall
不是应用 API。候选不启用受控测试 inode、不恢复完整通用 NOMMU VMA 管理，不声称
新增完整 fork、进程隔离、exec 竞态处理或崩溃恢复支持。

## 验收

本地已通过 138 项内核宿主检查、项目 TypeScript 7 检查及 C 语法检查。Linux 自带
MIT 测试 `arch/wasm/tests/run-mmap-file-host.py` 使用 GCC/Clang 编译真实候选 C，
替换 VFS/LSM/原子/分配器为宿主 shim，检查两种 offset 单位、来源/权限、旧模块、
LSM 拒绝、EOF、容量、短读/错误、分配/复制回滚和预算拒绝。它不证明真实 Linux
VFS/LSM、32 位机器 ABI、Wasm 原子或内核执行；候选内核公开构建也会运行此检查。

新增双位宽 `mmap-benchmark[-wasm64]-check-file` 聚合入口，分别启动：

1. 候选配置加初始化导出：标准只读/RW 映射、非零 libc/raw offset、EOF 补零、
   来源/flags/权限拒绝、独立副本、fd 位置及匿名 sentinel。
2. 候选配置加旧模块：保留匿名分配，认证文件请求明确拒绝。
3. 默认内核加初始化导出：不能仅因模块有导出就放行文件映射。
4. 原私有测试内核的预算/生命周期回归：共用读取实现不得破坏已有拒绝/回滚路径。

实际 Node 承载的 Wasm 目标结果见下文，不将宿主 shim 或旧版回归记为候选成功。原 EROFS
压力语料改为两个并发最大请求，以匹配八页在途预算；预算耗尽仍由独立屏障语料检查，
不是允许四个最大请求超配。浏览器、标准发布后生命周期和初始性能结果见下文；
真实设备高并发背压、重复压力和性能开销分解仍须继续，默认发行配置不会因候选自动开放。

distro `4b06c21` 固定该内核及上述集成。首轮
[wasm32 检查](https://github.com/HighCWu/distro/actions/runs/39016551516) 和
[wasm64 检查](https://github.com/HighCWu/distro/actions/runs/39016555063) 均已失败，
实际日志确认已进入候选程序，在标准文件 mmap 拒绝断言失败，不能记为通过。
检查源码发现 `O_PATH` 预期错误：上游 `fget()` 排除此类 fd，返回 EBADF，而不是
后续 FMODE_READ 检查的 EACCES。distro `cbd0d89` 修正此断言并增加失败参数、
返回指针和实际/预期 errno 诊断；本机 Linux 也验证 O_PATH mmap 返回 EBADF，
但这不能替代候选内核的重跑结果。
[wasm32 重跑](https://github.com/HighCWu/distro/actions/runs/39024983496) 和
[wasm64 重跑](https://github.com/HighCWu/distro/actions/runs/39024986125) 均已成功。
实际 heavy job 日志确认四组各自的通过标记：候选 RO/RW 内容/offset/EOF/独立性、
默认内核拒绝、旧模块拒绝、预算/生命周期回归。该结果只适用于认证来源和有界复制范围，
不扩展到普通文件系统或完整 NOMMU mmap；浏览器和初始性能证据分别见下文。

[Zstandard 强制字典映射验收](zstd-runtime.md)也已通过 Node 双位宽及实际日志检查：
只在测试变体导出初始化能力，默认发行包和内核准入保持不变。
distro `0d473c2` 将同一标准程序和 Zstd 工作负载接入双位宽 Chromium/Firefox。
浏览器使用候选内核，不是原私有测试 syscall 内核；只加载标准程序或真实 CLI 的
initramfs，以及认证/普通两个同内容磁盘。每组须执行标准入口和 Zstd 两项测试，
检查详细阶段标记、无失败/页面异常和机器关闭，并通过精确测试名、零跳过/重试报告门禁。
本地新增八项编排替身检查已通过，不证明浏览器执行。下列四组公开检查均已成功：
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39047346035)、
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39047350401)、
[wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39047353874)、
[wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39047357984)。
实际 heavy job 日志均确认标准映射阶段、Zstd 五个尺寸、容量与来源拒绝以及两个 pass，
各 `2 passed`，精确报告门禁确认零跳过、零重试。实际浏览器为 Chromium 149.0.7827.55
和 Firefox 151.0；这是固定 Playwright 构建的结果，不泛化为所有浏览器版本。

## 标准入口生命周期扩展

distro `4133e3b` 新增 `mmap-benchmark[-wasm64]-check-file-lifetime`，使用候选内核、
认证 EROFS 和有初始化导出的普通 pthread C 程序，只调用标准 mmap/munmap 等接口，
不调用原私有实验 syscall 或资源统计槽。目标检查包含：

- 在创建线程之前，各运行八次正常退出和 SIGKILL 的私有 `clone(callback, SIGCHLD)`。
  子回调读取继承的 RO/RW 映射、修改 RW、unmap、重新打开来源并完成一次新映射。
  父任务等待明确发布标记再 kill/reap；随后核验自身映射不变并可重新映射。
- 两个同步线程各八轮最大长度映射，所有副本创建/检查后才独立修改并 unmap；
  检查彼此不别名和原 fd 位置、文件字节不变。不声称确定性重叠了设备读取。
- 关闭最后一个来源 fd，真正卸载快照挂载后仍可读取副本；部分 unmap 后其余页仍在，
  新匿名映射清零且不污染保留部分，最终正常解除全部映射。

GCC/Clang 编译并运行共享 helper 的宿主检查已通过。宿主将文件填充到完整三个
64 KiB 块，避免本机 4 KiB EOF fault，并以 unlink 代替卸载；不伪装目标证据。
Wasm [wasm32](https://github.com/HighCWu/distro/actions/runs/39047747728) 与
[wasm64](https://github.com/HighCWu/distro/actions/runs/39047751959) 已通过计划检查并进入
实际运行，两项均已成功，日志确认四个生命周期阶段和最终 pass。
这不是完整 fork 返回上下文恢复、任意多线程
fork、安全隔离、确定性在途 VFS/设备取消或严格内存泄漏/额度检查；SIGKILL 发生在
映射已经发布之后，不能把此结果扩展为读取期间退出安全。

## 初始性能诊断

distro `2706fb9` 新增[配对性能检查](file-mmap-performance.md)，在同一认证来源上
比较标准文件 mmap 主动复制和 malloc/pread，分别记录 64/128 KiB 的五对批次。
首轮双位宽目标已通过，实际数据经严格解析器校验并保留溯源；当前 mmap 在本轮比
malloc/pread 慢约 4.3–9.4 倍，尚不能归因于单个环节。
宿主原生 mmap 不代表本平台主动复制，解析器明确拒绝宿主输出。
没有速度门槛，也没有据此改变默认配置。生命周期和浏览器任务不因此取消或重启。

Linux 实现改动遵循 GPL-2.0；独立测试、宿主和集成修改、文档采用 MIT，其他组件
保持原协议。不把内核实现代码链接进用户程序。
