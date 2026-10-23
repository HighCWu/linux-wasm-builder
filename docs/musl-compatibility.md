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

## 既有 Wasm break 算术边界修复

`bf26831e` 相对 `e12bb18e` 的净差异仅为原 src/linux/brk.c 的 Wasm 分支，
没有新增公共函数、声明、头文件或通用包装。原非 Wasm 分支不变。
此处修正的是已有 brk/sbrk 的直接内存实现，不是新增内核 SYS_brk：标准号214
当前仍未接入，不能把 libc 的内存增长成功写成 raw syscall 已支持。

原 sbrk 先进行指针加法，极端负增量在 wasm32 可回绕为增长请求；wasm64 即使
增长失败也会发起错误的巨大 grow。现在先按原有单调分配政策拒绝负增量，检查
正增量的 uintptr_t 加法是否溢出，再构造地址；保留 ENOMEM 和锁释放行为。
这不新增缩小 break 的支持。

原缓存以指针保存已提交容量的字节末端，在 wasm32 内存已增长到4 GiB时回绕
为零，甚至使 break 查询失败。现在直接比较页面数量，用除法/余数计算目标页数，
避免向上取整加法溢出，不将完整4 GiB容量转换成32位末端指针。当前 break
仍须可由地址类型表达；不承诺能用32位指针表达4 GiB这个独占末端值。

