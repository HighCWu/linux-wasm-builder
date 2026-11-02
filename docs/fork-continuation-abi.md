<!-- SPDX-License-Identifier: MIT -->

# 可选 fork continuation v1 执行协议

本协议处于实验阶段，不是已经稳定发布的 Linux UAPI。应用使用 libc 的标准 `fork()`；
Wasm 架构移植代码可通过版本化 syscall import 发起请求，不必调用 musl 的私有 helper。
下面的 import/export 是工具链和 loader 之间的版本化执行协议，不是新 syscall。
Linux 的 clone、进程身份、描述符继承、信号、退出及 wait 仍由现有内核处理。

## 构建与准入

默认 musl、SDK 与编译路径不启用。实验包 `fork-continuation` 和
`fork-continuation-wasm64` 使用 `musl.override { enableForkContinuation = true; }`，
在完整静态链接后执行 Asyncify 变换。不得只变换包含 fork 的那个源文件。
只有该可选 musl profile 恢复头文件中的 fork/_Fork 声明，默认安装的头文件保持原样。

旧 checkpoint 路径只接受 `linux_fork_v1.checkpoint` 这一函数 import。
当前 syscall 路径不需要这一私有 import，而用导出 `__wasm_fork_abi` 显式识别。
含该 namespace 或 ABI 导出的模块必须导出以下基础函数及两个 global；
缺少导出的模块在装载准入时拒绝，未知 import 不被放行。
实例化后继续检查版本、初始状态和 global 的指针宽度。

| 名称 | 类型/要求 |
| --- | --- |
| `linux_fork_v1.checkpoint` | `(uintptr_t descriptor) -> i32`，返回 PID、0 或负 errno |
| `_start` | 无参数的主程序入口，也是 rewind 的重入入口 |
| `__wasm_fork_abi` | `() -> i32`，必须返回 1 |
| `__wasm_fork_child_entry` | `() -> uintptr_t`，返回 clone 的专用回调表项 |
| `__wasm_fork_clone` | `() -> long`，通过原有 raw clone 返回子 PID 或负 errno |
| `__stack_pointer`、`__tls_base` | 与用户 memory 位宽一致的 global，用于恢复子现场 |
| `asyncify_get_state` | `() -> i32`，0=正常、1=unwind、2=rewind |
| `asyncify_start_unwind`、`asyncify_start_rewind` | `(uintptr_t descriptor) -> void` |
| `asyncify_stop_unwind`、`asyncify_stop_rewind` | `() -> void` |
| `__wasm_fork_syscall_abi` | syscall 扩展标识，`() -> i32`；1 为旧 clone 扩展，2 才启用 clone3 |
| `__wasm_fork_descriptor` | syscall 扩展，`() -> uintptr_t`，初始化并返回保存区 descriptor |

`pid_t` 和 checkpoint 返回值在双位宽下均为 i32；wasm64 的地址及 raw clone 的 long
返回值跨 JS 边界使用 BigInt，不可通过无符号位运算截断。

Wasm32 的原始指针寄存器跨 JS 边界可以表示为负 Number；loader 按 i32 位模式
恢复无符号地址后才检查 descriptor 的实际内存范围。快照中的栈、TLS 和 descriptor
保留原寄存器表示，恢复 Wasm global/rewind 时不改变位模式。这个规则不适用于
PID、长度或普通 JS 元数据，也不取消当前线性内存边界检查。

最后两个导出是成对启用的 syscall 扩展，不要求旧 checkpoint 模块提供。
新完整链接变换须将 `linux.syscall` 与 `linux.syscall_v2` 纳入 Asyncify imports；仅变换旧 checkpoint import
不足以支持直接 syscall 调用。loader 不能替未变换的程序凭空复制引擎调用栈。

## Linux/Wasm 的 syscall 参数约定

两种入口均沿用 clone 号 220。import 名称明确选择参数布局，不根据 flags 数值或可能的
函数表索引猜测 ABI。

