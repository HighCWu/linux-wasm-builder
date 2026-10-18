<!-- SPDX-License-Identifier: MIT -->

# 可选 fork continuation v1 执行协议

本协议处于实验阶段，不是已经稳定发布的 Linux UAPI。应用使用 musl 的标准 `fork()`；
下面的 import/export 是工具链、libc 和 loader 之间的版本化执行协议，不是新 syscall。
Linux 的 clone、进程身份、描述符继承、信号、退出及 wait 仍由现有内核处理。

## 构建与准入

默认 musl、SDK 与编译路径不启用。实验包 `fork-continuation` 和
`fork-continuation-wasm64` 使用 `musl.override { enableForkContinuation = true; }`，
在完整静态链接后执行 Asyncify 变换。不得只变换包含 fork 的那个源文件。
只有该可选 musl profile 恢复头文件中的 fork/_Fork 声明，默认安装的头文件保持原样。

loader 只接受 `linux_fork_v1.checkpoint` 这一函数 import。含该 namespace 的模块还必须
导出以下函数及两个 global；缺少导出的模块在装载准入时拒绝，未知 import 不被放行。
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

`pid_t` 和 checkpoint 返回值在双位宽下均为 i32；wasm64 的地址及 raw clone 的 long
返回值跨 JS 边界使用 BigInt，不可通过无符号位运算截断。

## 保存区

descriptor 是两个小端 `uintptr_t`：当前 cursor、保存区 end，字段分别占 4 或 8 字节。
musl 在每次新请求前将 cursor 指向独立的 256 KiB 静态保存区起点。

宿主在新请求时检查 descriptor 边界及对齐、cursor/end 的安全整数表示、保存区边界、
非空、有界大小和不覆盖 descriptor。Asyncify 的越界断言保持开启。
保存区不足目前会 trap；尚未实现把中途 unwind 溢出安全恢复成父可见 errno。

## 一次分叉的次序

1. 标准 musl `fork` 执行 atfork prepare 及既有锁处理。
2. `_Fork` 保存并屏蔽信号，锁定 abort lock，再进入 checkpoint。
3. checkpoint 启动 unwind，不执行子初始化；宿主等待 `_start` 完整返回。
4. 宿主停止 unwind，记录 descriptor、栈指针、TLS base 及子回调表项。
5. 宿主调用 `__wasm_fork_clone`，仍使用当前架构已有的 callback clone 参数布局，
   flags 为 SIGCHLD，不设置 CLONE_VM。
6. 现有 Worker 握手复制用户内存。仅这次 clone 传递 continuation 元数据；
   父返回后删除元数据，不能污染之后的普通 clone 或 exec。
7. 子进程的 `switch_entry` 核对专用回调，不运行该 C 回调；恢复栈指针和 TLS base，
   rewind `_start`，到 checkpoint 停止 rewind 并返回 0。
8. 父进程以 clone 返回的实际 PID 或负 errno rewind 到同一 checkpoint。
9. 双方继续原有 musl `_Fork`/`fork` 收尾：子线程身份/robust list/线程链、锁、信号
   掩码及 parent/child atfork handler 均由标准封装处理。

父子不是重跑应用初始化；经过变换的恢复路径跳过分叉前已执行的副作用。
默认 callback clone 的应用入口和已有 posix_spawn 路径保持原样。

## 明确限制

- 只接受从主 `_start` 执行流发起的请求；普通 clone 回调和信号 handler 中返回
  `EOPNOTSUPP`，不得 unwind 穿过正在执行的宿主/内核回调。
  用户到内核的调用还单独记录嵌套深度，覆盖 syscall 再入其他用户导出的情况；
  正常返回和异常退出均必须恢复深度。
- 多线程进程仍由已有内核 clone 的 mm_users 检查拒绝，返回 `EOPNOTSUPP`；
  不能在缺少一致性快照的情况下放行多线程 fork。
- 当前协议仅覆盖本平台静态 C 配置。任意 mutable Wasm global、可变函数表、动态库、
  C++ EH、SjLj 和浏览器运行仍需专项验证，不能由 Node 单个程序的结果推导支持。
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

distro `d03ec28` 的双位宽目标检查已确认上述测试通过，链接与后续加强版状态见
[fork 路线](fork-continuation.md)。这一结论不能扩展到默认 SDK、任意应用、浏览器或
多线程 fork。原生 GCC/Clang 测试只确认共享 fixture 的 Linux 预期；宿主状态机测试
只确认协议边界，都不能替代实际 Wasm 内核执行。
