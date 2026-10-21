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
| `__wasm_fork_syscall_abi` | syscall 扩展标识，`() -> i32`，必须返回 1 |
| `__wasm_fork_descriptor` | syscall 扩展，`() -> uintptr_t`，初始化并返回保存区 descriptor |

`pid_t` 和 checkpoint 返回值在双位宽下均为 i32；wasm64 的地址及 raw clone 的 long
返回值跨 JS 边界使用 BigInt，不可通过无符号位运算截断。

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

当前只接受 `(SIGCHLD, 0, 0, 0, 0)`；未使用的第六寄存器忽略。其他组合返回
`EOPNOTSUPP`，绝不回退到回调式 clone。musl 通用 `_Fork` 保持原来的
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
宽度截断。当前只接纳 flags=0、exit_signal=SIGCHLD，其余字段全部为零的单线程
默认栈 fork；仍通过已有 continuation 与真正的 Linux 回调 clone 完成进程创建。
没有新增内核 syscall 号、Linux UAPI 结构或应用专用函数。

输入先有界拷贝、验证，再初始化 continuation descriptor。最小长度 64，已知字段
88 字节；较短结构补零，较长结构的未知尾部必须为零，长度不得超过当前架构的
64 KiB PAGE_SIZE。坏地址返回 EFAULT，过短或选定结构性错误返回 EINVAL，超长或
非零未知尾部返回 E2BIG，其他未支持形态返回 EOPNOTSUPP。这里不是完整 Linux
clone3 flags/错误优先级兼容承诺；不支持 alternate stack、CLONE_PIDFD、tid/TLS、
cgroup、namespace、线程创建或多线程 fork。

恢复现场时完成已接纳请求，不重新读取可能已被帧保存机制改写的参数。忙碌／重入
和 signal callback 仍受原有状态机约束。未启用可选执行对象的 v2 请求拒绝；旧
callback import 对 clone3 返回 ENOSYS，不再把未能保存用户现场的请求送入内核。
raw caller 仍须自行承担 libc post-fork 收尾，不自动获得 fork() 的 atfork/锁处理。

此为已实现待目标验收的增量：本地双位宽状态机及原始调用语料已接入，真实 Node
与浏览器支持结论见[进程 syscall 验收](process-syscalls.md)，不能只凭此协议定义推定。

入口处的 Wasm 执行适配器完成 unwind，再以现有非空回调 clone 进入真正的 Linux
进程创建路径。PID、资源继承、信号、退出与 wait 不是由适配器仿造；
这仍是架构执行 ABI 的增量支持，不代表内核已有通用硬件式执行现场快照。
libc 仍负责 atfork、锁和子线程状态收尾；绕过 libc 的 raw syscall 不会自动得到这些封装。

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