可选 libc profile 的 `linux.syscall_v2` 使用 Linux 默认的五参数 clone 布局：

```c
linux_syscall_v2(SYS_clone, flags, stack, parent_tid, child_tid, tls, unused);
```

当前接纳 SIGCHLD、默认栈，及经可选 helper 门控的 namespace/PIDFD 组合；
无 TID/TLS 更新标志时忽略相关寄存器，PIDFD 输出使用 parent_tid 槽。其它未支持
组合返回 `EOPNOTSUPP`，绝不回退到回调式 clone。musl 通用 `_Fork` 保持原来的
`__syscall(SYS_clone, SIGCHLD, 0)` 调用体，由 Wasm 架构层选择 import。
这不是声称所有 Linux 架构均采用相同参数顺序。

原 `linux.syscall` 保持既有回调布局：

```c
linux_syscall(SYS_clone, callback, argument, flags, parent_tid, child_tid, tls);
```

这不是 x86 或其他架构的 clone 寄存器布局。pthread 的架构层显式使用这一旧 import，
非空 callback 保持原来的回调式 clone；旧扩展保留空 callback 作为“从当前 syscall 调用点恢复”的请求。
首阶段只支持 `(0, 0, SIGCHLD, 0, 0, 0)`，不引入虚构的 SYS_fork 编号。
非空 argument 返回 `EINVAL`；其他未支持的 flags/tid/tls 组合返回 `EOPNOTSUPP`。
未启用 continuation 的程序发起空 callback 请求也返回 `EOPNOTSUPP`，不创建无效入口子进程。
只导入 `syscall_v2` 不会自动启用 continuation；仍须满足上述导出与完整链接变换契约。
v2 除 clone/clone3 外的 syscall 与旧入口使用相同内核调用及 exec 替换处理。

### clone3 的有限 fork 形态

distro `269f4d4` 在 v2 import 接入 Linux 标准号 435：参数为用户 `clone_args` 地址、
字节长度，其余寄存器忽略。结构字段在 wasm32/wasm64 上都是小端 u64，不按指针
宽度截断。基础形态接纳 flags=0、exit_signal=SIGCHLD，其余字段全部为零的单线程
默认栈 fork；下文增加受能力门控的 CLONE_PIDFD 形态。仍通过已有 continuation
与真正的 Linux 回调 clone 完成进程创建。
没有新增内核 syscall 号、Linux UAPI 结构或应用专用函数。

后续 distro `abddde6` 将新执行对象的 syscall 扩展标识升级为 2。仅认识 ABI 1 的
旧 loader 必须在 `_start` 前拒绝新对象，避免把 clone3 直接转发给缺少用户现场的
回调式内核路径。新 loader 兼容 ABI 1 对象的原 clone 功能，但其 clone3 返回
ENOSYS；只有 ABI 2 对象才接入下述解析与恢复。import 名称仍为 syscall_v2，
它选择参数布局，不替代执行对象的能力版本检查。

输入先有界拷贝、验证，再初始化 continuation descriptor。最小长度 64，已知字段
88 字节；较短结构补零，较长结构的未知尾部必须为零，长度不得超过当前架构的
64 KiB PAGE_SIZE。坏地址返回 EFAULT，过短或选定结构性错误返回 EINVAL，超长或
非零未知尾部返回 E2BIG，其他未支持形态返回 EOPNOTSUPP。这里不是完整 Linux
clone3 flags/错误优先级兼容承诺；该初始版本不支持自定义子进程 stack/stack_size
（不是 sigaltstack 的信号替代栈）、tid/TLS、
CLONE_INTO_CGROUP、线程创建或多线程 fork。命名空间传递增量见下节，
不将其与普通 flags=0 的已验收范围混为一谈。

### clone3 的 CLONE_PIDFD 增量

distro `16473c2` 新增仅含 CLONE_PIDFD、exit_signal=SIGCHLD、默认栈、无其他选项
的单线程形态。pidfd 字段保留完整 u64，必须指向当前线性内存内可容纳 int 的
非零地址；wasm32 不截断高位，未对齐地址不额外拒绝。参数拷贝完成后才开始
unwind，保存的是当次接纳的输出地址，恢复时不重读 clone_args。

