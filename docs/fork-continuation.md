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
[wasm64](https://github.com/HighCWu/distro/actions/runs/39121595010) 分别验收。
双位宽已完整成功，实际日志均确认拒绝后保留原程序、再次 fork/wait、成功 exec 和
原有回归通过，最终输出协议 pass。

### 信号继承与回调准入回归

distro `72216c8` 的 workload 扩展在 fork 前屏蔽并排队 SIGUSR1，要求子进程不继承父
pending 信号，子进程自己的信号也不能消费父 pending。父子各解除屏蔽一次，验证继承的 handler
执行，再恢复原掩码。目标 handler 还调用 `_Fork()`，要求明确返回 `EOPNOTSUPP`，
不得 unwind 穿过正在执行的内核/宿主信号回调；返回主执行流后仍须能够再次 fork。
新程序另检查 exec 保留阻塞掩码、将原来捕获信号的 handler 重置为 SIG_DFL。

GCC/Clang 原生检查验证 pending、handler 与 exec 的 Linux 预期；不在原生 handler 中
要求 `_Fork()` 被拒绝，因为那是当前 Wasm 执行 ABI 的限制。这一扩展的实际 Wasm
结果必须单独验收；它也不证明 unwind/复制/子发布各阶段随机信号竞态已全部覆盖。
目标复验为 [wasm32](https://github.com/HighCWu/distro/actions/runs/39121947248) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39121950640)。双位宽均已完整成功，
实际日志均确认上述信号扩展和原有 fork/exec 回归全部通过，最终输出协议 pass。

### 浏览器专项验收

distro `c0d0e94`、集成提交 `0301bc4` 新增独立浏览器检查，直接复用上述 Node 检查的
initramfs 和对应位宽 kernel，不重写应用逻辑。使用仓库固定版本的 Playwright 浏览器
运行库和独立运行器逐项检查输出；既有浏览器测试入口保持原有行为。

- [wasm32 / Chromium](https://github.com/HighCWu/distro/actions/runs/39123919317)
- [wasm32 / Firefox](https://github.com/HighCWu/distro/actions/runs/39123922920)
- [wasm64 / Chromium](https://github.com/HighCWu/distro/actions/runs/39123927247)
- [wasm64 / Firefox](https://github.com/HighCWu/distro/actions/runs/39123931316)

四项均已完整成功，实际日志记录 Chromium 149.0.7827.55、Firefox 151.0，均完成两轮
全阶段回归和关闭检查；集成仓库 CI 也已成功。每项要求 cross-origin isolation，
记录实际 browser.version()，检查
pending、PID/TLS/atfork/内存/文件 offset/嵌套 wait、exec 拒绝后恢复、新程序及 exec
信号语义、多线程与信号回调拒绝后恢复的全部输出，不接受仅最终协议 pass。
同一页面连续启动两台独立实例；每次必须等待 machine.closed 和最终控制台处理完成。
宿主反向检查要求每个阶段缺失或出现失败标记时拒绝，不将它当成浏览器执行证据。

对应公开检查入口为 `browser-tests-check-fork-wasm{32,64}-{chromium,firefox}`，例如：

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref YOUR_PUSHED_BRANCH \
  -f heavy-check=browser-tests-check-fork-wasm64-chromium
```

这里验证的是日志记录的固定浏览器引擎版本，不自动等同于用户安装的任意最新版浏览器。
不认证 WebKit、缺少跨源隔离的页面、多线程 fork 或任意应用；本路线保持显式 opt-in、
单用户模块、单线程 C 配置。默认 SDK、完整 fork 兼容性、C++/SjLj 等仍需独立验收。

## 显式启用的实验 SDK

distro `41747ff`、集成提交 `e3bb8e1` 将上述构建配置整理为独立包
`sdk-fork-continuation` 和 `sdk-fork-continuation-wasm64`，不替换默认 SDK。
它们提供 fork-enabled musl、匹配位宽的 sysroot 和所需链接导出；仅提供 C 编译入口，
不据此开放 C++ EH/SjLj 或动态模块。

在 distro checkout 构建选定位宽的包，编译完整程序后显式完成一次变换：

```sh
nix build .#sdk-fork-continuation-wasm64 --out-link result-fork-sdk
result-fork-sdk/bin/wasm-linux-fork-cc -O2 -c main.c -o main.o
result-fork-sdk/bin/wasm-linux-fork-cc main.o -o linked.wasm
result-fork-sdk/bin/wasm-linux-fork-finalize linked.wasm app.wasm
```

`linked.wasm` 不是可交付的 fork 程序；必须对完整静态链接结果执行 finalize，不能只变换
单个 object，也不能重复变换。finalize 使用 distro 固定 Binaryen 与显式标准功能开关，
保留 Asyncify assertions；变换失败保留已有输出，不留下临时结果。运行时需使用实现
`linux_fork_v1` 的对应位宽 loader/kernel。exec 的目标可以继续使用默认 SDK。

现有完整 fork/exec 回归程序现在通过安装后的 SDK 命令分离编译、链接及变换，
不再由测试配方重复拼接 fork 编译参数。宿主新增 4 项 finalizer/接线检查，连同默认
compiler wrapper 共 21 项通过。新路径的目标验收单独记录，不借用旧构建的成功结论：

- [Node wasm32](https://github.com/HighCWu/distro/actions/runs/39127395314)
- [Node wasm64](https://github.com/HighCWu/distro/actions/runs/39127400940)
- [wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39127405118)
- [wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39127408866)
- [wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39127412055)
- [wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39127416009)

首轮六项均因新增 shell 脚本未满足格式门禁而停止，未运行目标程序；`c5a9e38` 已修正，
上述为修正后的 CI，六项均已完整成功；实际日志核实双位宽 Node 全阶段通过，
四个浏览器组合各完成两轮全阶段回归和关闭检查。集成轻量 CI 也已成功。
安装包的 `share/linux-wasm-fork-sdk/profile.json`
明确版本和限制，`build-materials/` 保留新增配方、Binaryen 源码/许可证及默认 SDK
材料链接；这是 Nix store 包，不是可任意搬移的独立 SDK 压缩包。自有新增代码为 MIT，
不改变上游组件许可证。固定 256 KiB 保存区溢出仍会 trap，不承诺性能或多线程 fork。
后续补充更小的独立使用示例，以及体积、常态吞吐、分叉延迟和峰值内存测量。

## 接入验收与后续工作

### 当前推进：版本化 syscall 布局，而不是增加应用专用 API

distro `2759257`、集成提交 `924ac2d` 将新 profile 的 `_Fork` 改为通过已有
`linux.syscall` 发起本架构的 clone 请求，不再调用 musl 私有 checkpoint helper。
MIT 现场保存代码移到独立的 Wasm 执行支持对象，不使用 musl 私有头文件，也不再
编译进 musl。新模块可仅通过 ABI 导出启用，不要求导入 `linux_fork_v1.checkpoint`；
旧 checkpoint 模块保留兼容路径。

Wasm 的既有 clone 参数是 callback、argument、flags、parent_tid、child_tid、tls，
不是其他 Linux 架构的寄存器布局。该版本保留空 callback 表示从当前调用点恢复，
仅支持 `(0, 0, SIGCHLD, 0, 0, 0)`；其他组合、缺少执行支持、信号/内核回调和
多线程快照继续明确拒绝。实际进程创建仍进入原 Linux clone，不新增 syscall 编号。
完整约定见[执行协议](fork-continuation-abi.md)。

该版本新增独立 C 翻译单元直接导入 `linux.syscall`，绕过 libc 的 `fork()` 和 `syscall()`：
验证两次分叉、父子返回、PID/PPID、栈/全局隔离、退出、wait 单次回收，以及拒绝后恢复。
未经变换、使用默认 libc 的 exec 目标另检查相同空 callback 请求明确失败，随后仍可
执行普通 syscall。raw syscall 不会自动执行 libc 的 atfork 或子线程状态收尾。

宿主 kernel 测试共 235 项通过、零跳过，源码 TypeScript 检查通过；相关构建/浏览器门禁/
原生 raw fixture 共 7 项通过，其中原生 shim 含错误子进程身份的反向控制。
这些只是状态机与 fixture 验证，不替代实际 Wasm 结果。新路径公开验收为：

- [Node wasm32](https://github.com/HighCWu/distro/actions/runs/39128728974)
- [Node wasm64](https://github.com/HighCWu/distro/actions/runs/39128734308)
- [wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39128739259)
- [wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39128743343)
- [wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39128747329)
- [wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39128752368)

首轮因固定格式器对单行注释的换行要求停止，未运行目标程序；`61e0a08` 已修正。
上述为格式修正后的 CI，均已失败；已检查的 Node wasm32 日志显示测试项目严格类型
检查的元组推断错误，未运行到目标程序。此前遗漏了独立的测试项目类型检查，不能将
源码检查通过描述为完整类型验收；`924ac2d` 的集成轻量 CI 已通过。

distro `89ca598`、集成提交 `6ffbaab` 修正旧测试及新增测试的元组类型，并显式区分入口：

- 实验 profile 的 `linux.syscall_v2` 使用 Linux 默认 clone 五参数顺序
  `flags, stack, parent_tid, child_tid, tls`；只支持 SIGCHLD 且其余字段为零，忽略第六寄存器。
- musl 通用 `_Fork` 保持上游 clone 调用体，由 Wasm 架构 syscall 层选择 v2 import；
  pthread 回调 clone 显式保持旧 `linux.syscall`，不根据参数值猜测布局。
- 旧 callback/null-callback 及 checkpoint 路径兼容；新 raw fixture 改为直接验证 v2。
  新浏览器阶段要求该路径与已有线程拒绝/恢复检查共同通过，不能仅凭最终 pass 放行。

本地 kernel 242 项全部通过、零跳过，源码和测试两个 TypeScript 项目均通过；
7 项构建/浏览器门禁/raw 原生检查、共享 fork/exec 语料 GCC/Clang 检查、musl 补丁
dry-run 及固定版本格式检查通过。已重新提交双位宽 Node 和四路浏览器目标检查，
实际 Wasm 验收尚待核实；上述宿主结果不能替代它。

本轮目标检查：
[Node wasm32](https://github.com/HighCWu/distro/actions/runs/39129851545)、
[Node wasm64](https://github.com/HighCWu/distro/actions/runs/39129855574)、
[wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39129859785)、
[wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39129863949)、
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39129868970)、
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39129873069)。

其中 Node wasm32 已失败，实际日志确认类型检查和 242 项宿主测试均通过，但目标编译
报错 `no such file or directory: '${execution}/fork-execution.o'`，未执行目标程序。
distro `ab5b9e9` 将 Nix 的字面量 dollar 前缀与对象路径插值分开拼接，并为 SDK 契约检查
增加生成配置中的已求值路径校验。源码契约测试在本地通过，真正的 Nix 求值及目标链接
仍由公开 CI 验证，不将此构建错误描述为 fork 运行语义失败。

这一步不宣称其他 libc 已移植成功、任意 raw clone 组合
已支持、clone3 已实现或默认 SDK 已开放 fork。将两个 syscall import 纳入 Asyncify 会改变
插桩范围，体积和性能仍须重新测量；不能沿用旧 checkpoint 路径的性能假设。

### 一、形成可拒绝的 opt-in 执行 ABI

- 固定入口、checkpoint、unwind/rewind 状态、保存区布局和版本标识。
- 先限制为单线程、单用户模块；旧 loader 和未经变换的模块必须明确拒绝不支持的组合。
- 保存区必须独立于普通 C 栈，检查容量、对齐、地址宽度、越界及重入。
- 梳理栈指针、TLS base、其他 mutable globals 和 table 的完整继承契约。
  不能把实验中只恢复栈指针的做法扩大为任意程序支持。
- 所有可能进入 checkpoint 的调用路径都必须经过变换，包括 libc 和间接调用；
  不能只变换调用 `fork` 的那个 C 文件。

### 二、复用现有 clone 与失败回滚

distro `46a538d`、集成提交 `8cdadd2` 修正了初始化失败 Worker 的所有权漏洞：
此前异步错误路径在 `terminate()` 完成前移出资源集合，终止失败后整机关闭无法重试。
现将该路径与初始化消息发送失败统一为同一清理机制；只有终止成功才释放集合中的所有权，
失败则保留供关闭流程重试，不替换原初始化错误。

本地宿主 kernel 246 项全部通过、零跳过，源码和测试项目的 TypeScript 检查通过。
新增故障注入覆盖延迟终止、同步/异步终止失败及关闭重试、失败清理期间独立启动新 Worker，
另用真实 Node Worker 检查初始化异常后的终止等待。它们验证资源管理边界，
不是在真实 Wasm fork 中注入 OOM，也不是浏览器异常处理或内核进程回滚的完整验收。
本修正单独启动 [Node wasm32 目标复验](https://github.com/HighCWu/distro/actions/runs/39130451276)，
尚待核实；上一节六路 CI 固定在 `89ca598`，不覆盖本修正。

distro `73079b3`、集成提交 `7f1da80` 进一步修正迟到初始化失败的分类：
如果快照超时或分配失败已发布负 errno，之后的初始化异常仍归属于同一失败请求，
保留首个结果并回收 Worker，不误触发整机失败。成功发布之后及普通非快照 Worker 的
错误仍走整机故障路径，不借此屏蔽运行错误。主线程跳过已失败请求并关闭转发端口；
子 Worker 在启动和复制后的检查点提前退出，最终发布仍使用原子一次性判定。

本地 kernel 249 项通过、零跳过，源码/测试两套类型检查和 5 项 SDK 契约检查通过。
新增真实 Node Worker 测试确认父端超时后，迟到一方不能发布成功；这只验证共享状态协议，
不是实际 Linux fork 或浏览器的超时注入验收。取消是检查点检测，不保证立即中断
正在执行的内存复制或等到复制 Worker 完全退出才向父返回；真实 OOM、超时后的完整
内核回滚及所有资源释放仍需单独验证。此提交同时包含上述 SDK 路径修正，先进行
双位宽 Node 复验，再安排四路浏览器，避免重复消耗构建资源。
本轮为 [Node wasm32](https://github.com/HighCWu/distro/actions/runs/39130984682) 与
[Node wasm64](https://github.com/HighCWu/distro/actions/runs/39130988394)，尚待目标结果。

这两项后续均已失败。已检查的 Node wasm32 日志显示对象路径修正后继续到链接阶段，
报错 `import name mismatch for symbol: raw_linux_syscall`，仍未执行目标程序。
原因是执行支持对象与 raw fixture 用同一个 C 符号名声明了不同的 Wasm import。
distro `75d3eae` 为 callback import 使用独立符号 `fork_callback_syscall`，不改变其
`linux.syscall` 名称或参数布局；raw fixture 继续使用 `linux.syscall_v2`。

新增轻量 freestanding 链接回归直接编译这两个实际 C 源文件，检查产物同时包含两个
独立 import，并以重新制造符号冲突作为必须失败的反向控制。本地 Clang 18、22 的
wasm32/wasm64 四组均通过。测试使用最小测试头文件，不链接 libc、不执行 Linux，
不能替代真实 SDK/内核运行验收；已接入主仓库轻量 CI 和可选 SDK 的 wrapper 检查。

distro `e2c7edc`、集成提交 `da80732` 另将原父进程恢复流程提为共同内部函数，保持
原执行顺序：suspend、仅在 clone 期间附加元数据、finally 清除、按结果 rewind。
双位宽宿主测试通过一次性快照状态注入 EAGAIN、ENOMEM、再次 EAGAIN 后成功分叉，
核对错误返回、元数据清除、迟到发布拒绝及后续父子返回；另确认 trap 清除元数据后
继续抛出，不凭空转成 errno。整组 kernel 253 项与源码/测试两套类型检查通过。
这是执行适配器的故障注入，不是实际 Linux OOM、进程表回滚或 wait 回收的完整证明。
已重新启动双位宽 Node 目标复验，浏览器仍待构建与运行链路先通过。
本轮为 [Node wasm32](https://github.com/HighCWu/distro/actions/runs/39134412900) 与
[Node wasm64](https://github.com/HighCWu/distro/actions/runs/39134418533)，尚待目标结果。

上述 `e2c7edc` 双位宽 Node 工作流后续均已成功，实际日志逐项核实 raw syscall 分叉、
标准 fork 的 PID/TLS/atfork/内存/文件/嵌套 wait、信号继承和拒绝恢复、exec 成功及失败恢复、
未变换程序拒绝 raw clone、多线程拒绝恢复和新旧 clone ABI 共存，最终 pass。
这只对应普通运行语料，不覆盖下面新增的故障注入配置，也不代表浏览器复验已完成。

- 完成用户栈序列化后，再通过已有 Linux clone 创建真实子进程和独立用户内存。
  应用仍调用标准 libc `fork()`，不增加替代 Linux UAPI 的私有应用 syscall。
- 子进程的回调入口只负责恢复继承的 continuation，不作为应用需要手写的替代入口。
- 创建失败只能恢复父进程的错误路径，不发布半初始化子进程，不重复执行用户副作用。
- 保持当前多线程 private-memory clone 的安全拒绝；未经并发快照设计与验证不放开。
- 完成 Worker、内存和保存区的回收；验证失败后父进程还能继续创建子进程。

### 独立目标故障注入检查

distro `39819f1`、集成提交 `844c9c0` 新增 `fork-continuation-check-faults` 与 `fork-continuation-wasm64-check-faults`，
使用同一双位宽实验 SDK 构建独立静态 C 初始化程序，直接调用标准 libc `fork()`。
专用 loader 构建通过 `kernel.override { copyFaultTest = true; }` 启用内部固定计划：
只对前两次 private-memory COPY 请求依次注入 Worker 初始化异常和分配路径异常。
前者经过主线程错误回调返回 EAGAIN，后者经过既有复制失败路径返回 ENOMEM。
这不是实际耗尽浏览器/Node 内存，也没有添加 Linux syscall、应用 API、环境变量或
公开 boot 选项。普通构建的计划为空，Worker 中的注入也被 build-time 开关关闭。
计划按每次机器启动创建，不跨机器共享；共享内存线程和内核启动 Worker 不消耗计划。

目标程序要求两次失败均只向父进程返回预期 errno，atfork prepare/parent 收尾、信号
掩码和用户内存保留，`waitpid(-1, ..., WNOHANG)` 返回 ECHILD。随后连续完成八次
正常 fork，检查父子 PID、TLS、栈/全局/堆隔离、子退出状态及单次回收。
失败不得进入子程序分支；最终 pass 后等待 runner 主动关闭，避免 PID 1 提前退出。

本地 kernel 宿主测试 255 项及源码/测试两套类型检查通过，相关 SDK/原生/链接契约
12 项通过。GCC/Clang 原生运行只覆盖八次正常 fork，不执行 Wasm 专用的注入阶段；
另已检查启用注入阶段的 C 语法，以及 build-only 计划的启用、有限次数和按机器重置。
实际双位宽目标故障验收另行进行，未完成前不宣称 Linux 回滚路径已验证。
即使目标检查通过，也不证明全部资源无泄漏、真实 OOM、超时中断或多线程 fork 安全。

本轮独立检查为 [wasm32 faults](https://github.com/HighCWu/distro/actions/runs/39136819311) 和
[wasm64 faults](https://github.com/HighCWu/distro/actions/runs/39136823713)，均固定在上述提交，
两项工作流及对应 Heavy check 后续均已成功。本次读取完整阶段日志仍遇到下载超时，
故先记录 CI 结论，不追加逐阶段已核实、实际 OOM 或完整资源无泄漏的声明。

### 浏览器普通与故障配置共同复验

distro `7d0dad6`、集成提交 `143d962` 将上述故障语料加入既有四路 fork 浏览器检查。
每个 wasm32/wasm64 × Chromium/Firefox 组合先运行普通配置两次，再运行故障配置两次，
均在同一页面创建新机器并等待 `machine.closed`。故障配置使用独立目录中的测试版
loader 与独立 initramfs，普通配置继续使用默认 loader；不修改默认 SDK 或 boot API。
每轮故障配置重新创建两次故障计划，避免前一轮耗尽后误走纯正常路径。

门禁分别要求普通语料全部阶段、故障语料的初始化/分配错误阶段和八次恢复分叉阶段，
以及最终 pass；缺少任一阶段、迟到 fail、pageerror 或关闭失败均拒绝。
本地相关门禁与关闭流程 19 项通过、固定格式检查及 runner 语法检查通过，
这不是浏览器运行结论。四路公开浏览器 CI 已提交，实际引擎版本、阶段及关闭结果待核实。

本轮为 [wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39186168011)、
[wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39186174562)、
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39186180338)、
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39186185620)。

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
