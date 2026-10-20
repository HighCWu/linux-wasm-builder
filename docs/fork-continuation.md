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

上述四路工作流及 Heavy check 后续均成功。已实际核实 wasm64 Chromium
149.0.7827.55 日志：普通配置完整阶段两轮、故障配置的两阶段各两轮及四次关闭均通过。
其余三路完整阶段日志下载超时，暂只记录工作流状态，不标为逐阶段已核实。
原 Node faults 的 wasm32 日志也已核实两阶段通过；wasm64 阶段日志仍待补取。

### 发布前真实超时与迟到子进程拒绝

distro `74f58bf`、集成提交 `352e14d` 在独立测试构建中扩展第三次 COPY 为发布前暂停，
位置在私有内存复制及用户实例准备之后、发布成功的原子 CAS 之前。父端仍调用原有
`wait_user_copy`，使用原来的 30 秒单调时钟截止时间；没有直接注入超时 errno，
也没有缩短普通配置的等待时间。超时写入 EAGAIN 并唤醒子端，子端实际尝试发布，
必须被同一一次性 CAS 拒绝。子端随后写入专用确认，父端等待该确认后才返回 syscall，
缺少检查点、确认或结果错误会使测试失败，不允许静默退化为只测 errno。

专用协调字仅存在于 fault 构建，状态为结果、检查点/确认、超时标签三个字；
默认构建保持原来单字状态、空故障计划和无操作测试钩子。父端等待确认最多 5 秒，
子端发布屏障也有 35 秒防挂起上限；这些只是测试 watchdog，不是新运行时协议。
确认表示迟到发布已经被拒绝，不表示 Worker 已完全退出，也没有补齐生产超时路径中
立即终止正在复制 Worker 的能力。此测试只在副本完成后的发布点暂停，不模拟任意
复制中断、真实 OOM 或多线程一致性。

C 语料检查第三次 fork 返回 EAGAIN、atfork 收尾、身份、信号掩码与内存不变、
无可回收失败子进程，然后完成八次 fork/退出/wait。新增独立控制台阶段同时成为
浏览器故障门禁的必选项。宿主整组 256 项及源码/测试两套类型检查通过，相关故障/
门禁检查 6 项通过；真实 Node Worker 验证暂停、超时发布、CAS 拒绝与确认，并有错误
结果及缺失检查点的反向控制。宿主用例不等待 30 秒，不替代目标的真实截止时间验收。