这要求两个内部能力同时存在：独立执行对象的可选导出
`__wasm_fork_clone_pidfd(uintptr_t)`，以及内核导出 `fork_worker_abort_abi() == 1`。
缺少任一能力则返回 EOPNOTSUPP，且不初始化 descriptor。基础执行 ABI 1、syscall
扩展 ABI 1/2 和普通 fork 的旧对象兼容性不变；旧 loader 已拒绝这一 flags 组合，
不会因新对象的额外导出而错误创建普通子进程。

该 helper 以非空 continuation callback、CLONE_PIDFD|SIGCHLD 和 parent_tid
寄存器中的 pidfd 输出地址调用既有 Wasm clone；不同时启用 CLONE_PARENT_SETTID。
Linux kernel_clone 负责原子创建、pidfd 写回、CLOEXEC 和资源失败清理，不在 JS 中
用 clone 后 pidfd_open 冒充原子性。clone 结果为负或抛异常时也必须清除捕获选项，
不能污染后续普通 fork。musl 没有因此增加函数、头文件或应用 API。

内核 `8319e3950` / `feb624494` 补齐 copy_thread 成功创建 Worker、后续资源分配
失败时的 exit_thread 生命周期：使尚未发布的 Worker 进入不可调度的 abort 状态，
等待其停止访问任务数据的 release/acquire 确认后再释放 bootstrap/task/stack。
改变等待值避免先通知后等待的丢失唤醒；最终确认后不得再 notify 已可释放的内存。
它是 Wasm 内核架构兼容修复，保持 Linux GPL 边界，不添加用户 syscall。

此增量的实际目标验收仍待完成，见[进程 syscall 验收](process-syscalls.md)。

恢复现场时完成已接纳请求，不重新读取可能已被帧保存机制改写的参数。忙碌／重入
和 signal callback 仍受原有状态机约束。未启用可选执行对象的 v2 请求拒绝；旧
callback import 对 clone3 返回 ENOSYS，不再把未能保存用户现场的请求送入内核。
raw caller 仍须自行承担 libc post-fork 收尾，不自动获得 fork() 的 atfork/锁处理。

### flags-first clone 的 namespace/PIDFD 增量

distro `1bf7c36` 在 v2 import 的标准号220入口复用下述 namespace/PIDFD
传输与能力检查，未改动 callback import 的参数解释。legacy clone 按内核
lower_32_bits(flags) 规则使用低32位，不套用 clone3 的完整 u64 flags 规则；
PIDFD 指针仍按模块完整指针宽度验证，不能随 flags 一起截断。

要求 stack=0、CSIGNAL=SIGCHLD。支持范围不含 PARENT_SETTID、CHILD_SETTID/
CLEARTID、SETTLS 等标志，因此未请求更新的 parent_tid/child_tid/TLS 寄存器
按 Linux 忽略，不能因为短 syscall 调用中未使用寄存器非零而拒绝普通 fork。
CLONE_PIDFD 使用 parent_tid 槽并验证可写 int 的非零范围；第六寄存器忽略。
clone3 的结构与有限形态规则保持原样，不能把 legacy 的高位忽略规则用于它。

只在首次调用解析并捕获选项；parent/child rewind 完成此前接纳的请求，不再
用可能已变化的寄存器决定另一次 clone。负值与异常清理继续共用既有状态机，
无可选执行支持时先拒绝。独立目标将 clone3 与 flags-first clone 各运行三阶段，
固定1bf7c36的双位宽 Node 六阶段、唯一 pass 与关闭门禁现已核实通过。
这不覆盖后续原生 clone3/TID 增量或浏览器。

### clone3 的命名空间传递

