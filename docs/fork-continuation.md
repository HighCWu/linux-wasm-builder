<!-- SPDX-License-Identifier: MIT -->

# 标准 fork：执行现场恢复路线

目标是让普通用户程序从同一个 `fork()` 调用点继续执行：父进程得到子 PID，
子进程得到 0。已有 private-memory callback clone 不是这一接口，不能改名冒充。
保持 `CONFIG_MMU=n`、direct memory 和明确的能力边界，不加入内核 softmmu。

## 已实现的独立机制实验

`experiments/fork-continuation` 使用固定 Binaryen 132.0.0 的 Asyncify 编译后变换，
把活动 Wasm 调用帧序列化到线性内存，再分别恢复父子执行流。不依赖尚在提案阶段的
continuation、栈切换或内存映射功能，也不修改默认工具链、musl、内核或 loader。
实验自有代码为 MIT；Binaryen 仍遵循其 Apache-2.0 许可证。

机制分为以下顺序：

1. 专用实验 import 请求 unwind，先完整退回用户程序的最外层入口。
2. 停止 unwind，此时保存的活动帧已经在线性内存中。
3. 创建子实例，再复制内存，避免实例化时的 active data segments 覆盖继承数据。
4. 恢复实验要求的 `__stack_pointer`，为父子分别准备正数和 0 的返回值。
5. 重新进入相同入口，通过 rewind 恢复到检查点，再返回不同结果。

这不是重新从程序开头执行应用逻辑；变换后的恢复路径跳过已发生的副作用。
实验分别检查单 isolate 内的独立实例和真实 Node Worker 中的子实例。
Worker 用自己的新内存承接快照，不共享父用户程序的 backing。

### 检查范围与本地结果

Clang 18 和 Clang 22、Node 25.9.0 的以下四组实际 Wasm 执行均通过：

- wasm32，`-O0` / `-O2`；
- wasm64 Memory64，`-O0` / `-O2`。

每组包含：

- 间接函数调用、七层递归现场，以及需要保留的局部变量、局部指针和普通全局数据；
- 两次分叉形成四条执行分支，包括子分支再次创建子分支；
- 分叉前副作用仅一次，中间副作用两次，最终副作用四次；
- 子分支先写入并结束后，父分支的保存现场及私有数据仍不变；
- 模拟创建失败后，仅父分支从原调用点取得负错误结果；
- continuation 保存区过小时触发明确 trap，不静默继续；
- 不经变换的模块必须拒绝，省略子内存快照的反向控制必须失败。

独立公开工作流为 `Fork continuation experiment`，使用 Node 24 和 Clang 18，
不构建 LLVM、Linux 或 rootfs。提交 `8760ac4` 的
[公开 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39112743651)
已成功；实际日志确认四组各输出四分支及 Worker、创建失败、溢出和反向控制通过。
这证明上述独立机制，不是 Linux fork 或浏览器兼容性验收。

运行方式：

```sh
cd experiments/fork-continuation
npm ci --ignore-scripts --no-audit --no-fund
CLANG=clang-18 npm test
```

这只编译很小的 freestanding Wasm fixture，不要求本地重建平台。

### 尚未证明的边界

实验检查点不是标准 syscall，没有 Linux PID、wait、文件描述符继承或 libc atfork。
结果中的编号只是实验调度器的身份标识。创建失败是注入结果，不是实际内核 OOM 回滚证明。
子分支有意先执行完毕，再恢复父分支；不证明并发快照或父子同时执行的安全性。

实验不包含 libc、TLS、C++ 异常、setjmp/longjmp、信号处理回调、动态库、可变函数表或
任意 Wasm mutable global 的复制。它不认证 table64，也不访问超过 4 GiB 的地址。
保存区固定 64 KiB；耗尽时的 trap 只是实验的失败关闭，不是最终 `fork()` 错误契约。
尚未测定真实应用的体积、常态调用开销或分叉延迟，不能据此推荐全平台默认启用 Asyncify。

## 已验收的单线程 Linux 接入候选

distro `277932f`、集成提交 `59f4a87` 新增默认关闭的真实 Linux 接入候选，
具体 import/export、保存区和父子恢复顺序见[可选执行协议](fork-continuation-abi.md)。
它通过完整静态链接后的 Asyncify 变换、现有 clone 和标准 musl fork/_Fork 收尾工作，
不修改 Linux，不新增 syscall，也不改变默认 SDK 的 fork 能力。