Clang18/22 的双位宽小型 Wasm 执行和分析通过，涵盖负增量、正增量回绕、增长
失败后的原状态、满容量查询及互斥锁释放。容量由私有测试模型表示，没有分配
4/16 GiB真实内存；直接编译原 `e12bb18e` 的 brk.c 后，两种负增量检查及
wasm32 满容量查询分别明确失败。模型不等于浏览器大内存承载验收。
真实 SDK 的双位宽回归和版本见[第三十六组](process-syscalls.md#第三十六组既有-wasm-break-算术与增长兼容修复)。
固定 `11ee975` 的两位宽实际目标已核实三阶段、唯一 pass 与关闭门禁；这不将
小内存回归扩展为浏览器4 GiB承载或完整内核 SYS_brk 支持。

## Wasm clone trampoline 的启动边界兼容

`09a90c1a70ea569aa6649449274c6031a143a01c` 相对 bf26831e 的净差异仅为
既有 `src/thread/wasm32/clone.c` 中的五行：clone_entry 设置 C 栈和 TLS 后，
clone_entry_inner 在调用应用 callback 之前执行已有 `SYS_gettid`。这让 Linux
通用 syscall 返回工作先处理待投递信号和 ptrace newborn stop，而不是等应用
callback 自己第一次调用 syscall。没有新增函数、公共声明、头文件、包装、
syscall 号或执行 import；其它架构不变，已发布历史保留。

不能直接在当前内核的启动回调之前执行用户 signal handler：此时 Wasm 的栈和
TLS 尚未由该 trampoline 初始化。此修复只保证该既有 libc clone 路径的应用
callback 边界，不声称所有任意原始 Wasm callback 或第一条 Wasm 指令都已具备
原生 CPU 的内核返回模型。新增一次 gettid 是架构兼容检查点，不使用其返回值，
不写 errno；没有启用 seccomp，也未证明未来 syscall filter 与此检查点的组合。

原生 tracing 正/反向检查、双位宽前端及静态分析、提取实际 trampoline 函数体的
小型 Wasm 执行和移除检查点的对照均通过。公开源码预取实际日志已核实该版本
与 `sha256-PBeE+zw7yhknEJtCgcs1d20r5gROdLARjCr+eV02ZTs=`；
[第五十组](process-syscalls.md#第五十组clone-栈tls-初始化后的应用入口检查点)
单独跟踪真实目标验收，不把上述宿主/模型检查当作 Wasm 内核运行证明。

固定 distro 41e7245 的双位宽 ptrace-entry 已核实三阶段、唯一 pass 与关闭门禁：
停止发生在应用 store 之前，SIGTERM 后 marker 保持未写，真实父进程正确回收，
随后普通 fork 恢复。默认 C runtime 双位宽也已核实实际 pass，并检查固定程序
必须完成 pthread/TLS/信号等断言才输出成功；关闭失败会使 runner 非零退出。
接受这组有界 Node 结果，不因此声明任意 raw callback 或浏览器已通过。

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

## 调度接口：不把 Linux syscall 当作 POSIX libc 的替代语义

后续审查起初误将四个 sched_getscheduler/setscheduler/getparam/setparam 的
ENOSYS 函数体判断为 Wasm 专有调用缺口。固定 BusyBox chrt 源码明确说明 musl
保留这些桩与 Linux/POSIX 语义差异有关，并已经选择直接 syscall 路径；该 applet
默认也已启用。因此不把增加相同构建选项或相关测试当作新功能，更不改变 libc
语义来制造“已支持”的表象。pthread 的内部 raw syscall 路径也不等于这些公共
POSIX 函数应直接恢复为薄包装。

此结论仅针对上述四个接口，不是保留 Wasm 缺失的通用理由。直接基线仍是
tombl/musl；其 fork/_Fork 与通用 mmap 函数体仍在，但被 __wasm__ 条件排除。
对于这类架构缺口，应在内核、执行 ABI 和错误路径正确接通后复用现有实现，
不能仅因上游未支持就保持不可用。上述调度行为则可追溯到官方 musl 的
[2012 年线程调度提交](https://git.musl-libc.org/cgit/musl/commit/?id=1e21e78bf7a5c24c217446d8760be7b7188711c2)：
其理由是 Linux 线程级调度与 POSIX 进程级接口的语义不同，并非 tombl 删掉了
其它架构的正常实现。不能将这一局部核查泛化为全仓库没有其它删改。

musl 实验提交 `ab35b7d5` 已用后续 `f7f31459` 撤回；两者均保留公开 Git 历史，
没有 force-push、删除或重排已发布提交。已核对撤回后整个源码树与 `59301bde`
净差异为零。本项目 gitlink、distro rev/hash 和 SDK 从未固定该实验函数体；
该次排查结束时继续固定 `59301bde`，没有新增公共函数、头文件或通用包装，
也不宣称新的实时调度能力。后续架构编号增量与该调度实验分别记录。

2026-10-23 又一次误判发布 `ae2f7e47` 并短暂集成到 distro `8d14095`，
随后以 `631d5a2e` 追加撤回；已核实完整源码树与当前基线 `e12bb18e` 相同。
主仓库 `b534377` 重新固定原基线，distro `128b1e6` 撤回构建入口及负载，
不改写公开历史。与上一次不同，这次候选曾进入 pin，不能写成“从未集成”；
对应 CI 即使通过也不能证明 POSIX 语义正确，不计为新能力。详见
[本轮撤回记录](process-syscalls.md#调度候选复核与撤回不计为新增能力)。

## 现有 fchmodat 的 flags 分支接入

`d950af5c` 相对上述 `59301bde` 的整个净差异仅为现有 Wasm 架构 syscall 表：
补齐标准号 `__NR_fchmodat2=452`，并将编号范围计数与固定 Linux 的 472 对齐。
这不是为 472 个调用作支持声明，也没有添加所有新 Linux 接口的包装。
公开历史中的调度实验及撤回记录保留，其净源码差异为零；没有通过改写历史隐藏它们。

tombl/musl 原有 src/stat/fchmodat.c 已包含 SYS_fchmodat2 调用分支，原来因 Wasm
编号缺失而未编译进入该路径。补齐编号后，既有 fchmodat 接口可将 AT_EMPTY_PATH
等 flags 传给当前 Linux 内核；无 flags 的旧 syscall 路径、内核 ENOSYS 后的
兼容 fallback、函数体、公共声明与 flags 常量均保持不变。不新增 fchmodat2
包装函数、头文件或项目专有应用 API；新增的标准编号宏只用于已有接口的架构调用。

## SysV IPC 的 Wasm 架构元数据布局

`a0c027a4` 只增加 arch/wasm32/bits 的 ipcstat/msg/sem/shm 架构定义，复用 musl
已有 riscv32 的 time64 wire-prefix 与追加公开时间字段约定。wasm64 保持原有
generic 布局；src/ipc 的 msgctl/semctl/shmctl 函数体和公共函数集合不变，没有
新增公共头文件 API 或通用包装。shm 布局定义用于让既有 time64 转换代码正常
构建，不意味着内核已支持共享 backing。

旧 wasm32 generic IPC 结构与内核线格式不匹配，例如 msg_cbytes 原偏移为64，
内核要求60。修正后原样 libc 完成时间转换；固定内核 UAPI、双位宽小型 Wasm
执行和旧布局失败控制已核对，包含超过32位的时间值。这是 wasm32 IPC ABI
修正：使用相关结构的旧对象、静态库和程序必须与新 SDK/libc 一起重新编译，
不能混用旧布局对象与新 libc。wasm64 布局未改变。完整目标另行验收。

后续双位宽真实目标在 IPC_STAT 返回 EINVAL，发现还缺少原生控制命令约定。
`7eade118` 在 syscall_arch.h 声明内部 IPC_64=0，沿用 musl 已有 RISC-V 做法：
asm-generic 原生入口直接使用 IPC64 结构，不再把旧式0x100命令位传给内核。
wasm32 公共 IPC_STAT 中的 time64 标记仍由原样 libc 剥离并触发字段转换；
wasm64 仍使用原有结构。src/ipc、公开函数和公共头文件 API 不变。
回归另行执行固定内核的原生分派函数，避免测试再次错误假设内核接受命令258；
修复后的完整目标仍单独跟踪，不能将这项小型执行当作实际 IPC 已通过。

## 信号替代栈执行兼容候选

`e12bb18e` 沿用既有 sigaltstack 包装和 signal.h，仅修改已有
src/signal/wasm32/restore.c：通过内部版本化执行导入填充/返回 ucontext 的
stack 与 mask；引擎寄存器仍保持不透明。回调返回前复制对象，非局部跳转跳过
该提交路径；旧内核缺少上下文扩展时保留先前最小 context。不新增公共函数、
公共头文件 API、通用 Linux 包装或用户应用专有入口；标准程序仍调用原 libc
接口，SDK 链接配置负责导出可变的 C 栈全局。

真实的注册/在栈校验与回调栈切换分别属于 Linux 和宿主执行 ABI，不是在 libc
假装 syscall 成功。主负载五阶段、无栈导出模块及已有 fork 的双位宽六路 Node
均已核实阶段和关闭门禁；浏览器和应用结果分别记录，边界与实际证据见
[第三十组](process-syscalls.md#第三十组标准-sigaltstack-与版本化信号-c-栈执行候选)。

后续通用 ptrace 的接入只修改内核，不需要改动现有 libc：src/linux/ptrace.c
使用的内部 syscall 宏本来就转换机器字参数，不能将其误判为公共 varargs
函数而另加冗余 Wasm 分支。本次集成仍固定 `e12bb18e`，不新增函数/声明。