distro `7273efc` 为 syscall 扩展 ABI 2 对象增加可选内部执行导出
`__wasm_fork_clone_namespaces(uintptr_t namespaces, uintptr_t pidfd)`。
应用仍调用标准 clone3 syscall，无新增 libc 函数、Linux UAPI 或应用入口。
参数只保存已验证请求的 namespace 标志和可选 PIDFD 地址；新 helper 调用
原 callback clone，把这些标志与 SIGCHLD/可选 CLONE_PIDFD 交给 Linux。

可传递 CLONE_NEWNS、NEWUTS、NEWIPC、NEWUSER、NEWPID、NEWNET、NEWCGROUP，
掩码0x7e020000。内核负责配置、权限、组合合法性及失败回滚，传递能力不等于
所有命名空间都已启用；例如当前官方默认 USER_NS=n 保留。该旧传输中的
CLONE_NEWTIME 与 clone 的 CSIGNAL 位重叠，返回 EOPNOTSUPP，不截断/悄悄忽略；
后续原生 clone3 的独立准入见下文。自定义栈、TLS、CLONE_INTO_CGROUP 和
线程/多线程 fork 仍未接纳，TID 的后续传输也见下文。

缺少可选 helper 时在 descriptor 初始化前拒绝。与 PIDFD 组合仍要求内核的
Worker abort 能力；旧对象普通 fork/PIDFD 路径保持。参数只复制一次，unwind
后不重读；clone 负值或异常都清除 namespace/PIDFD 选项，之后普通 fork
不得携带它们。child rewind 仍完成已接纳请求，命名空间身份来自 Linux task，
不是宿主伪造 PID/hostname。独立目标覆盖 UTS/IPC/PID、权限拒绝与恢复，
固定7273efc的双位宽 Node 三阶段与关闭已核实，后续1bf7c36的两种 syscall
六阶段也已核实，见[进程记录](process-syscalls.md)。

此为已实现待目标验收的增量：本地双位宽状态机及原始调用语料已接入，真实 Node
与浏览器支持结论见[进程 syscall 验收](process-syscalls.md)，不能只凭此协议定义推定。

上述旧传输在 Wasm 执行适配器完成 unwind 后，以非空回调 clone 进入真正的 Linux
进程创建路径。PID、资源继承、信号、退出与 wait 不是由适配器仿造；
这仍是架构执行 ABI 的增量支持，不代表内核已有通用硬件式执行现场快照。
libc 仍负责 atfork、锁和子线程状态收尾；绕过 libc 的 raw syscall 不会自动得到这些封装。

### 原生 clone3 返回路径与 TID 输出

Linux `60908a259`、distro `92d79a5` 为通用 `kernel_clone()` 的无回调形态补上
Wasm 子进程返回路径。`copy_thread()` 对这种请求要求当前仅一个 mm 使用者、
默认栈、无 CLONE_VM/SETTLS，并从内部 `user_fork_v1.entry` 获取已暂停的入口。
没有入口时在创建 Worker 前返回 EOPNOTSUPP；不是把空 fn 留到子任务 BUG。
新任务仍通过 Linux 的 schedule_tail、既有私有内存快照和执行恢复回到用户态。

`native_clone3_fork_abi()==1` 和独立执行对象可选导出
`__wasm_fork_clone3_native` 必须同时存在，才把已接纳的 clone3 请求交给通用
syscall435。helper 的规范化结构位于静态存储区，88字节、aligned-u64 字段，
不借用已经 unwind 的活动 C 栈。内部入口只在当次父端快照存在、直接内核调用
深度和信号深度满足要求时可用，重入不得借用；负返回与异常都清除捕获选项。

legacy clone 的标准号220保持不变。独立 helper `__wasm_fork_clone_options`
使用原有 callback clone 传递 namespace、PIDFD 和 TID 选项，不改成 syscall435；
这一条不要求新内核的原生 clone3 能力。旧执行对象和旧内核保留原有形态的
回退；缺少相应传输时拒绝新增 TID 请求，不能悄悄丢失标志。