初版的本地协议检查 13 项通过，整个 kernel 宿主组 226 项通过、零跳过；TypeScript
检查及共享 workload 的 GCC/Clang 原生 Linux 执行也通过。实际目标结论另见下述 CI。

首次目标 wasm32 构建在 musl 编译阶段发现 `_Fork` 头文件声明仍被隐藏，未运行到用户程序。
distro `d03ec28`、集成提交 `db2c477` 已修正可选 profile 的 fork/_Fork 声明，并将补丁
dry-run 加入轻量 CI；默认头文件不变。当前双位宽复验为：

- [wasm32](https://github.com/HighCWu/distro/actions/runs/39119902451)；
- [wasm64](https://github.com/HighCWu/distro/actions/runs/39119906845)。

这两项检查已完整成功，实际日志均确认标准 `fork()` 从原调用点继续执行，
并输出 PID/PPID、TLS、atfork、信号掩码、内存隔离、共享文件 offset、嵌套 fork/wait
通过，以及多线程拒绝后恢复通过，最后输出协议 pass。目标使用 flake.lock 固定的
Binaryen 129，而上述独立机制实验使用 npm 固定的 132.0.0，不能混淆工具版本。

随后 distro `c861163` 为所有用户到内核调用增加重入深度保护，防止 syscall 再入
用户导出时启动 fork unwind；它不只依靠 signal handler 标记。新增双位宽宿主回归
覆盖嵌套调用和异常清理，整组 228 项通过、零跳过，TypeScript 检查通过。
这一加强版的 [wasm32 检查](https://github.com/HighCWu/distro/actions/runs/39120474650)
和 [wasm64 检查](https://github.com/HighCWu/distro/actions/runs/39120478704) 均已成功，
实际日志确认原有标准 fork 场景及多线程拒绝后恢复通过。

### fork 后 exec 的回归扩展

distro `3c3ef61`、集成提交 `06aa801` 加入第二个普通、未经 Asyncify 变换的静态程序，
使用默认 libc。分叉后的子进程先修改旧 TLS，再通过标准 `execve` 替换自身；新程序检查
参数、环境、父子身份和新 TLS 初始化，退出 37，由父进程 wait 并检查自身 TLS 未改变。
同时将 TLS 测试变量改为 volatile，要求实际读取和写入，避免优化器折叠测试断言。

共享 fixture 的 GCC/Clang 原生检查已通过；目标复验为
[wasm32](https://github.com/HighCWu/distro/actions/runs/39120891535) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39120895108)。双位宽均已完整成功，
实际日志确认新程序的参数、环境、TLS 和身份检查、父进程 wait 以及原有 fork 回归
全部通过，最终输出协议 pass。
首次扩展检查在 Nix 求值时发现原始 initramfs 文件接口格式错误，尚未运行用户程序；
当前提交已修正为文件路径，保留源文件执行权限，不能把这次打包失败解释为 exec 结果。

随后 distro `f2894c6` 新增失败路径回归：子进程先尝试不存在的路径，再两次装载只有
Wasm 头而没有 memory import/入口的文件，分别要求 `ENOENT` 和 `ENOEXEC`。目标上
后者进入 compile_begin/end 后必须在替换程序前中止，保留原 PID/PPID、TLS、栈局部值
和信号掩码。随后再次 fork/wait，最后 exec 普通程序，以检查失败没有污染后续状态。
GCC/Clang 原生检查通过；该扩展的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39121590536) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39121595010) 目标结果待验收，
不能沿用前一版成功结论。

目前只确认显式 opt-in、单用户模块、单线程 C 测试中的标准 fork 语义；默认 SDK、
浏览器、完整 fork 后 exec、C++/SjLj 和其他后续边界不因此变为已支持。

## 接入验收与后续工作

### 一、形成可拒绝的 opt-in 执行 ABI

- 固定入口、checkpoint、unwind/rewind 状态、保存区布局和版本标识。
- 先限制为单线程、单用户模块；旧 loader 和未经变换的模块必须明确拒绝不支持的组合。
- 保存区必须独立于普通 C 栈，检查容量、对齐、地址宽度、越界及重入。
- 梳理栈指针、TLS base、其他 mutable globals 和 table 的完整继承契约。
  不能把实验中只恢复栈指针的做法扩大为任意程序支持。
- 所有可能进入 checkpoint 的调用路径都必须经过变换，包括 libc 和间接调用；
  不能只变换调用 `fork` 的那个 C 文件。

### 二、复用现有 clone 与失败回滚

- 完成用户栈序列化后，再通过已有 Linux clone 创建真实子进程和独立用户内存。
  应用仍调用标准 libc `fork()`，不增加替代 Linux UAPI 的私有应用 syscall。
- 子进程的回调入口只负责恢复继承的 continuation，不作为应用需要手写的替代入口。
- 创建失败只能恢复父进程的错误路径，不发布半初始化子进程，不重复执行用户副作用。
- 保持当前多线程 private-memory clone 的安全拒绝；未经并发快照设计与验证不放开。
- 完成 Worker、内存和保存区的回收；验证失败后父进程还能继续创建子进程。

### 三、恢复 musl 的标准封装并验证系统语义

- 接入 `_Fork` 的子线程身份、TLS、robust list 和线程链处理。
- 恢复标准 `fork` 的信号掩码、锁与 `pthread_atfork` prepare/parent/child 顺序。
- 验证真正的父子 PID、父子返回值、文件描述符共享 open-file-description、退出状态、
  `waitpid` 单次回收、嵌套 fork 和 fork 后 exec。
- 验证信号在 unwind、复制、子发布及 rewind 各阶段到达时不会破坏现场或丢失结果。
  不允许在尚未定义的宿主重入回调里悄悄 fork。
- 对 C++ EH、SjLj、TLS 和浏览器 Worker 分别建立实际目标回归，再扩大支持范围。

### 四、单独处理 vfork 与性能

`vfork()` 的共享地址空间及父进程挂起至子进程 exec/exit 的约束必须单独实现与验证，
不得把普通快照分叉当作已经支持 vfork。已有 `posix_spawn` 路径继续保留。

比较 opt-in 变换与当前未变换基线的二进制大小、无 fork 工作负载吞吐、分叉延迟和
峰值内存。只有在实际应用收益与代价明确后，才评估默认配置；不以机制实验通过替代
Linux 兼容性、浏览器验收或性能结论。

### 五、多线程进程 fork 的后续准入

以下是待实现路线，不是当前支持声明。普通 fork 的子进程只保留调用线程；
父进程保留所有线程，不复制其他线程的执行 continuation。

- 在 libc 的 atfork prepare 和必要锁准备之后，再请求其他线程停车；不能先停住
  可能持有这些锁的线程。`_Fork` 的独立契约必须另行检查，不能偷偷调用 atfork handler。
- 用独立于被复制用户内存的协调状态记录请求代次、参与者和确认；用 Atomics 建立
  发布及唤醒顺序。单个 Worker 确认不代表整个地址空间已稳定。
- 第一阶段仅接纳能在受控等待点停车的线程。之后再为完整链接程序的计算循环加入
  协作安全点；postMessage/Atomics.notify 不能强制打断正在运行的 Wasm。
- 不得冻结持有快照或 clone 所需内核锁的执行流。阻塞 syscall、futex、信号处理、
  用户内存回写及异步完成都需明确的安全点或写入排除协议。
- 在线程创建/退出、并发 fork、用户内存增长之间建立一致的准入顺序；复制期间还要
  排除其他内核/宿主写入者，不能只暂停用户指令。
- 超时、Worker 退出、复制失败等路径必须先终止或隔离仍可能访问源内存的复制者，
  再释放屏障；恢复父进程不能留下迟到的快照或半发布子进程。
- 浏览器与 Node 共用协议，不阻塞浏览器主线程。分别验证真实 Worker；能力不足时
  保持明确拒绝，不以移除内核的 mm_users 检查替代一致性实现。

即使这一机制完成，多线程 fork 后也保留普通 Linux 的应用锁限制：其他线程持有的
应用锁可能留在子进程中，而持锁线程不再存在。不能据此承诺子进程可安全执行任意库调用。
