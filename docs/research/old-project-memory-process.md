<!-- SPDX-License-Identifier: MIT -->

# 旧项目内存与进程机制参考

状态：**历史设计研究，不是当前架构规范**。

本文件整理用户提供的《旧项目_调研_futex_mmap_fork_uuidd.md》。原调研基于
`mywebvmx/oldcore.wasm`、WAT、asm.js和JavaScript胶水的静态分析。原始工件未纳入本
仓库，本次也没有验证其完整版权和第三方来源，因此这里只记录可独立验证的行为与设计
启发，不复制实现代码。

## 历史架构前提

旧项目运行i386 Linux用户态，并由解释器执行guest指令。所有guest访存经过64字节TLB
和4 KiB二级影子页表；每个guest页使用独立backing。wasm和asm.js双后端共享固定
700 MB `SharedArrayBuffer`，浏览器Worker承担线程、时钟和异步I/O协调。

这与当前项目不同：当前目标是Linux `arch/wasm`上的原生Wasm用户程序，保持
`CONFIG_MMU=n`和普通direct pointer基线，只让确实需要虚拟地址语义的mapping进入
managed路径。旧项目可以证明某些机制可行，但不能证明它们适合当前ABI或性能模型。

## 适用性判断

| 主题 | 旧项目证据 | 对当前项目的用途 | 不能直接沿用的部分 |
|---|---|---|---|
| futex | WAIT、WAKE、REQUEUE、CMP_REQUEUE、WAKE_OP、WAIT_BITSET | 等待队列、超时、EINTR和唤醒测试 | 不重做Linux已有的generic futex语义 |
| futex_waitv | syscall表止于408，调用返回`ENOSYS` | 证明旧项目依赖用户态回退 | 没有可移植的waitv实现，不能解释当前`EFAULT` |
| mmap | 每进程影子页表、页backing、权限和shootdown | managed mapping生命周期与失效协议 | 不能让全部原生Wasm访存退回解释器TLB |
| fork | 重建VMA，文件映射保留inode/offset，匿名页重新提供 | eager copy基线、后续COW和文件backing设计 | i386解释器进程对象布局及固定地址字段 |
| 异步等待 | continuation record、时钟Worker和SAB唤醒 | 浏览器宿主异步I/O与等待实现参考 | 不暴露为新的应用UAPI，不复制私有vtable布局 |
| uuidd | 依赖信号、定时、AF_UNIX、进程退出和清理 | 作为跨子系统回归工作负载 | 不为单个程序增加内核特判 |

## futex与futex_waitv

旧实现说明基本futex可以用“进程内地址键→waiter集合”、明确deadline和调度器唤醒
完成，并正确区分`EAGAIN`、`EINTR`和`ETIMEDOUT`。但当前项目首先应复用Linux generic
futex实现，Wasm架构层只补齐正确的uaccess、原子操作、阻塞和唤醒能力。

当前`futex_waitv`对有效栈地址返回`EFAULT`，与旧项目的`ENOSYS`完全不同。这表明调用
已经进入当前内核实现，优先调查方向应是：

1. syscall参数结构的ABI布局和pointer width；
2. `copy_from_user`对Wasm用户memory的识别；
3. 嵌套`uaddr`的guest地址转换；
4. 对齐、访问检查和跨页处理；
5. private/shared futex key建立。

不应先移植旧等待队列来绕过这一错误。

## mmap与fork

旧项目最值得保留的是mapping生命周期：页表更新后先失效旧TLB，再等待可能正在访问
的执行单元确认，最后才能回收backing。文件mapping保留对象与offset，匿名mapping拥有
独立backing，这些概念可用于当前managed域。

当前第一版`fork()`仍应以正确性优先：复制进程可观察状态和用户memory，允许eager
copy。完成标准语义和失败回滚后，再评估页粒度COW。旧项目的“所有地址始终翻译”不能
成为当前direct pointer路径的前置条件。

## uuidd回归价值

当前基线CI曾在`uuidd`前台进程收到`SIGALRM`后等待退出超时，单独重跑通过。旧调研
显示`uuidd`会同时覆盖AF_UNIX、poll、随机数、时钟、信号、daemon化、pidfile和进程
回收，因此适合作为系统级回归测试。

诊断应观察：

- signal是否送达目标线程及是否被错误继承或屏蔽；
- 阻塞中的poll是否被唤醒并返回`EINTR`；
- handler之后的退出、socket/pidfile清理和父进程`wait`；
- 超时使用guest单调时钟还是host wall clock；
- 测试等待上限是否只是在掩盖调度饥饿。

只有确认是纯runner抖动后才允许有限重试；稳定复现时必须保留失败。

## 许可证和来源边界

在旧工件权属、第三方代码成分和重新许可范围形成书面记录前：

- 可以引用本研究记录中的行为、接口和测试需求；
- 可以依据Linux UAPI和公开规范进行独立实现；
- 不复制`oldcore.wasm.c`、WAT、asm.js、JavaScript胶水或反编译函数体；
- 不把旧二进制生成代码重新标记为MIT；
- 若将来获得明确授权，代码迁移仍须单独审查provenance和目标组件许可证。

## 建议验证顺序

1. 为当前`futex_waitv EFAULT`建立最小、确定性的kernel/userspace测试；
2. 给`uuidd SIGALRM`失败增加足够的进程、信号和poll诊断信息；
3. 恢复direct memory上的匿名映射和明确失败语义；
4. 建立managed mapping元数据、失效和backing生命周期；
5. 先以eager copy完成`fork()`，再用真实工作负载决定COW优化。