新增 CLONE_PARENT_SETTID、CLONE_CHILD_SETTID、CLONE_CHILD_CLEARTID 传递，
TID 写入和相应错误行为由 Linux 原实现决定，JS 不代写。clone3 的 pidfd、
parent_tid、child_tid 分别保留；legacy 的 PIDFD/parent_tid 共用槽位，别名
冲突由 kernel_clone 拒绝。wasm32 不截断结构中的高位 TID 地址。私有内存的
子进程清理不会变成父子共享的 futex/TID 通知；没有扩大为 CLONE_VM、TLS、
自定义栈或多线程 fork。raw caller 的 libc 收尾责任保持不变。

本地状态机、实际编译的双位宽 C helper 传输、类型和静态分析已通过。
固定92d79a5的双位宽Node实际十阶段、唯一pass及关闭现已核实，完整fork回归
32位也通过；64位原任务下载失败，获取修复e6b13da的同运行层独立重试现已核实
十二阶段与关闭，原失败记录保留。上述证据不扩大为浏览器或后续所有版本验收。
musl 和默认 LLVM pin 不变，无新增 Linux syscall、libc 函数或应用 API。

### clone3 高位 flags 与 CLEAR_SIGHAND

distro `7233d8c` 新增可选内部导出 `__wasm_fork_clone3_flags64`，flags 参数在
wasm32/64均为 i64，其余三个地址参数保留 uintptr_t 宽度。旧
`__wasm_fork_clone3_native` 保持原签名及低位标志范围，避免给旧 wasm32 helper
传入 BigInt/i64 或把高位截断。高位请求必须同时具备宽传输与原生内核能力，
否则在 descriptor 初始化前拒绝；普通旧对象仍可用原来的低位传输。

该版只新增 CLONE_CLEAR_SIGHAND（1ULL<<32）。Linux 原 copy_sighand 清除
自定义处理器并保留 SIG_IGN，运行层不修改 sigaction 表冒充该行为。
CLEAR_SIGHAND 与 SIGHAND 冲突按 Linux 返回 EINVAL；没有启用共享处理器、
CLONE_VM、多线程 fork 或其它高位标志。legacy clone 仍使用低32位规则。
捕获的高位值只属于当次请求，负返回和异常清理后不得污染下一次普通 fork。

固定7233d8c的独立 `clone-flags64` 双位宽Node目标现已核实三个完整阶段、唯一
pass与关闭，覆盖默认信号真实终止、IGN保留、冲突拒绝、PIDFD回收及后续普通
fork；范围不推广为浏览器或其它flags。实际证据见[进程记录](process-syscalls.md)。

### clone3 原生时间命名空间

distro `a630876` / 集成 `390297e` 在原生路径接纳 CLONE_NEWTIME（0x80）。
沿用宽 flags helper 的 i64 参数和规范化 clone_args，保持 exit_signal=SIGCHLD。
新增内部 `__wasm_fork_clone3_features()->i32` 的 bit0 作为执行对象准入标记；
同时要求宽 helper 与内核原生能力。旧对象缺少标记时在 descriptor 初始化前
返回 EOPNOTSUPP，不能把该位送进旧 clone 的 CSIGNAL，也不能忽略后继续 fork。
旧 pointer-width helper 和 legacy clone 的范围、签名保持不变。

Linux 原 copy_time_ns/timens_on_fork 负责创建、进入、偏移复制和冻结；权限、
PIDFD/TID 输出及失败回滚沿用内核。可组合现有 namespace、TID、PIDFD 和
CLEAR_SIGHAND，但不新增 libc 函数、应用入口、共享内存或多线程 fork。
本轮未改内核：当前 TIME_NS 已按官方默认启用，所需通用路径原已存在。