新一轮 [wasm32 faults](https://github.com/HighCWu/distro/actions/runs/39187832318) 和
[wasm64 faults](https://github.com/HighCWu/distro/actions/runs/39187836214) 已启动，
待核实运行结果后再做同一源码的四路浏览器复验。旧绿色结果不覆盖新增超时阶段。

上述双位宽工作流及 Heavy check 后续均已成功。wasm32 实际目标日志已核实：
初始化/分配错误阶段于 2026-10-19 02:10:47 UTC 通过，约 30 秒后的 02:11:17 UTC
出现发布超时、迟到子端拒绝及父端恢复阶段，随后八次恢复 fork/回收及最终 pass。
runner 仅在用户语料成功且关闭资源无错误后返回成功；这不是仅从宿主测试推导的结果。
wasm64 完整日志下载多次超时，暂只记录工作流成功，不标为阶段已逐项核实。
先前因 wasm64 日志下载问题尚未派发浏览器；后续按用户指示取消定时跟进并直接复验。
wasm64 Node 工作流成功状态再次确认，阶段日志仍超时，不据此扩大已核实结论。
四路浏览器检查固定在 `74f58bf`，不重建 Node，也不再把旧日志下载作为派发前置条件：

- [wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39190466707)
- [wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39190471668)
- [wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39190476374)
- [wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39190481428)

本轮已启动或排队，尚待运行结果。门禁要求普通/故障配置各两轮及关闭，故障配置
包含新增发布超时阶段；本地三项门禁检查再次通过，不替代本轮实际浏览器验收。

本轮后续结果为 wasm32 Chromium、wasm32 Firefox、wasm64 Firefox 成功，实际日志
均已核实普通配置两轮、故障配置（含超时、八次恢复 fork）两轮和四次关闭通过。
固定引擎为 Chromium 149.0.7827.55、Firefox 151.0。wasm64 Chromium 失败日志确认：
普通配置两轮及故障配置第一轮均完成并关闭，第二轮故障配置没有完成，最终触发
300 秒外层 watchdog。不是编译失败，也不能推断为单纯 runner 慢或已定位到内核缺陷。
旧日志没有实时启动/关闭进度，尚不能区分第二轮停在启动、程序执行还是回收。

日志下载现改为先读取重定向及 Content-Length，再以显式起止字节读取尾部，避免整份
数 MiB 编译日志的下载超时。补取的 wasm64 Node faults 日志已核实三阶段及 pass：
初始化/分配错误之后实际约 30 秒才出现超时阶段，然后完成八次恢复 fork。

distro `dc30f4f`、集成提交 `b22ce5a` 只增加测试诊断：每轮 begin、启动前后、实时
用户/启动控制台、关闭前后、pageerror/crash 和外层 watchdog 所在轮次。
诊断回调异常不影响返回输出、pass/失败判定或关闭逻辑；超时长度、两轮要求和阶段
门禁不变。本地相关 21 项测试、固定格式及 runner 语法检查通过。
仅针对 wasm64 Chromium 启动带诊断复验；这是定位性修改，不是已修复第二轮卡住的声明。
本轮 [wasm64 Chromium 定位复验](https://github.com/HighCWu/distro/actions/runs/39203662121)
固定在 `dc30f4f`，运行结果待核实；定时跟进任务保持已取消。

上述定位复验后续成功，实际日志已核实 Chromium 149.0.7827.55 的普通/故障配置
各两轮及关闭通过。两次故障轮次均出现约 30 秒等待、超时发布拒绝、八次恢复分叉。
本次仅增加诊断，未修改 fork 语义，故不能把没有复现卡住写成根因已修复。

### 小规模稳定性复验与当前验收边界

distro `1dd78e5`、集成提交 `05aaa9d` 增加独立检查
`browser-tests-check-fork-wasm64-chromium-stability`。它复用相同 Wasm 程序、引擎和门禁，
在同一页面执行普通/故障配置各四轮，共八次启动与关闭；四次故障轮次仍使用真实
30 秒截止时间，检查初始化失败、分配失败、迟到发布拒绝与恢复分叉。
独立 derivation 显式设置测试 runner 的 `FORK_BROWSER_STABILITY=1`，不只重新请求
已成功的原检查输出。默认检查仍各两轮，未知 profile 拒绝；不增加 SDK/boot 选项。
整体 watchdog 保持 300 秒，每轮运行/关闭的判定不变，不自动重试失败轮次。

本地相关 22 项测试、固定格式和 runner 语法检查通过。独立公开 CI 已提交，
实际八轮运行结果待核实；即使成功，小样本也不能证明无偶发卡住或长期资源无泄漏。
本轮 [wasm64 Chromium 独立稳定性检查](https://github.com/HighCWu/distro/actions/runs/39205889224)
固定在 `1dd78e5`，未恢复定时任务。

上述稳定性检查后续成功，已实际核实 Chromium 149.0.7827.55 的普通配置四轮、
故障配置四轮及八次关闭；四次故障轮次均在初始化/分配失败后等待约 30 秒，完成
迟到发布拒绝与八次恢复 fork。此次小规模复验没有复现卡住，不意味着先前根因已修复。

| 内容 | 当前证据 | 仍保留的边界 |
| --- | --- | --- |
| 标准 fork、raw clone、exec、信号与线程拒绝恢复 | 双位宽 Node 及已记录浏览器语料通过 | 默认 SDK 不启用，静态 C、单线程 opt-in |
| 初始化/分配失败、发布前超时、错误后再次 fork/wait | 双位宽 Node；三路首轮浏览器通过，wasm64 Chromium 定位复验通过 | 是可控故障，不等于真实 OOM、任意复制中断或完全回收证明 |
| 同页重复运行稳定性 | 常规两轮检查、诊断复验及独立八轮检查已核实通过，另有一次 wasm64 Chromium 第二轮卡住 | 根因未定位，小样本重复成功不证明长期无故障 |
| 进一步兼容性 | 已记录支持范围内的实际语料 | 多线程 fork、vfork、动态链接、任意 C++ EH/SjLj、全阶段信号竞态未扩大支持 |

本轮稳定性复验完成并核实日志后，已推进以下受控信号时序测试；
不以增加重复次数替代对再次卡住的定位。

### 三、恢复 musl 的标准封装并验证系统语义

#### 保存现场后、clone 前的受控信号时点

distro `cfc6629`、集成提交 `3964313` 新增独立
`fork-continuation-check-signals` 与 `fork-continuation-wasm64-check-signals`。
测试版 loader 通过 `kernel.override { forkSignalTest = true; }` 启用内部门禁，
默认构建为 false，没有新的用户 import、Linux UAPI、环境变量或 boot 参数。
它在 `suspend()` 停止 Asyncify unwind 并保存元数据之后、真正 clone 调用之前，
通过现有 getpid/kill syscall 向当前父进程发送 SIGUSR1。PID、syscall 参数和返回值
分别检查 wasm32/wasm64 位宽，失败会使测试停止，不能悄悄跳过注入。
调用受现有内核重入保护约束；hook 或 clone 抛错时均清除该次 fork 元数据。

独立静态 C 语料预先屏蔽 SIGUSR1 并安装 handler，连续两次调用标准 `fork()`：
atfork prepare 时要求尚无该 pending 信号，恢复后要求父端 pending、子端不继承；
双方均检查掩码及 handler 状态，父端解除屏蔽后恰好一次递送，子端自发信号再解除屏蔽
验证继承的 handler 和屏蔽状态。每次还核对 PID、atfork 收尾和单次 wait 回收。
不在用户程序内伪造 fork 返回，不通过新应用 API 注入信号。

本地 kernel 宿主 261 项、源码/测试两套类型检查通过；SDK、故障与信号契约共 11 项
通过。GCC/Clang 原生正例和省略注入的反向控制均通过，但原生只在 atfork prepare
末尾排队信号，不能证明 Wasm 保存现场后的精确时点。另有双位宽宿主检查核对
after-suspend-before-clone 顺序、hook 失败时不调用 clone、元数据清理与 syscall 布局。
只有实际目标检查才能验收新时点；它不代表复制中、发布后或 rewind 期间的信号竞态
已覆盖，也不扩大多线程 fork、默认 SDK 或任意 libc 的支持。

本轮 [wasm32 signals](https://github.com/HighCWu/distro/actions/runs/39208723250) 和
[wasm64 signals](https://github.com/HighCWu/distro/actions/runs/39208729699) 固定在 `cfc6629`，
均已成功；实际 Heavy 日志分别核实两个 `fork-signal:` 阶段及最终用户 pass。
这证明双位宽 Node 的受控保存现场时点，不替代其他时点或浏览器的验收。

`59c1600` 将同一信号语料接入现有四路浏览器 fork 检查，使用独立的
`kernel.override { forkSignalTest = true; }` loader 与 signals initramfs；普通、故障、
信号配置不混用 loader，默认内核和 SDK 均不变。每路在同一页面分别运行三种配置
各两轮，每轮必须包含对应语料的全部精确阶段，且等待 `machine.closed` 完成。
原有稳定性配置仍对普通/故障各跑四轮，信号配置固定两轮；外层 300 秒 watchdog
与页面错误门禁不放宽。信号阶段缺失、普通/故障输出冒充、带前缀输出或迟到失败
均由宿主反向门禁拒绝。

本地浏览器相关契约 40 项、SDK/故障/信号契约 11 项、运行及关闭语义 18 项通过；
固定版本格式检查通过。它们不单独证明浏览器实际运行结果；定时任务未恢复。

固定在 `59c1600` 的四路浏览器运行均已成功且实际 Heavy 日志已核实：
[wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39212115655)、
[wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39212123583)、
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39212129762)、
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39212135695)。
四路分别通过普通/故障/信号各两轮的完整阶段门禁及关闭，共 24 次启动/关闭。
每路故障两轮均包含真实 30 秒发布超时及八次恢复 fork；信号两轮均核对两个
`fork-signal:` 阶段。引擎为 Chromium 149.0.7827.55、Firefox 151.0。
该结果只覆盖当前受控 clone 前信号时点，不代表任意恢复阶段竞态或此前偶发卡住
的根因已经修复。

#### clone 成功后、父端 rewind 前的受控信号时点

distro `f198df0`、集成提交 `205e36c` 增加独立
`fork-continuation-check-resume-signals` 与
`fork-continuation-wasm64-check-resume-signals`。测试版 loader 只启用
`kernel.override { forkResumeSignalTest = true; }`，默认仍为 false；构建层拒绝
同时开启 clone 前和 clone 后两种注入，以免信号合并掩盖时点错误。

clone 返回正的子 PID、父端临时快照元数据已清除之后，且尚未调用
`resumeParent()` 开始 Asyncify rewind 之前，通过现有 getpid/kill 向父进程排队
被屏蔽的 SIGUSR1；clone 负错误或抛错时不注入。它不访问子 Worker，也不要求
子进程此时已经执行或退出；不是新的 Linux syscall、用户 import 或应用 API。
注入异常会使测试失败，不伪造成功，也不声明此时已有子进程的异常可作为 fork errno
恢复。

语料与 clone 前测试共享 C 源码，分别编译；新增宏只选择不同阶段标记和原生基线
注入位置，不在 Wasm 用户程序内注入。连续两次标准 fork 检查父 pending、子不继承、
掩码及 handler、解除屏蔽后恰好一次递送、PID、atfork、单次 wait 和栈/TLS 标记。
新增精确阶段为 `post-clone pre-rewind parent pending and child isolation pass` 与
`two post-clone forks, stack, TLS and single delivery pass`，均带 `fork-signal:` 前缀。

本地 kernel 宿主 268 项、源码/测试两套类型检查、相关契约 20 项通过；
固定版本格式检查通过。GCC/Clang 原生正例和省略注入的反向控制均通过，但原生
只能在 atfork parent 中排队信号，不能证明 Wasm pre-rewind 时点。双位宽宿主检查
另核对 suspend→clone→注入→rewind 顺序、元数据清理、负 errno 不注入和后续复用，
以及 clone/注入异常不启动 rewind。

本轮先完成双位宽 Node 真实目标验收，不能复用 `59c1600` 的浏览器结果作为
新增时点的验收。它只覆盖被屏蔽信号跨父端恢复边界的保留和
随后递送，不证明 rewind 内任意时刻的异步中断、复制期间信号、完整多线程 fork
或其他 libc 已支持。默认 SDK、内核配置和应用 API 均不变。

固定在 `f198df0` 的 [wasm32 resume-signals](https://github.com/HighCWu/distro/actions/runs/39217577300)
与 [wasm64 resume-signals](https://github.com/HighCWu/distro/actions/runs/39217584314)
均已成功，实际 Heavy 日志分别核实两个新增 `fork-signal:` 阶段与最终用户 pass。

`7a29e67` 随后将此语料接入四路浏览器检查。新增 `resume-signals` 仅是测试模式，
使用独立的 `forkResumeSignalTest = true` loader 和匹配的 initramfs；不与 clone 前
信号 loader 混用。每路同页依次运行普通、故障、clone 前信号、clone 后信号四种
配置各两轮，新增两轮必须包含 post-clone pre-rewind 与 stack/TLS/single-delivery
两项精确阶段且完成 `machine.closed`。原有稳定性配置对普通/故障各四轮不变，
两个信号配置均固定两轮；300 秒外层 watchdog、页面错误与迟到失败检查不放宽。

本地浏览器、SDK/故障/信号、运行及关闭契约合计 73 项通过；固定版本格式检查通过。
反向门禁确认两个信号配置不能相互冒充，缺阶段、带前缀输出和迟到失败均不能通过；
loader/initramfs 选择与跨源隔离要求另有执行检查。真实浏览器新增时点结果待核实，
宿主测试不替代浏览器验收；默认 SDK、内核与公开应用 API 不变。

固定在 `7a29e67` 的四路浏览器检查结果如下：
[wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39230648311)、
[wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39230659107)、
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39230668048)、
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39230676723)。
wasm32 两路和 wasm64 Chromium 已成功，实际 Heavy 日志核实四种配置各两轮、完整
阶段门禁及关闭。wasm64 Firefox 失败，不能声明四路验收完成：普通两轮、故障第一轮
全部通过并关闭；故障第二轮输出初始化/分配失败阶段后约 21 秒，内核报告
`rcu_sched detected stalls`，涉及 CPU 1（`0 ticks this GP`），随后主端收到 Worker
错误并关闭机器。尚未到真实 30 秒发布超时或任一新增信号配置；不是新增信号阶段
断言失败，也不是外层 300 秒 watchdog。RCU stall 与 Worker 退出的因果细节仍待定位。

错误栈显示控制台在机器失败清理中先被无原因 abort，测试先记录了 `Error: undefined`，
而 `machine.closed` 的后续原始错误不在原诊断日志中。`84e7d58` 只增加测试运行器
对每次 `reportFailure` 原因的实时诊断，即使首个拒绝已发生也记录后续原因；原先
错误优先级、超时、关闭与通过条件完全不变。不把此诊断改动宣称为 RCU/Worker 修复。
本地运行/关闭与 fork 契约 26 项、固定版本格式检查通过；仅派发 wasm64 Firefox
定位复验，不重复派发已成功的三路。按照先处理验收失败的顺序，子进程恢复前信号
测试暂未实现；本轮不放宽 RCU 检查、不缩短 30 秒超时、不扩大多线程 fork 支持。
定位复验 [wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39234403618)
固定在 `84e7d58`，结果待核实；即使复验成功，也不能因此声称根因已修复。
该诊断版复验随后成功，实际日志已核实四种配置各两轮及关闭；两轮故障均完成真实
30 秒等待及八次恢复 fork。因为该版没有改动等待机制，这进一步说明先前失败存在
偶发性，不能把重跑成功作为根因修复证据。

#### 复制等待交还逻辑 CPU 的候选修复

源码检查发现，旧 `copy_thread()` 调用同步宿主复制接口时，父端可能连续执行最长
30 秒的 `Atomics.wait`，既不进入 Linux 调度器，也不服务这个逻辑 CPU 的时钟中断。
结合 Firefox 日志中的 CPU 1 `0 ticks this GP`，这是明确的调度/RCU 进展风险；
与 Worker 退出的完整因果链仍需目标证据，不能仅凭日志相邻就认定所有退出根因。
Linux [RCU stall 说明](https://cdn.kernel.org/doc/html/latest/RCU/stallwarn.html)也将
内核持续运行且不调度/不服务中断列为相关原因；不能靠屏蔽告警处理。

Linux `6494640f6` 在架构代码增加私有 host/kernel 执行接口 `copy_worker_wait`，
限定为当前 `copy_thread()` 的可睡眠等待栈上调用，拒绝原子或关中断上下文，
调用 `schedule_timeout_uninterruptible(1)`。这是真正的内核调度，不是假报 RCU
quiescent state，不是 Linux UAPI、应用 import 或新的 SDK API；内核改动遵循该文件
原有 GPL 边界，独立 runtime/测试新增仍为 MIT。

distro `33f6600` 在副本尚未发布时最多等待 10 毫秒，再经此内核调度点让出 CPU；
已完成/失败的结果不再调度，整个请求始终使用同一个单调时钟 30 秒截止时间，
调度耗时也计入，不按分片重置。第一终态 CAS、迟到子进程拒绝与错误返回规则不变。
旧内核没有此 export 时保留原同步等待兼容路径，不承诺该旧组合解决 stall；新的
超时故障验收必须观察到实际调度点，不能用兼容回退冒充新路径。

新增宿主检查验证分片超时不等于总超时、调度耗时不延长期限、调度后读到终态立即
返回、已过期/已发布不再调度，以及调度 trap 不伪造成功或 errno。真实 C 故障语料
用 CLOCK_MONOTONIC 要求该超时至少耗时 29 秒（保留分辨率余量，实际截止仍 30 秒）；
浏览器严格门禁新增 RCU stall 拒绝，即使全部阶段和 pass 都出现也不能成功。

本地 kernel 273 项、源码/测试两套类型检查、浏览器/SDK/故障/信号/关闭相关 75 项
通过；GCC/Clang Wasm 条件语法检查和固定版本格式检查通过。内核实际构建、真实
30 秒超时和调度行为仍须 CI 验收，不用宿主通过替代目标结果。内核固定哈希由公开
[预取检查](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39235044366)
确认，集成提交 `012ada9` 同步更新 Linux 和 distro gitlink。

先针对双位宽 Node faults 与 wasm64 Firefox 提交候选修复验收，暂不扩展其他功能。
即使单次复验通过，也须与先前失败、诊断版复验分开记录，不把低频问题写成长期
无故障承诺；子进程恢复前的信号测试继续暂缓。
候选修复运行固定在 `33f6600`，以下三项均成功且实际阶段已核实：
[wasm32 Node faults](https://github.com/HighCWu/distro/actions/runs/39235387623)、
[wasm64 Node faults](https://github.com/HighCWu/distro/actions/runs/39235396808)、
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39235404155)。
双位宽 Node 均包含初始化/分配失败、真实发布超时、八次恢复 fork 及最终用户 pass；
日志中前两阶段间隔分别约 30.001 秒、30.011 秒。测试版调度点计数门禁也必须满足，
故不能以旧内核同步等待回退冒充该结果。

wasm64 Firefox（151.0）实际日志确认普通、故障、clone 前信号、clone 后信号各两轮
完整阶段及关闭，共八次同页启动/关闭；故障两轮各约 30 秒等待，随后均完成八次
恢复 fork。新的 RCU stall 拒绝检查也通过。它证明这个新组合的一次完整回归通过，
并非长期无故障或先前 Worker 退出的所有因果链均已解释。

在相同 `33f6600` 上补齐另外三路浏览器回归，不重复派发已成功的 wasm64 Firefox，
也不以旧源码上的三路通过代替新内核/等待路径验收。
补充回归固定在 `33f6600`，三项均成功且实际日志已核实：
[wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39238131103)、
[wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39238139400)、
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39238147058)。
三路均完成四种配置各两轮的全部阶段及关闭，故障两轮均保留真实约 30 秒等待和
八次恢复 fork；RCU stall 拒绝门禁通过。与前述 wasm64 Firefox 合计四路、32 次
同页启动/关闭均已核实，引擎为 Chromium 149.0.7827.55、Firefox 151.0。
这完成该源码的双位宽 Node faults 与四路浏览器一轮回归，不是长期稳定性证明，
也不补足早先偶发 Worker 退出的全部因果链。

#### 子进程恢复前的受控信号时点

distro `a13d080`、集成提交 `3294e00` 新增独立、默认关闭的
`fork-continuation-check-child-signals` 与
`fork-continuation-wasm64-check-child-signals`，使用
`kernel.override { forkChildSignalTest = true; }`。构建层拒绝它与任一父端信号
配置同时开启；默认内核、SDK、应用 API 均不改变，没有新增 Linux UAPI 或内核改动。

子端的 `switch_entry` 仍处于内核启动回调，测试不得在那里重入 syscall。
因此仅测试构建把 child continuation 的恢复推迟到该回调返回后的正常 `user.call`
入口：尚未执行用户 `_start` 或 Asyncify rewind、尚未恢复子端栈/TLS 时，在现有
内核重入保护下用 getpid/kill 向当前子进程排队被屏蔽的 SIGUSR1，然后恢复原 snapshot
并进入用户 continuation。默认构建继续原有 `switch_entry` 恢复路径；不能把测试版
这一时点等同于任意生产路径上的异步到达。缺失 snapshot 或注入异常不会启动 rewind，
临时元数据会清除；它不是 fork errno 恢复承诺。

独立 C 语料预先屏蔽 SIGUSR1，连续 fork 两次：子端恢复后必须 pending、handler
尚未执行，解除屏蔽后恰好一次递送；父端在 fork 返回、解除屏蔽和 wait 完成后均不得
获得该信号。双方还核对 atfork、PID、屏蔽字、栈/TLS、退出状态及单次回收。
新增精确阶段为 `fork-signal: child pre-rewind pending and parent isolation pass` 与
`fork-signal: two child-restored forks, stack, TLS and single delivery pass`。
Wasm 用户语料不自行注入这个信号；原生基线只在 child-atfork 回调中注入，不能证明
Wasm 恢复前的精确时点。

本地 kernel 278 项、源码/测试两套类型检查、浏览器/SDK/故障/信号/关闭相关 78 项
通过；GCC/Clang 正例和省略注入的反向控制、Wasm 条件语法检查及固定版本格式检查
通过。宿主还检查注入在 rewind/栈/TLS 恢复前发生、重入 fork 被拒绝、元数据清理、
注入异常不 rewind 和重复调用拒绝。旧父端信号或旧源码浏览器结果不能代替
新时点的验收。仍不覆盖未屏蔽
信号在 rewind 内任意时刻的递送、完整多线程 fork 或任意 libc。
固定在 `a13d080` 的 [wasm32 child-signals](https://github.com/HighCWu/distro/actions/runs/39243430478)
与 [wasm64 child-signals](https://github.com/HighCWu/distro/actions/runs/39243437899)
均已成功；实际 Heavy 日志分别核实两个子端信号阶段及最终用户 pass，包括父端
隔离、子端 pending、栈/TLS 与单次投递，不以工作流状态替代阶段证据。

distro `24217a3`、集成提交 `48ab09a` 随后把同一语料接入现有四路浏览器检查。
新增 `child-signals` 仅是测试页面模式，使用独立的 `forkChildSignalTest = true`
loader 与对应 initramfs；父端两个时点和子端时点的输出不能相互冒充。
默认内核、SDK 与公开应用 API 不变。

四路各在同一页面运行普通、故障、clone 前父端信号、clone 后父端信号、子端信号
五种配置各两轮，目标每路十次启动/关闭。新增子端两轮都须包含完整精确阶段并等待
`machine.closed`；RCU stall、页面错误与迟到失败检查保留，外层 300 秒 watchdog
及真实 30 秒故障截止不放宽。原稳定性配置对普通/故障各四轮不变，三个受控信号
配置均固定两轮。

本地浏览器、SDK/故障/信号、运行/关闭相关 79 项、固定版本格式及 JS 语法检查通过。
反向门禁覆盖缺阶段、带前缀输出、迟到失败、RCU stall 及三个信号时点间的错误
替代；loader/initramfs 选择和跨源隔离也有执行检查。
固定在 `24217a3` 的四路检查均已成功，实际 Heavy 日志已核实：
[wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39248612815)、
[wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39248622383)、
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39248631380)、
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39248642286)。
每路五种配置各两轮的全部阶段和关闭通过，共 40 次启动/关闭；两个子端信号阶段
均出现，故障两轮保留真实约 30 秒截止和八次恢复 fork。引擎为 Chromium
149.0.7827.55、Firefox 151.0。该小样本不证明长期无故障，也不证明此前 RCU stall
与 Worker 退出的完整因果链已查明，不扩大任意异步恢复时点的支持范围。

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

#### 首轮单线程 Node 测量协议

distro `a86902d`、集成提交 `c92083d` 增加独立、默认不执行的性能工作流。
通过已有 `ci.yml` 的 `fork-benchmark=true` 手动输入启动，分别构建 wasm32/wasm64
不可变输入，再在工作流测量步骤执行；不能用 Nix 缓存中的旧检查结果替代新测量。
内核、默认 SDK 和单线程准入边界不变，本轮不实现 vfork，也不放宽 ABI 门禁。

无 fork 工作负载使用四组可运行对照：

| 组 | libc / 链接与变换 |
| --- | --- |
| default | 默认 libc，未变换 |
| fork-libc-raw | fork libc，但不链接 continuation 对象，未变换 |
| fork-libc-asyncify | 对上一组的同一个已链接文件做 Asyncify |
| sdk-asyncify | 真正 opt-in SDK 链接并完成 Asyncify |

真正 SDK 的未变换模块带执行 ABI 声明，却缺少 continuation 入口，现有 loader
会拒绝；它仅记录体积，不启动。中间两组用于隔离同一链接产物的变换成本，不能
冒充真正 SDK 的未变换可运行版本。工作负载分别计时含周期性 getpid 的函数调用
循环和 getpid syscall 循环，检查次数、校验和与身份，不称为纯算术吞吐。

另三组使用真正 SDK，分配并每 4 KiB 触碰 1/16/64 MiB 载荷，测量父端 fork 返回
和 fork+wait 完成耗时；同时检查父子 PID、栈/TLS、快照隔离及单次回收。载荷不是
完整被复制地址空间大小，报告另存实际用户线性内存分配大小。

每组分别启动三个全新 Node 进程和 Linux 实例，每次一轮预热、五个计时样本；
每个位宽 21 次启动/关闭，两位宽共 42 次。交替正反组顺序，先取各次启动内的
中位数，再取三次启动中位数的中位数；不把同一次启动内的样本当成独立启动。
全部精确样本、校验和、pass、RCU stall 拒绝和最终 `machine.closed` 均为门禁，
暂不设置性能数值阈值。结果保留原始 stdout/stderr、报告 JSON、二进制大小与
SHA-256、编译器/Node/CPU 信息及构建来源，公开工作流 artifact 保留七天。

内存同时报告用户/内核线性内存分配大小，以及 Linux Node 整个进程生命周期的
最大 RSS，后者含内核、JIT、Workers 与关闭阶段，单位为 KiB，来自
[Node.js resourceUsage](https://nodejs.org/docs/latest-v24.x/api/process.html#processresourceusage)。
这些指标不是单个用户程序的 RSS、浏览器内存或已完全回收的证明。首轮实际目标
编译与测量尚待 CI；宿主六项新回归、连同已有相关 85 项通过不构成性能结论。
首轮已提交至[公开双位宽性能工作流](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39252491842)，
固定在集成 `c92083d` / distro `a86902d`；不能以输入构建成功替代 42 次新启动的实际结果。
首个 wasm32 作业止于全仓格式检查：Statix 要求地址位宽字段使用 `inherit`，未进入
目标编译或测量。distro `db77b19` / 集成 `abb724b` 按实际 diff 修正，重新提交
[双位宽检查](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39252720608)，
新结果仍待核实；不取消原任务，也不将格式失败解释成性能退化。

#### 首轮 wasm32 实测与构建缓存调整

上述运行 `39252720608` 的 wasm32 作业 `118060942005` 已成功。实际日志核实七组
各三次新启动和关闭，artifact 中 21 份原始 stdout 与报告逐一一致，重新执行样本
校验与分组中位数计算通过。测量于 2026-10-19 13:58:43 UTC 完成，固定 distro
`db77b19` / 集成 `abb724b`，Node v24.21.0、Clang 22.1.8、四逻辑 CPU 的
Intel Xeon Platinum 8573C；Linux 实例仍用两个逻辑 CPU。报告 SHA-256 为
`9fae69dd7611e08d0acaff85f95f4963229704fd94459ecc1031b6061f24007f`，原始资料为
该运行的 `fork-benchmark-wasm32-db77b19fd1d68bb152fff055da66efcba05edf7b` artifact。
同一份[原始 JSON 报告](data/fork-baseline-20261019-wasm32.json)已按原字节保存于仓库，
SHA-256 与上述值一致，保留 21 次启动的原始输出、逐样本数据、摘要、环境和二进制
哈希，避免七天 artifact 留存期结束后只剩表格。该报告不包含 wasm64 验收结果。

以下耗时均为三次启动内中位数的中位数，单位 ms；不是单次调用耗时。
函数循环为 262144 次，syscall 循环为 4096 次，保留前述周期性 syscall 口径。

| 无 fork 组 | 文件字节 | 函数循环 ms | syscall 循环 ms |
| --- | ---: | ---: | ---: |
| default | 37970 | 0.990 | 1.455 |
| fork-libc-raw | 37979 | 1.005 | 2.480 |
| fork-libc-asyncify | 96215 | 1.780 | 1.430 |
| sdk-asyncify | 96666 | 1.810 | 1.360 |

同链接产物的变换后体积约 2.53 倍，函数循环耗时约 1.77 倍；真正 SDK 相对默认版
分别约 2.55 倍、1.83 倍。短 syscall 循环波动明显，例如 fork-libc-raw 三次启动的
中位数为 2.480/2.575/1.115 ms，SDK 为 1.710/1.360/1.080 ms，不能把比值小于一
解释为普遍加速。更长工作负载、JIT 稳态和浏览器测量仍需另行设计与验收。

| 已触碰载荷 MiB | 用户线性内存 MiB | 父端返回 ms | fork+wait ms | Node 整进程峰值 RSS 范围 KiB |
| --- | ---: | ---: | ---: | ---: |
| 1 | 9.6875 | 58.860 | 59.505 | 885736–908296 |
| 16 | 24.6875 | 58.950 | 59.680 | 920876–955184 |
| 64 | 72.6875 | 68.270 | 69.190 | 1016148–1054496 |

16 MiB 组三次父端返回中位数为 58.950/67.160/58.900 ms，不能隐藏其跨启动波动。
1 至 64 MiB 的总耗时并非按载荷倍数增长，提示存在较大的固定成本；尚不能据此
分离 Worker 启动、模块实例化、内存复制、调度和 continuation 恢复的占比。
后续优化应先做阶段计时诊断，不直接假定复制是主要瓶颈，也不引入内核 softmmu。
RSS 含整个 Node 进程和生命周期，约 GiB 量级不等于用户程序线性内存占用或泄漏。
wasm64 当前仍在原运行中构建，不能以这 21 次成功宣称双位宽共 42 次验收完成。

本轮另确认主仓库 Actions 缓存列表为空，而 distro 有匹配分支的双位宽 targeted
缓存；原作业冷构建耗时约 85 分钟，远大于约 50 秒的实际测量。为避免后续重复冷
构建，`308dd3e` / `09b2e3a` 将工作流迁至 distro，并由集成 `11a648c` 固定。
后续入口是 **HighCWu/distro** 的 `ci.yml`，设置 `fork-benchmark=true`；
`fork-benchmark-width` 可选 `both`、`wasm32`、`wasm64`，以便只复验失败的一路。
主仓库旧 fork-benchmark 入口已移除，文件复制性能入口不变。

新入口固定校验 checkout SHA、拒绝和 heavy-check/Python 专用模式混用，跳过普通
重型矩阵，只复用不可变构建缓存，测量仍在 Nix 构建之外执行。单个位宽作业预算
改为 180 分钟，150 秒子进程及原有运行/关闭门禁不变。新增工作流归属与准入回归，
相关共 86 项、固定版本格式和 actionlint 通过；新入口本身尚未完成公开目标验收。
原 wasm64 作业不取消、不重复派发；待其实际结果再决定是否需要定向复验。
随后单独派发[迁移入口的 wasm32 验收](https://github.com/HighCWu/distro/actions/runs/39267019054)，
固定 `09b2e3a`，不重复原运行中仍在执行的 wasm64。新入口的模式校验已通过，普通
构建矩阵、部署与发布均跳过，已完成缓存恢复和格式检查、进入输入构建；实际缓存
命中详情、21 次新测量及关闭结果仍待核实，不能仅以缓存步骤成功冒充缓存命中。

该迁移验收随后成功，实际作业 `118109185884` 日志确认命中
`nix-targeted-v1-Linux-wasm32-a018a96e67d2f3c936b9cd8fe2fd3c6d7bb9900945c11c7aa34cb5aa0fb5dfa0`
并成功恢复。输入构建为 14:14:59–14:25:49 UTC，随后约 61 秒完成七组各三次新启动、
测量和关闭；普通矩阵及部署/发布保持跳过。该次宿主是四逻辑 CPU 的 AMD EPYC
7763，不能把与首次 Xeon 宿主的时长差异全部归因于缓存。

下载的 21 份原始 stdout 与报告逐一一致，样本/校验和/关闭和分组中位数再次核验
通过；11 个 Wasm 产物的字节数和 SHA-256 与首次完全相同。已按原字节归档
[第二份 wasm32 报告](data/fork-baseline-20261019-wasm32-cached.json)，其 SHA-256 为
`30f7f13740aff6ce6d3b0855826446f67b4c83ae2805e74b789f07715026a254`，固定源码
`09b2e3a`，Node v24.21.0、Clang 22.1.8，测量完成于 14:26:50 UTC。

| 组 / 载荷 | 函数循环或父端返回 ms | syscall 循环或 fork+wait ms |
| --- | ---: | ---: |
| default | 1.370 | 1.640 |
| fork-libc-raw | 1.370 | 1.565 |
| fork-libc-asyncify | 2.335 | 1.505 |
| sdk-asyncify | 2.355 | 2.015 |
| fork 1 MiB | 62.500 | 64.380 |
| fork 16 MiB | 66.525 | 67.450 |
| fork 64 MiB | 77.980 | 78.985 |

同链接变换的函数循环比值约 1.70、SDK/默认版约 1.72，体积不变；SDK 的短 syscall
比值约 1.23，与首次约 0.93 的方向不同。只能把它们视为不同 CI 宿主上的两轮
小样本，不能混合后宣称普遍性能比值、加速或回退。后续需要更长/JIT 稳态负载和
分阶段诊断。本轮收尾了新工作流的 wasm32 入口验收，不代表迁移入口的 wasm64
已验收；原 wasm64 仍在构建，没有取消或重复派发。

#### 独立分阶段诊断配置与 wasm64 定向复验

旧运行 `39252720608` 的 wasm64 后续止于输入构建：GitHub annotation 明确报告
超过 **1h30m0s**，作业结果为 cancelled，测量步骤跳过；没有 wasm64 原始样本。
这不是 fork 运行失败或性能结果，也不是主动取消慢任务。2026-10-20 已在缓存归属
正确、180 分钟预算的新入口仅提交 [wasm64 基线复验](https://github.com/HighCWu/distro/actions/runs/39342225965)，
固定旧源码 `09b2e3a`，不重跑已验收的 wasm32；新基线结果仍待核实。

distro `d291605` / 集成 `c870467` 同时实现默认关闭的私有诊断配置。
`forkProfileTest = true` 仅用于 `benchmarkProfileAssets`，对应 workflow 输入
`fork-benchmark=true`、`fork-benchmark-profile=true`，可选择位宽。普通 SDK、
Linux 内核、复制结果 SAB 的布局、一次性发布及 30 秒截止协议均未改变。
它不能和复制故障或信号注入配置混用，不增加用户 import、UAPI 或公开应用入口；
所有独立新增代码使用 MIT。

每次 COPY 使用不含地址的随机关联 ID，分别采集以下五类记录：

| 记录 | 时钟与精确范围 |
| --- | --- |
| worker-start-message | 主线程：创建 Worker 前至收到其启动通知；含模块启动、转发和消息排队，不是纯线程创建耗时 |
| parent-ready | 父 Worker：派发前至快照完成等待结束；不是完整 fork syscall 延迟 |
| child-ready | 子 Worker：进入初始化至发布完成，另存内存分配、复制、内核实例化和用户实例化四个局部耗时 |
| child-prepare-rewind | 子 Worker：恢复 stack/TLS、准备 Asyncify rewind 的同步调用 |
| child-rewind-checkpoint | 子 Worker：从准备 rewind 前至真正到达并停止 rewind 的原 syscall 检查点；包含上一行，不含其后的 libc/atfork 收尾 |

所有区间均用同一 isolate 的单调时钟计算，不相减跨 Worker 的时间戳，不按日志
到达顺序推断执行时间。主线程、父端与子端区间存在重叠，不能直接相加成为总耗时，
也不能把准备 rewind 的短调用当成完整恢复。诊断消息本身有成本，带诊断的数值
不能替代未插桩基线；本轮不进行算法优化、COW 或多线程 fork 扩大。

每个 fork 组每次启动必须收齐预热一轮和五次计时分叉的六组记录，每组五类完整、
关联 ID 唯一。三个载荷各三次新启动共 54 组分叉诊断；无 fork 对照不得出现记录，
默认基线也拒绝混入记录。原有功能、样本、错误/RCU stall 和关闭门禁全部保留。
用户 pass 不能立即终止尚有诊断消息排队的 Worker：仅诊断 runner 增加输出完成门禁，
收齐至少应有的记录后才关闭，再严格检查类别/重复/缺失/数值；缺记录仍受原运行
watchdog 和 150 秒子进程上限约束。记录单独保存在 `phaseDiagnostics`，包含预热，
不得把六组诊断误称为六个正式基线样本。

本地 kernel 285 项、相关回归 90 项、源码与测试两套 TypeScript、固定版本格式和
actionlint 通过。用例覆盖默认不调用时钟/不产生 request，局部时钟起点差异、记录
输出异常不改变返回/错误、i32/i64 真正检查点仅通知一次、父端不误触发子端通知、
缺阶段/重复/错误关联 ID/无效耗时拒绝，以及 user pass 后迟到记录与缺记录的清理。
真实目标尚待 [wasm32 诊断配置](https://github.com/HighCWu/distro/actions/runs/39342888032)
和 [默认关闭路径 Node 回归](https://github.com/HighCWu/distro/actions/runs/39342893626)，
均固定 `d291605`。诊断性能工作流沿用不取消的并发组，可能等旧 wasm64 基线完成；
上述本地检查不代表已经取得任何阶段耗时结论。

#### 双位宽基线验收收尾与诊断传输修复

wasm64 基线运行 `39342225965` / 作业 `118366316662` 随后成功。实际日志已逐项
核实七组各三轮新启动和关闭；21 份原始 stdout 与报告逐一一致，重新执行完整样本、
校验和、错误/RCU stall 拒绝及分组中位数检查通过。固定 `09b2e3a`，Node v24.21.0、
Clang 22.1.8、四逻辑 CPU 的 AMD EPYC 9V74；测量于 2026-10-20 07:44:10（UTC+8）
完成，Linux 实例使用两个逻辑 CPU。已按原字节保存
[wasm64 原始报告](data/fork-baseline-20261020-wasm64.json)，SHA-256 为
`84886c67eef2241731235e4d862b784efbf87208cb45807f40d0012e539c6b6c`。

以下仍是三次启动内中位数的中位数，单位 ms；每个循环的次数与前述协议一致。

| 无 fork 组 | 文件字节 | 函数循环 ms | syscall 循环 ms |
| --- | ---: | ---: | ---: |
| default | 39860 | 1.165 | 1.650 |
| fork-libc-raw | 39869 | 1.265 | 1.625 |
| fork-libc-asyncify | 97285 | 1.795 | 1.755 |
| sdk-asyncify | 97738 | 1.775 | 1.540 |

| 已触碰载荷 MiB | 用户线性内存 MiB | 父端返回 ms | fork+wait ms | Node 整进程峰值 RSS 范围 KiB |
| --- | ---: | ---: | ---: | ---: |
| 1 | 9.6875 | 49.195 | 50.300 | 951060–969728 |
| 16 | 24.6875 | 55.515 | 56.170 | 980556–982924 |
| 64 | 72.6875 | 58.320 | 59.205 | 1078708–1098292 |

SDK/默认版体积约 2.45 倍、指定函数循环约 1.52 倍；同链接变换的函数循环约
1.42 倍。短 syscall 样本仍有波动，且三份报告来自不同宿主，不能跨位宽比较后
宣称 memory64 更快、普遍加速或稳定性能上限。当前未插桩 Node 基线已有两位宽
各 21 次的完整证据，另有 wasm32 入口复验的 21 次；不代表浏览器性能基线、
诊断配置或完整 fork 兼容性已验收。

默认关闭路径运行 `39342893626` / 作业 `118368570505` 也已核实真实输出：所有
raw syscall、身份/隔离/等待、pending 信号、atfork/TLS/fd、嵌套 fork、exec 成功与
拒绝恢复、多线程/信号回调拒绝及 flags-first/legacy 共存阶段与最终 pass 齐全。
它固定 `d291605`，不能代替后续修复版的运行结论。

诊断运行 `39342888032` 则在首个 1 MiB 分叉组失败：四组无 fork 对照已执行，
该分叉组的五个正式样本与用户 pass 都出现，却没有任何 `fork-profile:` 记录，
最终触发 120 秒门禁超时。代码审查确认诊断误用了 Linux 启动控制台：正式 console
接管后该流已关闭，后续 write 的拒绝被既有日志路径忽略。不能把这次失败说成
分叉功能失败，也不能用其程序 pass 或部分计时冒充完整诊断验收。

`bd640b0` / 集成 `8a081b6` 改为私有 Worker 记录消息，主线程诊断配置将指定前缀
写到 host logger；独立 Node runner 临时捕获这一前缀，保留其他错误输出，并在
`finally` 恢复 logger。它不依赖已关闭的启动控制台，也不新增 Machine、SDK 或
Linux 应用接口。runner 的额外完成条件改为 Promise，诊断在最后一行用户输出
之后到达也能直接唤醒门禁；仍须用户 pass 与完整诊断同时满足。缺记录的 watchdog、
原失败/关闭逻辑和严格五类记录校验不放宽；失败时已捕获的记录也保留在错误证据中。

修复本地通过 kernel 285 项、相关 94 项及源码/测试两套 TypeScript 和格式检查。
新增真实 Node Worker 在启动流已关闭后的迟到记录用例、收集器前缀隔离与 logger
恢复、默认不安装收集器，以及等诊断期间用户失败仍立即失败的反例。
[修复版 wasm32 诊断](https://github.com/HighCWu/distro/actions/runs/39349721033) 与
[默认路径回归](https://github.com/HighCWu/distro/actions/runs/39349726498) 已提交，
固定 `bd640b0`；真实目标结果尚待核实，尚无阶段耗时结论。

#### wasm32 分阶段记录验收与首轮诊断

修复版运行 `39349721033` / 作业 `118390812384` 随后成功，实际日志已核实七组
各三次新启动、测量和关闭。下载的 21 份 stdout 与报告逐一一致，全部基础样本、
校验和、错误/RCU stall 拒绝及分组中位数重新校验通过。从原输出重建的九个 fork
启动批次与 `phaseDiagnostics` 完全一致：共 54 个不同关联 ID、270 条记录，每个
ID 的五类阶段齐全，无重复、缺失或非 fork 对照混入。

固定源码 `bd640b0`，Node v24.21.0、Clang 22.1.8，宿主为四逻辑 CPU 的 AMD EPYC
7763；Linux 实例两个逻辑 CPU。报告于 2026-10-20 09:00:38（UTC+8）生成，已按原
字节归档[完整 wasm32 诊断报告](data/fork-profile-20261020-wasm32.json)，SHA-256 为
`40458b593612fc1d615454adc1ac21ad652099bb3e46fbcc01c9067c9280d231`。

下表单位 ms：每次启动先取六组诊断（**包含预热**）的中位数，再取三次启动中位数
的中位数。不同于正式基线的五个计时样本；不把这些结果当作未插桩性能数值。

| 局部区间 | 1 MiB 载荷 | 16 MiB 载荷 | 64 MiB 载荷 |
| --- | ---: | ---: | ---: |
| 主线程：创建 Worker 至收到启动通知 | 56.691 | 56.865 | 56.882 |
| 父端：派发至快照等待完成 | 68.392 | 68.944 | 77.937 |
| 子端：初始化入口至快照发布 | 5.375 | 7.414 | 14.292 |
| 子端：内存分配 | 0.222 | 0.218 | 0.226 |
| 子端：内存复制 | 2.196 | 4.035 | 10.840 |
| 子端：内核实例化 | 1.682 | 1.752 | 1.732 |
| 子端：用户实例化 | 0.610 | 0.626 | 0.634 |
| 子端：准备 rewind | 0.110 | 0.121 | 0.118 |
| 子端：准备前至真正 rewind 检查点 | 0.506 | 0.473 | 0.449 |

这轮较大的固定区间落在 Worker 启动通知路径，复制区间则随载荷增大。下一候选
调查点应优先分解 Worker 模块加载、初始化/转发及主线程消息排队；不能把第一行
全归为操作系统线程创建成本，也不能将父端与子端重叠区间相加、相减得到精确成本
占比。各列是独立分组统计，不是同一个请求的可加时间线。暂不据此引入 Worker
池、复用用户实例、COW 或改变 Linux 调度/复制协议；这些方案的隔离和资源生命周期
必须另行设计与验证。当前仅是该负载、该宿主的一轮 Node 诊断，不是浏览器或通用
程序性能保证。

同一源码默认关闭路径 `39349726498` / 作业 `118390899804` 的实际日志也已核实
全部 raw syscall、信号、身份/TLS/atfork/内存/fd/嵌套等待、exec 及拒绝恢复阶段和
最终 pass，不能再将旧源码通过代替它。随后仅提交同一 `bd640b0` 的
[wasm64 诊断验收](https://github.com/HighCWu/distro/actions/runs/39354667910)，
沿用相同 21 次启动与 54 组完整记录门禁；结果仍待核实，不重复已完成的 wasm32，
也不把未插桩 wasm64 基线通过当成其诊断验收。

#### wasm64 分阶段验收与双位宽诊断结论

上述 wasm64 运行 `39354667910` / 作业 `118406640919` 随后已核实通过：实际日志
包含全部 21 次新启动和关闭；21 份原始 stdout 与报告一致，基础样本及分组统计
重新校验通过。九个 fork 批次重建结果与报告完全一致，共 54 个唯一关联 ID、
270 条完整五类记录，无重复或缺失。

固定 `bd640b0`，Node v24.21.0、Clang 22.1.8，四逻辑 CPU 的 AMD EPYC 7763
宿主，Linux 实例两个逻辑 CPU。报告生成于 2026-10-20 09:53:16（UTC+8），
按原字节归档[完整 wasm64 诊断报告](data/fork-profile-20261020-wasm64.json)，
SHA-256 为 `e34922ec70e29fc41f75becf9b61f56447958df2defd97b08b4dce3daaca17e6`。
下表沿用上一表的含预热、三次启动中位数口径，单位 ms。

| 局部区间 | 1 MiB 载荷 | 16 MiB 载荷 | 64 MiB 载荷 |
| --- | ---: | ---: | ---: |
| 主线程：创建 Worker 至收到启动通知 | 57.584 | 58.801 | 57.048 |
| 父端：派发至快照等待完成 | 63.783 | 69.076 | 76.926 |
| 子端：初始化入口至快照发布 | 5.398 | 7.875 | 14.550 |
| 子端：内存分配 | 0.234 | 0.221 | 0.233 |
| 子端：内存复制 | 2.069 | 4.258 | 11.004 |
| 子端：内核实例化 | 1.681 | 1.852 | 1.728 |
| 子端：用户实例化 | 0.614 | 0.638 | 0.635 |
| 子端：准备 rewind | 0.114 | 0.110 | 0.102 |
| 子端：准备前至真正 rewind 检查点 | 0.491 | 0.455 | 0.442 |

双位宽这轮诊断均观察到较大的固定启动通知区间，复制随载荷增长，rewind 区间
相对较小。这是继续细分启动路径的依据，不是纯线程创建成本或跨位宽性能排名；
不能用独立中位数相减计算组件占比，也不构成浏览器性能结论。

#### 第二版私有启动诊断：待目标验收

`4f562a6` / 集成 `4c60d63` 增加默认关闭的 Node 专用诊断，仍不改变公开应用
API、Linux syscall、快照发布协议或 30 秒截止时间。它不实现 Worker 池、实例
复用、COW，也不扩大多线程 fork 支持。

新增主线程同步创建区间、收到 Node `online`、零延时主线程定时器探针、模块加载
完成通知、实际 init 发送完成五类记录。Node 的
[`online` 事件](https://nodejs.org/docs/latest-v24.x/api/worker_threads.html#event-online)
表示 Worker 开始执行 JavaScript，不表示模块图已加载；主线程收到事件还包含
投递/排队。定时器只是主线程响应性探针，不是消息排队时间的精确测量。

仅诊断配置改用 bootstrap，先等待 `worker.js` 模块图加载完成，再发送暂存的
init。因此本轮会主动改变启动时序，不能与第一版直接比较速度或当作默认路径
优化。模块加载使用子 Worker 自己的时钟；暂存时长和 post 调用时长使用主线程
自己的时钟。暂存时长包括受控等待模块就绪，不称为纯主线程队列成本。其余主线程
记录为累计区间，彼此重叠，不与局部区间拼成可加时间线。

第二版显式使用 `profileVersion=2`，每个关联 ID 须十类记录齐全；21 次启动中
54 个请求应产生 540 条记录。旧版五类报告仍可读取，混版、缺类或非法时长均拒绝。
取消/发送失败关闭仍归队列所有的端口，迟到就绪不得再次发送；成功转移的端口
不再由队列关闭。默认 Node 路径仍直接加载原 Worker，不安装这些探针或暂存队列；
浏览器路径未接入第二版诊断。

本地 kernel 291 项、相关轻量检查 95 项、源码/测试两套 TypeScript 和固定版本
格式检查通过，含真实 Node Worker 的模块加载后发送与端口转移用例；既有五份
归档报告也重新通过解析和分组校验。这些不能替代 Wasm 目标证据。
[wasm32 第二版诊断](https://github.com/HighCWu/distro/actions/runs/39357982365) 与
[同源码默认路径回归](https://github.com/HighCWu/distro/actions/runs/39357987618)
已提交，目标阶段结果待核实；先验收 wasm32，再决定同版 wasm64 复验，不提前
给出新阶段耗时或优化收益。

#### 第二版 wasm32 目标验收

`39357982365` / 作业 `118417178298` 已核实全部 21 次启动、测量和关闭及最终
pass。下载的 21 份原始 stdout 与报告逐一一致，重算基础分组与九组诊断均与报告
一致；54 个全局唯一请求各十类，共 540 条记录齐全。默认关闭路径同源码运行
`39357987618` / 作业 `118417257744` 的实际日志也已核实全部十一阶段及最终 pass。

固定 `4f562a6`，Node v24.21.0、四逻辑 CPU 的 AMD EPYC 9V45，报告生成于
2026-10-20 10:25:50（UTC+8）。[原始报告](data/fork-profile-v2-20261020-wasm32.json)
按原字节归档，SHA-256 为
`a2b690bd45b5f6e2fa192a9f5ff447c55ebe1e1e332c3059c04fd93ff3558ce5`。
下表仍为含预热的三次启动中位数口径，单位 ms；累计区间不相加。

| 诊断量 | 1 MiB | 16 MiB | 64 MiB |
| --- | ---: | ---: | ---: |
| 主线程同步创建区间 | 0.430 | 0.446 | 0.422 |
| 主线程累计至 online 通知 | 18.378 | 17.260 | 18.118 |
| 主线程累计至零延时探针 | 1.638 | 1.664 | 1.646 |
| 主线程累计至模块就绪通知 | 24.325 | 23.180 | 24.226 |
| 子 Worker 局部模块加载区间 | 4.574 | 4.463 | 4.546 |
| init 受控暂存区间 | 23.857 | 22.586 | 23.759 |
| init post 调用区间 | 0.021 | 0.022 | 0.022 |
| 主线程累计至原启动通知 | 36.806 | 35.186 | 36.769 |

这些记录区分了同步创建与异步启动/模块加载，post 调用在该负载中较小；不能把
online 通知归为纯线程创建，也不能把暂存成本归为默认路径排队。宿主从上一版
EPYC 7763 变为 9V45，且诊断主动改变发送时序，不得声称相对第一版加速。
随后提交[同源码 wasm64 第二版诊断](https://github.com/HighCWu/distro/actions/runs/39360700490)，
其完整阶段和关闭证据尚待核实。尚未实施启动优化或 Worker 复用。

#### 第二版 wasm64 验收与后续优化边界

运行 `39360700490` / 作业 `118425978721` 已完成。实际日志核实七组各三次
新启动、测量和关闭及最终 pass；21 份原始 stdout 与报告逐一一致。基础分组重算
以及九组诊断重建均与报告相同，54 个全局唯一请求各十类，共 540 条记录齐全。
该结论覆盖第二版 Node 诊断，不扩展为浏览器或默认 SDK 的性能结论。

固定 `4f562a6`，Node v24.21.0、四逻辑 CPU 的 AMD EPYC 7763；报告生成于
2026-10-20 10:59:20（UTC+8）。[完整原始报告](data/fork-profile-v2-20261020-wasm64.json)
按原字节归档，SHA-256 为
`2a28ea7f362e2a1f00e5158a1420cf6c2df8a16fc907c9466791e9be86638237`。
下表沿用含预热、三次启动中位数口径，单位 ms。

| 诊断量 | 1 MiB | 16 MiB | 64 MiB |
| --- | ---: | ---: | ---: |
| 主线程同步创建区间 | 0.514 | 0.526 | 0.522 |
| 主线程累计至 online 通知 | 27.263 | 27.261 | 27.508 |
| 主线程累计至零延时探针 | 1.721 | 1.711 | 1.670 |
| 主线程累计至模块就绪通知 | 37.279 | 37.065 | 37.434 |
| 子 Worker 局部模块加载区间 | 7.576 | 7.483 | 7.545 |
| init 受控暂存区间 | 36.768 | 36.615 | 36.780 |
| init post 调用区间 | 0.021 | 0.019 | 0.021 |
| 主线程累计至原启动通知 | 57.328 | 57.230 | 57.253 |
| 子端局部内存复制区间 | 2.101 | 3.821 | 10.605 |

双位宽第二版证据现已齐全。两轮宿主 CPU 型号不同，不能从表间差值推导位宽
成本或加速比例；累计通知时间也不能与局部模块加载时间拼成可加分解。当前证据
仅支持优先调查异步启动/模块图，而非优化很小的同步 post 调用或 rewind。

下一候选为默认关闭的独立 Worker 模块打包实验：先审查打包对 URL、Node/web
平台选择、循环依赖和消息初始化顺序的影响，再以同源码、同 runner 交错执行原版
与实验版，保留每次 fork 全新 Worker、完整状态隔离、超时回滚与关闭门禁。性能
结论须来自未启用诊断 bootstrap 的目标对照；诊断只辅助定位。若没有稳定收益，
不提升为默认构建。此处仅记录待实施实验，不表示已添加打包配置或获得收益。
Worker 池、实例复用、COW、多线程 fork 仍不在此次优化范围内。

#### 独立 Worker 打包对照实验：已实现，待目标验收

`3273aa7` / 集成 `3d0c9e9` 实现默认关闭的 `benchmarkWorkerPairAssets`。
它复制普通 kernel 包，仅替换实验目录的 `dist/worker.js`；原 npm 包、公开 API、
主入口、Worker URL 和默认构建均不改。采用 [esbuild 的 ESM 打包与构建元数据](https://esbuild.github.io/api/)，
保留名称，法律注释采用 inline 策略（不表示所有普通注释原样保留），不启用
压缩、代码拆分、tree shaking 或注解驱动删除；独立许可文件不变，记录实际
工具版本和完整 metafile。打包仍可能改变循环依赖初始化行为，不能声称语义自然
等价，必须通过目标测试。

构建门禁要求仅输出一个 Worker、无残留外部模块导入，且原包中除 worker.js 以外
的所有文件逐字节不变；三次真实 Node Worker 模块加载完成并等待终止。之后在
实验版上运行完整普通 fork 语料及独立故障语料，包含真实 30 秒发布超时、迟到子端
拒绝和八次恢复 fork；任一门禁失败都不得开始测量。

测量仅接受未插桩配置，不与诊断 bootstrap 混用。原版和打包版使用完全相同的
用户 Wasm、内核 Wasm、initramfs、manifest 及主入口，运行前重新比较哈希。七组
工作负载各三次，每组相邻运行两种构建，交替先后顺序，并反转第二轮工作负载顺序，
共 42 次全新 Node 进程与 Linux 启动；每次保留原有预热、五个正式样本、校验和、
失败/stall 拒绝和机器关闭门禁。保存全部 stdout/stderr、成对顺序、包内 Worker
哈希及分组报告；缺轮次、非预期顺序、插桩输出、关闭失败或输入不一致均拒绝，
不覆盖既有结果目录。比率只是该轮分组统计，不设性能通过阈值，也不代表浏览器
或稳定通用收益。

本地 291 项 kernel 宿主测试、16 项实验检查及 16 项 SDK/raw syscall/browser
契约回归通过；包含完整成对脚本编排、错误输入/覆盖拒绝和打包门禁反例。真实
源码的本地模块打包与三次 Worker 加载/终止通过，但不代替 Nix 包或 Linux 目标
验收。Nix 格式、工作流检查与 scoped diff 检查通过，未在本地构建 Linux/LLVM。
[wasm32 对照验收](https://github.com/HighCWu/distro/actions/runs/39363717751)
已提交，固定 `3273aa7`，真实功能、故障阶段与全部 42 次关闭结果待核实。先完成
该项再决定 wasm64 复验；目前没有实验版性能结论，不改变默认配置，也不引入
Worker 池、实例复用、COW 或多线程 fork。

#### wasm32 打包对照验收：功能通过，但出现 syscall 性能退化

运行 `39363717751` / 作业 `118435604604` 的实际日志已核实实验包两次闭合模块图
及其他文件字节一致门禁、真实 Worker 加载/终止、普通 fork 全部十一阶段与最终
pass，以及故障语料全部三阶段与 pass。真实发布超时约 30 秒，之后迟到子端被拒绝，
八次恢复 fork 的身份、TLS、隔离和单次回收检查通过。测量日志包含全部 42 次
成对启动和关闭及最终 pass，不只依据 workflow 的 success。

下载的 42 份原始 stdout 与报告逐一一致，stderr 均为空。重新验证 manifest、
每次启动的样本、关闭和成对顺序后，重算两组摘要与全部比率，均与报告完全相同。
报告含十一份用户 Wasm 的哈希、不同的两份 Worker 哈希及闭合单输出元数据；
打包图有 15 个输入，输出 61,996 字节，无外部导入。

固定 `3273aa7`，Node v24.22.0、esbuild 0.27.2，四逻辑 CPU 的 AMD EPYC 7763。
报告生成于 2026-10-20 11:35:37（UTC+8），按原字节归档
[完整 wasm32 成对报告](data/fork-worker-pair-20261020-wasm32.json)，SHA-256 为
`eff46cdea2b99c27bba71b6d4eb33733ab3d2c1db35c428aa669ee17fb0bbded`。
以下为每次启动五个正式样本的中位数，再取三次启动中位数，单位 ms；比率小于
1 才表示本轮打包版更快，不将它解释为通用或稳定收益。

| 负载 / 指标 | 原版 | 打包版 | 打包 / 原版 |
| --- | ---: | ---: | ---: |
| default / 4096 次 getpid | 1.730 | 7.105 | 4.107 |
| fork-libc-raw / 4096 次 getpid | 2.565 | 5.655 | 2.205 |
| fork-libc-asyncify / 4096 次 getpid | 2.155 | 5.515 | 2.559 |
| sdk-asyncify / 4096 次 getpid | 1.570 | 5.800 | 3.694 |
| 1 MiB / fork+wait | 70.360 | 67.870 | 0.965 |
| 16 MiB / fork+wait | 82.910 | 79.325 | 0.957 |
| 64 MiB / fork+wait | 112.255 | 106.870 | 0.952 |

本轮 fork+wait 约减少 3.5%–4.8%，但四组 syscall 循环的打包版耗时增至原版
2.2–4.1 倍；每组的三个启动中位数都呈现退化，不是仅一条离群样本。指定函数
循环比率约 1.002–1.131，也不能宣称全负载改善。功能验收通过并不构成优化验收
通过，因此保留原版默认构建，禁止据此启用默认打包。

当前测试每次启动只有一轮预热；这些证据不足以确认稳定态 JIT 成本，也尚未
确定退化来自代码布局、打包转换、分层编译或其他因素。不能把原因直接归给某个
esbuild 参数，也不修改预热次数来覆盖已观察到的退化。后续先用
[同源码 wasm64 对照](https://github.com/HighCWu/distro/actions/runs/39369695719)
核实是否存在相同取舍，仍须功能/故障门禁和完整 42 次关闭；新结果待验收。
需要进一步优化时，再做独立、可重现的单因素构建/JIT 调查，而非将整个模块
打包方案作为已成功的性能改进。未增加池化、复用或多线程 fork 支持。

#### wasm64 对照收尾：复现 syscall 退化，不提升默认打包

运行 `39369695719` / 作业 `118454568659` 的实际日志已核实：普通和故障配置
均通过闭合模块图、包文件字节一致及三次真实 Worker 加载/终止门禁；普通语料
十一阶段及 pass、故障语料三阶段及 pass 全部齐全。发布超时阶段约 30 秒，包含
迟到子端拒绝和父端恢复，随后八次恢复 fork 通过。测量日志核实全部 42 次启动、
关闭及最终 pass。

42 份原始 stdout 与报告逐一一致，stderr 均为空；重新校验 manifest、样本、
关闭及交错顺序，重算摘要和全部比率与报告一致。元数据仍为 15 个输入、单个
61,996 字节输出且无外部模块导入；报告包含十一份 Wasm 哈希和两份不同的 Worker
哈希。该验收不扩展为浏览器结论。

固定 `3273aa7`，Node v24.22.0、esbuild 0.27.2，四逻辑 CPU 的 AMD EPYC 7763，
报告生成于 2026-10-20 12:43:49（UTC+8）。按原字节归档
[完整 wasm64 成对报告](data/fork-worker-pair-20261020-wasm64.json)，SHA-256 为
`2008c2b9703b4f079852efa7f4227597e363dd4f1ee295896bf905c68248ec4c`。
下表口径与 wasm32 相同，单位 ms，比较仅发生在各自相邻对照内部。

| 负载 / 指标 | 原版 | 打包版 | 打包 / 原版 |
| --- | ---: | ---: | ---: |
| default / 4096 次 getpid | 2.250 | 6.210 | 2.760 |
| fork-libc-raw / 4096 次 getpid | 3.260 | 6.030 | 1.850 |
| fork-libc-asyncify / 4096 次 getpid | 2.165 | 6.440 | 2.975 |
| sdk-asyncify / 4096 次 getpid | 2.465 | 5.880 | 2.385 |
| 1 MiB / fork+wait | 70.705 | 66.395 | 0.939 |
| 16 MiB / fork+wait | 79.795 | 79.425 | 0.995 |
| 64 MiB / fork+wait | 109.705 | 106.455 | 0.970 |

wasm64 本轮 fork+wait 减少约 0.5%–6.1%，但四组 syscall 循环耗时增至原版
1.85–2.97 倍，各组的三个启动中位数均复现退化；指定函数循环比率约
1.093–1.195，也没有改善。两位宽均观察到相同方向的取舍，但不是同一宿主上
重复同一个位宽的独立复验，不能据此宣称稳定收益或定位根因。

本轮双位宽功能和测量证据收尾，**整包 Worker 打包方案不满足默认优化准入**，
保留原版默认路径和可复现实验，不追加同配置性能 CI 来掩盖退化。源码与默认
配置本轮均未改变。当前已排除该轮用户/内核 Wasm 或主入口内容不同的解释，
但尚未排除 JS 变换、模块合并、代码布局或 JIT 分层等因素。

若继续调查，下一项应为单因素对照：先保持原模块边界，仅对 worker.js 使用同版
esbuild 做不打包的 ESM 转换，与原版交错测量，以区分入口变换和模块图合并。
它仍须独立构建配置、相同输入及功能/超时恢复门禁；不改变现有预热/采样口径。
另行采集的 JIT 跟踪只能用于解释，不与无跟踪计时混为性能证据。此项尚未实现，
不推断关闭某个参数即可修复，也不以池化、复用或改写 syscall 绕过该问题。

#### 入口转换控制：已实现，待 wasm32 目标验收

`750db36` / 集成 `9fb32d9` 接入默认关闭的 `benchmarkWorkerTransformAssets`。
复用同一固定工具链和参数，仅去掉 `--bundle`，转换已由 TypeScript 输出的
`worker.js`；其他依赖文件、主入口、内核及用户 Wasm 均不改。输出有且仅有一个
输入文件，不合并依赖。转换前后用 ESM 解析器比较静态导入路径及顺序，并要求
输出元数据逐项一致；新增/删除/改向导入、依赖文件改变或多个输入都拒绝。
解析器只解析不求值，其 Node `--experimental-vm-modules` 标志仅用于构建检查和
宿主反例测试，不传给功能 runner 或计时进程，不引入实验性 Wasm/浏览器特性。

普通和故障 kernel 各有独立转换配置。仍先运行三次真实 Worker 模块加载/终止、
完整普通 fork 语料和真实发布超时/迟到子端拒绝/八次恢复语料，之后才允许测量。
成对 runner 新增显式 `worker-transform-v1` / `transformed` 标签；保留旧版 bundle
报告及默认标签读取，未知或不匹配的实验/变体拒绝，不混淆成打包结果。转换、整包
打包和诊断插桩配置互斥。仍为交错的 42 次新进程、新 Worker、Linux 启动和关闭，
保持原预热/五个正式样本、输入哈希和完整原始输出，不设性能阈值。

本地 kernel 291 项、实验 19 项、SDK/raw syscall/browser 契约 16 项及源码/测试
两套 TypeScript 检查通过。19 项含两种成对 driver 的完整编排及失败反例、导入
改向/模块合并/依赖改变拒绝和不执行模块代码的检查。以新编译源码和 esbuild
0.27.2 运行入口转换、原导入一致及三次真实 Worker 加载/终止通过；旧双位宽 bundle
报告重算仍一致。格式、工作流和 scoped diff 检查通过，未在本地构建 Linux/LLVM。
[wasm32 入口转换对照](https://github.com/HighCWu/distro/actions/runs/39389036927)
已提交，固定 `750db36`；真实功能/超时阶段与全部 42 次关闭证据仍待核实。

这项对照仅检验入口转换是否足以产生退化：若未复现，仍不能直接认定模块合并
是唯一原因，因为完整 bundle 也转换了依赖代码。不得将不同运行的比率直接相减
归因；进一步定位须单独控制依赖转换或采集独立 JIT 证据。默认路径不变，尚无
本控制的目标性能结论，不增加池化、复用、COW 或多线程 fork。

#### wasm32 入口转换验收：无需模块合并也会退化

运行 `39389036927` / 作业 `118515861663` 已核实普通和故障配置的原导入/包文件
一致门禁、真实 Worker 加载/终止、普通语料十一阶段与 pass、故障语料三阶段与
pass。真实发布超时约 30 秒，迟到子端拒绝和八次恢复 fork 齐全；实际测量日志
包含全部 42 次成对启动、关闭及最终 pass。

下载的 42 份 stdout 与报告逐一一致，stderr 均为空；重新校验未插桩 manifest、
全部样本和交错顺序，重算两组摘要及比率与报告一致。元数据仅一个输入和一个
20,918 字节输出，保留十二个外部静态导入；不是闭合单模块 bundle。报告保留
十一份 Wasm 哈希及两份不同的 Worker 哈希。

固定 `750db36`，Node v24.21.0、esbuild 0.27.2，四逻辑 CPU 的 Intel Xeon
Platinum 8370C。报告生成于 2026-10-20 16:03:11（UTC+8），按原字节归档
[完整 wasm32 入口转换报告](data/fork-worker-transform-20261020-wasm32.json)，SHA-256 为
`35d551d89f6f05060d4793215da96f45e32d430dfc1eaf80e56ad3f82ade5148`。
下表仍为每次启动五个正式样本中位数，再取三次启动中位数，单位 ms。

| 负载 / 指标 | 原版 | 入口转换版 | 转换 / 原版 |
| --- | ---: | ---: | ---: |
| default / 4096 次 getpid | 1.880 | 4.065 | 2.162 |
| fork-libc-raw / 4096 次 getpid | 2.170 | 5.260 | 2.424 |
| fork-libc-asyncify / 4096 次 getpid | 1.515 | 4.420 | 2.917 |
| sdk-asyncify / 4096 次 getpid | 1.935 | 4.200 | 2.171 |
| 1 MiB / fork+wait | 65.995 | 66.140 | 1.002 |
| 16 MiB / fork+wait | 70.935 | 69.950 | 0.986 |
| 64 MiB / fork+wait | 82.770 | 82.270 | 0.994 |

四组 syscall 循环耗时增至原版 2.16–2.92 倍，每组的三个启动中位数均退化；
指定函数循环比率约 1.042–1.144。fork+wait 则从约慢 0.2% 到快 1.4%，没有
可据此提升默认配置的收益。该结果说明，在此入口/参数配置下，**不合并模块也
足以出现退化**；不能再将模块合并或依赖转换视为必要原因。不同运行的宿主和
Node 版本不同，不从旧 bundle 与本次比率之差推导它们各自的成本。

同版工具的本地生成代码检查发现更具体的候选：
[`--keep-names`](https://esbuild.github.io/api/#keep-names) 在 syscall 回调内部为
每次新建的 `invoke` 闭包插入 `__name(..., "invoke")`；该 helper 调用
`Object.defineProperty` 设置函数名称。原版同位置仅创建闭包，没有该属性操作。
这一源码证据能指出热路径上新增的操作，但不是其解释全部性能差异或 JIT 行为的
证明，不能将本地代码检查当作目标计时验收。

本控制的 wasm32 验收收尾；不为已复现的问题立即追加 wasm64 或同配置重跑，
默认源码和构建仍不变。下一候选应直接比较同版、同模块边界的入口转换配置
`keep-names=true` 与 `keep-names=false`，只切换这一个选项，保留功能、真实超时
恢复和交错计时门禁。关闭名称保留也可能影响诊断中的函数名，不能未经验证就
推广到发布构建。该新控制尚未实现或派发，退化根因仍待单因素证据确认；不改写
syscall 语义、不调整预热口径，也不增加池化或复用。

#### 日常进程延迟：同机原生 Linux / Node 对照入口

`1594891` / 集成 `05bbea7` 新增默认不执行的 `nativeComparisonAssets`，暂停继续
打包参数试错，先回答 fork 的实际可用性。首阶段选择主要目标 wasm64，在同一个
公开 CI job 上交错运行原生 Linux 与普通、未打包、未插桩的 Node Wasm 配置。
此阶段还没有浏览器性能入口或结果，不能将 Node 当作浏览器测量。

两种构建使用同一份 `latency.c` 和 `latency-exec.c`，均以 `-O2` 构建，分别测量
`fork + child validation + exit + wait` 和
`fork + child validation + exec(helper) + exit + wait`。父端另计 fork 返回时间。
载荷为 1/16/64 MiB，父端每 4 KiB 触碰，子端检查全部已触碰位置、栈/TLS、身份，
改写一个位置，父端再检查隔离和单次回收；exec helper 检查新 TLS、参数、环境及
身份，默认 libc 编译的 helper 不含 continuation 变换。失败或 exec 返回不产生
成功报告。载荷检查在 fork+wait 区间内，不声称测量纯内核 syscall 成本。

每个模式/载荷分别交错执行三个新进程，新进程内一轮预热与 30 个正式样本：
六组 × 两平台 × 三次启动，共 36 次测量进程、每个平台 540 个正式样本；Node
部分为 18 次全新 Linux 启动并等待 machine.closed。不修改旧五样本基线。
报告每次启动的 nearest-rank P50、P95、最大值及汇集 90 个样本的描述性统计，
汇集样本仍聚集于三个进程，不能称作 90 个独立启动或可靠极端尾延迟估计。
保留全部 stdout/stderr、编译器版本、源码/辅助源码、二进制和内核哈希及 CPU/Node
信息，不覆盖旧结果；缺样本、失败、stall、插桩输出或未关闭都拒绝。

原生使用宿主 ABI/libc 和正常 COW；Wasm 使用 opt-in 单线程静态 SDK 和 eager
copy。native 的 linear_bytes=0 仅表示“不适用”，不是零内存占用。总地址空间、
指令集、libc、exec loader 和编译路径不同，测量是同机端到端平台差异，不是这些
单因素的独立成本；不保证 CPU 亲和性或无宿主背景负载。不设置性能通过阈值，
先取得绝对延迟、尾部和同机倍数，再判断日常短命进程是否可用。

本地六项新检查通过，包括 GCC/Clang 的全部六组真实原生语料、错误 helper
拒绝、完整 36 槽位编排与原始记录保存、采样/尾部分组及覆盖拒绝。原实验 19 项、
kernel 291 项及格式/工作流检查通过；轻量检查不构成同机 Wasm 性能验收。
[wasm64 同机原生 / Node 对照](https://github.com/HighCWu/distro/actions/runs/39394000022)
已提交，固定 `1594891`，实际目标结果和比率待核实。后续浏览器必须复用这份
语料并单独保存引擎版本、原始输出及关闭证据；当前不派发额外打包优化，不扩大
fork 支持范围或改变默认 SDK。

#### 同机 wasm64 / 原生 Linux 验收：短命进程差距显著

运行 `39394000022` / 作业 `118532223559` 已完成；实际日志核实全部 36 次新进程
开始和完成以及最终 pass。18 次 Node 测量均等待 Linux machine.closed，18 次
原生进程均正常退出。全部 36 份 stdout 与报告逐一一致，stderr 均为空；重新验证
六组语料、每轮 30 个正式样本、交错顺序和关闭，重算分组摘要和比率与报告一致。
源码及 helper 源码哈希与固定版本相符，原生/Wasm 各七份二进制哈希均被记录。
共核实 1,080 个正式样本，仍仅为每组各三个测量进程，不扩大独立运行次数。

固定 `1594891`，Node v24.21.0、原生 GCC 15.2.0、Wasm Clang 22.1.8，四逻辑 CPU
的 AMD EPYC 7763。报告生成于 2026-10-20 16:46:05（UTC+8），按原字节归档
[完整同机 wasm64 / 原生报告](data/fork-native-node-20261020-wasm64.json)，SHA-256 为
`c076289d92837e32cf47ea1e657ec56606a67f214a4c9196a085fb12e8dac336`。
下表单位 ms，P50/P95 为各组汇集 90 样本的 nearest-rank 描述性分位数；每轮分位数
及最大值保留在原报告。时间含子端校验和 wait，不含初始 Linux 启动。

| 模式 / 载荷 | 原生 P50 | Node P50 | 原生 P95 | Node P95 | Node / 原生 P50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| fork+exit+wait / 1 MiB | 0.183 | 71.390 | 0.209 | 81.455 | 389.8 |
| fork+exit+wait / 16 MiB | 0.183 | 70.025 | 0.223 | 77.645 | 383.5 |
| fork+exit+wait / 64 MiB | 0.279 | 79.395 | 0.318 | 80.830 | 284.8 |
| fork+exec+wait / 1 MiB | 0.598 | 69.750 | 0.663 | 79.105 | 116.6 |
| fork+exec+wait / 16 MiB | 0.599 | 76.545 | 0.688 | 79.850 | 127.7 |
| fork+exec+wait / 64 MiB | 0.696 | 80.580 | 0.794 | 88.300 | 115.8 |

父端 fork 返回本身的 pooled P50，原生约 0.071–0.092 ms，Node 约 65.3–78.4 ms；
并非只有父端 wait 慢。不同模式是不同进程，不能用 exec 与 exit 两行相减估计
exec 的独立成本，也不能从数值接近推导 exec 没有成本。

这轮证据否定了“当前 Node 短命进程体验已接近原生 Linux”的说法：fork+exit
约慢 285–390 倍，fork+exec 约慢 116–128 倍。几十毫秒的绝对延迟对偶尔启动后
长时间工作的子进程可能可接受，但不能据此宣称 shell、构建系统或频繁短命进程
负载已日常好用。倍数只属于此主机、语料和配置；原生 COW、不同 ABI/libc、
编译器和 loader 的差异均在端到端结果内，不归因于单个指令集或某项内核逻辑。
先前诊断提示 Worker 异步启动有较大固定成本，但不能将重叠区间相加，或承诺
解决 keep-names 即可消除此处普通路径的差距；该配置没有启用 keep-names 打包。

下一必要证据是相同语料在固定 Chromium/Firefox 的实际延迟和关闭结果，尽量
与原生及 Node 放在同一 runner job 中比较，并记录浏览器版本；目前尚未接入，
没有浏览器性能结论。不立即开展更多打包参数或 wasm32 扩展测量。是否接受此
绝对延迟，或需要调整进程创建架构，应在浏览器结果和真实短命进程负载之后明确
评审，不以优化几个百分点代替这个产品边界决定。默认构建和 fork 支持范围不变。

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