391项运行层检查、两套类型检查、实际编译的双位宽执行对象参数检查，以及
GCC/Clang 前端与双位宽 Wasm 静态分析通过。标准 C 消费者通过 procfs 核对
不同时间命名空间，在 unshare 配置偏移后再 clone3，核对 monotonic/boottime
及绝对定时；随后验证非特权 EPERM、输出不变与普通 fork 恢复。消费者不在
宿主执行命名空间操作。固定a630876的两项Node目标现已独立核实实际三阶段、
唯一pass和关闭门禁，接受上述双位宽范围，不扩大为浏览器；精确日志见
[目标验收](process-syscalls.md#远端复制的双位宽node与四路浏览器验收)。

### clone3 直接创建到 cgroup

distro2c48032 / 集成c868659接通CLONE_INTO_CGROUP（1ULL<<33）。Linux原有
clone3/cgroup路径负责目标fd、权限、控制器准入、子进程归属和失败回滚；
本轮移除的是执行适配层的额外拒绝，没有新增syscall号或内核cgroup实现。

clone_args必须达到VER2的88字节，cgroup字段保持u64且不得超过INT_MAX，
未请求该标志时忽略此字段。快照前从单次复制捕获fd，rewind时不重新读取。
新对象提供独立__wasm_fork_clone3_cgroup导出，flags和cgroup均为i64，其余
指针保持目标位宽；同时要求原生内核能力及features的bit1。缺少导出/标记的
旧对象在descriptor初始化前拒绝，原有宽helper保留签名并拒绝此新标志，
不会因缺少参数误用fd0。负值或trap后清除捕获状态，普通fork不继承目标组。

真实双位宽语料将验证PIDs上限拒绝、错误fd和短结构、无子进程/PIDFD泄漏，
出生后首次用户观察已在目标组、父组不变、PIDFD/reap与普通fork恢复。
运行层397项、两套类型检查、实际编译的双位宽执行对象及消费者前端/静态
分析通过；新目标阶段和关闭仍待验收。未增加musl接口或多线程fork能力。

### clone3 未请求字段的兼容性

distro3a77133 / 集成66f4f99修正原解析器对未使用字段的额外拒绝。Linux只在
相应PIDFD/TID/TLS标志请求时使用这些字段；未请求时忽略，即使u64值不能
表示为wasm32地址或指向无效位置。已请求的输出仍保留原位宽和地址规则，
默认栈及不接纳set_tid选择的限制不变，不把它们当成可忽略字段。

标准raw clone3语料保留零字段用例，再使用全u64最大值和可写哨兵地址，
要求父子仍正常恢复、哨兵不被写入及单次wait回收。更新同一阶段标记以区分
这一增量，不能用旧版本标记证明新语义。运行层/两套类型检查、双位宽分析与
宿主工作负载检查通过，真实双位宽目标仍待验收。Linux/musl源码不变。

## 保存区

descriptor 是两个小端 `uintptr_t`：当前 cursor、保存区 end，字段分别占 4 或 8 字节。
独立 MIT 执行支持对象在每次新请求前将 cursor 指向 256 KiB 静态保存区起点。
该对象不使用 musl 私有头文件，也不再编译进 musl；其他 libc 可链接同一对象。
rewind 时禁止重新初始化 cursor，以免覆盖继承的活动帧。

宿主在新请求时检查 descriptor 边界及对齐、cursor/end 的安全整数表示、保存区边界、
非空、有界大小和不覆盖 descriptor。Asyncify 的越界断言保持开启。
保存区不足目前会 trap；尚未实现把中途 unwind 溢出安全恢复成父可见 errno。

## 一次分叉的次序

1. 标准 musl `fork` 执行 atfork prepare 及既有锁处理。
2. `_Fork` 保存并屏蔽信号，锁定 abort lock，再通过 v2 发起 flags-first clone syscall；
   已有旧模块仍可使用空 callback 请求。
3. syscall 执行适配器启动 unwind，不执行子初始化；宿主等待 `_start` 完整返回。
4. 宿主停止 unwind，记录 descriptor、栈指针、TLS base 及子回调表项。
5. 宿主调用 `__wasm_fork_clone`，仍使用当前架构已有的 callback clone 参数布局，
   flags 为 SIGCHLD，不设置 CLONE_VM。
6. 现有 Worker 握手复制用户内存。仅这次 clone 传递 continuation 元数据；
   父返回后删除元数据，不能污染之后的普通 clone 或 exec。
7. 子进程的 `switch_entry` 核对专用回调，不运行该 C 回调；恢复栈指针和 TLS base，
   rewind `_start`，到 syscall 调用点停止 rewind 并返回 0。
8. 父进程以 clone 返回的实际 PID 或负 errno rewind 到同一 syscall 调用点。
9. 双方继续原有 musl `_Fork`/`fork` 收尾：子线程身份/robust list/线程链、锁、信号
   掩码及 parent/child atfork handler 均由标准封装处理。

父子不是重跑应用初始化；经过变换的恢复路径跳过分叉前已执行的副作用。
默认 callback clone 的应用入口和已有 posix_spawn 路径保持原样。
旧 checkpoint 模块继续使用原 v1 入口；上述 syscall 适配不移除其兼容路径。

## 明确限制

- 只接受从主 `_start` 执行流发起的请求；普通 clone 回调和信号 handler 中返回
  `EOPNOTSUPP`，不得 unwind 穿过正在执行的宿主/内核回调。
  用户到内核的调用还单独记录嵌套深度，覆盖 syscall 再入其他用户导出的情况；
  正常返回和异常退出均必须恢复深度。
- 多线程进程仍由已有内核 clone 的 mm_users 检查拒绝，返回 `EOPNOTSUPP`；
  不能在缺少一致性快照的情况下放行多线程 fork。
- 当前协议仅覆盖本平台静态 C 配置。任意 mutable Wasm global、可变函数表、动态库、
  C++ EH、SjLj 仍需专项验证；浏览器只认证路线文档记录的引擎和配置，不能由 Node
  单个程序的结果推导支持。
- 不提供 COW、不引入 softmmu，不改变 direct memory 的可用地址范围。
- `vfork()` 尚未实现共享地址空间和父进程挂起至子 exec/exit 的语义，不作支持声明。
- fork 后 exec 普通静态程序、exec 拒绝后恢复和上述信号扩展的双位宽回归已通过；
  更多组合仍需分别验收。
  各阶段信号竞态、真实 OOM/超时回滚及长期资源泄漏边界尚未验证。
- 这不是性能结论；Asyncify 的体积和常态执行开销须与未变换基线分别测量。

## 验收入口

真实目标检查是 `fork-continuation-check-runtime` 和
`fork-continuation-wasm64-check-runtime`。测试覆盖主调用点的局部变量、间接递归、
PID/PPID、TLS、atfork、信号掩码、栈/全局/堆/匿名映射隔离、共享文件 offset、嵌套 fork、
退出状态、单次 wait 回收，以及多线程拒绝后恢复。
后续检查另加入 fork 后 exec 到未经变换、使用默认 libc 的程序，验证参数、环境、
新 TLS、父子身份及父进程 wait；该扩展的目标验收状态独立记录，不沿用旧测试结论。
另已加入 exec 拒绝后保留原程序、再次 fork 及成功 exec 的回归，状态见下述路线。
信号扩展另检查 pending 不继承、handler 和掩码继承、信号回调中 `_Fork()` 的明确拒绝
及返回主执行流后的恢复；exec 后保留掩码并重置捕获 handler。原生及旧目标结论不能
替代这项扩展的实际 Wasm 验收，也不能证明全部信号竞态安全。

distro `d03ec28` 首先通过双位宽基础 fork 目标检查；后续 exec、失败恢复和信号扩展
在各自提交独立验收。`c0d0e94` 的 Chromium 149.0.7827.55 / Firefox 151.0 已在
wasm32/wasm64 上各完成两轮同一 corpus 及关闭检查，链接与具体边界见
[fork 路线](fork-continuation.md)。这些结果不扩展到默认 SDK、任意应用、未测浏览器或
多线程 fork。原生 GCC/Clang 测试只确认共享 fixture 的 Linux 预期；宿主状态机测试
只确认协议边界，都不能替代实际 Wasm 内核或浏览器执行。
