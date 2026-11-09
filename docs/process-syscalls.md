<!-- SPDX-License-Identifier: MIT -->

# 标准进程控制与 direct 内存 syscall 准入

本阶段以真实程序能力为主，不恢复性能实验。新增进程控制工作负载把已有 Linux
实现、Wasm syscall 转发和用户态恢复组合起来验证；不是新增私有 syscall 编号或
应用 API，也不能仅凭 Linux 上游有实现就认为当前 Wasm 配置已经支持。

## 第一组：pidfd 与退出生命周期

程序仍通过现有可选单线程 fork profile 创建子进程；父子用 pipe 建立确定的运行
状态，然后使用以下标准接口：

| 接口 | 当前准入内容 |
| --- | --- |
| `pidfd_open` | 获取活着的子进程句柄，核对 `FD_CLOEXEC`，拒绝非法 flags |
| `pidfd_send_signal` | signal 0 存活检查、SIGTERM 投递、坏 fd/flags 拒绝、回收后 ESRCH |
| `poll` | 活进程尚未退出时不就绪，退出后 pidfd 可读 |
| `waitid(P_PIDFD)` | 两次 WNOWAIT 观察相同子进程、CLD_KILLED 和终止信号 |
| `waitpid` | 终止状态一致，回收后 pidfd waitid 返回 ECHILD，之后仍能 fork/wait |

当前 musl 没有 pidfd 专用包装函数，工作负载中的薄适配仅在测试内使用普通
`syscall()`，所有参数按机器字宽显式传入并补齐六参数；不安装项目自有包装 API。
这里以 `tombl/musl` 为直接上游，不为缺少包装而扩展本项目 musl 的公共 API；
新增包装实验已清理，具体审计与历史处理见[musl 变更边界](musl-compatibility.md)。
不把上述测试扩大成所有 pidfd flags、pidfd_getfd、PID 实际回绕压力、非子进程
权限、进程组或多线程 fork 的支持声明。信号目标进入正常内核等待点，不证明
任意纯用户态计算循环可被立即抢占。

## 浏览器准入

复用现有 `runRuntimeSmoke` 等待机器关闭与控制台收尾的机制，新增独立运行器。
每个引擎在同一页面启动两次独立机器，要求隔离上下文、对应位宽、完整且有序的
阶段输出和唯一最终 pass，并拒绝 panic、RCU stall、页面错误及关闭后的迟到错误。
随后有界关闭浏览器及服务进程，确认浏览器连接已断开，再报告最终成功。

同一运行器接收明确的 Dash 或 pidfd 工作负载，不使用回调 clone 改写 Dash，也
不把单个协议 pass 当作所有阶段已经执行。浏览器由公开 CI 的固定引擎运行，
不在本地下载或构建浏览器。

## 本轮状态

distro `3ddc9d6` / 集成 `cec0a99`。本地相关 19 项检查通过，包含 GCC/Clang 的
实际原生 pidfd 执行及伪造信号成功的反向控制；还包含宿主模拟浏览器驱动的两轮
与迟到错误拒绝。模拟检查不是浏览器运行证据，原生 Linux 也不是 Wasm 证据。
格式和 workflow 检查通过，默认 SDK、内核配置及 fork 支持范围保持不变。

[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39518885256) 已成功，固定
`3ddc9d6` 的实际日志确认全部三阶段与最终 pass。运行器必须等待 machine.closed
且关闭错误使进程非零退出；结合该目标作业成功，确认本轮收尾门禁通过。没有
新增内核实现或 syscall 编号，而是确认这一组已有接口在当前 Wasm 配置可运行。

随后派发同源码的 [Chromium](https://github.com/HighCWu/distro/actions/runs/39526613240)、
[Firefox](https://github.com/HighCWu/distro/actions/runs/39526618525) 与
[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39526623595) 均已成功，实际
日志逐项核实完整三阶段、最终 pass。Chromium 149.0.7827.55、Firefox 151.0 各两轮，
含每轮机器关闭和最终浏览器关闭标记；wasm32 Node 通过等待 machine.closed 的退出
门禁。不据此推定 CLONE_PIDFD 原子获取、全部 flags 或无控制的 PID 回绕压力通过。

## 第二组：execveat 与 fexecve

distro `9025bdd` / 集成 `4c885e6` 新增独立 `exec-fd` 工作负载。程序 fork 后从
已打开的可执行文件 fd 重新执行自身，验证：

- musl 的 `fexecve`、原始 `execveat(AT_EMPTY_PATH)` 与目录 fd 的相对路径执行；
- 子进程 PID/父身份、参数环境、TLS 新初始化、可执行 fd 的 CLOEXEC，以及未标记
  关闭的数据 fd 和共享文件 offset 的继承；父进程 TLS 不变；
- EBADF、EINVAL、ENOENT、EACCES 返回后旧程序仍存在，后续 fork/wait 可正常运行。

测试本地的 execveat 薄适配使用标准 syscall 号和六机器字参数，不安装新应用 API。
目标自执行文件是 Wasm 可执行模块，不是脚本；不覆盖脚本解释器与 CLOEXEC 的特殊
组合、全部 execveat flags、权限模型或多线程 exec。默认 SDK 和内核保持不变。

GCC/Clang 实际原生运行、故意去掉 CLOEXEC 的反向控制及相关阶段/SDK 检查共 13 项
通过，格式/元数据检查通过；这些不是 Wasm 证据。
[wasm64 目标](https://github.com/HighCWu/distro/actions/runs/39526747006) 已成功，实际
日志核实全部三阶段与最终 pass，并通过运行器关闭门禁。distro `73f74b2` / 集成
`6c088a6` 只补充相同语料的浏览器装配，随后派发
[Chromium](https://github.com/HighCWu/distro/actions/runs/39530457614)、
[Firefox](https://github.com/HighCWu/distro/actions/runs/39530463413) 和
[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39530468988) 均已成功，实际
日志核实全部三阶段和最终 pass。Chromium 149.0.7827.55、Firefox 151.0 各执行两轮，
每轮确认机器关闭，最终确认浏览器关闭；wasm32 Node 通过运行器关闭门禁。
这些是原 exec-fd 语料的结果，不覆盖下文新增 close_range 阶段。

## 第三组：clone3 fork 形态的实际接入

此前的执行适配只识别 clone 220，不能直接将 clone3 普通 fork 送入原回调式内核
路径。distro `269f4d4` / 集成 `8d5d0d4` 实现标准号 435 在可选 v2 执行入口的有限
接入，旧 callback import 明确返回 ENOSYS。默认 SDK 不启用 continuation，Linux 内核源码未改；
新增解析与执行适配为 MIT，不新增应用 API 或内核 softmmu。

随后发现 Wasm musl 公共头文件缺少标准 `SYS_clone3` 编号，已在 musl `e7bde79`
补齐，并由 distro `edb5719` / 集成 `f1d1cb0` 固定源码及验证过的下载哈希。
这只是公开标准号声明，不是 musl 新增 clone3 包装函数，也不表示默认程序已获得
fork continuation。早期 `269f4d4` 未包含该头文件修复，不作为目标验收版本。

最终版本 distro `abddde6` / 集成 `e72d8fa` 要求 syscall 扩展 ABI 2，防止新程序
被仅认识 ABI 1 的旧 loader 错误接纳。新 loader 继续兼容 ABI 1 的旧 clone 功能，
但仅为 ABI 2 对象启用 clone3；未知版本拒绝。支持边界仍不扩大。

支持边界与错误策略见[clone3 执行 ABI](fork-continuation-abi.md#clone3-的有限-fork-形态)。
该早期版本只接纳无 flags、默认栈、SIGCHLD、无 tid/pidfd/TLS/cgroup 选项的单线程 fork。
指针/长度先验证，结构字段保持完整 u64；保存区重入和恢复受现有状态机控制。
对未支持的合法组合拒绝，不声称实现完整 clone3。该阶段尚不支持 CLONE_PIDFD
原子返回 pidfd；后续 PIDFD 与命名空间传递各自记录实现和目标范围，不沿用早期结论。

新原始调用语料检查旧 import 拒绝、坏地址/长度/尾部、未支持形态、不留下可回收
子进程，随后按 64/80/88/96 四种长度从相同 syscall 调用点恢复父子，核对 PID/PPID、
栈局部变量、私有全局隔离及单次 wait。未经变换的 exec 子程序也必须拒绝 clone3。
浏览器 normal fork 门禁增加独立阶段，不能只靠原有 fork pass 代替。

最终版本本地 298 项内核侧检查、18 项相关协议/工具检查及源码和测试 TypeScript 检查通过。
后者包含 Clang 实际编译链接 wasm32/wasm64 小模块，并实例化核对 ABI 2 导出；
freestanding 测试专用 memset 仅补足测试环境，不改变正式 C 语料或 libc。
GCC/Clang 的 C 语料通过原生 fork shim 运行，另有 clone3 专属错误身份反向控制；
它们不是宿主原生 clone3 或 Wasm 运行证明。新的
[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39532388311) 与
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39532393851)
已成功，实际日志核实新增 clone3 阶段、原 raw clone、PID/TLS/atfork、pending signal、
exec 成功／失败、pthread 与 signal callback 拒绝及后续恢复、最终 pass。两个目标
均通过等待 machine.closed 的运行器关闭门禁，因此记录双位宽 Node 准入通过。
浏览器另对 distro `8c3d612` 派发四路完整 fork 检查；该源码只在 exec-fd 语料扩展
close_range，clone3 实现仍与 `abddde6` 相同。未完成前不计为浏览器准入通过。

本轮浏览器任务为
[wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39534457837)、
[wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39534465683)、
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39534471508)、
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39534477059)。
仍要求 normal/fault/signal 对应完整阶段、各两轮和关闭，不用 Node 结果代替。

其中 Firefox 151.0 双位宽已成功，实际日志逐项核实全部 normal 阶段（含 clone3）、
faults 三阶段（含真实 publication timeout）及三类 signal 阶段各两次；五种 profile
各两轮均有机器关闭标记。作业成功且运行器等待 browser.close 完成，浏览器收尾
门禁通过。Chromium 两路仍在运行，不由 Firefox 推定通过。

## 第四组：close_range 与 exec 前 fd 清理

distro `8c3d612` / 集成 `3e61caa` 扩展原 exec-fd 语料，直接调用标准
`SYS_close_range`，不安装新的应用包装函数。公共 musl 已有该编号，Linux 也已有
实现，因此本轮先验证真实 Wasm 路径，未重复编写内核实现。

- 关闭含空洞的有界区间，核对区间内关闭及区间外 fd 保留；
- `UINT_MAX` 上界和 `CLOSE_RANGE_UNSHARE`，核对 fork 子进程关闭后父进程 fd 保留；
- 首末倒置或非法 flags 返回 EINVAL，原 fd 保持有效；
- `CLOSE_RANGE_CLOEXEC` 及其与 UNSHARE 的组合：此前未标记的复制 fd 在调用后
  仍可访问且带 FD_CLOEXEC，直到 fexecve 替换程序才关闭；数据 fd 继续继承；
- 原 execveat/fexecve、共享文件 offset、错误返回和后续 fork/wait 回归继续执行。

本地 298 项内核侧检查、15 项相关语料/协议/链接检查通过。GCC 与 Clang 各执行
正常路径和三种反向控制：可执行 fd 泄漏、close_range 伪造成功、丢失 CLOEXEC
语义都必须导致失败；这些仅验证宿主语料，不证明 Wasm syscall 已通过。

新增阶段被纳入原 execfd 的严格阶段门禁。
[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39534312750) 与
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39534320861) 的实际
阶段与关闭结果见下文。测试是在单线程 fork 后独立 fd 表上执行，
不覆盖 CLONE_FILES 共享表被 UNSHARE 分离的分支，也不声称支持多线程 fork。
本轮没有改变默认 SDK、内核配置、执行 ABI 版本或原 clone3 的支持范围。

双位宽 Node 现均成功，实际日志各自核实全部五阶段、最终 pass 和运行器关闭门禁。
这里的五阶段包含新增两项 close_range 阶段，不能用较早的三阶段结果替代。
随后对 `96a3ea6` 派发
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39535788089) 与
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39535792530)；该版本仅扩展独立
pidfd 语料，exec-fd/close_range 的 C 语料与 `8c3d612` 相同，新增两阶段仍须各两轮
和关闭验收，尚未计为浏览器通过。

## 第五组：停止、继续与非退出 wait 状态

distro `96a3ea6` / 集成 `0e820fc` 将既有 pidfd 工作负载扩展到进程的非退出状态，
仍使用标准 pidfd_send_signal、waitid、waitpid 和 poll，不增加 syscall 号或应用 API。
子进程用 pipe 固定在正常内核等待点，父进程按确定顺序执行：

- SIGSTOP 后，两次 `waitid(P_PIDFD, WSTOPPED | WNOWAIT)` 必须观察同一 PID、
  CLD_STOPPED 与 SIGSTOP，再由 `waitpid(WUNTRACED)` 消费该状态；
- 消费后 `waitid(WSTOPPED | WNOHANG)` 成功但 si_pid 为零，不能再次报告已消费状态；
- 停止的进程仍存在，pidfd 不应报告退出就绪；
- SIGCONT 后，同样两次观察 CLD_CONTINUED/SIGCONT，用 `waitpid(WCONTINUED)`
  消费，再核对 WNOHANG 空结果、存活与非退出就绪；
- 之后仍须执行原 SIGTERM、退出就绪、WNOWAIT 退出观察、单次终止回收及后续 fork。

Linux 上游已有相应路径，本轮先验证 Wasm 适配是否正确组合这些行为；并非重新
实现信号内核或声称已修复尚未发现的问题。本地 298 项内核侧检查、13 项相关检查
通过，含 GCC/Clang 实际宿主执行和伪造 continued 返回状态的拒绝控制。这些不是
Wasm 证据，新增两阶段已纳入 pidfd 的严格浏览器阶段协议。

[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39535613953) 与
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39535619241) 已派发，待目标
阶段与关闭验收；浏览器尚未对该增量派发。范围仅为单线程 fork 子进程，不覆盖
终端 foreground process group、完整 shell 作业控制、多线程 group-stop 或任意
纯用户态循环的即时抢占。默认 SDK、内核配置及 fork 执行 ABI 均不改变。

## 第六组：prlimit64、fd 限额与 exec 继承

distro `04724e7` / 集成 `f8a42c0` 扩展独立 exec-fd 语料，调用公开的
`getrlimit/setrlimit/prlimit`，并用六机器字 raw syscall 检查坏指针返回。musl 已提供
这些标准接口，新增代码只做组合验收，不增加私有应用 API 或重复实现内核路径。

- 两种位宽均静态断言 rlim_t 为 8 字节、struct rlimit 为 16 字节；NOFILE 查询时
  getrlimit 与 prlimit 一致；非法 resource、soft 大于 hard 和坏输入／输出指针分别
  返回 EINVAL 或 EFAULT，之后原 NOFILE 限额保持不变；
- CORE soft 分别设置为 `0xfffffff0` 和 `0x100000007`，核对普通有限值以及按内核
  位宽处理的高值和不变的 hard，再恢复原限额。测试要求独立机器原 CORE hard 为
  infinity，并非发布平台的一般使用前提。Linux32 在 ULONG_MAX 饱和为 infinity，
  Linux64 保留该高位有限值；两者的公开 rlim_t 结构均仍为 64 位；
- fork 子进程用 prlimit 原子设置 NOFILE soft=32 并取回旧值，保留原 hard；实际 dup
  直到 EMFILE，再关闭全部临时 fd；不能只靠查询数值判断限额已经执行；
- 随后从 fd exec 自身，替换后的程序核对 soft=32、原 hard、fd/TLS/身份与文件
  offset；父程序每轮仍保持原 NOFILE soft/hard。其余五种原 exec 模式继续保留。

本地 298 项内核侧检查、13 项相关语料/工具检查通过；GCC/Clang 的正常和反向语料
包含伪造 32 位 CORE 查询结果的拒绝控制。新增两阶段进入 execfd 严格阶段门禁。
[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39536454222) 与
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39536460094)
已对最终版本派发，尚不计为目标验收通过；不扩展为 RLIMIT_AS/CPU/
NPROC 等所有资源的实现或完整权限模型验证，也不扩大多线程 fork 支持。

wasm32 `39536454222` 的实际日志在 CORE 高值阶段失败。静态核对固定 Linux
`6494640` 的 kernel/sys.c 发现：rlim64_is_infinity 在 BITS_PER_LONG<64 时使用
`rlim64 >= ULONG_MAX`，是标准 Linux32 的饱和语义，不是本项目丢失高位。
`5f69138` / 集成 `c8edd2e` 修正此前不正确的跨位宽测试预期，不修改内核；宿主
测试额外模拟 Linux32 饱和分支，原窄化查询的反向控制仍须失败。修正后重新派发
[wasm32](https://github.com/HighCWu/distro/actions/runs/39537681796)，不能用旧失败结果或
宿主模拟取代真实复验。

## 第七组：使用普通 fork 的独立 Bash 候选

`444d2b6`（随 `5f69138` / 集成 `c8edd2e` 发布）增加 bash-fork 和
bash-fork-wasm64；它们不替换原 Bash、默认 shell、SDK 或原有 callback 程序。
候选复用原 Bash 固定源码和相同九个 GNU 维护补丁，仅保留 anonfile 的标准声明
修正，不使用 bash-clone、fork-shim 或应用回调改写，也不把 vfork 替换为 fork。
完整程序使用可选编译器构建并执行一次 whole-link continuation finalization。

候选的非交互真实程序语料覆盖：

- 普通 subshell 的私有状态、函数 local 与嵌套 command substitution、外部命令和管道；
- `/dev/fd` process substitution、coprocess 双向 pipe、复制 fd 的生命周期与 wait；
- 后台子进程退出码、USR1 trap 和父状态保持；
- exec 的 126/127、语法错误返回、错误后继续启动子程序。

测试初始化只在目标机器挂载 devtmpfs/procfs，原生测试不修改宿主挂载点；coprocess
先复制描述符再交互，避免 Bash 自动收尾 fd 造成测试自身竞态。原生完整四阶段及
依赖失败的拒绝控制通过；ShellCheck、shfmt、oxfmt、nixfmt 与配方契约检查通过。
这些仅证明语料和静态装配，不证明 Wasm 运行或 SjLj/Asyncify 兼容性。

这比此前 Dash 更明确地触及 C setjmp/longjmp 与 continuation 的组合，因此仍是
独立实验候选。保留 SjLj lowering，不以删除 trap、改成应用 callback 或宣称支持
任意 C++ EH/SjLj 来回避问题。首轮只派发
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39537687874)；wasm32/浏览器尚未验收。
本轮关闭 readline 以隔离非交互进程能力，不对交互式行编辑或完整终端 job control
作支持声明，原默认 Bash 的 readline/交互构建保持原样。

新增配方、测试脚本为 MIT；Bash 自身保持 GNU GPLv3+，安装其 COPYING，固定源码、
维护补丁、额外声明补丁、配置日志和 SDK 构建材料引用一同提供，不更改其许可证。

### 独立的 C SjLj 执行前提

`fa31773` / 集成 `651e4b1` 新增 bash-fork[-wasm64]-check-sjlj，直接使用同一个
可选 SDK 编译一个独立静态 C 程序并进行 whole-link finalization，不依赖 Bash
构建完成。它验证 Bash 所需的具体前提，而不是增加一项与实际程序无关的 syscall。

程序在 sigsetjmp 保存的祖先 C 帧内 fork。父子分别改变 volatile 局部变量、私有
TLS 和信号掩码，再从较深的普通用户 C 帧 siglongjmp 回保存点，核对返回值、身份、
局部/TLS 私有性及恢复的掩码。父进程单次回收子进程，恢复原掩码；随后验证
longjmp(env, 0) 返回 1，并再次 fork/wait，防止非局部跳转留下失效的 continuation 状态。

setjmp 仅用于 switch 控制表达式；跨跳转读取的被修改自动变量均为 volatile。
跳转发生于 syscall 返回后的普通用户执行，不从 signal handler 或内核回调跨出，
也不跳转至已经返回的 C 帧。GCC/Clang 正常语料与伪造子返回值、丢失 mask 的反向
控制通过；原生结果不能证明 Wasm EH/catchpad、SjLj lowering 与 Asyncify 已兼容。
[独立 wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39538323649)
已对 `5a366bf` 派发，仍不修改 SDK 的现有 SjLj/C++ 支持限制。

上述独立 SjLj 目标现已成功，实际日志核实两阶段与唯一最终 pass，运行器等待
machine.closed 且关闭失败会使检查失败。Bash 的
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39537687874) 也已成功：
实际四阶段完整、唯一最终 pass，并通过同一关闭门禁。它们分别证明有限 C 执行
前提和非交互 Bash 工作负载，不扩大到任意 C++ EH 或完整终端作业控制。

`c7b299a` / 集成 `d178195` 将同一普通-fork Bash 的 runtimeAssets 接入独立的
wasm64 Chromium/Firefox 检查，不替换默认 Bash，不新增 musl 函数，也不重写应用
为 callback clone。复用既有固定 Playwright 运行器和内核包，每个引擎在同一页面
启动两次独立机器，要求全部四阶段、唯一 pass、每轮机器关闭、最终浏览器关闭，
并拒绝关闭期间的迟到页面错误。本地相关 13 项检查和 Clang analyzer 通过；
宿主模拟驱动与原生 Bash 结果不是浏览器证明。浏览器及 wasm32 Node 补验已派发，
实际阶段与关闭结果仍待核实，不因验收入口存在就声明通过。
本轮固定源码的任务为
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39541630662)、
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39541635978) 与
[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39541642469)。

该批次现已核实通过。Chromium 149.0.7827.55 与 Firefox 151.0 的实际日志各有
两轮完整四阶段及唯一 pass，每轮机器关闭和最终浏览器关闭标记齐全；wasm32 Node
也核实完整四阶段、最终 pass 与等待 machine.closed 的退出门禁。此证据固定在
`c7b299a`，不覆盖后续新内核的 PIDFD 回滚或用户 NULL 访问修复。

Clang 静态分析还对 exec-fd 的重复 getenv 检查给出保守 nonnull 警告。本例没有
证实并发环境修改缺陷；`5a366bf` / 集成 `7b70ef4` 将它改为单次读取并守卫同一个
指针，增加缺失／错误 marker 的明确拒绝检查。新 C 契约与 exec-fd 现都通过宿主
Clang analyzer，根仓库 CI 将相关 analyzer 警告作为错误；这不替代 Wasm 目标分析。
候选材料同时补齐独立 C 源码和两套宿主检查源码。

## 第八组：原子 CLONE_PIDFD 与创建失败回滚

distro `16473c2` 通过标准 clone3 选项在创建子进程时取得 pidfd，不新增 musl 公共
函数，不使用 fork 后 pidfd_open 代替内核原子路径。仅接纳单线程、SIGCHLD、默认栈
和单独 CLONE_PIDFD；普通 clone、其他 clone3 选项及默认 SDK 的边界不扩大。
完整执行约定见[clone3 PIDFD 增量](fork-continuation-abi.md#clone3-的-clone_pidfd-增量)。

静态 review 发现必须先修复的内核缺口：copy_thread 提前创建 Worker，随后
pidfd_prepare 可能因 EMFILE 失败，原架构没有 exit_thread 来停止该 Worker；
内核继续释放任务和栈会使尚未调度的 Worker 留下失效引用。Linux `8319e3950`
补齐同步 abort 确认及 bootstrap 生命周期，`feb624494` 增加内部能力标记。
新 loader 只在该内核能力为 1 且执行对象提供专用 helper 时开放 PIDFD 形态，
旧内核/旧对象明确拒绝，防止把成功路径接通误当作失败路径也安全。

新增真实目标语料覆盖：坏的完整 u64 输出地址；NOFILE 耗尽后三次 EMFILE、输出
不变及无可回收子进程；恢复 fd 容量后原子创建；父端 CLOEXEC、子端输出值隔离
和未继承父 pidfd；通过返回的 pidfd 发信号、poll、waitid 核对同一子进程并单次
回收；随后仍执行普通 fork/wait，检查捕获选项没有残留。新增完整阶段加入 pidfd
语料门禁，不能用旧五阶段通过替代这一增量。

本地 300 项内核侧检查、源码/测试 TypeScript、18 项相关语料/链接检查和 Clang
analyzer 通过。小型 wasm32/wasm64 实例实际调用新增执行 helper，检查 callback
clone 参数及高位输出地址不被截断；这不是 Linux 运行证据。内核确切函数另经
GCC/Clang 原生并发及 ASan/UBSan 检查，覆盖早到/迟到 Worker，撤销确认等待必须
失败；小型 Wasm 编译检查最终确认后无任务数据读取。宿主进程语料显式使用
fork+pidfd_open shim，因此只验证语料逻辑，不证明原子创建或 Wasm 内核。

公开源码预取已固定最终 Linux rev/hash，集成提交为 `f14d72e`。
[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39543176343) 与
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39543181756) 已派发；实际
新增阶段、失败后恢复及关闭结果尚未核实，浏览器尚未对这个版本派发。

上述 `16473c2` 双位宽 Node 现已成功。实际日志各自核实完整六阶段，包含新增
原子 PIDFD、三次 EMFILE 回滚与输出隔离、之后普通 fork/wait，以及唯一最终 pass；
两项均通过等待 machine.closed 的运行器退出门禁。没有以宿主 fork+pidfd_open
shim 代替原子目标证明。随后在 `a7926dc` 派发
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39545435360) 与
[wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39545440270)，要求完整
六阶段各两轮、机器及浏览器关闭。该版本同时含后续 NULL/部分复制修复，不能用
旧 Node 结果推定浏览器或这些新访问层变更已通过。
该批次浏览器现已成功：固定 `a7926dc` 的实际日志逐项核实 Chromium 149.0.7827.55
和 Firefox 151.0 各两轮完整六阶段、每轮唯一 pass 与机器关闭，以及最终浏览器
关闭标记。它覆盖实际原子创建和 EMFILE 后恢复，不由 host shim 替代。它仍不是
完整 clone3、多线程 fork、wasm32 浏览器或独立用户访存故障语料的验收。

## 第九组：标准 syscall 的 NULL 用户指针

静态 review 发现 user.read/write/write_zeroes 直接把用户地址交给通用线性内存
view；Wasm 中存在第 0 字节，因此非零长度 NULL 地址可能被当作普通缓冲区读写，
而不是向 Linux 返回未复制字节数。futex 的原子访问也有同样的零地址问题。

distro `4aafe2f` / 集成 `08d7bd6` 将用户复制和原子 word 校验集中到内部模块：
非零长度 NULL 用户指针返回全量未复制字节数，原子路径返回 EFAULT；内核据此决定
syscall 错误。不更改通用 memory_bytes，不把内核自己的地址 0 误判为用户 NULL；
零长度复制不触碰缓冲区。普通有效地址、对齐检查和既有边界检查保持不变。
新增模块不由包的公共 exports 导出，没有新增应用 API、musl 函数或 Linux 改动。

撤掉 NULL 校验后，双位宽标量的四项回归实际复现失败；恢复后完整 306 项内核侧
检查、源码/测试 TypeScript、GCC/Clang 原生 syscall 语料及 Clang analyzer 通过。
这不是实际 memory64 或 Linux/Wasm 执行证明。真实 C 语料检查 NULL read 不消费
pipe 中原字节、NULL write 不额外排队、NULL 路径/结构输出/原子目标返回 EFAULT，
零长度 read/write 成功，随后有效 uname 和 pipe 读写及 fd 清理仍正常。
原生反向控制会拒绝伪造 uname 成功和先写入字节再伪造 EFAULT 的错误实现。

[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39544430341) 与
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39544435571) 已派发，要求
实际两个阶段、最终 pass 和运行器关闭门禁；目前未核实，不由原生 Linux 结果推定。
仍保留一个独立缺口：跨越当前线性内存末端的复制目前整段拒绝，尚未实现有效
前缀复制及剩余字节计数；下一增量应补齐该行为，不把此处 NULL 修复泛化为完整
Linux 用户访存、页权限或内存保护支持。

其中 `4aafe2f` 的 wasm64 Node 已成功，实际两个阶段、唯一最终 pass 与运行器
关闭门禁已核实；它不含下文的部分复制阶段，wasm32 实际日志仍待补取。
随后 wasm32 实际日志也已补齐：同一两个阶段、唯一最终 pass 和运行器关闭门禁
通过，因此该 NULL 基线的双位宽 Node 均已核实。不要用此两阶段结果代替下文
`a7926dc` 的新三阶段验收。

## 第十组：用户复制的有效前缀与剩余字节

distro `a7926dc` / 集成 `fcce5af` 补齐上述独立缺口。用户范围跨当前线性内存末端
时，读取、写入和清零只作用于有效前缀，返回请求长度减去实际复制长度；完全
无效的起点和非空 NULL 仍整段拒绝。内核侧缓冲区必须完整有效，不能借部分用户
范围访问损坏的内核范围。通用 memory_bytes、原子 word 的完整宽度/对齐要求、
musl、执行 ABI、Linux 源码和 CONFIG_MMU 均不改。

实现每次重新查看内存范围，不持有旧 view 作为永久上限。两项新前缀回归在修改前
实际失败，修改后完整 310 项内核侧检查及源码/测试 TypeScript 通过；小型真实
memory32/memory64 共享内存模块执行 memory.grow 后，下一次复制可访问新增范围。
清零的未完成部分不触碰地址空间之外的字节，不伪造完全成功。

syscall 的短读写或错误仍由 Linux 调用路径决定，不能直接用前缀长度替换 syscall
返回值。核对固定 Linux 的 fs/pipe.c、mm/filemap.c 和 lib/iov_iter.c 后，真实
语料分别要求：普通文件按复制字节返回短读写、更新 offset 并保留原文件后缀；
本轮小型 pipe 请求的失败读取返回 EFAULT、用户缓冲区已收到有效前缀，但原 pipe
队列不被消费；不完整 pipe 写入返回 EFAULT 且不发布字节。之后仍执行有效重试
和 fd 清理。这不是所有文件系统、设备、iov 组合或页保护的完整支持声明。

GCC/Clang 原生语料用 mmap+PROT_NONE 构造不可访问边界，核实完整三阶段并拒绝
伪造复制计数、吞掉 pipe 队列等反向控制；目标 Wasm 不使用 mprotect，而用标准
memory.grow 预留新页，在新的线性内存末端构造同样的有效前缀。没有内核 softmmu、
浏览器新提案依赖或新应用 API；原生页权限仅用于测试，不能推定 Wasm 有页权限。

新版本 [wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39545413872) 与
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39545418579) 已派发，必须
核实新增前缀阶段、原 NULL 阶段、恢复阶段、唯一 pass 和机器关闭；尚不计为通过。
上述 `a7926dc` 双位宽 Node 现均成功，实际三阶段和唯一最终 pass 已逐项核实，
均通过运行器等待 machine.closed 的收尾门禁。不要用更早的两阶段 NULL 基线替代
该结果，也不要据此推定后续高地址指针修复通过。

## 第十一组：Wasm32 高位指针的寄存器表示

静态 review 发现：原始 Wasm i32 导入把 0x80000000 以上的指针作为负 Number
交给 JS，旧的非负 offset 校验因此错误拒绝本来位于用户线性内存中的地址。
distro `0ba04b0` / 集成 `70345ba` 在原始指针入口恢复无符号 i32 位模式，应用于
用户复制、清零、futex 原子 word 和相关内核旧值缓冲区。memory64 的 BigInt 不按
32 位截断；越出真实 i32 表示范围的 Number、非整数和不可安全表示地址仍拒绝。
通用 memory_bytes、JS offset/元数据校验、长度和 flags 的解释不放宽，不把所有
整数参数一律当成无符号指针。没有新增 musl 函数、应用 API、Linux 或 MMU 改动。

本地 312 项内核侧检查及源码/测试 TypeScript 通过。小型真实 Wasm 导入验证
指针进入 JS 时确实是负值，并核对完整无符号地址恢复；恢复旧转换时，两项回归
实际失败。没有在本地申请 2 GiB 内存，也不把小模块证明当作高地址 Linux 运行证明。

新增 `toolchain-smoke-check-user-access-upper32` 独立配置，只在 wasm32 提供。
它按声明内存上限请求 2 GiB+一页的地址范围，在新高页上检验 pipe 数据源/目标、
uname 结构输出与 FUTEX_WAKE_OP 原子操作，然后继续原有效重试、fd 清理和关闭。
默认 user-access 程序不定义该测试宏，不请求这块大地址范围；不修改默认 SDK
或应用内存初始值。请求失败会明确使目标检查失败，不跳过后宣称高地址通过。

[wasm32 高地址](https://github.com/HighCWu/distro/actions/runs/39546540226) 与
[wasm64 普通回归](https://github.com/HighCWu/distro/actions/runs/39546545079) 已派发。
前者要求原三阶段加高地址阶段及关闭，后者仍为原三阶段，实际结果尚待核实。
这不保证每个宿主可分配完整 4 GiB，不涵盖所有执行 ABI/设备的高位地址，也不
表示内核会接受超出当前线性内存或 TASK_SIZE 的地址。

上述 `0ba04b0` 两项 Node 现均成功，实际日志已核实：wasm32 的 NULL、前缀、
upper-half、恢复四阶段及唯一最终 pass 完整，包含 0x80000040 以上的真实 pipe、
结构输出和原子操作；wasm64 的原三阶段及唯一 pass 完整。两项均通过等待
machine.closed 的退出门禁。当时尚未把这组访存语料接入浏览器，不用此前 pidfd 浏览器
通过代替高地址或访问故障的浏览器验收。

### 同期 CI 检查修复

主仓库 `39541628806` 和 `39543174124` 的实际日志确认：Python workflow 检查
假定 native job 紧邻 jobs 标题，benchmark job 插入后触发 undefined.split；plan
条件也已增加 benchmark 排斥，旧断言未跟进。这不是 Python 或 Wasm 目标执行失败。
distro `84a3675` / 集成 `c4256ac` 改为按顶层 job 名定位，保留原只读权限、无发布
凭据和不派发目标矩阵断言，并用插入前置 job、移除 guard、扩大权限、缺失 job
的控制验证。19 项相关 Node 检查及 10 项源码包检查通过，主仓库 CI 已随 push 复验。

### 第十二组：浏览器访存与高地址 fork 执行入口

distro `15fde40` / 集成 `141e5e4` 将普通 user-access 与 upper32 独立语料接入
Chromium/Firefox。CPU 数从构建产物传入（访存 1 CPU，原进程语料仍为 2），
每项要求同页两次完整阶段、机器关闭与最终浏览器关闭；普通三阶段不能误接收
upper32 专属阶段。四路 `39547734031`、`39547739983`、`39547746725`、
`39547753636` 的实际日志均表明停在相同 treefmt 属性格式检查，未执行目标语料。
`1ad6de6` 已修复为 `inherit (assets) cpus` 并更新断言，不将它记录为运行时失败
或目标通过。最终源码 `d74784a` 重新派发四路，已核实结果见下文。

独立 review 发现 fork continuation 对原始 i32 栈、TLS、descriptor 仍使用非负
地址解析。`d74784a` / 集成 `457f7ea` 改用原始指针位模式解码，JS 内存视图只用
检查后的无符号偏移，快照与 Wasm 恢复保留原寄存器表示，ABI 版本不变。
新增独立 `fork-high32-check-runtime`：链接布局从 0x80000000 开始，真实检查栈、
TLS、全局数据和执行 descriptor 均在高半区，然后验证 fork 的父子身份、私有状态
隔离及单次 wait 回收。默认构建不采用该布局，不新增 musl 公共函数或应用接口。

本地 314 项内核检查、42 项相关宿主检查、源和测试两个 TypeScript 项目及 Clang
静态分析通过；高寄存器单测只验证保存/恢复，不访问模拟地址，原生 C 检查只验证
工作负载及错误控制。真实 Wasm 高地址 fork 尚待目标 CI，不将宿主检查当作验收。
该配置需要超过 2 GiB 的线性地址范围和完整子进程快照，可能受 runner 内存限制；
不在本地运行，不承诺所有宿主均可分配、不扩大到多线程 fork，也不宣称性能改善。

`d74784a` 浏览器复验已成功，实际日志核实：

- [wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39549000128)、
  [wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39549004552)：
  NULL、有效前缀、upper-half、恢复四阶段，各两轮与唯一 pass。
- [wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39549009880)、
  [wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39549015174)：
  普通三阶段，各两轮与唯一 pass。

四路均确认每轮机器关闭及最终浏览器关闭，固定 Chromium 149.0.7827.55 /
Firefox 151.0，CPU 数均为 1。它们不包含高布局 fork 工作负载；后者单独的
[Node 检查](https://github.com/HighCWu/distro/actions/runs/39548994652) 仍在运行，
不能用高地址普通复制通过来代替高地址 fork 验收。

### 第十三组：用户复制的无符号长度寄存器

distro `e358284` / 集成 `69d7fab` 修复相邻的原始 `size_t` 入口：Wasm32 的
0x80000000..0xffffffff 长度跨 JS 边界同样表现为负 Number，旧入口误用非负
宿主地址转换，导致导入抛异常。新入口显式按无符号机器字解码，用于用户 read、
write、clear 三个内核导入及无用户 context 时的完整 residue 返回；不改 syscall
编号、不新增 musl 函数、不改变普通 JS 元数据、PID 和有符号返回值校验。

本地真实小 Wasm 模块把高位长度作为 i32 参数传入，再把 residue 作为 i32 返回：
验证 read/write 在内核缓冲区不完整时不修改内存，clear 只清除实际存在的两字节
前缀，其余按完整无符号值报告未复制数量。该测试只用两页本地内存，不申请大缓冲
或据此宣称超大 syscall 已准入。内存64的 BigInt 不做 32 位截断，不接受不安全
整数。316 项内核侧检查与源/测试两套 TypeScript 检查通过。

随后派发同源码的 [wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39549366030)
与 [wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39549372193) 普通访存
回归，两项现均成功，实际日志已核实原三阶段、唯一 pass，并通过运行器等待
machine.closed 的退出门禁。它们是普通访存回归，不包含高布局 fork。Linux 的
access_ok、MAX_RW_COUNT 等上层限制仍然生效，不将原始导入修复描述为放开 4 GiB
单次 I/O 或浏览器容量保证。Linux、musl 固定版本与默认配置保持不变。

### 第十四组：exec 装载边界与损坏模块后的恢复

distro `0af5e3c` / 集成 `485a7cf` 修复内核 `compile_write` 导入对高位 i32 源指针
的处理。旧入口把原始内核指针直接按非负 JS 偏移解析，可能抛异常而中断内核错误
处理；现在先解码指针位模式，再完整检查源范围、u32 模块偏移及块长度。失败返回
原有 EINVAL，暂存模块不接受部分写入，成功重试仍可写入。内核偏移 0 仍有效，
不套用用户 NULL 策略；每次读取当前 kernel memory 范围，memory64 不做 32 位截断。

这是内部 loader 修复，`compile_write` import 签名未变，没有新增 syscall 或 musl
公共函数。Linux 的 `load_wasm_binary` 在 `begin_new_exec` 之前处理编译错误，通过
既有 `compile_abort` 清理状态；本次不修改 Linux 的 exec 生命周期或不可逆边界。

真实 exec-fd 语料新增第八阶段：创建有正确 Wasm magic、但类型段损坏的可执行文件，
两次 execveat 都应返回 ENOEXEC，PID、TLS、CLOEXEC fd 和文件位置均保留，随后
fork/fexecve 正常文件成功。文件先关闭写端再以只读 fd 执行，避免把 ETXTBSY 当成
编译器错误。该阶段不代替已有 close_range、limit 及普通 exec 错误恢复阶段。

本地 319 项内核侧检查和两套 TypeScript 检查通过；小 Wasm32 模块实测高位源/
偏移/长度进入 JS 后是负 Number，错误导入返回 EINVAL 而不 trap，后续合法写入成功。
小内存测试不证明真实内核已能在高半区分配 exec chunk。GCC/Clang 语料及协议检查
15 项通过，包含错误关闭失败 exec 的 CLOEXEC fd 的反向控制；原生不认识 Wasm，
因此这只是负载验证，不代替 Wasm 编译器 abort。Clang 静态分析通过。

[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39549892599) 与
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39549899461) exec-fd
已按同一源码派发，要求完整八阶段、唯一 pass 和机器关闭；
实际目标结果待核实，旧七阶段结果不覆盖新增 abort 恢复。浏览器合同也要求新增
阶段，但不因此宣称本轮浏览器已验收。

上述 `0af5e3c` 双位宽 Node 均已成功，实际日志已核实全部八阶段、唯一最终 pass，
并通过等待 machine.closed 的运行器退出门禁。新增损坏模块 abort 后成功执行正常
文件的阶段实际出现，不以此前七阶段结果替代。

### 第十五组：direct mremap 接入

本轮从 loader 位宽 review 转入新的标准 syscall 能力：号 216 的 mremap，继续
保持 CONFIG_MMU=n 和普通线性内存指针。不添加地址翻译或应用侧私有 API。
Linux `82d9b0b3b` 校验 flags、溢出、TASK_SIZE 及 64 KiB 页取整，再交由进程自己的
分配器验证活跃映射归属；内核中的变更保留 GPL。loader 的内部 user_v2 桥原样转发
机器字，旧程序没有 `__wasm_mremap` 时返回 ENOSYS，不退化为“分配成功但丢失内容”。

musl `c4c3591d` 恢复 tombl/musl 本来已有但对 Wasm 关闭的 mremap 声明/实现，
补齐标准 syscall 编号，并只在 Wasm 调用路径显式传递六个机器字。`08ab5ec6`
补齐分配器编译所需的已有 GNU 常量可见性。不新增公共函数、头文件 API 或通用
包装文件；新增的 `__wasm_mremap` 仅是已有 direct 分配器的内部执行辅助入口。

目前实现一条完整活跃记录的缩小、保留地址的扩展、MREMAP_MAYMOVE 允许的匿名
迁移。扩展部分清零，邻近活跃映射不能被覆盖；迁移分配/初始化在锁外完成，重新
取得锁后必须重新验证源，再复制并原子发布元数据。失败不撤销旧映射，分配和
引用计数在锁外回收。它不是硬件页表重定位，移动需要复制原数据，未做性能承诺。

不支持固定地址替换、DONTUNMAP 保留旧范围、old_len=0 的共享别名，以及跨/部分记录的
一般重映射。已初始化文件副本保留来源标记，拆分时传递；因没有可供扩展补读的
文件来源，扩展明确拒绝，不能用零页假装正确的文件映射。这里仍不是完整 mremap
或所有 NOMMU/Linux 映射语义的验收。

本地 321 项内核侧检查、两套类型检查通过；6 项精确源码宿主检查包括 GCC/Clang
的 ASan/UBSan、Clang 静态分析、分配失败回滚、分配期间源被撤销后的重新验证、
副本增长拒绝与资源归零。故意删除迁移复制的版本必须失败。另有标准 musl 构建宏
下的 wasm32/wasm64 真实源码前端检查（曾抓到缺少 GNU 常量，修复后通过）。这些
不是 Wasm/Linux 运行证据。

独立 `toolchain-smoke[-wasm64]-check-mremap` 使用普通 mmap/mremap/munmap，
要求缩小/原地扩展、阻塞增长拒绝/迁移/邻居隔离、清理后再次映射三阶段及关闭。
真实目标结果待核实，应用仍使用标准接口，不增加私有调用。

最终集成为 distro `6438a90` / 主仓库 `5bc28b0`，固定 musl `08ab5ec6` 和 Linux
`82d9b0b3b`。两份源码下载哈希分别由公开 prefetch `39552008910`、`39551288116`
核实。最初的 `c4c3591d` 缺少已有 GNU 常量的可见性，被本地真实源码检查抓到；
修复前没有派发重型 mremap 检查，不将宿主 GNU 环境下通过误记为正式 musl 构建通过。

本轮目标为 [wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39552184749)
与 [wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39552192188)，源码固定
`6438a90`，当前均在运行。必须检查三阶段和关闭，不能以源码接线或宿主模拟替代。

其中 wasm32 `39552184749` 现已成功，实际日志核实缩小/原地扩展、阻塞增长拒绝/
匿名迁移/邻居隔离、清理恢复三阶段和唯一 pass；作业通过等待 machine.closed 的
运行器门禁。wasm64 此时仍在运行。该结果不包含下一组新增的子区间能力。
随后 wasm64 `39552192188` 也已成功，实际日志核实相同三阶段、唯一 pass 及
machine.closed 退出门禁，完成初版双位宽 Node 验收；新增子区间仍须以下四阶段验证。

### 第十六组：mremap 单记录内子区间

musl `0a8b3917` 在既有标准入口上继续实现子区间，而不是要求应用把原始整块
mmap 当成不可拆分对象。源范围必须完整落在一条活跃记录内；支持其中的缩小、
尾段原地扩展，以及 MAYMOVE 允许的首段、中段、尾段迁移。ABI 与 syscall 号
不变，没有新增公开函数或更改 Linux pin。

缩小只移除请求范围自己的尾部，不能丢弃原记录中未参与请求的后缀。中段迁移
保留原记录两侧，复制从实际源子区间开始，而不是从整条记录起点开始。需要的
拆分记录在锁外预分配，重新取得锁后再次确认源；所有分配成功前不修改旧记录。
失败清理统一回收临时 backing 和 split 元数据，引用计数随保留记录数量调整。
初始化副本的来源标记在 mremap 拆分时继续传播，增长拒绝策略不变。

精确源码 GCC/Clang ASan/UBSan 与 Clang 静态分析通过；夹具检查两侧字节和逻辑
归属（对保留页 MAP_FIXED_NOREPLACE 必须 EEXIST），旧洞可重用且归零，迁移内容
与零尾正确。另覆盖三种迁移位置、尾段原地扩展、拆分/迁移分配失败、分配期间源
被撤销，以及全清理后资源计数归零。已准备 split 后再次分配失败也走统一回收，
不以可读的旧字节冒充仍注册的映射。

目标语料增加独立的“subrange shrink and relocation”阶段：原六页映射内部缩小，
复用缩小洞，再从保留的右段内部迁移一页、扩展为两页；核对左右活跃页不能被
NOREPLACE 覆盖、迁移洞可安全复用，最后回收全部 backing。现在要求四阶段及关闭，
旧版本三阶段结果不能代替。仍不支持跨多条记录的重映射、固定地址替换、保留旧
范围和文件副本增长；目标结果尚待真实 CI，不以宿主测试宣称全部 mremap 已实现。

musl 源码哈希由公开 prefetch `39552965261` 核实，集成为 distro `9b93cc9` /
主仓库 `f56b594`。本轮 [wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39553195723)
与 [wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39553202261) 均固定
该源码，仍在运行；要求新增子区间阶段与原三阶段、唯一 pass 及 machine.closed。

两项现均成功，实际日志核实缩小/原地扩展、阻塞增长拒绝/迁移/邻居隔离、子区间
两侧保留/洞复用、清理恢复四阶段和唯一 pass，并通过等待 machine.closed 的
运行器退出门禁。由此记录单记录内子区间的双位宽 Node 准入；不扩大为跨记录、
固定替换、共享映射或文件副本增长的支持证明。

### 第十七组：CPython 复用标准 mremap

distro `809df7b` / 集成 `7dba8ce` 让真实 Python fixture 使用上游已有的
mmap.resize()；不修改 CPython 源码或强制 HAVE_MREMAP 探测，不新增 libc API。
测试扩大、缩小/再扩大、保留数据和零尾、导出缓冲区的 BufferError、失败后仍可用
及 close/retry，和原有内核拒绝边界共四个 mmap 阶段。构建材料检查要求实际
HAVE_MREMAP=1，已有浏览器用例补上 resize 必需标记；旧版本结果不能替代。

23 项相关宿主检查通过，包括假成功、丢数据、吞错误、残留整页四个反向控制。
[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39554209066) 与
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39554218265) 仍在运行，
实际安装/位宽门禁、完整四阶段和关闭尚待核实，不能用 C mremap 或原生 Python
通过代替。细节见 [Python mmap 记录](python-mmap.md#标准-mremap-接通后的-resize)。

主仓库 `39554196967` 在独立浏览器模拟门禁失败，实际原因是模拟输出遗漏新增
resize 阶段，不是目标 Python 已执行并失败。distro `8ec790f` 同步模拟预期，
保留逐个删除阶段的拒绝控制；完整门禁 60 项和 Python 宿主 23 项检查通过，
不以此替代上述目标验收，也不重复派发相同 Python 重型检查。

### 高布局 fork 的独立失败

`d74784a` 的 `39548994652` 实际失败发生在“栈/TLS/数据/descriptor 都在高半区”
前置断言，尚未到 fork。因此没有证明高布局 fork 成功，也没有证据把本次失败
归因于 fork 本身或内存复制资源耗尽。distro `c59c497` 保留全部高地址要求，增加
各地址与逐项断言以定位实际布局；不弱化门禁来获得 pass，需独立目标复验。
对应 [诊断复验](https://github.com/HighCWu/distro/actions/runs/39552197047) 固定
`6438a90`，仍在运行；不能把本轮 mremap 结果当作 fork 高地址结果。

该次诊断现已失败，实际输出为 stack=0x7ffffc、tls=0x80000000、
global=0x80000dc4、descriptor=0x80080e70，唯一未满足的布局项是栈。已核对固定
LLVM `137009e2` 的 LLD Driver/Writer/Options：stack-first 默认启用，global-base
不改变前置栈的位置。distro `ac46f14` / 集成 `047d0e7` 只为独立高地址测试设置
`--no-stack-first`，让栈位于高数据之后；默认 SDK 和 LLVM 源码不改，全部高地址
断言保留。[修正复验](https://github.com/HighCWu/distro/actions/runs/39554319163)
固定 `ac46f14`，实际布局和 fork 结果仍待核实，不能据此提前宣称通过。

该修正复验现已成功，实际日志为 stack=0x8088163c、tls=0x80000000、
global=0x80000dc4、descriptor=0x80080e70，全部位于高半区；随后真实 fork 完成
父子数据隔离、身份与单次子进程回收，输出两个必需阶段及唯一 pass。运行器
等待 machine.closed，目标作业成功确认关闭门禁。仅证明该独立布局，不代表
默认请求容量、所有高地址 ABI 或性能保证。

上述 `809df7b` 的双位宽 Python Node 也均已成功，实际日志核实 ABI/安装路径、
私有缓冲区、resize、旧 flush ENOSYS、共享/文件拒绝全部阶段和唯一 pass，
并通过机器关闭门禁。主仓库模拟门禁修复后的 `39555029885` 成功；这些旧目标
结果不覆盖下面新增的私有 msync。

### 第十八组：标准 msync 的私有映射语义

Linux `a36fe0d0ab`、musl `c6e6b380`、distro `c2f1c5f` / 集成 `1d5721e` 接通
标准号 227。Linux 架构入口校验 flags、地址对齐、页取整溢出和 TASK_SIZE，
经内部 user_v2.msync 桥交给进程分配器核实整个活跃范围；旧程序缺少内部导出时
返回 ENOSYS，不凭线性内存仍可读猜测映射有效。musl 公共 msync 本来就存在于
直接上游 tombl/musl，本轮只增加 Wasm 内部映射兼容代码，没有新增公共 API。

已核对固定 Linux 的 mm/msync.c：同步文件回写要求 MS_SYNC、文件以及 VM_SHARED。
当前 direct 映射仅接受 MAP_PRIVATE，因此有效私有范围成功而不回写、不丢弃数据；
不能据此宣称共享文件落盘。支持 ASYNC/SYNC/INVALIDATE 的合法组合、零长请求、
相邻多记录覆盖；拒绝冲突/未知 flags、未对齐地址、空洞、释放范围和溢出。
不实现共享映射、mlock、页回收或内核 softmmu，文件初始化副本也不会发布私有修改。

目标 C 工作负载三阶段检查范围与 flags、空洞及相邻记录恢复、释放后的拒绝。
原版 CPython 的 mmap.flush() 直接复用该标准 syscall：私有数据不变，未对齐
请求 EINVAL；没有 Python 私有兼容层。默认共享/文件映射拒绝仍保留。

本地 323 项运行层检查及双类型检查、10 项精确源码/native 检查、双位宽 musl
前端、Clang 静态分析和 GCC/Clang ASan/UBSan 通过。60 项浏览器门禁和 32 项
Python/模拟/native 检查通过；这些不是目标或浏览器执行证据。源码哈希来自公开
prefetch `39556482787` 与 `39556630858`，目标 CI 单独验收，不复用旧 ENOSYS 结果。

同一 `c2f1c5f` 已派发 [C wasm32](https://github.com/HighCWu/distro/actions/runs/39557605298)、
[C wasm64](https://github.com/HighCWu/distro/actions/runs/39557611325)、
[Python wasm32](https://github.com/HighCWu/distro/actions/runs/39557618206) 与
[Python wasm64](https://github.com/HighCWu/distro/actions/runs/39557624512)。本轮要求：
C 要求完整三阶段，Python 要求含新 flush 的四阶段、ABI/安装布局，两者均须
唯一 pass 及关闭；当前没有新增浏览器结果，不因等待而重复派发。

其中两项 C 目标现均成功，已读取实际日志：私有范围/flags/页取整/数据保持、
空洞拒绝及相邻记录恢复、释放范围拒绝三阶段和唯一 pass 全部出现。运行器
closeTestResources 等待 machine.closed，作业成功确认关闭门禁。Python 两项随后
也已核实实际 ABI/安装路径、含新 flush 的四阶段、唯一 pass 和关闭。由此完成
`c2f1c5f` 私有 msync 的双位宽 Node 验收，不覆盖新增 madvise 或浏览器。

### 第十九组：标准 madvise 的匿名丢弃

Linux `7ba501fbb`、musl `d61bd4aa`、distro `130f0f0` / 集成 `ece1180` 接通
标准号 233。Linux 检查 advice、地址对齐、页取整与溢出、TASK_SIZE，再调用
内部 user_v2.madvise；旧对象没有相应分配器导出时返回 ENOSYS，不在 JS 猜测
范围或直接改写原始指针附近的线性内存。

对已注册私有匿名范围，MADV_DONTNEED 清零整个页取整范围，保留地址占用和
映射记录；MADV_NORMAL/RANDOM/SEQUENTIAL/WILLNEED 对驻留 backing 是有效提示，
不会丢弃内容。映射管理锁覆盖完整范围验证与清零；先核实全部记录，再修改数据，
防止后段空洞或文件副本使前段被提前清零。相邻记录可组合，空洞及释放范围
ENOMEM，未知/不支持 advice 或非法几何 EINVAL。不能重建来源的初始化文件
副本对 DONTNEED 返回 EOPNOTSUPP，拆分后仍保留该限制。

这实现的是应用可见匿名页丢弃语义，不宣称 WebAssembly.Memory 缩小、物理内存
归还浏览器、共享映射、MADV_FREE、DONTFORK 或完整 Linux madvise 支持。保持
CONFIG_MMU=n，不引入翻译层、页保护或新的应用接口。

恢复的是 tombl/musl 已有 madvise/posix_madvise 的声明和 Wasm 编译门控，包装
函数体不变。POSIX_MADV_DONTNEED 保持上游原有非破坏性语义；POSIX 失败返回
错误号而不修改 errno。没有补造上游缺失函数。原版 CPython 直接使用既有
mmap.madvise()，构建检查要求实际 HAVE_MADVISE=1，不强制配置探测。

本地 325 项运行层检查与双类型检查、12 项精确源码/native 检查、双位宽 musl
前端、GCC/Clang ASan/UBSan 及 Clang 静态分析通过。Python 真实原生负载和反向
控制验证部分页清零、邻页、活跃 memoryview、重复使用与非法 advice；60 项
浏览器模拟门禁通过。这里均不是 Wasm 或浏览器执行证据。目标 C 要求三阶段，
Python 增加 madvise 后要求五个 mmap 阶段及原 ABI/安装路径、唯一 pass 和关闭。
公开源码哈希由 `39558589678`（musl）与 `39558597924`（Linux）计算。

同一 `130f0f0` 已派发 [C wasm32](https://github.com/HighCWu/distro/actions/runs/39558934760)、
[C wasm64](https://github.com/HighCWu/distro/actions/runs/39558945270)、
[Python wasm32](https://github.com/HighCWu/distro/actions/runs/39558954741) 与
[Python wasm64](https://github.com/HighCWu/distro/actions/runs/39558963824)。四项均已成功，
实际日志核实双位宽 C 三阶段、Python 五阶段及 ABI/安装路径、唯一 pass 和关闭；
Python 的新增 madvise 阶段包含匿名页丢弃、邻页、活跃视图与非法 advice。
前一批 msync 工作负载固定旧源码，自然运行完毕后独立核实，不取消或复用它们
作为新增 madvise 的证明。

### 第二十组：有界匿名 MAP_FIXED 替换

Linux `b30bfebb0`、musl `e6543914`、distro `5115c9a` / 集成 `4cab302` 补齐
此前完全拒绝的匿名 MAP_FIXED。只支持整个请求落在单个仍保留的 mmap backing
中的情形；不覆盖栈、普通 malloc、自有元数据或未知地址。跨 backing、超出可管理
范围的固定请求仍失败，不退回另一地址，也不引入 softmmu。文件固定映射、
MREMAP_FIXED、PROT_NONE 和权限切换仍不在本轮范围。

Linux 验证 flags、保护位、对齐、页取整与 TASK_SIZE 后，覆盖请求走独立内部
user_v2.mmap_fixed；旧模块缺少 __wasm_mmap_fixed 时 ENOSYS，绝不把请求交给
会忽略覆盖位的旧 v2 allocator。NOREPLACE 与 FIXED 同时给出时仍以 NOREPLACE
为准，保留 EEXIST 和洞复用语义。没有新增 syscall 号或 musl 公共函数。

内部实现锁外准备替换与拆分节点，锁内重新确认 backing，再一次性拆分/移除
覆盖记录、清零目标并发布新记录。保留请求之外的两侧内容与文件副本来源标记；
新匿名记录不继承旧文件来源。先持有新引用，防止移除最后一个旧记录时提前释放
backing。分配失败或锁内重验已找不到目标 backing 时不修改旧数据，没有永久地址保留。

327 项运行层检查及双类型检查、14 项精确源码/native 检查、双位宽 musl 前端、
GCC/Clang ASan/UBSan 和 Clang 静态分析通过；覆盖中间替换、跨多记录、完整替换、
保留页洞、两个准备分配失败、源撤销、初始化来源拆分和最终资源计数归零。
原生负载的“忽略 FIXED”反向控制必须失败；原生检查不尝试覆盖宿主栈。
这些不代表 Wasm 已验收。公开 prefetch 为 musl `39560334281`、Linux `39560341933`。

同一 `5115c9a` 的 [wasm32](https://github.com/HighCWu/distro/actions/runs/39560729491)
与 [wasm64](https://github.com/HighCWu/distro/actions/runs/39560736823) 已派发，要求
中间/跨记录替换、NOREPLACE 优先/洞复用/错误恢复、最后旧引用替换及继续使用三阶段，
唯一 pass 和机器关闭。两项现均成功，实际日志逐项核实上述三阶段和唯一 pass；
运行器等待 machine.closed 且目标成功确认关闭门禁。无新增固定替换浏览器结果。

此前 `c2f1c5f` 的双位宽 Python msync 检查现已核实实际 ABI/安装路径、完整四阶段、
唯一 pass 和机器关闭；`130f0f0` 的双位宽 C madvise 也已核实完整三阶段、唯一 pass
与关闭。这些分别补齐对应旧源码的结果，不作为本组固定替换或浏览器验收。

### 浏览器应用回归与独立 munmap 边界修正

distro `fc7e4a8` / 集成 `abc3181` 沿用现有 Python 浏览器两个用例，不新增场景：
完整解释器及搬移应用、私有 mmap 五阶段。只给公共运行器已有 onProgress 加
控制台输出，保留真实阶段与 shutdown completed；诊断不能改变完成或错误语义。
29 项宿主检查通过。以下四路均固定该源码，尚待目标与报告核实：

- [wasm32 Chromium](https://github.com/HighCWu/distro/actions/runs/39564585105)
- [wasm32 Firefox](https://github.com/HighCWu/distro/actions/runs/39564595414)
- [wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39564602645)
- [wasm64 Firefox](https://github.com/HighCWu/distro/actions/runs/39564610620)

每路要求两项预期用例、零跳过/零重试、实际位宽/安装路径及全部相应阶段、
pass 和机器关闭，不误写成每项两轮。使用公开 CI 的固定 Playwright 引擎，不在
本地下载浏览器；这批不执行新的固定替换工作负载。

四路现均成功，已读取实际日志：每路完整解释器/搬移应用十个必需阶段、mmap
五阶段、两次 ABI/安装布局、两次 pass 和两次 shutdown completed 均出现，
Playwright 报告两项通过，精确报告门禁确认零跳过/零重试。由此验收 `fc7e4a8`
在双位宽 Chromium/Firefox 的这两个应用用例，不推广到新的固定重映射。

独立 review 发现 wasm_munmap 只检查整数回绕，没有拒绝超过 TASK_SIZE 的范围，
wasm64 可错误地把平台上限之外当成普通空洞成功。核对固定 Linux mm/vma.c 的
do_vmi_munmap 范围检查后，Linux `366e444d2` 增加上限校验，合法范围内空洞仍可
no-op 成功。精确源码 GCC/Clang 检查通过，故意移除上限的反向控制失败；现有
fixed-mmap 目标增加 wasm64 上限拒绝和原映射保留检查，不增加新测试场景。
这项修正须随新 pin 单独验收，不能用上面 `5115c9a` 的结果证明。

修正已集成为 distro `c46abc6` / 主仓库 `3cc2527`，Linux 哈希来自公开 prefetch
`39564945010`。同一修正的 [wasm32](https://github.com/HighCWu/distro/actions/runs/39565306036)
与 [wasm64](https://github.com/HighCWu/distro/actions/runs/39565313107) 已派发，仍在
排队/运行；现有三阶段必须完成新增上限拒绝及合法空洞/原映射恢复后才能 pass，
还须等待机器关闭。四路 `fc7e4a8` 浏览器继续自然运行，不取消或重复派发。

该 `c46abc6` 双位宽 Node 现也均成功，实际日志核实 fixed-mmap 三阶段、唯一 pass
与关闭门禁；wasm64 的第三阶段包含新增 TASK_SIZE 拒绝及原映射继续使用。它们
证明独立边界修正，不覆盖下文的新事务重构。

### 第二十一组：有界 MREMAP_FIXED 事务

Linux `dbc6a5054`、musl `0600f012`、distro `bb8e564` / 集成 `8e71b1a` 接通
MREMAP_FIXED | MREMAP_MAYMOVE，应用仍调用既有标准 mremap。Linux 校验页取整、
源/目标上限和不重叠要求后，经独立 user_v2.mremap_fixed 内部入口执行；旧模块
缺少 __wasm_mremap_fixed 时 ENOSYS，不退回旧的非固定 resize，也不新增公共函数。

源完整范围须在一条活跃记录内，目标须完整落在一个仍保留的 mmap backing 中。
支持匿名扩大/缩小、覆盖目标、保留两侧记录与数据，并解除完整旧范围。源、目标
可在同一个原始记录内，或属于不同 backing；复制 min(old,new)，新增尾部清零。
初始化文件副本可移动/缩小且保留来源限制，不能补读的增长仍 EOPNOTSUPP。
跨多源记录、DONTUNMAP、共享别名、任意高地址和页权限仍不支持。

复用同一固定放置事务实现 MAP_FIXED，锁外准备目标记录和两侧拆分节点，锁内
重新验证全部范围与来源。进入修改点后无可失败步骤；新目标先持有 backing 引用，
避免移除最后一条旧记录时提前释放。源 backing 最后引用释放后才在锁外回收。
三个准备分配点失败、源记录或目标 backing 在准备期间被撤销、重叠或未知目标均不部分修改。
事务指映射登记和错误回滚，不保证与无同步用户写入之间的逐字节原子性。

329 项运行层检查及双类型检查、16 项精确源码/native 检查、双位宽 musl 前端、
GCC/Clang ASan/UBSan 与 Clang 静态分析通过。精确源码包含同记录双重中间拆分、
源位于目标前/后、同/跨 backing、零尾、旧洞复用、文件来源与最后引用归零。
原生仅运行共享 C 负载新增 fixed_move 部分，故意丢弃 FIXED 必须失败；不把它
当成全部六阶段或 Wasm 验收。下载哈希由 `39566770716` 与 `39566783271` 计算。

目标沿用原 mremap 检查，新增两阶段后共六阶段；旧四阶段通过不覆盖本增量。
另对同一新源码定向运行双位宽 MAP_FIXED 三阶段，防止共享事务重构产生回归。
不以宿主检查、浏览器旧工作负载或工作流状态代替新阶段和关闭证据。

同一 `bb8e564` 的 [mremap wasm32](https://github.com/HighCWu/distro/actions/runs/39567396466)、
[mremap wasm64](https://github.com/HighCWu/distro/actions/runs/39567406781)、
[MAP_FIXED wasm32](https://github.com/HighCWu/distro/actions/runs/39567414604) 与
[MAP_FIXED wasm64](https://github.com/HighCWu/distro/actions/runs/39567424449) 已派发，
当前在运行；不重复派发，也不把旧 `5115c9a` 或 `c46abc6` 的结果当作新事务验收。

双位宽 mremap 现已成功，实际日志核实原四阶段、新同 backing 固定移动/扩大/
缩小/旧洞复用、跨 backing 固定替换/零尾/完整源释放共六阶段、唯一 pass 及关闭。
wasm32 MAP_FIXED 回归三阶段也已核实。wasm64 MAP_FIXED 的第 1 次尝试在获取
Linux source 时连续 HTTP 429，尚未编译或运行，并非已证实的 allocator 回归。
读取实际日志后仅重试 `39567424449` 的失败作业；第 2 次尝试保持同一 `bb8e564`，
其它运行中的任务未取消或重派，目标结果仍须另行核实。

第 2 次尝试现已成功，实际日志核实 wasm64 MAP_FIXED 完整三阶段、唯一 pass 与
机器关闭门禁，补齐 `bb8e564` 共享事务重构的双位宽回归。未修改源码来规避
429，也未将首轮下载失败视为运行失败或跳过目标验收。

### 第二十二组：匿名 mmap 提示和无关 fd

Linux `31234c7fd`、distro `abebc79` / 集成 `ae75750` 修正对匿名 mmap 参数的一概拒绝。
核对固定 Linux 的 mmap/NOMMU 路径后，MAP_ANONYMOUS 不查询无关 fd；当前入口忽略该参数并在送入旧
allocator ABI 前规范化为 -1。新增接受 MAP_NORESERVE、MAP_STACK、MAP_POPULATE、
MAP_NONBLOCK、MAP_DENYWRITE、MAP_EXECUTABLE 及其组合，规范化后沿用旧匿名/
NOREPLACE 入口；固定覆盖仍走独立事务，因此不削弱 NOREPLACE 的 EEXIST 优先级。
文件路径保留原 fd/flags，默认仍不开放普通文件映射。

提示位不等于新页能力：POPULATE 由已经清零、驻留的直接 backing 满足；NONBLOCK
不新增缺页 I/O；NORESERVE 不保证稀疏保留、容量或延迟提交；STACK 不启用自动
增长；历史 EXECUTABLE/DENYWRITE 提示不授予 PROT_EXEC 或文件写保护。仍拒绝
PROT_NONE/只读/执行权限、GROWSDOWN、LOCKED、HUGETLB、共享语义和非零匿名 offset。
没有新增 syscall、musl 公共接口、libc 包装或内核 softmmu。

共享 C 目标增加提示位单独/组合、无效 fd、零初始化、读写/同步/清理阶段，并
验证提示位与 FIXED/NOREPLACE 混用仍正确；原 fixed-mmap 现在要求四阶段。
原版 CPython 使用已提供的 STACK/POPULATE/历史提示常量，经普通 mmap 构造验证
零初始化、flush、resize、madvise 和关闭；目标 Python 增至六个 mmap 阶段，
现有浏览器规范和独立模拟同步修改，不新增 Python 补丁或新浏览器用例。

本地精确源码/native 检查、Clang 静态分析、allocator ASan/UBSan、双位宽 musl
前端、Python 原生负载及 60 项浏览器门禁通过；这些不能代替新参数在 Wasm 上的
执行与关闭结果。新源码 pin 和目标结果单独记录，不复用上一组的旧阶段通过。

Linux 哈希由公开 prefetch `39569265125` 核实。同一 `abebc79` 已派发
[C wasm32](https://github.com/HighCWu/distro/actions/runs/39570086630)、
[C wasm64](https://github.com/HighCWu/distro/actions/runs/39570094754)、
[Python wasm32](https://github.com/HighCWu/distro/actions/runs/39570103286) 与
[Python wasm64](https://github.com/HighCWu/distro/actions/runs/39570111350)，仍在运行。
C 需新增提示位阶段及原三阶段，Python 需新增提示位阶段及原五阶段，两者都要
完整 pass 和机器关闭；没有新增浏览器结果，不改或重试旧的已通过任务。

随后双位宽 C 已成功，实际日志核实全部四阶段与唯一 pass，成功作业通过等待
machine.closed 的关闭门禁。Python wasm32 也已成功，实际日志核实完整六阶段、
唯一 pass 和相同关闭门禁。Python wasm64 随后也已成功，实际日志核实六阶段、
唯一 pass，成功作业通过相同关闭门禁；不据此扩大浏览器覆盖范围。

### 第二十三组：启用上游 inotify 与现有 BusyBox inotifyd

Linux `cb557f63c`、distro `7007682` / 集成 `d90ba34` 在默认、wasm32、wasm64
三套 defconfig 启用 `CONFIG_INOTIFY_USER`，复用 Linux 上游 inotify/FSNOTIFY
实现及标准 syscall 26/27/28。构建检查解析后的 `.config` 确实启用两项能力；
没有新增事件模拟器、syscall 编号或内核 softmmu，仍为 NOMMU。源码哈希由公开
[prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39572005506) 核实。

直接上游 tombl/musl 已有 inotify 头文件及四个函数，实现没有被 Wasm 门控；
本增量不修改 musl。BusyBox 的固定源码已带 `inotifyd` applet，本增量只启用
现有构建选项，不新增软件包或补丁。其原 GPL 许可证与对应源码材料继续保留；
本项目新增验证代码为 MIT，不改变应用开发与发布的原有许可边界。

标准 C 负载核对 NONBLOCK/CLOEXEC、epoll 就绪与 64 位 opaque data、FIONREAD、
过短 read 的 EINVAL 与队列保留，以及 create/modify/close/rename/delete 事件、
重命名 cookie、清空队列、rm_watch/IN_IGNORED 和重新安装监听后的清理。
BusyBox 负载运行真实 `inotifyd -`，通过 `/proc/PID/fdinfo` 确认 watch 已安装后
才写入、重命名和删除文件；移除目录后核对 delete-self/ignored，并 wait 回收
监控程序。准备及事件等待有界，不靠固定启动延时推断就绪。

GCC/Clang 原生语料和 ASan/UBSan、损坏 cookie 的反向控制、Clang 静态分析及
双位宽已有 musl 头文件/结构布局检查通过。宿主 BusyBox 没有 inotifyd applet，
因此没有宣称宿主 applet 实测通过；其运行由公开目标验收负责。

同一 `7007682` 已派发
[C wasm32](https://github.com/HighCWu/distro/actions/runs/39572450386)、
[C wasm64](https://github.com/HighCWu/distro/actions/runs/39572459397)、
[BusyBox wasm32](https://github.com/HighCWu/distro/actions/runs/39572468594) 和
[BusyBox wasm64](https://github.com/HighCWu/distro/actions/runs/39572476584)。
C 要求三阶段，BusyBox 要求两阶段；各自还需最终 pass 和机器关闭，当前尚未
完成目标验收。不据配置启用推定所有文件系统后端、递归监听、队列溢出、所有
watch flags、跨进程权限或浏览器运行都已通过；不启用 fanotify。

上述 `7007682` 四路 Node 目标现已成功。实际日志逐项核实双位宽 C 三阶段、
BusyBox 两阶段及各自最终 pass；成功作业通过运行器等待 machine.closed 的关闭
门禁。不将这些结果扩大为后续源码、浏览器或其它文件系统后端的验收。

### 第二十四组：上游 IPv6 socket 与现有 HTTP 应用

Linux `c5b78cfcc`、distro `5cfe25a` / 集成 `7fc47f4` 将三套 defconfig 的
`CONFIG_IPV6` 从关闭改为内建，构建时检查解析后的配置。此前 AF_INET6 缺少
对应协议族；本增量接通上游网络实现，不用用户态伪造 IPv6，不新增 syscall
编号、musl 函数或应用 API。保持 NOMMU 和原先 fork 支持边界不变。
源码哈希由公开 [prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39572979736)
核实。BusyBox 显式开启现有 FEATURE_IPV6，沿用固定源码及许可证，不加程序补丁。

C 工作负载在 Wasm initramfs 内用标准网络 ioctl 将 lo 置为 UP，不改变宿主网络。
三阶段分别核对 IPv6 TCP 连接/accept/二进制传输/有序 EOF、V6ONLY=0 的双栈
监听与 IPv4-mapped peer，以及 UDP sendmsg 的两段 iovec、recvmsg 的来源地址、
IPV6_PKTINFO 辅助数据和实际 loopback 接口编号。socket 使用 NONBLOCK/CLOEXEC，
连接完成还核对 SO_ERROR，读取前有界等待 readiness。没有用原生结构替代 Wasm
头文件，双位宽前端独立检查现有 sockaddr_in6/in6_pktinfo 等布局与声明。

真实 BusyBox 负载以 `/proc/net/tcp6` 确认 ::1 HTTP listener 后，再由普通 wget
和 nc 请求 IPv6 地址 URL/服务，核对实际内容，停止并 wait 回收服务进程。
该负载只验证实例内 loopback，不依赖外网路由、DNS 或宿主 IPv6 转发。

GCC/Clang 原生语料、ASan/UBSan、损坏 packet-info 接口断言的反向控制、Clang
静态分析、双位宽 musl 前端以及宿主参考 BusyBox 的实际 IPv6 HTTP 传输均通过。
review 核对非阻塞连接、地址/辅助数据边界、资源收尾和 host/target 网络边界；
这些结果不是 Wasm 目标执行证明，宿主 BusyBox 也不等于固定 Wasm applet。

同一 `5cfe25a` 已派发
[C wasm32](https://github.com/HighCWu/distro/actions/runs/39573454397)、
[C wasm64](https://github.com/HighCWu/distro/actions/runs/39573461715)、
[BusyBox wasm32](https://github.com/HighCWu/distro/actions/runs/39573471226) 和
[BusyBox wasm64](https://github.com/HighCWu/distro/actions/runs/39573478191)。
C 要求三阶段，BusyBox 要求两阶段，各自还需唯一 pass 和机器关闭，目标结果待验收。
不据 loopback 通过推定外部 IPv6 连通、SLAAC/邻居发现、DNS、全部 socket options、
多播、IPsec、namespace 隔离或浏览器验收完成；外部连通还取决于实际网络后端。

上述 `5cfe25a` 四路 Node 目标现已成功，实际日志逐项核实双位宽 C 三阶段、
BusyBox 两阶段及最终 pass。结合固定运行器的关闭失败非零退出约束，确认机器
关闭门禁通过；没有新增浏览器或外部网络连通结果。

### 第二十五组：wasm32 宽 syscall 标量与 wasm64 同步参数顺序

Linux `2237e08ea`、musl `59301bde`、distro `aa2db02` / 集成 `cfc22a7`
修正两处实际 ABI 缺陷，不是新增包装函数或只增加测试：

- 原 wasm32 内核 wrapper 每个 C 参数只读取一个 syscall 机器字；musl 已将
  loff_t 等 64 位标量拆成连续 low/high 两字。旧入口会丢高位并错置后续参数，
  不仅影响超过 4 GiB 的 pread/pwrite/truncate，还影响 fallocate 等两个宽参数。
  新入口按声明类型、依次重组 64 位标量；没有偶数寄存器对齐空位。明确用两个
  unsigned long 声明的 preadv 等仍逐字传递，不再次合并。六字边界先验证，无法
  表达的超长签名拒绝 ENOSYS 而不越界读取；零参数和 wasm64 路径保持原取值方式。
- musl 的 Wasm syscall 表此前不分位宽选择 sync_file_range2，但内核只有 wasm32
  选择 flags-first 的 range2，wasm64 使用 offset-first 的 sync_file_range。
  架构表现在按 long 位宽选择正确名称，沿用同一标准号 84、上游已有函数体。
  不增加公共函数、通用包装或项目 API；旧 wasm64 程序须重新链接修正后的 libc。

源码哈希分别由公开 prefetch
[Linux](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39574895129)、
[musl](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39575139024) 核实。
Linux 派生修改保留内核 GPL，新增独立语料为 MIT，不改 MMU/fork 支持边界。

原样 syscall_wrapper.h 的小型 freestanding Wasm 执行先复现旧 wasm32 第一用例
失败，修正后双位宽通过：两个宽参数、负宽参数、后随标量、指针、六个普通字、
零参数和六字边界；重新引入旧取值方式的反向控制仍失败。该检查不是完整内核
执行。还实际编译并执行 musl 原样 sync_file_range.c，在 import 处核对双位宽
完整七参数的顺序和数值，不只看预处理宏名称。

共享 C 负载用可写 ext4 根目录上的稀疏文件验证 >4 GiB 的 ftruncate、pread/
pwrite 与低地址不混叠、preadv/pwritev、fallocate/posix_fallocate、posix_fadvise、
sync_file_range/fsync、路径 truncate、负数拒绝、POSIX errno 保留与回收。
文件逻辑大小超过 4 GiB，但只实际分配少量块；不扩大用户线性内存范围。
GCC/Clang native 与 ASan/UBSan、Clang 静态分析、双位宽头文件/声明及既有
mapping 检查通过，可选 fork 补丁对新 musl dry-run 通过。review 核对类型别名、
符号位、split-word 例外、顺序求值和寄存器边界；没有以此宣称所有 syscall 已完整。

同一 `aa2db02` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39575748736) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39575757814) 已派发，要求大文件
完整四阶段、最终 pass 与机器关闭，尚待目标验收。不把前两组旧配置结果当作
新通用入口的回归证明，也不宣称浏览器、大文件 mmap 或物理持久化崩溃恢复已通过。

首轮两路均未进入目标编译或运行：实际失败日志是 treefmt 中的 ShellCheck
SC2093，指出 large-file-test.sh 在 exec 后仍有语句，不是已经观察到的宽参数
内核回归。distro `0e68343` / 集成 `382cfe8` 移除不必要的启动脚本，直接以
大文件 C 程序作为已安装 ext4 系统的 `/init`；Linux/musl 修复与负载均不变。
没有压低门禁、跳过检查或修改已发布历史；删除的脚本仍可从原 Git 提交恢复。

同一 `0e68343` 的定向
[wasm32](https://github.com/HighCWu/distro/actions/runs/39576392143) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39576401631) 已派发。原样入口、
实际 musl 包装、native 大文件和双位宽前端重新通过；新目标仍需四阶段、最终
pass 与关闭证据。首轮失败结果保留，不以宿主验证替代真实目标验收。

`0e68343` 的 wasm64 现已成功，实际日志核实完整四阶段及唯一 pass，成功作业
通过等待 machine.closed 的关闭门禁。wasm32 则在内核编译时失败，首个错误为
syscall_wrapper.h 对尚未完整定义的 pt_regs 访问 syscall_args；失败翻译单元是
kernel/sys_ni.c，不是已经观察到的文件读写错误。原小型测试在 ptrace shim 内
提前给出了完整结构，掩盖了这一真实包含顺序。

Linux `5bc1ee5e6` / distro `1459987` / 集成 `fb2eea5` 显式包含 asm/sigcontext.h。
辅助函数在定义点取得完整 pt_regs；参数解码数学和 musl `59301bde` 不变。
回归改为 ptrace 仅前置声明，并使用同一固定内核的真实 UAPI sigcontext.h，
先复现相同编译错误，再核实双位宽执行和旧布局反向控制。CI 只提取两份确切
固定头文件，无需本地构建或完整下载 Linux。源码哈希由
[prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39578646883) 核实。

同一 `1459987` 已定向派发
[wasm32](https://github.com/HighCWu/distro/actions/runs/39579254479) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39579262438)，仍要求四阶段、
最终 pass 及关闭。旧 wasm64 结果仅属于 `0e68343`，不将其当作新 pin 的通过证明。

同轮调度排查没有形成新接口增量：musl 的四个调度桩并非 Wasm 独有缺失，
固定 BusyBox chrt 原本默认启用且直接调用 Linux syscall。已撤下未集成的重复
构建选项/测试，不把它们计作能力进展。musl 实验只用后续撤回提交保留历史，
SDK 与 gitlink 仍为原基线；审计见[musl 兼容性边界](musl-compatibility.md)。

`1459987` 双位宽大文件目标现已成功，实际日志逐项核实完整四阶段及各自唯一
pass：包括 wasm32 的高偏移不混叠、显式拆字 vectored I/O、两个宽参数及后随
flags、负数错误与收尾。成功作业通过等待 machine.closed 的关闭门禁。
这补齐该宽参数修复的 Node 验收，不扩大为大文件 mmap、浏览器或崩溃持久化。

### 第二十六组：现有 fchmodat flags 与 O_PATH 权限操作

musl `d950af5c` / distro `574af86` / 集成 `5b0ffda` 补齐 Wasm 架构表缺少的
标准 fchmodat2 号 452，使 tombl/musl 已有 fchmodat 函数内的对应分支进入构建。
原先 AT_EMPTY_PATH 在 libc 层直接返回 EINVAL；NOFOLLOW 路径则可能退回依赖
procfs 的兼容实现。当前固定 Linux `5bc1ee5e6` 已有该 syscall，不需新增内核
实现或编号。没有新增函数包装或头文件；fchmodat 公开声明、AT_* flags 常量、
编译器和执行 import 不变。新增宏仅为既有接口接入所需的标准架构 syscall 号。

对同一固定 Linux 的 asm-generic/arch unistd 按 wasm32/wasm64 展开后，既有共同
名称未发现其它数值错配；部分历史别名名称不同但编号相同，未机械删除。表内
__NR_syscalls 从过时的 451 修正为该内核的 472，只是编号范围，并非全部调用
已支持或验收。新源哈希由公开
[prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39580528712) 核实。

原样 src/stat/fchmodat.c 的小型 Wasm 执行先复现旧表在双位宽下没有进入
fchmodat2；补齐后核对完整机器字分派、内核 errno、无 flags 仍使用旧 fchmodat，
以及 ENOSYS 后仍进入原有 fallback。删除新增编号的反向控制必须重新得到旧
EINVAL/零次 syscall 行为。函数体不修改，不把项目自己实现的包装当作原函数。

共享 C 程序通过普通 fchmodat 调用核对：重命名后的 O_PATH fd 配合空路径修改
mode、dirfd 相对 regular file 的 NOFOLLOW、symlink 不误改目标、坏 fd/flags/
缺失路径拒绝、unlink 后仍持有 fd 的 inode 权限与最后关闭回收。raw initramfs
不挂载 procfs，因此目标不依赖 /proc/self/fd 兼容路径。只覆盖当前权限位和根
进程工作负载，不扩大到 ACL、跨用户权限、所有文件系统或 namespace 模型。

GCC/Clang native 与 ASan/UBSan、Clang 静态分析、双位宽前端及实际 libc 分派
检查通过；可选 fork 补丁对新 musl dry-run 通过。review 核对原 fallback 保留、
fd/inode 生命周期、flags 与机器字宽度；musl 相对 `59301bde` 的净差异只有架构
编号表，src/include 无新差异，调度桩保持上游原状。

同一 `574af86` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39581038415) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39581048899) 已派发，要求完整
三阶段、最终 pass 与机器关闭。当前尚未完成目标验收，不以 native/小型模块
或前一组大文件目标代替这一路径的真实内核运行，也没有新增浏览器结果。

上述 `574af86` 双位宽现已完成验收：实际日志逐项核实 O_PATH/rename、symlink
保护与错误恢复、unlink 后 inode 生命周期三个阶段，各自唯一 pass，成功作业
通过等待 machine.closed 的关闭门禁。没有扩大为浏览器或所有权限模型结论。

### 第二十七组：SysV 消息队列与信号量

Linux `9e49334d3` 在三套 Wasm 配置启用 CONFIG_SYSVIPC，接通上游消息队列和
信号量实现，使用原有 uaccess 拷贝路径。此前配置关闭时对应 syscall 不可用。
此增量不是新写 libc 包装：musl `a0c027a4` 仅修正 Wasm 架构元数据定义，复用
已有 time64 控制函数；distro `3aaf7df` / 集成 `6791165` 固定双方源码与哈希。

共享内存家族 shmget/shmctl/shmat/shmdt 仍明确返回 ENOSYS：通用 NOMMU shmat
返回的内核线性地址不是独立用户 WebAssembly.Memory 中的真实共享映射，不能
因启用 SYSVIPC 而暴露。入口使用匹配 pt_regs 的 syscall 包装，避免 Wasm
间接调用签名不匹配。CONFIG_MMU=n、直接内存边界与多线程 fork 限制不变。

wasm32 原 generic IPC 结构存在错位，现使用 musl 已有 riscv32 风格 wire-prefix
和追加时间字段，原样 msgctl/semctl/shmctl 完成转换；wasm64 保持 generic。
此修正要求相关旧 wasm32 对象、静态库和程序用新 SDK/libc 重编译，不得混用。
精确固定内核 UAPI 布局、双位宽原样控制函数执行、超过32位时间值和旧布局
失败控制通过；native GCC/Clang ASan/UBSan 与双位宽 Clang 静态分析通过。

共享工作负载覆盖类型选择与二进制消息、E2BIG 不丢消息、截断/空队列/坏类型、
IPC_STAT 元数据与删除；信号量覆盖 SETALL/GETALL、多操作失败原子回滚、超时与
坏 timespec、GETNCNT 确认实际入队后 IPC_RMID 唤醒 EIDRM、重新创建及回收。
目标还通过原有 posix_spawn 启动未经修改的 BusyBox ipcs，分别读取另一进程
创建的队列和信号量，检查实际对象 ID 和退出结果；此步骤在创建 pthread 前
完成，不扩大多线程 fork。native 不冒充该 applet 或 Wasm 内核运行证据。

同一 `3aaf7df` 的 Node
[wasm32](https://github.com/HighCWu/distro/actions/runs/39587100196) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39587106606) 已派发，
要求完整三个 sysv-ipc 阶段、最终唯一 pass 和机器关闭。
当前目标待验收；不宣称 SHM、SEM_UNDO 的进程退出恢复、所有 IPC namespace、
跨用户权限或浏览器已验证。架构细节见[musl 兼容性边界](musl-compatibility.md)。

首轮 `3aaf7df` 两路均实际进入工作负载，随后在 message metadata ABI 阶段失败，
errno=22。原因不是结构 offset，而是 Wasm 架构未声明 IPC_64=0，原有 libc
IPC_CMD 将控制命令加上旧式 0x100 位。固定内核的原生 msgctl/semctl 入口已
直接选择 IPC64 布局，不会解析旧命令版本位，IPC_STAT 应传2而非258。
此前小型检查也错误预期258，未能暴露这个协议问题；其通过不构成目标验收。
修正沿用 musl 现有 RISC-V 的架构约定，不更改通用控制函数或公开 API。
新增回归直接编译固定内核 ksys_msgctl 原函数与固定 UAPI 常量，分派逻辑不
重写，只替代分配/复制依赖，核实2命中、258返回 EINVAL；原样 libc 必须传2。
musl `7eade118` / distro `ea37cb4` / 集成 `af5915f` 已提交该修复；源哈希由
[prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39589895762) 核实。
原样控制函数、固定内核分派、结构和 native/sanitizer 四项检查通过，可选
fork 补丁 dry-run 通过。同一 `ea37cb4` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39590198798) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39590206054) 已定向重派；
必须重新核实全部三阶段、最终 pass 与关闭，尚不宣称目标修复已验收。

`ea37cb4` 双位宽现已核实实际日志：typed binary queues/metadata/errors/removal、
semaphore atomicity/metadata/timeout/recovery、blocked removal/EIDRM/recovery/
direct-memory boundary 全部三阶段及各自唯一 pass。原样 BusyBox ipcs 在阶段
报告前必须成功读取队列/信号量元数据并正常退出；工作负载没有 native 跳过
分支。成功作业通过等待 machine.closed 的关闭门禁，补齐该修复的 Node 目标
验收。共享 backing 仍明确不可用，SEM_UNDO 和浏览器不在此验收范围内。

### 第二十八组：上游持久文件句柄 syscall

Linux `5c25d2f4e` / distro `10d7c71` / 集成 `5983fa4` 将三套配置原先显式关闭的
CONFIG_FHANDLE 改为启用，由上游选择 EXPORTFS，提供
name_to_handle_at/open_by_handle_at 的真实内核实现。
tombl/musl 已有两个函数及对应 GNU 声明，和当前源码逐文件比较无差异，不修改
libc、公共函数集合、结构或编号；没有用新增包装代替内核接通。

工作负载安装在可写 ext4 系统：先通过 EOVERFLOW 查询所需句柄长度，再编码
文件路径和 AT_EMPTY_PATH fd，比较句柄/挂载 ID，重命名后按句柄重新打开，
核对 inode、二进制内容与 CLOEXEC。零长度、超长、无效类型和坏 anchor 拒绝
后仍可重开；临时移除有效 CAP_DAC_READ_SEARCH 时必须 EPERM，恢复能力后
继续验证，保留内核原有权限模型。最后 unlink，核对仍打开 fd 可读，关闭最后
引用后必须 ESTALE；清理全部完成才报告 pass。

review 核对锚点使用普通目录 fd，而非被该内核 fdget 排除的 O_PATH；检查
固定长度前缀、能力 ABI 的双32位数据字、原始 syscall 的完整 long 参数、
句柄分配边界及恢复/关闭顺序。双位宽原样 musl 包装和 syscall_ret 小型 Wasm
执行核对参数、指针和 errno，Clang 静态分析与 GCC/Clang sanitizer 检查通过。
native 若缺少可编码文件系统或解码 capability，会明确报告目标仍需验证，
Wasm 分支没有这一跳过路径。完整 ext4 目标与关闭仍待验收。

固定源码哈希由公开
[prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39588019258) 核实。
同一 `10d7c71` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39588423184) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39588429206) 已派发，要求三个
file-handle 阶段、最终唯一 pass 和机器关闭；不复用前一个 IPC 配置的运行结果。

上述两路首轮均在 Plan checks 失败，实际错误是 installedDisk requires at least
one APK package：缺少 installedTest 镜像所需的基础软件包，尚未编译或运行
内核/工作负载。distro `2cee432` / 集成 `54d4555` 为镜像加入现有 BusyBox，
与同类 installedTest 的构造保持一致；内核、C 工作负载和验收要求不变。
同一 `2cee432` 已定向重派
[wasm32](https://github.com/HighCWu/distro/actions/runs/39588740610) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39588747729)，完整目标待验收。

`2cee432` 双位宽现已验收：实际日志逐项核实 size discovery/descriptor encoding/
rename reopen、invalid handles/decode permissions/recovery、unlink lifetime/
stale refusal 三阶段，各自唯一 pass；成功作业通过等待 machine.closed 的
关闭门禁。此证据属于该源码的 Node ext4 工作负载，不扩大为浏览器或所有文件系统。

不把此配置解释成所有文件系统、跨重启/跨挂载稳定性或 NFS 服务已验收；句柄
是上游不透明对象，不是线性内存地址，不改变 NOMMU/映射边界或隔离模型。

### 第二十九组：恢复官方默认目录通知

Linux `059800405` / distro `8236b08` / 集成 `ad9704d` 删除三套 Wasm defconfig
中额外关闭 DNOTIFY 的条目，让
[Linux 官方 v7.1 的 default y](https://github.com/torvalds/linux/blob/v7.1/fs/notify/dnotify/Kconfig)
及 FSNOTIFY 选择条件正常生效；构建检查最终 CONFIG_DNOTIFY=y。通过上游
fcntl(F_NOTIFY) 和信号路径提供目录变更通知，不新增 syscall 号、musl 包装或
应用 API；inotify 仍是更现代的接口，此恢复用于保持原有 Linux 程序兼容。

普通 C 工作负载使用现有 F_SETOWN/F_SETSIG 和阻塞实时信号集，检查通知中的
si_code、si_fd、si_band，一次性订阅自动撤销、多次订阅连续通知、先撤销再
更换 CREATE/DELETE 掩码、显式撤销后不再通知、非目录/坏 fd 拒绝后恢复，
最后关闭 watch fd 后从另一目录 fd 创建文件不得遗留通知。所有清理完成并
恢复原信号掩码后才报告 pass；不依赖异步抢占、不创建线程或扩大 fork 范围。

GCC/Clang 的 native 实际三阶段和 ASan/UBSan、双位宽 Clang 前端及静态分析
通过；将 F_NOTIFY 替换成配置关闭时的 EINVAL 后，工作负载必须在第一次注册
失败且不得输出 pass，不能靠空事件队列误判支持。review 核对所有 fcntl 变参
使用完整 long、SIGIO fallback 也进入阻塞/检查集合、同步文件事件完成后的
零超时空队列检查，以及撤销/关闭顺序。真实 Wasm 三阶段与关闭待单独验收。
固定源码哈希由公开
[prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39589249774) 核实。
同一 `8236b08` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39590288141) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39590295634) 已派发；目标须有
完整三个 dnotify 阶段、最终唯一 pass 和关闭证据，当前仍为待验收。

`8236b08` 的 wasm64 已核实实际三阶段：one-shot/descriptor/automatic disarm、
multishot/mask replacement/removal、invalid descriptors/recovery/close cleanup，
唯一 pass 与等待 machine.closed 的关闭门禁通过；wasm32 状态单独跟踪，不
使用 wasm64 结果代替它，也不扩大为浏览器验收。

wasm32 随后也已核实同一 `8236b08` 的实际完整三阶段与唯一 pass，成功作业
通过相同关闭门禁。至此该 DNOTIFY 增量的双位宽 Node 验收齐全，旧的目录
通知配置关闭路径不能再作为当前版本的能力描述；浏览器仍未新增验收。

### 第三十组：标准 sigaltstack 与版本化信号 C 栈执行候选

Linux `ba9894d96` / musl `e12bb18e` / distro `40ff62a` / 集成 `9c339f0` 接回
通用 sigaltstack syscall，记录当前用户 C 栈指针，不再跳入旧的 ENOSYS 替代。
注册、查询、最小尺寸、flags 和在栈状态校验仍由 Linux 原实现负责。信号返回
复用同一 do_sigaltstack：仅将它改为内核内部可见并声明，不复制或改变原校验
函数体；这是 Linux 内的 GPL 变更，不是供用户程序链接的函数。

内部 user_signal_v1 ABI 读取模块导出的可变整数 __stack_pointer，并在 SA_ONSTACK
回调时切换该全局；引擎按导入类型验证精确 i32/i64 和 mutability，不凭数值
猜测。区域范围、加法溢出、空基址和16字节对齐在进入回调前检查；共享内存
包装可能滞后时只 grow(0) 刷新视图，不扩大内存。嵌套返回恢复本实例的栈，
异常原样传播到编译器 SjLj catchpad；exec 替换实例不被旧回调覆盖。新增内核
C 栈全局导出及 syscall 异常边界恢复，避免用户非局部退出遗留内核线性 C 栈深度。

musl 只修改既有 Wasm 信号 trampoline：linux_signal_v1.frame/finish 复制并返回
原有 ucontext 的 stack/mask 字段，context 仍在 C 对象生命周期内时即复制到
内核帧，不保存失效的用户栈对象指针。正常返回使用通用校验恢复注册与掩码，
保留在栈保护，过滤 SIGKILL/SIGSTOP；SS_AUTODISARM 和 SjLj 分别走正常恢复或
跳出后保持禁用的路径。没有新增公共函数、公共头文件 API 或通用 libc 扩展；
sigaltstack 原包装和声明不变。引擎寄存器仍不伪造，不宣称支持 setcontext、
原生 rt_sigreturn、引擎 trap 转换或栈溢出恢复；协作式投递和 NOMMU 边界不变。

普通 SDK 导出 C 栈全局；无导出的模块在 sigaltstack 返回 EOPNOTSUPP，普通
一/三参数信号回调仍保留兼容路径。独立负载故意省去导出，并检查最终二进制
实际没有该 export；主负载则检查 export 确实存在，避免仅凭链接参数宣称匹配。
新内核需配套宿主的 user_signal_v1 导入；新宿主对缺少上下文扩展的旧内核保留
最小 context fallback，不把版本缺失猜测成新的支持。

主负载要求五阶段：注册/查询/错误；siginfo 和嵌套栈；自动撤销与正常恢复；
16次 SjLj 跳出及原帧/掩码恢复；返回 context 的掩码和受保护/自动撤销注册修改、
KILL/STOP 保护及清理。GCC/Clang native 与 ASan/UBSan 参考检查、双位宽前端
及静态分析、339项运行层检查和源码/测试 TypeScript 检查通过。native ASan
保留边界检查，但不预装自身信号栈或把局部变量搬到 fake stack，以便检查实际
C 栈地址；这些结果都不是 Wasm 内核目标证据。可选 fork 补丁 dry-run 通过。
固定源码哈希已由公开
[Linux](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39597788439) 与
[musl](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39597795570) prefetch 核实。
双位宽主负载、无导出兼容负载及已有 fork runtime 均单独派发，阶段和关闭
分别记录如下；`40ff62a` 阶段默认 CONFIG_SITE 仍保留 sigaltstack 负向答案，
后续移除及应用验证见本节末尾。

同一 `40ff62a` 的定向目标均已核对实际 Heavy 检查名：

| 检查 | wasm32 | wasm64 |
| --- | --- | --- |
| 信号栈五阶段 | [阶段与关闭已核实][alt-node32] | [阶段与关闭已核实][alt-node64] |
| 无栈导出模块 | [阶段与关闭已核实][alt-legacy-node32] | [阶段与关闭已核实][alt-legacy-node64] |
| 原有 fork runtime | [阶段与关闭已核实][alt-fork-node32] | [阶段与关闭已核实][alt-fork-node64] |

[alt-node32]: https://github.com/HighCWu/distro/actions/runs/39599563781
[alt-node64]: https://github.com/HighCWu/distro/actions/runs/39599576739
[alt-legacy-node32]: https://github.com/HighCWu/distro/actions/runs/39599594972
[alt-legacy-node64]: https://github.com/HighCWu/distro/actions/runs/39599607937
[alt-fork-node32]: https://github.com/HighCWu/distro/actions/runs/39599617389
[alt-fork-node64]: https://github.com/HighCWu/distro/actions/runs/39599624459

wasm32/wasm64 主负载实际日志均已逐项核实全部五阶段和各自唯一 pass；双位宽
无导出模块均已核实拒绝/普通回调阶段与唯一 pass，四项成功作业通过等待
machine.closed 的关闭门禁。

双位宽 fork runtime 随后也已核实实际全部阶段及唯一 pass：raw clone/clone3、
pending signal、PID/TLS/atfork/mask/memory/fd/nested wait、拒绝 exec 后恢复、
未变换 helper 的 raw clone 拒绝与 exec 继承/重置、exec 替换及 wait、多线程
和信号回调内 fork 拒绝、flags-first/legacy callback 共存及后续恢复。两项成功
作业通过同一关闭门禁；至此本候选六路 Node 验收齐全，不扩展为新 fork 支持
范围或浏览器结果。

浏览器门禁已在 distro `92eb6b1` / 集成 `5e8791b` 接入既有 process runner，
复用以上同一标准负载及无栈导出负载，不重复实现 syscall。两类均要求精确、
有序且不重复的阶段、唯一 pass，同一页面两轮启动、各轮 machine.closed、
浏览器关闭后无迟到错误。本地控制器及负向门禁 18 项通过，不作浏览器证明。

2026-10-23 已逐项核实以下八项实际 Heavy 日志和关闭结果：

| 负载 | 位宽 | Chromium | Firefox |
|---|---|---|---|
| 信号栈五阶段 | wasm32 | [两轮及关闭已核实][alt32-chromium] | [两轮及关闭已核实][alt32-firefox] |
| 信号栈五阶段 | wasm64 | [两轮及关闭已核实][alt64-chromium] | [两轮及关闭已核实][alt64-firefox] |
| 无栈导出兼容 | wasm32 | [两轮及关闭已核实][legacy32-chromium] | [两轮及关闭已核实][legacy32-firefox] |
| 无栈导出兼容 | wasm64 | [两轮及关闭已核实][legacy64-chromium] | [两轮及关闭已核实][legacy64-firefox] |

[alt32-chromium]: https://github.com/HighCWu/distro/actions/runs/39881687103
[alt32-firefox]: https://github.com/HighCWu/distro/actions/runs/39881688862
[alt64-chromium]: https://github.com/HighCWu/distro/actions/runs/39881691449
[alt64-firefox]: https://github.com/HighCWu/distro/actions/runs/39881693540
[legacy32-chromium]: https://github.com/HighCWu/distro/actions/runs/39881695121
[legacy32-firefox]: https://github.com/HighCWu/distro/actions/runs/39881696874
[legacy64-chromium]: https://github.com/HighCWu/distro/actions/runs/39881699057
[legacy64-firefox]: https://github.com/HighCWu/distro/actions/runs/39881700447

双位宽 Chromium 149.0.7827.55 和 Firefox 151.0 的实际 Heavy 日志均已核实
主负载每轮五阶段、无导出负载每轮一阶段，各项均有两轮各自唯一 pass、每轮
machine shutdown 及最终 browser shutdown。这关闭固定 `92eb6b1` 的八项
浏览器门禁，不将它扩大为 CPython 浏览器或后续内核版本的完成证明。

`f404198` / 集成 `9a2a516` 在上述六路 Node 真实语义验收基础上移除共享
CONFIG_SITE 的 `sigaltstack=no`，不预填 yes；此应用增量与浏览器验收异步推进。
SDK Autoconf 消费者须通过真实链接检测发现该函数，CPython 构建须由原有
configure 生成 HAVE_SIGALTSTACK，不添加 CPython 私有补丁或编译宏强制项，
也不改变 musl。Vim 配方关于 ENOSYS 的旧说明已同步撤除，但不宣称新版 Vim
运行已验收。

实际 CPython 负载使用 `-X faulthandler` 启动，核实正常配置和备用栈注册，
由原有 faulthandler.register 在 SA_ONSTACK 上执行 16 次 SIGUSR1 traceback，
检查确切 Python 帧、取消注册后的原 handler 恢复、无效注册及 enable/disable
恢复与文件清理。当前线程及 all_threads 输出均只针对该单线程解释器；不宣称
多线程信号备用栈、引擎 trap、原生栈溢出或完整故障恢复支持。
本地含关闭特性/未启用启动选项的负向对照及现有兼容检查共 32 项通过，非目标
证据。四项实际 Heavy 检查已派发，完成后仍须核实实际阶段、唯一 pass 和关闭：

| 检查 | wasm32 | wasm64 |
|---|---|---|
| CPython faulthandler | [阶段与关闭已核实][python-alt32] | [阶段与关闭已核实][python-alt64] |
| SDK Autoconf 消费者 | [检测及运行已核实][sdk-alt32] | [检测及运行已核实][sdk-alt64] |

[python-alt32]: https://github.com/HighCWu/distro/actions/runs/39882160137
[python-alt64]: https://github.com/HighCWu/distro/actions/runs/39882162040
[sdk-alt32]: https://github.com/HighCWu/distro/actions/runs/39882164072
[sdk-alt64]: https://github.com/HighCWu/distro/actions/runs/39882165733

双位宽 SDK 实际日志均已确认真实 Autoconf 消费者检查通过（其中断言正常探测
sigaltstack=yes）、目标 allocation 阶段和唯一 pass。双位宽 CPython 实际日志
均核实 ABI/安装布局、全部三个 faulthandler 阶段及唯一 pass；四项成功作业
通过原有等待 machine.closed 的关闭门禁。CPython 没有新增该功能的私有补丁，
这也是原有应用通过正常探测实际使用恢复后的 syscall 的证据，不扩展为 trap
恢复、Vim 或浏览器 Python 的验收。

### 第三十一组：恢复官方默认 membarrier 与任务切换屏障

Linux `2b572a9a0` / distro `0083011` / 集成 `b9d305a` 删除三个 Wasm
defconfig 中额外的 MEMBARRIER 关闭项，使用官方 Linux init/Kconfig 的
`default y`，并在解析后的 .config 检查 CONFIG_MEMBARRIER=y；不是以
tombl 的裁剪配置作为默认基准。CONFIG_MMU 继续为 n。

此恢复不是仅改开关：通用 NOMMU switch_mm 为空，Wasm 的任务在独立内核
实例之间交接。根据[官方架构屏障要求](https://github.com/torvalds/linux/blob/master/Documentation/scheduler/membarrier.rst)，
__switch_to 在调度器发布 rq->curr 后、返回用户态前显式执行完整 smp_mb。
原有发送/接收 IPI 与通用 smp_call_function 路径保留；通用 membarrier
注册、RCU、命令校验和 CPU 筛选实现未重写。Linux 内改动保留 GPL；独立语料
及校验为 MIT。不选择 ARCH_HAS_MEMBARRIER_SYNC_CORE 或 RSEQ 来虚报能力。

同一独立负载通过标准 SYS_membarrier、完整机器字参数直接验证真实内核，
不使用 libc 私有 fallback，不新增 musl 函数或公共命令声明；尚未被固定 libc
命名的标准 GET_REGISTRATIONS 位值只在负载内定义。三阶段为：

1. QUERY、无效 flags/command 和未注册 private expedited 的 EPERM；Wasm
   目标还必须拒绝不支持的 sync-core/rseq 命令，而非静默成功。
2. private/global 注册、重复注册、已注册状态查询和单线程执行。
3. 两个线程绑定到不同允许 CPU，128轮 private expedited 与 compiler-barrier
   配对的有界 ordering 语料、穿插 global/global-expedited、join 后恢复原
   affinity 并再次执行屏障。没有两个允许 CPU 就失败，不跳过 SMP 检查。

两线程共享 C 状态均使用明确原子/发布握手，工作线程的非原子结果只在 acquire
确认完成后读取。GCC/Clang ASan/UBSan（诊断即失败）、ENOSYS/伪造成功对照、
双位宽前端和 Clang 静态分析通过；这不是对所有内存顺序的形式证明，也不是
Wasm 内核目标结果。原线程循环定期 sched_yield 以服务当前 Wasm IPI；不宣称
浏览器能异步打断纯用户态无限循环，亦不保证这种循环中的 membarrier 完成延迟。

源码 [prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39882589630)
已核实对应修订及 unpacked hash。固定 `0083011` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39882973622) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39882975247) 均已成功。
实际 Heavy 日志逐项核实全部三阶段和各自唯一 pass；两项成功作业经同一
未改变的运行器等待 machine.closed，确认关闭门禁通过。此为两 CPU Node 的
有界负载证据，不泛化为浏览器、任意 CPU 数、sync-core/rseq 或实时完成延迟。

### 第三十二组：接回通用 ptrace 请求与 detach

Linux `64e7b1c6f` / distro `e766014` / 集成 `629012b` 将 arch_ptrace 接到
Linux 已有 ptrace_request，去掉旧的分发和 ptrace_disable BUG。没有硬件单步
或调试寄存器需要撤销时，后者不应使通用 detach 崩溃。syscall 入口同时在通用
追踪工作之前保存当前 syscall_nr，避免读取上一笔编号。通用权限、停止、信号
及恢复实现不重写；内存请求经 generic_ptrace_peekdata/pokedata 和现有
Wasm remote-mm 桥访问子进程独立线性内存，不把数值地址当成内核指针。

musl 保持 `e12bb18e`，现有 ptrace 实现不变。复核了它包含的内部 syscall 宏
本来就完成机器字转换，不为此新增包装、分支或公共声明。内核改动保留 GPL，
新独立检查和语料 MIT，不增加项目专有应用 API。

标准 C 负载使用既有可选单线程 fork profile 创建 tracee，三阶段验证：

1. TRACEME/SIGSTOP 的 wait 与 GETSIGINFO/GETEVENTMSG；全1 PEEKDATA 不误判
   errno，POKEDATA 全宽往返（wasm64 含高于32位的值）和父进程内存隔离；
   GETSIGMASK/SETSIGMASK 的精确8字节内核布局、KILL/STOP 保护，以及无效
   长度/指针/远程地址/未知 request 的标准错误。
2. CONT 后子程序实际看到修改过的数据和掩码，退出码及单次回收一致。
3. 第二个 tracee 的 DETACH 不触发架构 trap，恢复后实际验证修改；随后普通
   fork/wait 可继续执行，父进程掩码保持原值。

GCC/Clang native ASan/UBSan（诊断即失败）、伪造 POKEDATA 成功却不写入的
负向对照、双位宽前端及原样 libc/工作负载的 Clang 静态分析通过。检查仅在
临时头文件副本恢复既有可选 fork 声明，不改默认 musl；libc 按真实内部
include 顺序检查，避免把其 syscall 宏误判为公共 varargs 函数。负向失败
只清理仍属于该父进程的子进程，不按已回收 PID 盲目发信号。

Linux [prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39883561288)
已核实完整修订和 hash；固定 `e766014` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39884130096) 与
[wasm64](https://github.com/HighCWu/distro/actions/runs/39884132618) 实际 Heavy
检查已启动，尚待三阶段、唯一 pass 及机器关闭证据。不宣称 GDB/strace、
寄存器视图、断点、单步、SECCOMP 或完整 syscall-tracing 验收；也不扩大
多线程 fork 或对纯用户态计算的异步停止能力。

上述 `e766014` 两项目标随后均明确失败于“generic event and original blocked
mask”，errno=0，没有通过本组验收。源码复核发现 musl raise() 在 tkill 前临时
屏蔽应用信号，并在返回后恢复旧掩码；测试却要求此窗口中仍为先前的精确掩码，
并要求 tracer 的修改在 libc 恢复后保持，两项假设均不成立，不能修改 musl
去迎合这个断言。

`6fa36a1` / 集成 `2f7e852` 让单线程 tracee 直接通过标准 tkill syscall 停止，
六参数均显式机器字宽，保留所有精确掩码、保护位和恢复断言，并分开 event/mask
错误定位。原生 GCC/Clang 加入模拟 musl 临时屏蔽窗口的负向控制，明确在相同
掩码检查失败；伪写入控制仍在读回处失败。双位宽前端和静态分析通过。
修复后的 [wasm32](https://github.com/HighCWu/distro/actions/runs/39886766208) 与
[wasm64](https://github.com/HighCWu/distro/actions/runs/39886765701) 定向复验均已
核实实际完整三阶段和各自唯一 pass，两项成功作业通过等待 machine.closed 的
关闭门禁。内核和 musl 未因该测试假设改变；不扩大为寄存器、单步或浏览器验收。

### 第三十三组：Vim 双位宽与正常信号栈探测

distro `6f56e24` / 集成 `885c998` 新增 vim-wasm64，复用现有 Vim 9.1.2148
配方，明确选择匹配的 stdenv、platform、ncurses、BusyBox 和 vm-test；默认
wasm32 不替换。两种位宽都由原 configure 检测 sigaltstack，构建核查生成的
HAVE_SIGALTSTACK=1，而不是预填 yes 或新增 Vim 信号处理补丁。最终 src/vim
由既有字节解析器检查共享 env.memory 的真实位宽和平台内存上限，不能仅凭
包名认为是 wasm64。

原有安装系统 editing 检查继续执行版本/功能、默认启动及安装 runtime、
多行替换和文件字节、shell-out 捕获/过滤/外部命令、xxd 二进制往返；新增
三条确切阶段输出以便核实日志，不用单个 pass 推定所有步骤运行。
源码修改为集成 MIT，不改变 Vim 自有许可；既有 USE_SYSTEM/posix_spawn
策略和唯一 sys/wait 头文件补丁保持不变，不扩展默认 fork 或终端作业控制。

Nix 格式/语法、shell 语法、完整仓库元数据/文档检查和手工依赖闭包 review
通过，[wasm32](https://github.com/HighCWu/distro/actions/runs/39885517985) 与
[wasm64](https://github.com/HighCWu/distro/actions/runs/39885518633) 的实际 Heavy
日志均已核实 Vim 二进制分别为共享 memory32/4 GiB 和 memory64/16 GiB，以及
全部三个运行阶段、各自唯一 pass；两项成功作业通过等待 machine.closed 的
关闭门禁。这是固定 `6f56e24` 的双位宽 Node 应用证据，不扩展为浏览器或
所有交互式终端模式。原版 Vim 的 init_signal_stack 会
忽略 sigaltstack 返回值，因此“原路径编译启用且编辑正常”不是注册成功、
异步信号或引擎栈溢出恢复的单独证明；后者不能从本项扩大宣称。

### 第三十四组：有界内核栈诊断

Linux `562df5ddb` / distro `b0b3bff` / 集成 `1dba055` 修复默认诊断路径：
旧 show_stack 在 kmalloc 失败后仍继续使用指针，宿主复制不保证 NUL 终止，
且用块设备专用的 %pg 打印 task 指针，并将当前 Worker 的栈标成其他任务。
新实现使用内核栈上固定1024字节零初始化缓冲区，无 GFP_KERNEL 分配，末字节
强制 NUL 以兼容旧宿主；只将当前 Worker 的引擎栈标给当前任务，其他任务明确
输出 unavailable。PID 以整数打印，不把 task 指针解释为 block_device。
不宣称恢复远程栈、KALLSYMS/寄存器展开，或保证宿主引擎自身耗尽内存后仍能输出。
旧 %pg 的含义参见[官方 printk 格式说明](https://docs.kernel.org/core-api/printk-formats.html)。

MIT 宿主桥保留原导入签名，按无符号机器字解码指针和容量，校验完整缓冲区，
为非零容量保留 NUL，截断时点号也不覆盖终止符；零容量不写。没有新 syscall
号、应用 API 或内核 softmmu。内核改动继续留在 GPL 边界。

GCC/Clang sanitizer 使用实际 C 函数体和短/空/满长度旧宿主模型，删除末尾
终止防线的负向控制明确产生 ASan 越界读；它不是实际内核编译。宿主全套343项
和源码/测试类型检查通过，新负载的双位宽前端与静态分析通过。最终 review
发现 PID helper 的直接头依赖，Linux `9d8422855` 显式包含 linux/pid.h；宿主
模型不能证明真实头依赖，检查也因此补充了该直接依赖约束。

首轮 b0b3bff 的 [wasm32](https://github.com/HighCWu/distro/actions/runs/39888040995)
实际日志确认 task_pid_nr 未声明，和上述补充依赖对应；
[wasm64](https://github.com/HighCWu/distro/actions/runs/39888043286) 则未进入内核
编译/运行，两个源码镜像均 HTTP 429。不能将两种失败混称为目标功能结果。
新修订 [prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39888301245)
核实固定 hash；cfda708 / 集成001ca24 接入头依赖修正及间隔15秒、5次、180秒
重试窗口的下载退避，仍强制相同40位修订和解包 hash，不降级校验或换版本。
重试窗口不等于成功传输的总时限。

标准 C 驱动只允许编译到 Wasm，在隔离测试内核挂载 proc、两次写 SysRq t、
读取 syslog、检查本任务身份及其他任务明确不可用，再清理 fd/mount 并继续
执行 syscall。构建宿主只运行模型和前端分析，绝不运行宿主 SysRq。
cfda708 的 [wasm32](https://github.com/HighCWu/distro/actions/runs/39889070509) 与
[wasm64](https://github.com/HighCWu/distro/actions/runs/39889071887) 作业已成功结束，
但不以工作流状态代替阶段/关闭证据，也不能覆盖后续 READ_CLEAR 条件。

最新 `c9b05d1` / 集成 `2ec49ed` 将驱动改为 READ_CLEAR：仅清理本隔离测试
内核的日志，让每轮必须读到新诊断，避免借用上一轮标记。前端/分析已通过，
但 cfda708 任务不包含这一条件；它们终态后已从 c9b05d1 派发同名新版本
[wasm32](https://github.com/HighCWu/distro/actions/runs/39890210382) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39890211826) 实际 Heavy，
现已逐项核实全部三阶段、各自唯一 pass 与运行器关闭门禁。每项在同一机器内
执行两轮 SysRq/READ_CLEAR，不是两次启动；第二轮不能借用第一轮日志。两项
Node 目标验收通过，不扩展为浏览器结果或远程任务栈展开支持。

### 调度候选复核与撤回（不计为新增能力）

本轮再次误将已有四个 sched_* 的 ENOSYS 当成 Wasm 缺口，发布 musl
`ae2f7e47`、distro `8d14095` 和集成 `5d598c1`。复读已有兼容性审计后发现
这是官方 musl 有意保留的 POSIX 进程级语义，而非 tombl 的 Wasm 实现缺失。
本地 raw syscall/薄包装对照通过不能证明这样的 libc 语义变更正确。

musl `631d5a2e`、distro `128b1e6`、集成 `b534377` 追加撤回，保留所有公开
提交，不 force-push。已核实 musl 整树与 `e12bb18e`、distro 整树与
`c9b05d1` 净差异为零；集成重新固定 `e12bb18e`，移除候选语料和构建入口。
两个已派发任务 [wasm32][scheduler-withdrawn32]、[wasm64][scheduler-withdrawn64]
属于撤回版本，即使成功也不能计作验收或新能力，不重复派发。它们不因耗时被取消。
后续选择 libc 缺口前必须先核对[既有语义审计](musl-compatibility.md)，不能仅凭
函数中的 ENOSYS 或 raw syscall 可用就恢复调用。

[scheduler-withdrawn32]: https://github.com/HighCWu/distro/actions/runs/39892427024
[scheduler-withdrawn64]: https://github.com/HighCWu/distro/actions/runs/39892433063

### 第三十五组：NOMMU process_vm_readv/writev 候选

Linux `fdf8b7d90` / distro `726d797` / 集成 `7fb70bd` 接通此前因 MMU 依赖
而不构建的标准 process_vm_readv/writev。CROSS_MEMORY_ATTACH 在 Wasm 获得
实际复制路径后沿用官方 default y，Makefile 按该选项构建；不启用 MMU，也不把
原 pin_user_pages_remote 用在线性内存偏移上。其他 MMU 平台继续使用原页固定路径。

通用 import_iovec、远端向量导入、任务查找、mm_access 的
PTRACE_MODE_ATTACH_REALCREDS 权限检查、mm 引用和部分成功返回规则保持共用。
新增 NOMMU helper 用最多4 KiB临时缓冲区，且不跨 Wasm 页边界；通过已有
access_remote_vm 和进程 Worker 邮箱复制，不向远端发布本地 iov_iter 或用户指针。
写路径先读取本地数据，只把远端真正提交的前缀计入结果，未写入部分回退迭代器；
读路径只把实际送入本地目标的字节计入结果。零长度不分配缓冲，失败也释放临时资源。
内核改动保留 GPL，独立模型和程序语料 MIT。

musl 仍为 `e12bb18e`。tombl 原有 sys/uio.h 声明、src/linux/process_vm.c 和
两个标准 syscall 号无需修改；不新增函数、公共头文件或执行导入。应用仍使用
现有 Linux 接口。这与曾撤回的进程级 sched_* 语义实验不同，没有改写 libc 的
POSIX 行为。接口的向量顺序、部分成功及权限规则参见
[Linux 手册](https://man7.org/linux/man-pages/man2/process_vm_readv.2.html)。

真实程序候选在原有单线程 fork profile 下验证：

1. 子进程先设非 dumpable；父端临时移除有效 CAP_SYS_PTRACE，读写均须 EPERM，
   再恢复原能力集；子进程恢复 dumpable 后，父端跨向量/页读取其独有内容，
   父进程同数值地址内容仍保持独立。
2. 有效前缀后接无效远端向量返回准确前缀长度；首个无效地址、flags、过多向量、
   不存在 PID 返回标准错误，空本地/远端传输保留零长度快路。写入超过64 KiB
   非均匀数据后逐字节读回。
3. 子程序实际观察写入结果后退出；回收后的 PID 拒绝访问，关闭管道，当前 mm
   自访问及后续普通 fork/wait 恢复。

GCC/Clang ASan/UBSan、原样 NOMMU helper 模型、去掉迭代器回退的精确断言失败
对照、伪造远程写成功却不修改内存的读回失败对照，以及双位宽程序/原样 libc
前端与 Clang 分析通过。模型另覆盖本地/远端短复制、首字节失败和分配失败。
这些均不是实际 Wasm 内核运行证明。

[固定来源预取][process-vm-prefetch] 已核实精确修订及 unpacked hash。
同一 distro `726d797` 的 [wasm32][process-vm32] 和 [wasm64][process-vm64]
均已成功结束；两位宽实际日志均已逐项核实全部三阶段、各自唯一 pass 及不变
运行器的关闭门禁。这是上述固定版本的 Node 验收，不泛化为浏览器结果。
继承直接内存的权限边界、远程邮箱5秒未认领超时和协作式执行限制；不承诺原生
零拷贝性能、原子快照、对纯用户计算循环的异步抢占，或扩大多线程 fork 支持。

后续 review 发现新的长传输循环没有显式调度检查点，尤其当前 mm 的复制不经
其他 Worker 等待，也不会发生普通用户页缺页。Linux `a0811a8e0` 在每个最多
4 KiB块开始前轮询 Wasm 定时器并执行 cond_resched；此时没有远程请求或
mmap 锁持有，上一块已同步完成，不会把仍被远端引用的缓冲区交给调度/释放。
不改变权限、部分成功计数或错误规则，也不把 syscall 内检查点泛化为纯用户循环抢占。

原样 helper 的 GCC/Clang sanitizer 模型与分析通过；另一个删除条件调度的
反向控制必须在检查点计数断言失败。该模型证明调用路径覆盖，不证明真实调度
延迟或多任务公平性。[预取][process-vm-poll-prefetch] 已核实精确源码和 hash；
distro `bcd1637` / 集成 `977090b` 完成 pin 更新。旧任务终态后已派发
[wasm32][process-vm-poll32] 与 [wasm64][process-vm-poll64] 定向复验，仍须
核实新增路径而非沿用旧版本结果。两项现已成功，实际日志逐项核实全部三阶段、
各自唯一 pass 及不变运行器的关闭门禁；这是该修订的有界 Node 正确性验收，
不宣称实际调度延迟/公平性已测量，也不泛化为浏览器。

[process-vm-prefetch]: https://github.com/HighCWu/linux-wasm-builder/actions/runs/39893540026
[process-vm32]: https://github.com/HighCWu/distro/actions/runs/39893965748
[process-vm64]: https://github.com/HighCWu/distro/actions/runs/39893971173
[process-vm-poll-prefetch]: https://github.com/HighCWu/linux-wasm-builder/actions/runs/39894992836
[process-vm-poll32]: https://github.com/HighCWu/distro/actions/runs/39896332106
[process-vm-poll64]: https://github.com/HighCWu/distro/actions/runs/39896336670

### 第三十六组：既有 Wasm break 算术与增长兼容修复

musl `bf26831e` / distro `11ee975` / 集成 `3979c20` 修正原 Wasm brk/sbrk
实现。直接基线上已有这两个函数及 Wasm 内存增长代码，本轮只修改该架构分支，
无新增函数、公共头文件、声明或执行 import；非 Wasm 分支不变。内核 SYS_brk
仍未实现，不计为新增 raw syscall，也不把单调 allocator 说成支持缩小 break。

修正两类边界：先拒绝负 sbrk 增量和正增量地址溢出，再计算新指针；以页面数量
比较容量，避免 wasm32 的4 GiB字节末端回绕为零，同时避免舍入加法溢出。
查询使用当前已提交容量，失败不改 current，所有返回路径仍释放同一互斥锁。
不绕过已有 malloc/mmap 共用堆策略，不更改 CONFIG_MMU=n 或直接内存上限。

Clang18/22 对实际函数体的双位宽小型 Wasm 执行与分析通过，测试替换的只有
memory.size/grow 和互斥/errno 支撑，用模型验证容量边界，不分配数 GiB内存。
原 `e12bb18e` 源码对照分别复现负增量错误和 wasm32 满容量查询错误；高位数值
模型不代表真实宿主能承载相应内存。另已分析实际 SDK 负载及可选 fork 补丁
dry-run，新增独立测试和文档 MIT，沿用 musl 本身的 MIT 许可。

真实 Wasm 驱动只运行于隔离目标，不在宿主原生 libc 上修改 break。三阶段检查：
既有查询/负增量拒绝不改状态；普通64 KiB增长后与 malloc、匿名 mmap 字节独立；
释放库分配、再次分配后，主动保留的 break 字节仍完好。模型证明的4 GiB边界
不由这个小内存负载冒充验收。

[源码预取][brk-prefetch] 已核实精确修订和 unpacked hash。默认 SDK 的
[wasm32][brk32]、[wasm64][brk64] 均已成功，实际日志逐项核实全部三阶段、
各自唯一 pass 及不变运行器的关闭门禁。
这两项不覆盖所有依赖包、浏览器或多线程压力，已有 process_vm 任务不取消或重派。

[brk-prefetch]: https://github.com/HighCWu/linux-wasm-builder/actions/runs/39897485596
[brk32]: https://github.com/HighCWu/distro/actions/runs/39897700718
[brk64]: https://github.com/HighCWu/distro/actions/runs/39897705996

### 第三十七组：文件复制的可见 SIGKILL 取消点

Linux `50abafbb5` / distro `aed297b` / 集成 `a9638e9` 修正已有候选共用
复制路径：原 kernel_read 完整返回后会无条件进入用户初始化器，即使当前任务
已有可见的 SIGKILL。现在每次 VFS 读取前和完整读取后、初始化前检查
fatal_signal_pending，返回 EINTR 并走原 staging/预算清理。不在 kernel_read
仍执行时释放其目标缓冲，不把取消请求当成生产者已完成。

这是特定取消点的改进，不是把最终检查和未来信号入队做成原子事务。检查之后才
到来的信号仍有窗口；不能宣称任意时刻取消、全部用户分配器重入或真实块设备
在途 I/O 生命周期已解决。默认文件映射开关、来源政策、大小预算和执行 ABI 不变。
没有新增应用接口、libc 函数或 softmmu；内核实现保留 GPL。

原默认关闭私有测试内核增加 mode6 受控 VFS 生产者：entered 后用不可中断
completion 等待 controller，SIGKILL 不能自行结束读取。测试内核专有统计
selector0x100 只计初始化回调尝试，不能被 caller 重置；生产内核不编译该计数。
原无效 selector4 保持拒绝。这些均不加入 Linux 公共 UAPI 或 SDK 头文件。

扩展既有 vfs-exit 目标，每轮保留两种可中断读取，并加入不可中断生产者，共八轮：

- 等 entered 且请求、staging、来源各一份，向独立线程组的共享 mm 子任务发送
  SIGKILL；WNOHANG 必须表明它尚未退出，资源和初始化尝试计数保持原值。
- 显式 PROCEED 后 VFS 返回完整数据，子任务按 SIGKILL 退出，不回到用户回调，
  初始化器尝试计数仍不变；不得先取消生产者就假报安全回收。
- 来源 fd 位置、父映射内容不变，原来源再读取和新请求恢复，最终请求/staging/
  来源及预算回到基线；每轮单独输出完成标记，拒绝旧请求迟到返回。

GCC/Clang 原样候选 C 的宿主模型、分别绕过读取前/发布前检查的失败对照、真实
函数体模型分析及双位宽 controller 前端/分析通过。模型覆盖初始可见 SIGKILL、
短读后和完整读取后取消，不证明 Linux 调度或真实 VFS。构建候选或私有测试内核
均会运行相同模型；新 controller、检查与文档 MIT。

[源码预取][fatal-mmap-prefetch] 已核实精确修订和 hash。
review 又发现原稳定屏障资源查询只在零请求时检查预算；distro `d372d68` /
集成 `bf3073b` 补充 SIGKILL 排队后明确检查仍预留恰好双份页长度，不能只从
请求/staging 数量推导预算保留。此前 aed297b 的
[wasm32][fatal-mmap-initial32]、[wasm64][fatal-mmap-initial64] 不覆盖这条断言，
保留运行、不取消；`d372d68` 的 [wasm32][fatal-mmap-budget32]、
[wasm64][fatal-mmap-budget64] 已派发，但不作为后续构建修正版本的验收。

aed297b 的 wasm32 实际日志明确失败于 Nix 内核构建沙盒：
`python3: command not found`，退出127，尚未执行目标程序，不是 fatal 断言失败。
原因是把模型检查扩展到 mmapCopyTest 后，Python 依赖仍只受 fileMmapCandidate
控制。distro `2784222` / 集成 `df70a39` 用同一 copyHostChecks 条件控制
依赖和构建步骤，保留默认不检查配置的最小依赖；没有更改内核、运行断言或来源 hash。
静态配方约束和 Nix 语法/格式检查通过，不代替真实构建闭包或运行证据。

修正版 [wasm32][fatal-mmap32]、[wasm64][fatal-mmap64] 均已通过，实际日志逐项
核实生产者保留阶段、各八轮完成标记、无初始化回调/恢复阶段、各自唯一 pass。
两项 Heavy 作业均成功，未变的 runner 仍在成功返回前等待 machine.closed，
没有 runner cleanup failed 或 Kernel panic；这是该版本的有界验收。
该目标使用真实 Linux 受控 inode 和共用 VFS 路径，不是 EROFS/virtio 实际设备
在途压力，也不单独满足默认文件 mmap 的全部生产准入门槛。

[fatal-mmap-prefetch]: https://github.com/HighCWu/linux-wasm-builder/actions/runs/39898917489
[fatal-mmap-initial32]: https://github.com/HighCWu/distro/actions/runs/39899413464
[fatal-mmap-initial64]: https://github.com/HighCWu/distro/actions/runs/39899419274
[fatal-mmap-budget32]: https://github.com/HighCWu/distro/actions/runs/39899822579
[fatal-mmap-budget64]: https://github.com/HighCWu/distro/actions/runs/39899830583
[fatal-mmap32]: https://github.com/HighCWu/distro/actions/runs/39900385267
[fatal-mmap64]: https://github.com/HighCWu/distro/actions/runs/39900390783

## 第三十八组：文件初始化异常的内核所有权候选

Linux `48adb6d39` / distro `d36fbc4` / 集成 `3325f9b` 修复上轮小型复现
确认的 C 清理旁路。共用复制函数现在消耗
调用者传入的一个文件引用；标准入口和私有 VFS 调用者都不再在它返回后重复 fput。
只在 kernel_read 已结束、即将调用用户初始化器时建立任务所有的堆记录，持有
staging、文件引用和预算。普通返回释放该记录；执行桥撤销租约后，在重抛原异常前
调用内部 abort_file_mmap_v1 export。该 export 不是用户 import、Linux syscall
或公共应用 API，亦不把异常转成 errno。内核异常不被重新分类为用户分配失败。

初始化器若调用 exit，exit_thread 在交出 CPU 前释放记录；JS 遇 HALT_KERNEL
不再进入已死亡任务的内核实例。fork 创建任务时清空此所有权链，不复制父记录。
记录不在被跳过的 C 栈上；SjLj/exec 非局部退出后也不会留下悬空栈指针。
读取中的生产者不挂入链，退出钩子不能据此提前回收其仍可写入的缓冲区。

本地 Clang18/22、wasm32/64 对实际共用函数与 JS 桥的小型模块均确认 trap 后
资源归零、原异常传播和恢复请求；旁路 abort 的对照仍泄漏，随后退出钩子可清理。
GCC/Clang 的普通/失败返回模型、记录分配失败、致命取消点反向控制及静态分析通过；
两项 TS 工程检查和345项 kernel 宿主检查通过。它们不代替完整内核运行证据。

新增默认关闭测试配置中的独立 vfs-callback 目标：实际初始化器 trap 子任务必须
按 SIGSEGV 退出；嵌套 SYS_exit 必须保留73退出码，两类各四轮；父端确认未正常
返回、资源归零、关闭最后 fd 后来源释放，并能再次读取。另在父任务中从初始化器
siglongjmp 到原 catchpad，检查37返回值及后续映射恢复；重入文件复制须返回
EBUSY，不得撤销外层所有权或阻止外层完成复制。仅测试内替换可选初始化
archive member，不修改 musl 或新增公共函数。目标已集成，尚待 CI 验收；
exec、真实设备在途压力、用户分配器损坏恢复及默认 SDK 准入仍不在已验证范围内。

源码 hash 由[公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39902572370)
核实；途中429由原任务自行重试成功，没有重复派发。已集成并派发同源码的
[wasm32 callback](https://github.com/HighCWu/distro/actions/runs/39902993436)、
[wasm64 callback](https://github.com/HighCWu/distro/actions/runs/39902998433)，以及
[wasm32 取消点回归](https://github.com/HighCWu/distro/actions/runs/39903003400)、
[wasm64 取消点回归](https://github.com/HighCWu/distro/actions/runs/39903008720)。
四项均已成功结束，实际日志已逐项核实：双位宽 callback 各有 trap/exit、SjLj
恢复、嵌套 EBUSY 三阶段及唯一 pass；取消点回归各有保留阶段、八轮独立完成标记、
恢复与唯一 pass。四项通过既有 runner 等待 machine.closed 的门禁，且无关闭错误
或 kernel panic。这是 d36fbc4 的 Node 有界验收，不扩大为浏览器、exec、真实
设备压力或默认文件 mmap 放行，也不能由较早版本的成功代替。

## 第三十九组：匿名 PROT_READ 数据请求

Linux `f45a2bd47` / distro `7a1e3ad` / 集成 `0f41180` 接通原先被 Wasm
wrapper 硬拒绝的匿名 PROT_READ 请求。对照
通用 mm/nommu.c 的 validate_mmap_request 匿名复制路径及 NOMMU mmap 文档，
这类请求不要求 PROT_WRITE；不能把没有逐页写保护误写成必须拒绝只读数据请求。
标准请求仍为 MAP_PRIVATE|MAP_ANONYMOUS，零填充、直接可读、独立分配；不提供
违规写入 fault 保证。PROT_NONE、仅 WRITE、包含 EXEC 或未知保护位继续拒绝。
文件映射默认开关、MAP_SHARED、mprotect 和任意固定地址政策不改变。

现有 musl 的内部 v2 allocator 已能承接该请求，无需更改 musl、添加函数或头文件。
执行桥对 v2 原样保留 prot；对旧 length-only allocator 的回退也允许 READ 数据
请求，但仍不允许它处理 fixed。NOREPLACE、受限 FIXED 的原保留区规则保持不变。

既有默认内核 mmap 正确性程序增加 libc/raw 两条 READ 路径，核对页对齐和零填充，
再执行标准 msync、MADV_DONTNEED、mremap 增长及部分 munmap；测试不违规写入
READ 映射，也不把可读误记为硬件写保护。GCC/Clang 对实际内核 wrapper 验证参数
保留和拒绝边界，恢复旧 RW-only 条件的对照必须在 READ 成功断言失败。
双位宽目标前端/静态分析、源和测试 TS 项目及347项 kernel 宿主检查通过。
这些不是完整内核运行证据；源码 hash 经
[公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39903686392)
核实，新双位宽默认正确性目标已集成。
本轮 [wasm32](https://github.com/HighCWu/distro/actions/runs/39904062932)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39904072165) 不运行文件 mmap
候选配置，现均成功。实际日志核实新增 anonymous READ 阶段、原完整正确性程序
末尾的各自唯一 pass；成功返回仍以 runner 等待 machine.closed 为前提。
这是 7a1e3ad 的 Node 双位宽结果，不是浏览器或写保护证明，也不以文件 READ 替代。

## 第四十组：嵌套 signal handler 的局部 SjLj 收尾

Linux `8ec99f62d` / distro `6ae2ac5` / 集成 `44bcf55` 修正信号回调结束时的
元数据恢复。此前 clear_siginfo 无条件
清空 active frame/info；若内层 siglongjmp 只跳回仍在执行的外层 handler，外层
restorer 随后就找不到自己的 frame，finish 返回 EINVAL，可能触发错误 SIGSEGV。
这不同于此前从最外层 handler 一次跳回普通程序的语料，后者本来就应清空全部层。

每个内部 C frame 现在保存前一层 frame/info，JS 每结束一个回调只退一层。正常
C 返回的原恢复路径保持幂等；异常仍到原 compiler catchpad，不转换为 errno。
链指针不复制到公共 ucontext；stack/mask 用户布局、syscall 号和 musl 均不改变。
handler 内 SYS_exit 则在 exit_thread 清空元数据，JS 看到 HALT_KERNEL 不再调用
任何 C 清理函数，避免在交出 CPU 后通过失效实例访问任务状态。

新 signal-nested-jump 语料用普通和 SA_SIGINFO 内层 handler 各跳转八轮，落点在
外层 handler 内；外层正常返回并通过 uc_sigmask 修改 SIGWINCH，主程序验证修改
及 USR1/USR2 掩码恢复。另创建共享 mm、独立线程组的子任务，分别从普通/siginfo
handler 用标准 SYS_exit 退出，核对79/80退出码、回收及父进程后续投递。
只用现有公开接口，不扩大私有 fork 或多线程 fork 能力。

GCC/Clang 的原生信号语料与 UBSan 通过；实际内核 clear/copy/finish helper 的
宿主 uaccess 模型及 ASan/UBSan 通过，恢复旧清空行为的对照在外层 frame 断言失败。
双位宽 Wasm 前端/分析、两个 TS 工程和348项 kernel 宿主检查通过。这些不证明
Wasm 内核信号投递、任务 CPU 所有权或浏览器结果；新目标及既有 altstack 回归
已集成并派发真实目标验收，默认 SDK 与 CONFIG_MMU=n 保持不变。源码 hash 由
[公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39905286954)
核实；不把较早的普通 signal-altstack 通过记录当作本次内层局部跳转的证据。
本轮新语料的 [wasm32](https://github.com/HighCWu/distro/actions/runs/39905810842)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39905816629)，以及原 altstack 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39905822360)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39905827167) 均固定同一源码。
新语料须核实两个完整阶段、唯一 pass 与关闭；回归须核实原五阶段与关闭。

6ae2ac5 的两项新语料任务随后均失败，不能记录为完整验收。wasm32 实际日志
先通过局部 SjLj 阶段，再报 `Attempted to kill init! exitcode=0x00004f00`。
检查 musl 的 raise 和 clone 调用路径确认：CLONE_VM 未设置新 TLS 时，子任务
继承 libc 的父 TID 缓存，测试中的 raise 把退出信号发给了控制任务。79正是
测试 handler 的退出码。这是错误的测试投递身份，不需要新增或修改 libc API。
wasm64 实际日志随后也已核实：同样先过局部 SjLj 阶段，再以 init 退出79 panic。
两个局部阶段通过不等于包含子任务退出的完整新语料已验收。

distro `a1e4bd4` / 集成 `1212b62` 将子任务投递改为标准 gettid/tkill 的机器字
调用；handler 若发现自己仍是控制任务则拒绝退出，waitpid 对 EINTR 重试并回收。
GCC/Clang 正向原生执行通过，故意发给控制任务的反向语料须以 handler=8 失败，
不得杀掉 runner 或出现 pass。未改内核或 musl，不放宽 fork/TLS 支持。
针对失败项派发 [wasm32](https://github.com/HighCWu/distro/actions/runs/39908584489)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39908589716) 复验，仍待完整阶段
和关闭证据。原 altstack 两项日志现已核实各自完整五阶段、唯一 pass 与等待
machine.closed 的关闭门禁，没有重复派发；只记录该版本的 Node 回归通过。

## 第四十一组：shared memory 扩容后的用户复制边界

distro `1a903a2` / 集成 `9a27f54` 修正执行层检查过期 shared-memory wrapper
长度的问题。此前普通复制、清零和 futex word 可在另一个 isolate 已完成 grow 后
仍按旧长度返回短复制/EFAULT；单次 Worker 启动刷新不足以处理后续扩容。
新逻辑仅在请求超出当前 shared view 时执行一次同位宽 grow(0)，再重新检查，
不分配、不改变实际容量，不把越界地址变合法。零长度、NULL、真正越界及刷新失败
继续走已有 residue/错误政策；在视图内的调用不额外刷新。

覆盖用户复制/清零、原子 word、kernel 旧值回写及 exec chunk 的 kernel 源视图。
没有声称审完所有 host import，未修改 Linux、musl、执行 ABI 或任何应用 API。
实际旧版 6ae2ac5 的复制函数在双位宽受控旧视图中复现错误短复制及缺失 atomic
word；新实现的复制、清零、原子和 exec 模型通过，且断言刷新只用相应类型的零。
这是旧视图模型，不证明当前所有浏览器都会出现该现象。

新 shared-user-growth 目标由 pthread 在两次握手后各执行真实 memory.grow(1)。
主线程在首个新页通过标准 pipe write/read 检查数据，第二个新页通过标准
FUTEX_WAKE_OP 检查原子更新，之后通知线程退出并 join。两页只是测试期间暂用的
raw capacity，不宣称建立了 mmap 登记；握手期间不让线程析构/用户分配器复用它们。
双位宽前端/分析、两个 TS 工程及352项 kernel 宿主检查通过，不作为目标验收。

同源 a1e4bd4 的 [wasm32](https://github.com/HighCWu/distro/actions/runs/39908596295)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39908603494) 已派发，须核实
两个完整阶段、唯一 pass 和机器关闭。尚未派发浏览器目标，不把 Node 或模型当作
Chromium/Firefox 运行证明；原有内存上限及 CONFIG_MMU=n 不变。

a1e4bd4 的上述四项任务后来均失败。已读取 wasm32 信号与增长两项实际日志，
共同失败于 toolchain-smoke 程序集合构建：shared-user-growth.c 的 `test.h` 找不到。
Nix 插值单个 C 文件后源目录不再含相邻头文件，而本地直接编译原路径未暴露此点。
这两项尚未运行目标程序，不能当作新的信号或复制运行失败。wasm64 两项的实际
日志随后也均核实为相同 `test.h` 缺失；四项都停在共用程序集合构建，未执行目标。

distro `a576e9f` / 集成 `01dc041` 在该编译命令中显式加入现有测试头文件目录，
不复制新实现或改 libc。轻量回归现在将相同 C 文件移到没有相邻头文件的临时目录，
先确认缺少 include 路径确实失败，再用配方的显式目录完成双位宽前端与分析；
同时约束 Nix 配方包含该输入。实际 Nix 构建与目标复验仍待 CI，不凭本地补丁放行。

## 第四十二组：内核 Worker 名称与诊断导入的 direct 指针

distro `86b775a` / 集成 `94e8cfe` 将内核 boot console、Worker 名称及 trace 输出
统一到受检的 kernel byte view。Worker/console 指针原先按非负 JS 地址解析，会
在访问 buffer 之前拒绝合法的 wasm32 高半区位模式；直接构造视图也遗漏了此前
shared grow 后的刷新。新逻辑按原始指针位宽解码，必要时只做零增量刷新，然后
校验完整区间，不截断或局部发布 kernel 数据。console/名称仍在同步边界复制，
不把 C 栈缓冲区借给异步 Worker。trace 的截断与 NUL 收尾保持不变。

这些是可信内核指针，不是应用提供的虚拟地址；真正不可用的范围仍抛 kernel/host
错误，不伪装成应用 errno。没有改 Linux、musl、导入签名或公开应用接口。
实际旧版 a1e4bd4 的 kernel_imports 已在受控旧视图与高半区输入上复现两类错误；
新双位宽模型通过，还确认刷新失败不调用 host 消费者、不改坏数据。高半区检查
仅证明进入 buffer 访问前正确解码，没有分配 GiB 内存，不是实际高地址复制证明。
两个 TS 工程、355项 kernel 宿主检查及格式检查通过，仍不代替浏览器或内核目标。

包含头文件输入修正的 a576e9f 已统一派发：

- 嵌套信号复验：[wasm32](https://github.com/HighCWu/distro/actions/runs/39910385000)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/39910394654)。
- 共享增长：[wasm32](https://github.com/HighCWu/distro/actions/runs/39910400296)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/39910405285)。
- 既有诊断/Worker 回归：[wasm32](https://github.com/HighCWu/distro/actions/runs/39910411455)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/39910419541)。

六项工作流与 Heavy 均已成功结束，但验收另按实际日志记录：共享增长双位宽各有
两个完整阶段；stacktrace 双位宽各有三个完整阶段；signal-nested 的 wasm32
有两个完整阶段。上述五项各有唯一 pass，未见 panic 或 runner cleanup failed，
成功返回还受既有 runner 等待 machine.closed 的门禁约束。wasm64 信号日志下载
曾以 unexpected EOF 终止；重取后已确认同样的两个完整阶段与唯一 pass，六项现均
具备实际阶段与关闭门禁证据，不仅凭工作流状态补作验收。
诊断回归仅证明普通运行范围，不能替代真实高 kernel 地址分配、所有 import 审计
或浏览器旧视图压力验证。

## 第四十三组：clone 入口的元数据所有权

Linux `f7626f432` 将 clone_fn 的两个标量先复制到局部变量，再释放该记录，最后
调用 user.switch_entry 执行桥。后者在 continuation 验证/恢复中可以非局部退出；
旧顺序把 kfree 放在桥之后，会在这种异常下跳过释放。桥只接收 fn/arg 数值，
不需要保留原记录。正常 callback 的非法函数表项检查发生在后续 user.call，
不能误把它描述成这里新修复的 Linux 错误返回路径。

不改变 clone 参数、task 创建/失败处理或 fork 支持范围。这里提前释放的只是
clone_fn，不是仍可能被异步 Worker 读取的 task_bootstrap_args；后者的 abort/
ack 等待屏障保持不变。原始异常继续传播，没有转换成 errno 或新增恢复承诺。

实际函数体在 Clang18/22 的 wasm32/64 小模块中验证：释放会覆盖原字段，但桥
仍收到完整 fn/arg 位模式；正常返回、桥抛 RuntimeError 和后续恢复调用都只释放
一次。把释放移回桥之后的对照必须失败。高位值仅验证数值传递，不调用真实高位
函数表项；临时模块包含 GPL 内核实现，不是 MIT 用户 SDK 构件或 Linux slab 证明。

同时修正根仓库 fork-abort 宿主模型：先前加入实际 mmap 退出钩子与 signal
元数据清理后，模型缺少相应桩/字段，root CI
[39910385115](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39910385115)
已实际失败于该模型编译，而不是 Worker 运行。修正 `2f59fbc` 保留 mmap 资源
语义由独立模型负责，只观察退出钩子调用及 metadata 清理；GCC/Clang sanitizer、
早/晚 Worker ack、移除等待的失败对照与最终共享访问 codegen 再次通过。
不以宿主桩代替真实 mmap 退出或完整 clone 验收。包含本修复的后继内核 b8eafea09
已由 distro `ac84a1c` / 根仓库 pin `c98b13f` 集成。双位宽 Node fork/pthread
回归现已核实完整原阶段、唯一 pass 与关闭门禁；不把正常回归说成新增的完整
Linux 非局部异常注入验收，异常释放顺序的证据仍限于前述实际函数小模块。

首次[公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39912187207)
虽显示 success，实际日志却是下载反复429并最终失败，没有 hash。旧工作流的
管道未启用 pipefail，tee 掩盖 nix 的错误，摘要中的 jq 错误也未中止任务。
根仓库 `216fb59` 改为 codeload、严格 shell 失败传播和 SHA256 SRI 字符串校验；
实际 shell 的正常 JSON、缺失/错误 hash、下载失败即使输出合法 JSON、非法源码
标识四类轻量检查通过。不使用失败下载产生的空值更新 pin，也不把该假绿记为
源码 hash 验收；修正后的[新任务](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39914413999)
固定同一 f7626f432；它仍较慢时不取消。后继 b8eafea09 的独立预取已取得实际
hash，直接集成包含两项修复的完整版本，避免为中间版本重复重型构建。

## 第四十四组：vmsplice 的用户线性内存复制路径

Linux `b8eafea09` 为 CONFIG_WASM 单独实现 iter_to_pipe：用户偏移通过现有
copy_page_from_iter/uaccess 复制到内核分配页，只有实际复制的长度进入 pipe。
原因是通用实现走 iov_iter_get_pages2/GUP；NOMMU GUP 查 VMA 后用用户地址
计算内核 struct page，不能将分离的 Wasm 用户线性内存按此方式固定。不仅因
syscall 表存在就声称可用，也不把源代码核查写成已在完整旧内核复现故障。

外层 vmsplice 的 iovec 导入、管道锁、阻塞/信号等待、唤醒、通知及反向复制不变；
非 Wasm 构建仍使用原路径。每轮至多复制一内核页，管道满时不再读取用户数据。
初始 fault/分配失败返回错误；已发布前缀优先返回长度；add_to_pipe 失败由原函数
释放页，并撤回尚未发布的迭代器进度。沿用 pipe 页引用与 GIFT 标志，允许复制的
内核页继续走已有 tee/splice/steal 规则，不承诺用户页别名、零拷贝或性能收益。
未改 musl、syscall 号、公共 API、MMU 配置或 fork 支持范围。

本地实际 helper 的 GCC/Clang18/22 ASan/UBSan 检查覆盖多页数据、独立副本、短
复制、零复制 fault、分配失败与部分成功、管道满不读用户数据、插入失败和后续恢复；
删除迭代器回滚的对照必须失败。该模型替代页/uaccess/pipe 原语，不证明实际 VFS。
新标准 syscall 语料在原生 Linux 通过三阶段及唯一 pass，Wasm 双位宽前端与分析
通过：vectored vmsplice、tee、pipe-to-pipe splice、反向 vmsplice、容量与 EAGAIN、
GIFT、参数错误、Wasm 实际内存外范围及前缀、EPIPE 与失败后恢复。Wasm 专有越界
分支未在原生执行；完整内核构建、目标阶段及关闭仍待异步验收。

最终源码 hash 已在[公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39914590414)
实际日志中核实为 b8eafea09 和对应 SRI 值，不只看状态。distro `ac84a1c` 增加
独立 vmsplice 目标并更新 kernel pin，根仓库 `c98b13f` 单独更新 gitlink 与模型
门禁；musl 仍为 bf26831，源码仓库各自保留独立提交，没有删除或重写历史。
同一 ac84a1c 已派发：

- fork/pthread 回归：[wasm32](https://github.com/HighCWu/distro/actions/runs/39914957554)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/39914965093)。
- vmsplice 新目标：[wasm32](https://github.com/HighCWu/distro/actions/runs/39914973931)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/39914982260)。

新目标必须核实三个完整阶段、唯一 pass 以及既有 runner 的机器关闭门禁；fork
回归需核实原有完整语料与关闭。未派发浏览器，不把宿主 sanitizer 或 Node 状态
泛化为浏览器、零拷贝、所有页固定调用者或完整 syscall 兼容性验收。

ac84a1c 的 vmsplice 双位宽任务现均成功，实际日志已分别核实上述三个完整阶段
及各自唯一 pass，无 panic 或关闭错误，且既有 runner 成功返回须等待
machine.closed。这是 b8eafea09 内核的 Node 验收。同版本 fork 双位宽实际日志
也已核实：raw clone/clone3、PID/TLS/atfork/memory/fd/nested wait、信号隔离、
失败 exec 恢复、默认 libc helper 的 exec 三阶段、exec 后 wait、多线程拒绝和
恢复、旧/新 clone import 共存及 signal callback 拒绝恢复，各自唯一 pass 与
关闭门禁均满足。四项只记录该版本的 Node 结果，不据此放行后继 futex 或浏览器。

## 第四十五组：独立线性内存的 futex key 隔离

Linux `7141e252e` 修正通用 NOMMU 对单一地址空间的假设：原 get_futex_key 在
无 MMU 时将 private.mm 清为 NULL，仅用地址及页内偏移区分队列。Wasm 的不同
进程却有独立线性内存，相同数值偏移不代表同一 futex；必须保留 current->mm。
新条件仅增加 CONFIG_WASM，传统 NOMMU 和 MMU 分支保持原行为。CLONE_VM
线程仍有相同 mm，因此继续匹配，而普通 fork 的不同 mm 不再因偏移相同碰撞。
这是既有标准 syscall 的隔离修复，不是新增 libc 包装或项目专有接口。

NOMMU 的 FLAGS_SHARED 仍为零，普通 futex 与 PRIVATE 模式均走地址 key 路径；
不捏造文件页 key，不启用跨进程共享映射或 SysV SHM，不宣称实现新的进程共享
backing。内存边界、原子操作和 CONFIG_MMU=n 保持原策略，musl pin 仍为 bf26831。

实际 key 选择分支在 Clang18/22 的 wasm32/64 小模块通过：相同 mm/地址匹配、
不同 mm 的同地址不匹配、不同地址不匹配，并保留高位偏移。恢复旧条件的对照
实际重新得到跨 mm 碰撞；传统 NOMMU 与 MMU 配置各自结果不变。这些只检查
key 选择，不是 hash、调度或完整 syscall 的 Wasm 验收。

独立可选 fork profile 目标分别检查 PRIVATE 与普通模式：父子在相同静态偏移
保有独立数据；子进程线程通过 WAIT 入队，以非 PI 同 key CMP_REQUEUE 的计数
确认已排队后才通知父进程。父进程重复 WAKE 必须为零，子进程本地 WAKE 必须为
一，随后 join、退出42并被父回收；父进程也执行同 mm 线程唤醒正向控制。
所有 fork 均在父线程控制之前完成，避免将 join 后最后 mm 引用释放的窗口误作
受支持的多线程 fork，不修改内核的 mm_users 拒绝规则。

初稿把等待者移到另一个地址后假定它一直留在那里；原生未跟踪运行曾失败，实际
补充 WAKE 观察到等待者回到原 key，而跟踪运行通过。通用 __futex_wait 明确允许
spurious wake 后重新从原 uaddr 入队，因此该假设不可用于测试门禁。修正版只用
合法的非 PI 同 key 计数，不改变等待地址；GCC sanitizer 连续八轮、最终 GCC/
Clang 各三轮及双位宽前端/静态分析通过。未用延时掩盖初稿失败或改内核适配错误测试。

源码 hash 已在[公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39916242109)
实际日志核实；distro `d0da6c4` / 根仓库 `a15dd3a` 集成，再由 distro `977bf49`
/ 根仓库 `d9c0da2` 单独固定 fork-before-thread 测试顺序。源码及 pin 均已推送，
没有改写历史。独立目标已派发
[wasm32](https://github.com/HighCWu/distro/actions/runs/39917071562)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39917078967)，须核实两个完整
阶段、唯一 pass 和机器关闭；它们仍待目标验收，不把原生或小模块检查说成完成。

977bf49 的两项 Node 目标现均成功。实际日志已逐位宽核实 PRIVATE 和普通模式
两个完整阶段及唯一 pass，没有 panic 或 runner cleanup failed；固定版本的
runner 在 closeTestResources 中等待 machine.closed，关闭失败不得返回成功。
因此记录 7141e252e 内核的双位宽 futex 有界隔离验收，不扩大为跨进程共享 backing、
PI/全部 futex 操作、浏览器或尚未集成的后继内核验收。

## 第四十六组：跨页的远程机器字访问

Linux `d25423a8f` 修正 wasm_access_remote_vm 将有效请求截到单页末端的问题。
generic_ptrace_peekdata/pokedata 每次必须复制完整 sizeof(long)，而该桥在地址
位于页末一个字节时只传一个字节，导致即使相邻内存有效也返回 EIO。线性内存
复制并不需要逐页固定，因此改为限制 payload 至多 PAGE_SIZE，而不是限制地址
的页内剩余容量；同时按 TASK_SIZE 剩余范围截出有效前缀，先排除起址越界与负长度。
没有增加单次预算或更改 mailbox 的发布/认领/取消/DONE 生命周期、权限检查、
syscall 号、musl 和 MMU 策略。真正的内存末端短复制仍由现有 uaccess residue
处理，不把无效地址变成有效地址。

实际 admission 前缀的 Clang18/22 小 Wasm 模块在双位宽验证完整跨页机器字、
至多一页的 payload、高位偏移、TASK_SIZE 末端前缀、零/负长度及越界；重新加入
旧页切割的对照确实只剩一字节。这不运行 mailbox 或目标 ptrace，也不声称能
识别调用者已经在 wasm32 参数转换中丢掉的第33位。
既有 ptrace 程序增加对齐的两页静态缓冲区，在页末一字节处执行非对齐 PEEK/
POKE，再核对 child 恢复后读到完整新值、两侧邻接字节及 parent 原副本未变。
原生 GCC/Clang sanitizer、无真实写入/错误信号掩码的原反向控制，以及双位宽
前端/分析通过；独立源码的预取曾失败，现已随包含该修复的后继 22cdbc317 集成，
见下一组的实际 hash/pin 记录。仍待跨页目标验收，不计本地检查为 Wasm 通过。

同轮处理已明确失败的根仓库 CI：
[c98b13f](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39914944033) 与
[d9c0da2](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39917065833)
实际日志均在 GitHub API 取源码时遇429及 base64 错误；
[a15dd3a](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39916952481)
则在原 semaphore 的两个下载来源均失败后退出，日志没有保留 HTTP 码，不能也
断言为同一429。这些是输入下载失败，不是目标内核运行错误。
`673b5ef` 让主要轻量源码读取复用已有 raw-first 安全 fallback，`99f1fd4` 再加
最多三轮及5/15秒间隔的瞬态失败重试；每次保持同一完整 commit 和相对路径，
认证仅发往 GitHub API，禁止重定向转发认证、不改用分支/本地代码。非法路径、
404等永久错误不继续重试。下载器的纯本地检查通过，修复后的 CI 仍需异步复验。
raw-first 的首项 [673b5ef CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39918322464)
实际仍失败于两个来源均不可用，而非模型断言；有界重试版本的
[99f1fd4 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39918516394)
后来在更靠后的 syscall_wrapper.h / sigcontext.h 步骤再次实际遇429；主要检查
步骤已完成，但还漏改了这两个直连 API 的读取点。`1eaab01` 补齐，并新增覆盖整个
工作流的直接 contents API 管道检查；现12项下载器检查通过。不把上一次局部替换
描述为完整恢复，不用输入下载失败倒推 syscall 实现回归。
[1eaab01 复验](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39919698368)
现已成功结束，记录轻量 CI 恢复，不代替任何尚未运行的 Wasm 目标阶段。

d25423a8f 的首次预取现已明确失败：实际日志为 codeload 反复429，没有 hash。
`79795f2` 使预取与构建下载器一样保留同 commit 的 codeload/archive 两端点，
每端点通过 Nix 的 download-attempts 限为两次；仍须成功解包并校验 SHA256 SRI。
该设置语义核对了 [Nix 官方说明](https://nix.dev/manual/nix/2.34/command-ref/conf-file.html#conf-download-attempts)。
真实 shell 的原有失败/非法 hash 门禁与同 revision 回退检查共五项通过。只在原
任务终态且读取错误后派发[同源码新预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39920679240)，
不取消慢任务，不接受缺失 hash，不改用本地推算值。
该新任务现也已终态失败，实际日志确认两端点各两次均429，没有有效 hash，故没有
更新 pin 或派发跨页目标；没有立即重复请求同一受限下载。其后继续完成独立的
socket 修复，并取得包含两项增量的后继源码 hash，现已集成，详见下一组。
79795f2 的轻量 CI 本身已成功，不将其误写为旧源码预取成功。

## 第四十七组：socket MSG_ZEROCOPY 的标准复制回退

Linux `22cdbc317` 为 Wasm 的 TCP 及 IPv4/IPv6 UDP 用户迭代器选择已有复制路径，
而不是尝试将用户线性内存偏移固定为内核 struct page。MSG_ZEROCOPY 是可退回
复制的 Linux 提示，但仍须提供完成通知；原网络代码已具有复制及 COPIED 通知
逻辑，本次只修正可固定页的选择条件，不自建通知或伪造零拷贝。保留 SO_ZEROCOPY、
资源限制、错误收尾、发送序号和原引用释放路径，不承诺零拷贝或性能收益。

条件只限制 CONFIG_WASM 的 user_backed_iter；内核迭代器、非 Wasm 构建和
MSG_SPLICE_PAGES 路径不变。datagram 的非 ip_generic_getfrag 回调不一定接收
msghdr，选择条件短路后不得读取该未知类型，不能在所有回调前盲目解引用 from。
未改 syscall 号、musl、公共头文件或执行 ABI，CONFIG_MMU=n 和 fork 范围不变。
Linux 内修改保留 GPL；新独立验证程序及模型为 MIT，不把内核实现链接进用户 SDK。

实际选择表达式在 GCC/Clang18/22 sanitizer 模型中通过用户/内核迭代器、非 Wasm
及不同 getfrag 来源检查；强制允许用户固定、移除回调类型保护的对照须失败。
该模型不执行真实网络发送或通知。标准 socket 程序另检查 IPv4/IPv6 的 TCP/UDP：
每种组合连续两次 sendmsg 散集发送16KiB二进制数据，核对错误队列 origin、COPIED
标志、完整 cmsg 和准确的0/1发送序号；先等通知，覆盖原发送缓冲区，再让接收端
读出并与独立期望数据比较。之后普通发送不得生成零拷贝通知，所有 fd 必须关闭。

原生 GCC/Clang ASan/UBSan 的完整四阶段通过；篡改复制标志或发送序号均必须失败，
不得出现最终 pass。Wasm 双位宽前端及静态分析通过。测试只在 Wasm 隔离机器上
拉起 loopback，不改宿主网络；使用已有 libc 接口，错误队列结构只在测试内按
标准 Linux wire format 声明。旧 libc 的 CMSG_NXTHDR 宏存在 signedness 警告，
仅在测试私有 helper 中局部屏蔽该宏诊断，不改 musl 或全局关闭代码警告。

新源码已推送，包含第四十六组跨页修复。
[22cdbc317 公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39922877966)
实际日志已核实完整 revision 及对应 SHA256 SRI，不只看状态。distro `9bb1bb3`
加入独立 socket 目标，`f4da7a8` 固定新内核，根仓库 `e7759e2` 单独更新两个
gitlink 和轻量门禁；musl 仍是 bf26831，没有更改历史。未拿新 hash 冒充失败的
d25423a8f archive hash，而是完整构建、验证明确包含两项修复的后继版本。

同一 f4da7a8 已派发：

- ptrace 跨页：[wasm32](https://github.com/HighCWu/distro/actions/runs/39923928508)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/39923937955)。
- socket 复制通知：[wasm32](https://github.com/HighCWu/distro/actions/runs/39923948685)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/39923958794)。

四个任务的 Heavy 均成功，实际日志已逐项核实各自四阶段和唯一 pass。ptrace
两路均包含非对齐跨页机器字、邻接字节与子进程观察；socket 两路均包含 IPv4/IPv6
的 TCP/UDP 复制完成通知与缓冲区复用。固定 f4da7a8 的 runner 必须等待
`machine.closed`，关闭失败会使任务失败，本组均通过该门禁。由此接受这两组
有界 Node 目标，不把宿主程序或选择表达式模型当成 Wasm 执行。
尚未派发浏览器或外部网络目标，也不扩大为
RDS、DMA、io_uring、所有零拷贝接口、全部 cmsg 组合或真实页固定支持。

## 第四十八组：恢复标准 namespace 配置与无 vDSO 的时间偏移冻结

官方 Linux 的 `NAMESPACES` 默认值是 `!EXPERT`，而 Wasm defconfig 开启了
`EXPERT`，此前因此间接关闭了 UTS、IPC、PID、网络和时间 namespace。
这些能力并不要求 MMU。本组在三个 Wasm defconfig 显式开启 `NAMESPACES`，
其子项继续按官方 Kconfig 默认条件选择；`USER_NS` 仍默认关闭，`CONFIG_MMU=n`
不变。mount namespace 机制原本已存在，不将它描述成全新 syscall 实现。

静态 review 同时发现：当前 `timens_commit` 在无 `TIME_NS_VDSO` 时为空，
偏移冻结仅发生在 VVAR 初始化路径。不能只打开配置就声称完整支持。
Linux `57b4cb94f55bd05b93866396d85b8460b1a7cdf4` 为无 vDSO 路径补上
同一个 `timens_offset_lock` 保护的冻结操作，已有 setns 和 fork 提交点均复用
该函数；有 vDSO 路径及不启用 TIME_NS 的空实现保持不变。

distro `4db9ae7` 加入独立 `fork-continuation-check-namespaces` 和 wasm64
对应检查，使用标准 libc 已有接口，不修改 musl。六个阶段覆盖：

- UTS 标识与 hostname 隔离、setns 恢复及错误恢复。
- mount namespace 的 ramfs 可见性、重新进入与卸载清理。
- SysV 消息队列隔离、独立消息及对象清理。
- network namespace 的相同 UDP 地址独立绑定，以及 socket fd 保留所属网络。
- monotonic 与 raw clock 的偏移、realtime 不受影响、首次加入后禁止写偏移及恢复。
- NEWPID 只影响后续子进程、子 PID 为1/不可见父 PID、普通 fork/wait 与单次回收。

测试仅在隔离 Wasm 机器执行，明确禁止宿主原生构建，避免改动宿主 namespace。
双位宽 Clang 18/22 前端与静态分析通过；提取实际冻结函数体的 GCC/Clang
轻量模型通过，恢复不冻结行为的反向控制必须失败。这不是目标内核运行证据。
未新增 clone flags 支持、未扩大多线程 fork，也不声明已支持完整容器环境。

源码已分别推送；新内核的公开 hash 预取为
[39928710790](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39928710790)。
实际日志已核实完整 revision 与
`sha256-sgBMvc8ToYbcAQFI5yLKNw6kEn10bEJeLYNphNdzq90=`。distro `02bf190`
固定该版本，并对解析后的 Kconfig 检查六个 namespace 配置开启、USER_NS 关闭、
MMU 未启用；根仓库 `65d6dc1` 单独更新 gitlink 与轻量门禁。当时 musl pin 保持
bf26831，未修改或重写历史。目标运行结果另记，不能把预取或配置检查当作验收。
后续须核实六阶段、唯一 pass 与机器关闭。
已对同一 02bf190 异步派发
[wasm32](https://github.com/HighCWu/distro/actions/runs/39929257117) 与
[wasm64](https://github.com/HighCWu/distro/actions/runs/39929264789)，尚待实际目标结果。

两项后续均失败。实际日志确认前四阶段已完成，并通过首次加入后写偏移返回
EACCES 的冻结检查，随后失败于测试的错误假设：Linux 也会给
CLOCK_MONOTONIC_RAW 加 monotonic namespace 偏移（见该版本
kernel/time/posix-timers.c 的 posix_get_monotonic_raw），并非内核漏加偏移。
distro `3bc3ba5` 修正为 MONOTONIC/RAW 相对 REALTIME 都平移，再验证两者恢复；
未通过修改 Linux 的标准时钟行为来迎合测试。原失败任务不作为完整六阶段验收。

## 第四十九组：现有 BusyBox nsenter 的真实工具接入

distro `674242a` / 集成 `ca474b4` 在双位宽 BusyBox 配方开启原有 `NSENTER`，
并检查 oldconfig 后该项仍为 y。固定源码、默认 libc 和 ABI 均不变，未给工具
增加应用补丁。固定源码的 PID 选项本身已有 callback child/wait 路径，本组
不将它写成已迁移至普通双返回 fork，也不扩大 fork 支持范围。

审查同时确认固定 BusyBox 的 `UNSHARE` 仍有 `depends on !NOMMU`，所以没有
强行写入一个会被 oldconfig 丢弃的 y，更没有关闭 NOMMU 来满足工具条件。
独立 MIT 测试 helper 只调用标准 `unshare`、`sethostname` 和管道文件操作，
创建 UTS/IPC/network 目标并用 FIFO 明确通知就绪。它只进入测试镜像，不安装
进 BusyBox 生产包；原生构建明确报错，不能借轻量检查修改宿主 namespace。

`busybox-check-namespaces` 及 wasm64 对应目标执行真实 `nsenter` applet，要求：

- 进入目标三类 namespace 后 exec shell，读取的 namespace 身份及 hostname
  与目标相同，与父进程不同；父进程保持原 namespace。
- 使用 PID 选项走已有子进程管理路径，继承目标 UTS，并准确传回退出码42。
  此处目标仍在原 PID namespace，不把它冒充新 PID namespace 的运行证据。
- 普通文件被 setns 拒绝，之后仍可进入并 exec；释放并回收 holder，清理文件
  和 proc 挂载，输出三个完整阶段、唯一 pass，再由 runner 完成机器关闭。

双位宽 Clang 18/22 前端、静态分析、Shell 语法、格式、原有 source-bundle
宿主回归及根仓库元数据检查通过；没有本地执行 namespace 操作。实际目标为
[wasm32](https://github.com/HighCWu/distro/actions/runs/39930804736) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39930813043)，均固定
674242a，异步验收中；不把配置或前端通过当成实际工具运行通过。
第四十八组原有两个 C 目标继续运行，不重复派发、不取消慢任务。

后续两项 BusyBox 目标均在 treefmt/ShellCheck 阶段失败，尚未执行 applet。
wasm32 的实际日志确认是两个 sh -c 单引号脚本的 SC2016 提示；变量有意在
setns 后的子 shell 展开，不能改为父 shell 预先展开。distro `41e7245` 仅在
这两个命令加局部注释，完整 ShellCheck 0.11 检查通过，不全局关闭诊断。
修正后与新 musl 一同复验；原失败不能记为 namespace syscall 运行失败或通过。

## 第五十组：clone 栈/TLS 初始化后的应用入口检查点

审查发现 arch/wasm/kernel/process.c 在内核启动回调准备后直接调用 user.call，
没有原生 ret_from_fork 的通用 syscall 返回工作。任意 callback 若先写内存再
直接 exit，就可能在 ptrace newborn stop 前进入应用代码。直接在这一位置调用
完整 signal 返回处理也不安全：Wasm libc clone_entry 此时还没设置 C 栈/TLS。

musl `09a90c1a` 仅修改既有 Wasm clone_entry_inner：栈/TLS 准备后、应用 callback
前调用标准 SYS_gettid，让当前 Linux syscall 返回路径完成待处理工作。不新增
公共函数、包装或执行接口，也不修改其它架构或重写历史。该选择补齐的是 libc
clone 的应用 callback 边界，不声称任意原始 Wasm callback、第一条 VM 指令、
上下文追踪 CPU 记账或未来 seccomp filter 已获得相同保证。

新增 ptrace-entry 工作负载先 TRACEME，再以标准 clone 的 CLONE_VM|SIGCHLD
创建有独立退出身份、共享 marker 的子进程；没有 CLONE_THREAD 或扩大私有
多线程 fork。tracer 要求 fork event、准确的 newborn PID 和初始停止，读取共享
marker 仍为0，再投递 SIGTERM，要求应用 callback 第一条 store 永不执行。
真实父进程必须观察一致终止状态并回收；tracer 明确转发 SIGCHLD 的 signal stop，
最后普通 fork/wait 恢复、单次回收，共三个阶段及唯一 pass。

GCC/Clang 原生三阶段通过；故意跳过 birth stop 的控制必须失败。Clang 18/22
双位宽前端和静态分析通过，实际 trampoline 函数体的小型 Wasm 模型核对检查点
在 callback 之前，移除 gettid 后 pending-fatal 情况确实执行了错误的 callback。
这些都不是实际 Wasm 目标通过证据。可选 fork patch 已针对新 musl 做 dry-run，
未增改其公共声明。源码预取
[39932927721](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39932927721)
日志已核实完整 revision 与 SRI。distro `898e2e4` 固定新 libc 并加入独立目标，
`41e7245` 补上述脚本诊断；根仓库 `83432e4` 单独更新 pin 与轻量门禁。

以下均固定 41e7245，异步运行，不重复派发：

| 目标 | wasm32 | wasm64 |
| --- | --- | --- |
| ptrace-entry 三阶段 | [39933848569][entry32] | [39933857702][entry64] |
| 修正后的 namespace 六阶段 | [39933866168][namespace32] | [39933875691][namespace64] |
| BusyBox nsenter 三阶段 | [39933884669][nsenter32] | [39933893413][nsenter64] |
| 默认 C runtime 线程/TLS 回归 | [39933904341][clone-c32] | [39933912004][clone-c64] |

[entry32]: https://github.com/HighCWu/distro/actions/runs/39933848569
[entry64]: https://github.com/HighCWu/distro/actions/runs/39933857702
[namespace32]: https://github.com/HighCWu/distro/actions/runs/39933866168
[namespace64]: https://github.com/HighCWu/distro/actions/runs/39933875691
[nsenter32]: https://github.com/HighCWu/distro/actions/runs/39933884669
[nsenter64]: https://github.com/HighCWu/distro/actions/runs/39933893413
[clone-c32]: https://github.com/HighCWu/distro/actions/runs/39933904341
[clone-c64]: https://github.com/HighCWu/distro/actions/runs/39933912004

新目标必须读取实际阶段和最终 pass，并核实关闭门禁。旧 namespace 四阶段不能
替代修正后的完整六阶段，旧格式失败也不能代替 nsenter 工具运行结果。

上述八项现均成功，已读取每个 Heavy 的实际日志：namespace 两路完整六阶段、
nsenter 两路三阶段、ptrace-entry 两路三阶段及各自唯一 pass 均齐全。默认 C runtime
两路的唯一 pass 位于全部断言之后，已核对对应源码必须完成 pthread 创建/回收、
TLS 隔离、信号、匿名内存和文件系统检查后才能输出它。固定 41e7245 的 runner
等待 machine.closed，并把关闭错误计入非零退出；八项均通过该关闭门禁。
因此接受这些有界 Node 目标，尚未扩大到浏览器、任意 raw callback 或多线程 fork。

## 第五十一组：PI futex 无效线性地址的 NOMMU 错误恢复

静态审查追到一条不同于原 WAKE_OP 的可达路径：PI LOCK/TRYLOCK 的用户原子
访问返回 EFAULT 后，pi.c 的 uaddr_faulted 会调用 fault_in_user_writeable；后者
无条件调用 fixup_user_fault，而当前通用 NOMMU stub 内是 BUG。Wasm 的用户
内存独立于内核，即使 offset 小于 TASK_SIZE，也可能是 NULL 或超出当前容量，
不能因 NOMMU 就假设原子访问不会失败。原 WAKE_OP 的错误路径已有 !MMU
提前返回，不能用此前它的 NULL 检查证明 PI 路径安全。

Linux `ed725e29cf6f82a21c1da5ff24fac2bbc3f4a5a9` 在实际 repair helper 内仅为
CONFIG_WASM 返回 EFAULT，不试图补内核页表；其它架构/MMU 的锁、修复和结果
处理不变。没有禁用 PI futex、吞掉错误或把所有有效操作也改为 EFAULT。

distro `e7746d4` 扩展现有 user-access 目标：普通/private 两模式下分别验证
LOCK_PI、TRYLOCK_PI、LOCK_PI2 对 NULL 和当前线性容量外 offset 的 EFAULT；
随后用有效字验证 owner TID、自身重复获取的 EDEADLK、unlock/trylock/lock2
及最终释放。新增第四阶段；原部分复制、文件位置/pipe 前缀和恢复阶段仍保留。
Clang22 分析还要求将原测试的失败分支明确标为 noreturn，避免把失败后无限等待
误认为可能返回并继续使用无效 fd/地址；没有屏蔽分析器错误。

原生 GCC/Clang 工作负载和伪造 PI 成功的负向控制通过。Clang18/22 双位宽
前端、静态分析以及提取实际 helper 函数体的小型 Wasm 执行通过；恢复原函数体
会进入模拟通用 NOMMU stub 的 trap，而新 Wasm 分支不取锁、不调用 repair。
非 Wasm/MMU 的原锁/返回分支保持，非 Wasm/NOMMU 的原行为也不被模型偷偷改变。
这不是实际旧内核 panic 注入或新内核通过证明，目标需核实四阶段、唯一 pass 与关闭。

源码已分别推送，公开内核 hash 预取
[39952334659](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39952334659)
实际失败于两个下载入口的 HTTP 429；两路均已按既有有界次数尝试，未取得 SRI。
当时未为缺少 hash 的源码更新集成 pin 或派发重型目标，也未立即重复派发同一预取。
模型及 CI 接线保留到新源码 pin 可核实后一同集成，当时默认 CI 未对旧 pin 运行
要求新分支的模型。下述 Git 等价实验通过后才完成集成，不将源码推送冒充目标通过。

同轮轻量 CI
[39933625633](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39933625633)
的实际日志显示旧 IPC 取样脚本直接调用 Contents API，在首个 ipcbuf.h 下载时
遭 HTTP 429，未运行 IPC 语料。根仓库 `ec7f0b0` 将其迁移到共同的固定 SHA
下载器：raw 无认证优先、同一版本 API 后备、无跨域认证转发、有界瞬态重试；
七个输入全部获取成功后才发布文件，失败不混合新旧头文件。三项 wrapper 检查
及共同下载器十二项检查通过，未放宽 source pin 或把网络失败记为 syscall 失败。

### Git 取源的独立哈希等价性实验

预取限流后没有猜测 SRI 或放宽固定输出校验。根仓库 `65bda90` 加入独立脚本，
`030bf14` 将它作为既有 prefetch-source workflow 的显式可选模式，以便在当前
开发分支 dispatch；未修改默认分支。普通不带 baseline 参数的 archive 路径不变。
`16b623c` 补齐不完整/错误模式必须失败、不能回落到 archive 假成功的检查。

本实验仅用于本次 Linux futex 单文件修复，不作为任意仓库通用 fallback：

1. 只从 HighCWu/linux 获取精确 SHA 的 depth-two Git pack；核对 FETCH_HEAD 与
   唯一直接父提交。禁止 moving branch 和本地未经验证的源码替代。
2. 只允许 kernel/futex/core.c 内容变化；拒绝其它文件、文件模式及归档属性变化，
   并拒绝 export-subst 或属性检查失败，以免提交/ref 展开改变归档字节。
3. 先归档基线 57b4cb94f，以实际 nix hash path 对比该版本已独立取得的
   `sha256-sgBMvc8ToYbcAQFI5yLKNw6kEn10bEJeLYNphNdzq90=`。
   不相等就失败，不计算/发布候选 hash。
4. 仅基线等价通过后归档 ed725e29c 并计算候选 SRI；实际构建仍必须由正常源码
   fetcher 做固定输出校验，不将 Git 方法当作绕过校验的许可。

本地只执行小型 Git/tar/Nix 命令 stub 的流程测试，覆盖错误身份、父提交、路径、
模式、属性、baseline hash、archive/hash 命令失败和非法候选 SRI；未下载或展开
Linux，也不能以 stub 证明 NAR 等价。ShellCheck、shfmt、actionlint 和原预取
路径控制通过。公开实验
[39954310300](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39954310300)
已派发，实验启动时 pin 未变，没有预先声称 PI 修复已集成。

该实验随后成功。已读取实际日志，核实完整 baseline/candidate revision，基线
NAR SRI 与上面的独立 archive SRI 完全相同，候选实际计算结果为
`sha256-p3GPsfG8h/Ye1Op6D0gR0uaVn7hnVRMDNbQToiDcZP4=`，与基线不同。
这证明该受限变更的 Git 取源计算通过了基线门禁；并非放宽固定输出检查。
普通 fetcher 构建时仍须用此 SRI 核实新 archive，若不一致必须失败。

distro `d7089fc` 固定 ed725e29c 和此 SRI；根仓库 `3e84e06` 单独更新 Linux/distro
gitlink，将 `check_futex_fault.py` 和现有的精确源码下载接入轻量 CI。musl 仍为
09a90c1a，没有再次变更。额外加入“有内容变更但候选 hash 等于基线也必须拒绝”
的门禁及负向控制 b3bb030；实际候选值已独立核实为不同，未为该小门禁重派大取源。
目标运行结果另记，不能把 hash 获取成功当作 PI syscall 已运行通过。
已对固定 d7089fc 派发 user-access
[wasm32](https://github.com/HighCWu/distro/actions/runs/39955080607) 与
[wasm64](https://github.com/HighCWu/distro/actions/runs/39955087526)，要求完整四阶段、
唯一 pass 和机器关闭。两路实际日志现均已核实四阶段与唯一 pass，任务通过现有
机器关闭门禁，接受此有界 Node 结果。没有为此次修复再次要求大内存 upper32
目标，也没有派发整个旧矩阵或性能任务。

## 第五十二组：用户分配器重入时保留外层 syscall 状态

直接分配路径会回调用户分配器；分配器在互斥锁竞争等情况下又可能调用 Linux。
嵌套调用复用同一 task_pt_regs，原 dispatcher 只写回外层返回值，外层退出时的
syscall 编号、六个参数、用户 C 栈和模式仍可能属于内层。这不是 libc 包装缺口：
它影响 ptrace 退出观察、信号栈选择及 syscall restart 的实际执行状态。

Linux `4074db5aa1bdb0bc7c80fdd23acd802dab22e4d3` 在 entry/ptrace 修改完成后、
执行 handler 前保存寄存器帧，正常返回后恢复该帧并单独写入结果。任务信号掩码、
restart_block 等其它状态不回滚；退出信号处理与重启仍走原 Linux 路径。非局部
退出不登记持久快照，不留下堆对象或悬空注册项。

嵌套退出还会关闭 IRQ，故仅恢复寄存器不够。内核新增私有执行导出
callback_irq_save_v1 / callback_irq_restore_v1，固定 i32 标志 ABI；执行层只在
嵌套入口且两个导出均存在时保存/恢复调用者 IRQ，在返回活的分配器前完成恢复。
HALT_KERNEL 后不得再进入 C；异常路径恢复线性 C 栈并保持异常传播。旧内核缺少
导出对时保留旧行为，不宣称获得新保证。这不是公开应用 API，也不表示已完善
CPU accounting、vtime、抢占或多线程 fork。

distro `188ff21` 实现桥接与独立目标 syscall-reentry。测试通过链接期包裹现有
pthread_mutex_lock，在真实 mmap/munmap 分配器回调内发起 getpid；Wasm 必须实际
观察至少两次嵌套调用，否则失败。父端使用标准 ptrace 和 /proc/PID/syscall，
逐层核对退出编号、全部六个参数及 C 栈；再核对映射数据、释放和子进程回收。
650b70c 另修正原生诊断失败清理：仅对仍可 wait 的自有 tracee 发信号，避免已回收
PID 的复用风险；Wasm 路径不受此原生清理调整影响。

轻量验证包括完整宿主测试 361 项、源/测试两套 TypeScript 检查、Clang 18/22
双位宽前端与静态分析。实际 dispatcher 与 IRQ 导出的小型 Wasm 模型覆盖嵌套、
ptrace 参数修改、带符号结果、重启目标及旧实现负向控制；原生参考另独立破坏
编号、参数、SP 验证拒绝。原生 mmap 不经过 Wasm 用户分配器，不能替代真实嵌套
目标；异常/IRQ 模型也不等于全部目标压力验收。

普通源码预取 [39960080381](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39960080381)
实际日志核实完整 revision 及 SRI
`sha256-TIVj77Fp9i5Eo3IB45ZVxbfsGC/hpRoO+Eb7Z8m7SGw=`。
distro `227d54e` 固定该源码，根仓库 `b594462` 单独更新 gitlink 并接入轻量模型。
musl 仍为 09a90c1a，没有新增函数、头文件 API 或包装。双位宽真实重入、信号栈及
fork/exec 回归异步派发，实际阶段和关闭结果待核实，不以本地验证或取源成功代替。

固定 227d54e 的派发记录：重入
[wasm32](https://github.com/HighCWu/distro/actions/runs/39961744403)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39961754938)；信号栈
[wasm32](https://github.com/HighCWu/distro/actions/runs/39961766108)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39961775132)；fork/exec
[wasm32](https://github.com/HighCWu/distro/actions/runs/39961785386)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39961797715)。

其中 wasm64 重入任务 39961754938 已失败；实际 Heavy 日志确认，固定 Linux
4074db5aa 的 codeload/archive 两个入口均连续 HTTP 429，source derivation 无法
构建，未运行目标程序。这不是 syscall 断言或 hash mismatch；其余活任务不取消、
不重复派发。根仓库 b594462 的轻量 CI 39961751947 已成功，仍不替代目标验收。

## 第五十三组：读取 cpuinfo 不等待正在计算的其它 CPU

Linux `7258cf2c632190dc4fe9b2541b0fa2a0b521cc39` 修复 proc 读取的架构阻塞路径。
原 c_show 通过同步 smp_call_function_single 在每个在线 CPU 上执行 seq_printf，
却只读取 smp_processor_id。Wasm CPU 正在执行不进入内核的用户代码时，无法
服务该 IPI；读取方会等待与输出内容无关的远端执行。现由读取线程直接遍历在线
CPU 编号，输出格式与编号顺序不变，不读远端局部状态、不新增锁或远端请求。
这修复普通 read(/proc/cpuinfo) 的可用性，不表示新增抢占或支持全部 SMP 场景。

distro `2422afa` 增加独立双 CPU 目标：将读取线程与计算线程固定在不同 CPU，
计算线程发布 ready 后只执行原子循环，不调用 Linux；读取方完整读取三轮 CPU
记录，核对两颗 CPU 均出现且无重复，然后释放/回收线程、恢复 affinity 并再次
读取。仅在 Wasm 测试机挂载 proc，原生参考不修改宿主挂载。与 fork 无关，使用
默认 SDK 的既有 pthread/affinity/read 接口，musl 没有变更。

GCC/Clang 原生程序、真实 formatter 的稀疏在线编号模型及旧同步 IPI 负向控制
通过；Clang 18/22 的 wasm32/64 前端和静态分析通过。模型里的远端 IPI 被受控
拒绝，不伪称本地重现了真实 Wasm 死锁；原生测试也不能证明协作式 Worker 行为。
源码已原子提交推送；公开源码预取
[39963218440](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39963218440)
现已成功。实际日志核实完整 revision 及 unpacked SRI
`sha256-zNz3opyVl76ZYIA9mrNbP/24k9rtbPgVJhzNQdGVVjo=`，未使用猜测或移动 ref。
distro `5c11fb4` 固定源码与 hash；根仓库 `bd021e7` 单独更新 Linux/distro
gitlink 并接入精确源码模型。两路 cpuinfo 目标异步派发，尚待真实阶段与关闭验收。
已结束于下载429的 wasm64 重入目标也对该后继源码定向重试；该源码保留此前全部
重入修复，没有改写 IRQ/寄存器实现来处理取源失败，其余活任务不重复派发。
本次固定 5c11fb4 的目标：cpuinfo
[wasm32](https://github.com/HighCWu/distro/actions/runs/39964338534)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39964348105)；重入
[wasm64](https://github.com/HighCWu/distro/actions/runs/39964358354)。

两路 cpuinfo 的 Heavy 实际日志现已补核实：各包含三轮无 syscall 计算线程
运行期间的完整读取阶段、线程释放/affinity 恢复/再次读取阶段，以及唯一
`::vm-test::pass`。固定 5c11fb4 运行器在退出成功前等待 `machine.closed`，
关闭错误使任务失败，两路均通过该门禁。因此接受双位宽、双 CPU 的有界 Node
回归，不泛化为浏览器、异步抢占或任意 SMP 操作。

上一批固定 227d54e 的 wasm32 信号栈任务 39961766108 已成功，实际日志逐项
核实注册/错误、siginfo 嵌套、autodisarm、反复 SjLj、context 编辑/清理五阶段及
唯一 pass；固定运行器关闭失败会使任务失败，关闭门禁通过。这只是该双位宽矩阵
中的一路 Node 回归，不泛化为其余重入、fork/exec 或浏览器目标已验收。

同一 227d54e 的 wasm64 信号栈 39961775132 也已读取实际日志，五阶段和唯一 pass
齐全，关闭门禁通过。wasm32 fork/exec 39961785386 的实际日志已核实 raw clone、
clone3、信号隔离、continuation/继承、失败 exec 恢复、未变换程序拒绝、成功 exec、
多线程/信号回调拒绝及后续恢复全部既有阶段和唯一 pass；关闭门禁通过。仍不据此
宣称专门的 syscall-reentry 目标或 wasm64 fork/exec 已验收。

## 第五十四组：Wasm 轻量分配器的可恢复耗尽

静态 review 发现，tombl/musl 既有 lite_malloc.c 在 Wasm 无法通过 sbrk 增长时
直接 a_crash。其它平台可回退到 mmap，但 Wasm mmap 与此处共用分配路径，不能
递归照搬。这是已有架构实现中的错误收尾，不是缺少一个 libc 公共函数；也不能
把修正该路径说成增加了内核 SYS_brk。

musl `b1c51ef9096167aacf5bcccc22a0684146937392` 只将该 Wasm trap 分支改为释放
原锁、设置 ENOMEM 并返回 NULL。非 Wasm fallback、函数/头文件集合与分配政策
不变；没有新增包装、公共声明或辅助执行入口，没有改写历史。正常启动所需的
不可恢复 TLS 分配仍由启动代码决定，不把该局部修复推广为所有 OOM 都能恢复。

实际源文件的小型 wasm32/64 模型由 Clang 18/22 编译执行，覆盖首次/后续增长
失败、锁释放、break 不变、剩余尾部保留、后续增长、过大请求和原栈交叉保护。
恢复旧 trap 分支的控制在同一调用处触发 RuntimeError 并保留锁，不能假通过。
源文件与目标程序的双位宽前端/静态分析均通过；模型使用假的容量，不申请巨大
内存，也不是默认 libc 链接选择或真实内核的验收证明。

distro `75cad05` 发布 lite-oom 独立目标：链接期对既有 sbrk 做受控失败注入，
通过已有 malloc/getcwd/write 验证错误、恢复和已分配内容。构建要求链接 map
选中 lite_malloc.o 且未选中完整 malloc.o，防止由 mallocng 的类似错误路径代跑。
故障包装只在该测试程序，未加入 libc 或应用 SDK。源码 hash 预取后另行集成，
真实双位宽阶段和关闭结果尚未验收。

公开预取 [39965887373](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39965887373)
实际日志现已核实完整 b1c51ef9 revision 及 SRI
`sha256-z0dhmwlHMueAb/V8grw4q5gzUFhPyPwPRqoSLjuMa/Q=`。
distro `db46ac8` 固定该源码，根仓库 `d61efcd` 单独更新 musl/distro gitlink 和
轻量模型门禁，Linux 仍为 7258cf2c6。可选 fork 补丁对新基线 dry-run 通过。
双位宽 lite-oom 与默认 C runtime 回归异步派发，真实阶段/关闭结果待验收；
未新增 syscall、公共函数、头文件 API 或通用包装，也未改写已发布历史。
固定 db46ac8 的真实目标：lite-oom
[wasm32](https://github.com/HighCWu/distro/actions/runs/39966367935)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39966378171)；默认 C runtime
[wasm32](https://github.com/HighCWu/distro/actions/runs/39966388876)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39966402001)。

### 链接选择失败后的修正

这批四路工作流均失败，不能列为目标验收通过。已读取 wasm32 lite-oom
39966367935 和 wasm64 C runtime 39966402001 的实际 Heavy 日志：链接 map 同时
包含 lite_malloc.o 的公共转发入口和 malloc.o 的真正 __libc_malloc_impl，门禁
正确拒绝了由 mallocng 代跑。此前关于该程序能保留默认 lite backend 的推断不
成立；不能把 lite 源码修复泛化为默认 mallocng 的错误修复，也不能靠移除门禁
冒充验收成功。由于旧诊断被放在公共 programs 构建中，它也阻断了 C runtime
目标的构建，未到程序运行阶段。

distro `93255d5` 将 lite-oom 移到独立 derivation，普通 programs 不再构建该诊断。
独立目标从同一固定 musl.src 的 lite_malloc.c 编译测试专用命名空间对象，不改
源文件正文，不替换 SDK 默认分配器，也不安装任何新函数或头文件。符号检查要求
该对象定义自己的 weak backend、不得引用正常 malloc/calloc/realloc/free
backend；链接 map 必须选中该对象的私有入口。目标程序明确调用这个仅测试用的
入口，再通过已有 getcwd/write 验证恢复。它是对既有轻量实现的隔离验证，不是
默认 mallocng 的行为证明。

本地 Clang18/22 双位宽实际源文件、私有命名空间对象、符号与 map 门禁以及旧 trap
控制均通过；追加构建隔离检查，防止诊断再次耦合普通程序。根仓库 `4479e10`
单独更新 distro pin 和验证脚本；Linux 91ab8b356、musl b1c51ef9 没有再改动。
双位宽诊断和默认 C runtime 分别定向复验，仍需实际阶段及关闭结果。
固定 93255d5：lite-oom
[wasm32](https://github.com/HighCWu/distro/actions/runs/39970507248)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39970515370)；普通 C runtime
[wasm32](https://github.com/HighCWu/distro/actions/runs/39970524942)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39970532018)。
后继 distro `7c3699f` / 根仓库 `75b0232` 为新 musl 源依赖显式补上 wasm64
scope 覆盖；当前两位宽 .src 固定同一 b1c51ef9，未修改编译源或执行逻辑，未重复
派发活任务。结构检查保证将来 scope 覆盖也保持匹配；上述目标仍按其实际 93255d5
源码记账，不将后继提交偷换成已验收版本。

固定 93255d5 的四路现均完成。两路 lite-oom 实际日志逐项核实首次/后续增长
错误、锁与内容恢复，以及 getcwd/write 两阶段和唯一 pass；普通 C runtime
两路各自唯一 pass 也已核实，其断言均位于该 marker 之前。已复查固定运行器
确实 await machine.closed，关闭失败会使目标失败；四路关闭门禁通过。接受
有界 Node 回归：lite 结果仅针对隔离的固定源码对象，不证明默认 mallocng OOM
或浏览器大内存行为。

## 第五十五组：独立 syscall-info 能力与标准 ptrace 编辑

先前 227d54e 的 wasm32 重入任务 39961744403 已失败。实际日志报
`syscall-info wire size errno=5`，不是下载故障。审查确认内核未选择
HAVE_ARCH_TRACEHOOK，通用 PTRACE_GET_SYSCALL_INFO 分支根本未构建，请求返回
EIO；/proc/PID/syscall 及其 task_current_syscall 实现也被同一门控排除。
不能通过放宽 wire-size 断言宣称重入验收通过。

Linux `91ab8b356c3bfc052d9d64a7fe9f5158728da8df` 增加内核内部能力选项
HAVE_ARCH_SYSCALL_INFO，已有 HAVE_ARCH_TRACEHOOK 架构默认保持开启；Wasm 单独
选择该能力。通用 GET/SET_SYSCALL_INFO、proc syscall 文件与收集器改由它控制；
GET/SETREGSET 与 task_user_regset_view 仍只受原 tracehook 条件控制，不为 Wasm
虚构完整 regset ABI。原有未定义 audit 架构编号仍为0，不发明新编号或 syscall。

Wasm 为通用 SET 实现补齐现有 pt_regs 的编号/参数访问器。dispatcher 在 entry
工作前初始化 ENOSYS，entry 返回 -1 时不执行 handler，也不覆盖 tracer 留下的
返回值；其它非法编号仍返回 ENOSYS。外层重入帧保存和 IRQ 桥接保持原设计。
这修复了真实标准 syscall 能力，而不是新增 libc 包装；musl 本增量不变。

distro `e1047c4` 扩展原重入目标，使用完整88字节标准 syscall-info 结构：让
getpgid 被改为 getpid、getsid 被跳过，再在 exit stop 把 ENOSYS 改为42，子程序
必须实际收到对应结果。跳过状态的 proc 文件按标准短记录核对；其它状态仍
核对全部六参数、编号和 C 栈。Wasm 新增编辑阶段，原生参考保留旧两阶段，不把
宿主对较新 SET 请求的支持作为本机验证前提。

Clang18/22 的 wasm32/64 模型执行实际通用 GET/SET helper、真实 UAPI 布局及
Wasm 访问器，覆盖读写、编号/参数范围、错误结果、保留位、长度、坏地址及不匹配
stop 类型；源文件和目标前端/静态分析通过。真实源文件预处理检查覆盖无能力、
原 tracehook 架构和仅 syscall-info 架构，确认没有连带启用 regset。dispatcher
模型另验证 tracer 自定义返回值在 skip 路径保留、无 handler/nested 调用。
这些不替代实际 Wasm ptrace 阶段或完整 Linux 构建。

源码已原子提交推送；精确预取
[39968495583](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39968495583)
已派发，待取得 SRI 后单独更新 pin 并定向复验。旧 5c11fb4 的 wasm64 重入任务
39964358354 不包含本修复，不能据其结果宣称 syscall-info 新能力已通过。

精确预取现已成功，实际日志核实完整 91ab8b356 revision 和 SRI
`sha256-jHrNPU4788e7llT9h7HKgwKxWoTN0baDBIveJkC7sl4=`。distro `2243541` /
根仓库 `c60ec83` 已独立集成，并将配置/通用 helper 模型接入固定源码轻量检查。
该修订的重入目标
[wasm32](https://github.com/HighCWu/distro/actions/runs/39969281730)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/39969292353)
已派发；这次要求新增编辑阶段、原两阶段、唯一 pass 与机器关闭，不据旧版本
结果替代本次验收。旧 5c11fb4 的 wasm64 重入实际日志也已取回，确认相同的
syscall-info EIO，而非下载错误；新修复针对两位宽共同门控问题。

两路固定 2243541 现已成功，实际日志均逐项核实完整三阶段：标准 entry 重定向/
skip/exit 编辑；嵌套回调后的编号、六参数与 C 栈；实际分配器重入、mmap/munmap
及 tracee 回收。各自唯一 pass 和固定运行器的机器关闭门禁通过。接受 Linux
91ab8b356 的双位宽 Node syscall-info/重入能力，不扩大到完整 regset、未知
audit 架构编号、任意异步抢占、浏览器或多线程 fork。

## 第五十六组：内核栈辅助判定的算术修正

独立架构 review 发现两个确定的算术错误。on_thread_stack 原先计算
`base - SP`，栈内正偏移转换成 unsigned 后反而被拒绝，紧邻 base 之前的地址
却可能被接受。Linux `67a716797895a8ac7078754c7f041c8bc27280a4` 改为以机器字
无符号数计算 `SP - base < THREAD_SIZE`，保持基址包含、顶端不包含的分配区间。
同一架构的 THREAD_SHIFT 原为 `PAGE_SHIFT << THREAD_SIZE_ORDER`；64 KiB 页面、
order1 的128 KiB栈应是 shift17，而不是32，现改为相加。

这不是新增 syscall 或内核栈 ABI，也不修改分配大小、保存布局或用户栈策略。
当前默认 Wasm 没有启用会使用 on_thread_stack 的调试/擦栈路径，THREAD_SHIFT
也未被当前通用 kernel/include 路径消费。不能把这项修正写成已重现普通程序
崩溃，或宣称已启用 x86 的 DEBUG_ENTRY、Wasm 栈擦除/抢占支持。

独立 MIT 模型读取真实宏，由 Clang18/22 编译为 wasm32/64 后执行：核对栈内、
恰好边界、前后栈外、32位高半区和64位4 GiB以上地址；分别恢复旧区间方向、旧
shift 的控制检出各自错误。新 shift/size 恒等式在 C 编译期断言，Clang 分析通过。
地址仅作为标量模型，不申请大内存，不替代完整内核调试配置的运行验收。

源码已原子提交推送；精确预取
[39973059533](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39973059533)
已派发，后续独立更新 pin。预取启动时主仓库仍固定 91ab8b356；未提前把新源码计入
已经运行的 syscall-info、诊断或普通程序目标。

该预取随后成功，实际日志已核实完整 revision 和 SRI
`sha256-FpW4srxMEa7ZxpPtc6f0GYG7J66ywQ8uj6D7KiXsJwE=`；distro `5839a9e` /
根仓库 `a87f595` 单独完成 pin 和精确宏检查集成。上述已验收任务仍按原 Linux
91ab8b356 记账，不作为新源码或未启用调试配置的运行证明。

## 第五十七组：匿名 mmap 的 offset 入口兼容

Linux `3e2199eca60d5436bd32f40e47fe7e299632c1d0` 修正另一个真实 syscall 限制：
原 Wasm 入口把所有非零匿名 offset 拒绝为 EINVAL。官方 Linux 的匿名映射不
使用文件来源 offset，但入口仍检查 ABI 对齐；现 wasm64 mmap 按64 KiB页面
检查字节 offset，wasm32 mmap2 按固定4096字节单位检查16单位对齐。合格请求
才将匿名 fd/offset 归一为 -1/0，再调用既有分配器；不新增执行导出或更改 musl。

实验文件映射在归一化之前继续走原文件 helper，原始 offset、范围、来源、EOF
规则不变；默认文件映射拒绝也不放开。MAP_FIXED/NOREPLACE、保护位、地址上限
及其它现有准入规则保持，不引入 MMU、共享 backing 或任意地址映射。

distro `2180b2a` 更新既有 offsets 目标，不另造同类程序。它区分 libc 字节
offset 与 raw ABI 单位，验证合格匿名 offset（含高位）得到独立零初始化 backing，
无效对齐/无法表达的 libc offset 仍拒绝，文件请求仍拒绝且文件位置和活映射
不变；成功对象均释放。offset 数值不是内存大小，不分配大文件或大内存。

GCC/Clang 的真实 Linux 参考、小型 Wasm 中的原样内核 mmap 入口、Clang18/22
双位宽前端/分析通过。模型覆盖文件能力开/关、对齐、最大对齐 raw offset、
固定/NOREPLACE、旧拒绝分支控制和原文件 delegation；这些不替代实际 Wasm
三阶段与关闭结果。源码已原子发布并单独集成；不派发性能 benchmark，
也不增加 libc 包装函数。
精确预取 [39975423664](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39975423664)
的实际日志已核实完整 revision 与
`sha256-jFaO/DMlHpMe7i/PFISHJ0tNAvohhSD5RLU6T7ycm3c=`，distro `8320989`
更新构建 pin，根仓库 `92aa65e` 更新 gitlink 并接入实际入口轻量模型。
本轮重跑 Clang18/22 × Wasm32/64 模型、工作负载前端及静态分析均通过。

同一 distro `8320989` 已派发两路 offsets 和两路 fixed-mmap 回归：
[39976703172](https://github.com/HighCWu/distro/actions/runs/39976703172)、
[39976713154](https://github.com/HighCWu/distro/actions/runs/39976713154)、
[39976723594](https://github.com/HighCWu/distro/actions/runs/39976723594)、
[39976735593](https://github.com/HighCWu/distro/actions/runs/39976735593)。
目前运行或排队，真实 offsets 三阶段、唯一 pass 与机器关闭仍待核实；
不把源码哈希预取或本地模型当作目标验收，也不等待它们才继续独立能力审查。

## 第五十八组：匿名 mmap 的 WRITE 请求兼容

Linux `bba354425ff9149f38daa3a8d7f98368e26b9307` 修复匿名 `PROT_WRITE`
请求被架构白名单拒绝的问题。官方 NOMMU 的私有复制路径不要求 WRITE 同时
携带 READ；本项目的直接线性 backing 可以提供写访问，但不能隔离读取。
现允许非零且仅含 READ/WRITE 的匿名 protection，将 WRITE 归一为 READ|WRITE
后传入既有分配器，兼容旧执行层的保护值白名单；不新增执行 ABI 或修改 musl。
PROT_NONE、EXEC、未知位仍拒绝，文件候选路径保留原限制，固定地址范围与
NOREPLACE 冲突规则不变。不把这种能力称为硬件式写独占或内存保护。

distro `8d83b32` 扩展原 mmap 工作负载，通过 libc/raw WRITE 检查零初始化、
首尾数据访问、discard 后清零、resize 和分段释放，不新增重复目标。
Clang18/22 × Wasm32/64 原样入口模型、工作负载前端/静态分析通过；模型确认
WRITE 向旧回调转成3、原拒绝分支不调用分配器，GCC/Clang 原生参考与固定映射
回归通过。本地验证不替代实际 Linux/Wasm 运行。

源码及工作负载已分别原子提交推送，精确
[hash 预取 39978007643](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39978007643)
已成功，实际日志核实完整 revision 与
`sha256-vd75NUbMIHzlyuLgIrsGYHdgEPy0oFknN14keA26m9E=`。
distro `0ff3b06` 单独更新构建 pin，根仓库 `6525559` 更新 Linux/distro
gitlink 并提交配套检查；没有用旧内核跑新能力断言。

固定同一 `0ff3b06` 的既有 mmap correctness 目标已派发：
[wasm32 39978400559](https://github.com/HighCWu/distro/actions/runs/39978400559)、
[wasm64 39978409127](https://github.com/HighCWu/distro/actions/runs/39978409127)。
这些是正确性检查，不运行 benchmark。验收需核实新增 WRITE libc/raw 阶段、
全部既有 mmap 阶段、唯一 pass 与机器关闭；目前运行或排队，尚未宣称通过。
第五十七组的四项旧目标继续运行，不重复派发或取消。

raw SYS_brk 同轮核查仍未冒充实现：既有 musl brk/sbrk 的当前 break 是用户
分配器状态，mmap 又使用同一 malloc arena。它仅允许单调增长；不能直接给
内核入口接一个查询/增长回调就宣称支持 Linux 的收缩与映射避让。此项保持为
实际缺口，没有为其新增公共函数或更改现有分配语义。

## 第五十九组：阻塞取消点的 Wasm 返回路径

静态 review 发现真实调用路径缺口：Wasm 的 SIGCANCEL handler 保留 SA_RESTART，
却不能像原生汇编一样改写返回 PC；仅在 __syscall_cp_c 返回后检查 cancel，
不能打断一直重启的阻塞 read。read/futex 的 Linux 重启语义本身没有错，修复
属于已有 libc 的 Wasm 信号/取消执行兼容，不是新增 syscall 包装或公共函数。

musl `ccd9d346` 发布初始实现，后续 `264eb0007269b4ba8881a87afd466ef2f84777e3`
补全原有 arch.mak 的 SjLj 对象编译策略；后者才是待集成的完整候选，不集成
前者的 hash。新增的是静态内部 helper 与 TCB 非 ABI 部分的取消点状态，不改
Part 1/Part 3 布局约束，不增加公共函数、头文件 API 或通用扩展。
内部 checkpoint 借助既有 LLVM Wasm SjLj 回到取消包装，保留 masked cancellation
返回 ECANCELED 的行为，让 cond_wait 先重新取得 mutex 后再执行取消收尾。
不直接从 deferred handler 退出，不移除 SA_RESTART，close/disabled/raw 调用的
原有边界保留。SjLj helper 单独 noinline，防止编译器的 activation 分配进入
禁用取消的 allocator 锁路径并递归建立 checkpoint。未宣称新增 OOM 恢复保证。

一参数和 SA_SIGINFO handler 都暂时清除外层取消点标记；正常返回恢复原标记，
handler 内的取消点可以独立建立 checkpoint。沿用 C-private __restore 函数，
将其导出为版本化内部执行入口 __wasm_signal_handler_v2，不提供应用 API。
distro `137c6e6` 提供 linux_signal_cancel_v1.abi 私有执行导入及普通 handler
trampoline 分派，缺少配套导出的新模块在准入时拒绝。新运行器保留旧模块直接
调用路径；旧运行器不会静默接纳要求该新协议的取消实现。

| 内部执行契约 | 形状与含义 |
| --- | --- |
| import `linux_signal_cancel_v1.abi` | `() -> i32`，返回1承诺一参数 handler 也经过配套 trampoline；不执行 Linux syscall |
| export `__wasm_signal_handler_v2` | `(uintptr_t table_index, i32 signal) -> void`，保留 Wasm32/64 函数表索引位宽，调用前后维护取消点状态 |

这两项由 libc/运行器使用，普通程序仍只调用标准 pthread/read/futex 路径。

Clang22 双位宽原样取消/restore 函数及真实 SjLj helper 的小型执行模型通过，
旧“返回后才取消”和不清除嵌套标记两种控制可区分；包含 close、disabled、raw、
两类普通 handler、handler 自己的取消点和 masked 返回。模型没有执行 Linux
调度，不以替代真实 Worker 返回边界。GCC/Clang 原生负载通过三阶段；源码/
目标前端与静态分析、运行器 src/test 两套类型检查、363 项运行器 host 检查通过。
可选 fork 补丁对候选 musl dry-run 通过，但不据此宣称 fork 已实际回归。

独立 deferred-cancel 目标不耦合普通 programs 构建：先通过 /proc/task syscall
观察真正阻塞的 read/futex，再请求取消。普通 libc read 不发送数据或 EOF 来
“救出”取消；raw/disabled read 要完成实际 I/O，条件等待则验证 cleanup 时
mutex 已重新取得且其后仍可锁。每次 join 有截止时间，fd/proc 均清理。
完整候选的精确预取
[39981879968](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39981879968)
已成功；实际日志核实完整 revision 与
`sha256-leZrlNNzyfVaoSekg8D9XewoAMa8PWK0s8qPZJaZ4TU=`。
distro `a8194ae` 单独更新构建 pin，根仓库 `244689a` 更新 gitlink 和模型。
轻量模型命令为 `python3 -B scripts/check_deferred_cancel.py`，需要 Clang22 的
原生 Wasm SjLj；不提供 Emscripten JavaScript shim 冒充真实非局部返回。
后续 root `0be826c` 修正信号栈前端检查：仅对包含现有 private TCB header 的
restore.c 放宽原有 inline 的 unused-parameter 警告，应用负载仍保持严格警告。
该既有信号栈脚本的三项原生/双位宽检查再次通过，没有修改 libc 来消除此警告。

同一 `a8194ae` 的实际目标已异步派发：取消
[wasm32 39982289264](https://github.com/HighCWu/distro/actions/runs/39982289264)、
[wasm64 39982297387](https://github.com/HighCWu/distro/actions/runs/39982297387)；信号栈回归
[wasm32 39982306882](https://github.com/HighCWu/distro/actions/runs/39982306882)、
[wasm64 39982314549](https://github.com/HighCWu/distro/actions/runs/39982314549)。
四项实际 Heavy 日志现已核实：取消各有阻塞 read 无数据/EOF 的取消收尾、raw/
disabled 真实 I/O、masked cond-wait mutex 重取得三阶段；信号栈各有原五阶段，
均包含唯一 pass。固定 a8194ae 运行器退出成功前等待 machine.closed，关闭错误
会使任务失败，四项均通过该门禁。因此接受 musl 264eb000 / distro a8194ae 的
双位宽有界 Node 验收，不泛化为浏览器、所有取消窗口或后继线程释放修复。
不等待这些 CI 才推进其它独立 syscall 审查，也不据此扩大多线程 fork。
较早 ccd9d346 的预取 39981476691 不覆盖后续编译策略，不拿它更新 pin。

## 第六十组：恢复显式 fork profile 中既有终端/daemon 实现

核对直接上游 tombl/musl 后，forkpty 和 daemon 不是缺少的函数：源码和其它平台
声明均存在，只是 Wasm 被 #ifndef 门控。distro `6f14171` 扩展原可选
fork-continuation.patch，恢复这两个既有声明及原实现；函数体逐字保留，没有
补造公共函数、头文件 API 或 Linux 扩展。默认 musl 源码/构建不打该补丁，
仍保持原声明门控；只有显式 fork profile 的 WASM_FORK_CONTINUATION 分支启用。
根仓库 `5a693b9` 单独更新 gitlink 和轻量验证，musl pin 仍为 264eb000。

这是依托已有 fork syscall 恢复标准程序调用路径的兼容增量，不是新增 syscall
编号。底层仍由 Linux 的 setsid、TTY ioctl、dup2、信号、poll/read/write、wait
和 subreaper 机制实现；不以项目专有应用接口替代这些调用。范围仍限显式 profile
的单线程静态 C，不开放默认 fork、不扩大多线程 fork，也不宣称完整交互式 job
control、vfork 或动态链接支持。

独立 terminal-process 目标验证：forkpty/login_tty 将子进程置为 session leader
和前台进程组，三条标准描述符均接到 slave；检查初始 winsize、canonical 输入/
echo/输出、master TIOCSWINSZ 触发前台组 SIGWINCH 和更新尺寸，再 wait/reap。
窗口信号在握手前阻塞，sigsuspend 原子解除阻塞等待，避免 pause 的丢失唤醒窗口。
daemon(0,0) 从非根 cwd 开始，经原双次 fork 后检查新 session、非 session-leader
最终进程、根 cwd 与 /dev/null 标准描述符；测试进程只在自身启用 subreaper，
回收 launcher 和两级后代恰好各一次，恢复原设置。Wasm 挂载的 devpts/devtmpfs
最终卸载，原生参考不修改宿主挂载；子分支失败也不向测试父进程伪造 pass。

Clang18/22 × Wasm32/64 前端与静态分析通过，声明负向控制确认默认配置仍隐藏；
原样实现校验确认只改 profile 门控。GCC/Clang 原生负载实际链接 tombl/musl 的
daemon、forkpty、login_tty，而非误测 glibc daemon 的不同 fork 策略，三阶段
与唯一 pass 均通过。原生仅对未修改上游错误管道 write 的 glibc fortified
unused-result 警告作局部放宽，应用负载仍严格编译。这些不是 Wasm Worker 证据。
原 SDK/finalizer 五项检查、完整可选补丁 dry-run、Nix 格式及 actionlint 通过。

同一 `6f14171` 双位宽实际目标已派发：
[wasm32 39984725651](https://github.com/HighCWu/distro/actions/runs/39984725651)、
[wasm64 39984734768](https://github.com/HighCWu/distro/actions/runs/39984734768)。
两项实际 Heavy 日志均已核实上述三个阶段及唯一 ::vm-test::pass，任务退出成功。
固定 6f14171 的 run-test.js/shutdown.js 在成功退出前等待 machine.closed，
关闭失败会使目标失败；这两个文件相对已审查的 a8194ae 无差异。因此接受
6f14171 / musl 264eb000 的双位宽有界 Node 验收，不以原生参考或恢复声明代替
目标证据，也不扩大为浏览器、完整 job control 或后继 musl pin 的验收。

## 第六十一组：detached thread 的栈释放与分配器锁生命周期

静态 review 在 tombl/musl 的 Wasm __unmapself 路径确认两个相关缺口：它从
仍在使用的用户 C 栈上 free 自己的 stack/TLS 存储，再进入 SYS_exit；分配器
发布复用后，另一线程可以清零/改写旧栈。同时 __pthread_exit 在减掉最后一条
额外线程后提前设置 need_locks=-1，这在原生 munmap 退出路径不使用 malloc，
但 Wasm 的后续 free 仍须和剩余线程的 malloc 串行，不能提前停用锁。

musl `f949d1b1612f1b4cbc42a4924d59bd13f7728e6a` 修改这两个既有架构路径：
先把 __stack_pointer 切到进程内专用静态退出栈，再进入 noinline/noreturn
内部 helper 释放旧存储并调用 SYS_exit；即使 tracer 跳过 exit，也不返回旧调用
帧。原线程列表锁一直保持到内核 clear_child_tid 清零，因此同一地址空间内的
退出栈复用仍串行，不新增锁或内核执行协议。退出栈大小取既有 DEFAULT_STACK_SIZE
（当前128 KiB），是链接该路径时的固定开销，不是每个线程另分配128 KiB。
Wasm 退出不再使用最后线程的停锁优化，保留无争用锁开销以保证共享分配器安全；
非 Wasm 分支保持。没有新增公共函数、头文件 API、syscall 或 softmmu。

Clang18/22 × Wasm32/64、-Os/-O2 的小型模型执行原样 __unmapself，free 回调
立即 poison 旧栈，再执行真实 C 调用帧写入：修复后旧范围保持 poison，恢复旧
路径的控制会在已释放范围写入。两次有序退出验证静态栈可复用；原样计数分支
另验证 Wasm 保留锁和传统平台行为不变。这不执行实际 malloc/内核/Worker，
不伪称本地重现了整机并发崩溃。实际源文件与目标双位宽前端/静态分析通过；
pthread_create 既有的通用 stack 赋值后被 wasm_tls 覆盖会触发 DeadStores，
该文件只关闭此检查器，内存检查保留，未为过检查修改无关代码。

distro `b7cfd8a` 提供独立 thread-reclaim 目标，32 轮 detached 返回/TLS destructor
与主线程分配写入并行。测试私有链接 wrapper 在真实 free 前检查当前 C SP 已离开
释放范围，且不在 free 后读取旧 TLS；观察计数后还创建/回收 joinable 线程，通过
已有线程列表同步等待最后释放完成，再删除 key 并验证分配器可用。wrapper 不进入
SDK 或 libc 公共接口。GCC/Clang 原生参考通过两个公共阶段，不能代跑 Wasm 的
私有 SP 检查。可选 fork 补丁 dry-run、Nix 格式及 actionlint 通过。

源码已分别原子提交推送，精确预取
[39987636348](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39987636348)
已成功；实际日志核实完整 revision 和
`sha256-2de32oGY1FG8F8QOWHJCE/N85QAcC8u5tw0wK0vdlTk=`。
distro `19e8fd0` 单独更新构建 pin，根仓库 `a87f9c6` 更新 musl/distro gitlink，
提交原样函数模型和轻量 CI 门禁。Linux pin 未变，没有将 libc 架构兼容修复
描述为新增内核 syscall。模型、源码/负载前端与分析、原生参考再次通过。

固定同一 `19e8fd0` 的双位宽 thread-reclaim 和取消点回归共四项已派发：
[39988479944](https://github.com/HighCWu/distro/actions/runs/39988479944)、
[39988488638](https://github.com/HighCWu/distro/actions/runs/39988488638)、
[39988496691](https://github.com/HighCWu/distro/actions/runs/39988496691)、
[39988504426](https://github.com/HighCWu/distro/actions/runs/39988504426)。
四项实际 Heavy 日志均已核实：thread-reclaim 各有真实 SP 离开旧范围后释放、
32轮 destructor/分配并行、后续 joinable 与清理三个阶段；取消点各有原三个阶段，
均有唯一 pass。固定 19e8fd0 的 run-test.js/shutdown.js 相对已核实的 6f14171
无差异，成功退出前等待 machine.closed，关闭失败使目标失败，四项均通过。
因此接受 f949d1b1 / 19e8fd0 的双位宽有界 Node 结果，不扩大为浏览器、无限
并发或后继内核/运行时的验收；不是用旧版本取消测试代替新 pin 的实际执行。

## 第六十二组：内核与用户回调的执行相位基础

Linux `d3203ef365e219e6b046b79e18420aa6afa9d5d1` 将当前执行相位与保存的
syscall/signal 寄存器帧分开维护。generic entry/exit 的架构 hook 维护任务状态；
首次 wasm_user_call 前和返回后显式转换，但不提前执行 pending return work，
保留 clone 用户 C 栈/TLS 设置后首次 syscall 的信号/ptrace 检查点。新任务
显式从 kernel 相位启动。IRQ 使用调用帧内的寄存器快照，而非共享零值 dummy，
从 user 相位进入的 IRQ 在处理前转回 kernel、结束后恢复 user；IRQ 路径不擅自
投递用户信号。此时仍保持原记账配置，不能据 IRQ 快照改动宣称精确 CPU 分账。

私有固定 i32 导出 user_context_v1 的模式0/1/2分别为 kernel/user/query，返回
旧相位，非法模式返回 EINVAL 且不改状态。它不是 UAPI 或应用导入；只供执行层
在现有同步调用之间恢复状态，不替代 Linux syscall，也不为 musl 新增函数。
Linux 内修改保留 GPL；配套执行层与模型保留 MIT。

distro `d83cbd7` 为原有分配器（包括 initialized-copy）、实例初始化和 clone
continuation 准备加相位作用域，TLS/信号帧等 leaf 内核导出使用 kernel 作用域。
普通 syscall 仍由自己的 generic entry 转换。作用域复用 C 栈/IRQ 恢复边界，
先恢复活调用者的相位再恢复 IRQ；SjLj/exec 异常继续传播，HALT_KERNEL 后不再
进入 C。旧内核缺少导出时沿用旧行为，不宣称老组合获得了新相位保证。

Clang18/22 × Wasm32/64 的小型模型执行实际相位 helper、架构 hook 与 IRQ
函数体；通用 entry/exit 使用严格替身，不是链接完整 Linux。嵌套 callback/
leaf、SjLj、IRQ 用户快照和成对转换、IRQ 标志保留、非法模式均通过；删除 IRQ
转换的负向控制会被拒绝。模型静态分析、原 syscall 重入模型通过；365项宿主
测试及源/测试两套 TypeScript7 检查通过。checkpatch 无错误，仅有新增文件的
MAINTAINERS 提醒；通用 helper 替身与本地小模型不能代替真实整机回归。

精确源码预取 [40046015736](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40046015736)
成功，实际日志核实完整 d3203ef365e219e6b046b79e18420aa6afa9d5d1 和
`sha256-4nHM3QjFJ0j1nRqCtcJOF7t8QGN7YCOv34QoPUIVfN0=`。distro `07ae2d6`
单独更新构建 pin，根仓库 `c0c764c` 更新两个 gitlink 并加入精确源码轻量模型；
musl 保持 f949d1b1。新版重入、信号栈/取消和 fork/exec 的双位宽整机回归已
安排异步执行，结果仍需核实实际阶段与关闭，不把上一组通过转记到新内核：

- 重入：[wasm32 40046344886](https://github.com/HighCWu/distro/actions/runs/40046344886)、
  [wasm64 40046349884](https://github.com/HighCWu/distro/actions/runs/40046349884)。
- 取消：[wasm32 40046354215](https://github.com/HighCWu/distro/actions/runs/40046354215)、
  [wasm64 40046358498](https://github.com/HighCWu/distro/actions/runs/40046358498)。
- 信号栈：[wasm32 40046362695](https://github.com/HighCWu/distro/actions/runs/40046362695)、
  [wasm64 40046367981](https://github.com/HighCWu/distro/actions/runs/40046367981)。
- fork/exec runtime：[wasm32 40046372468](https://github.com/HighCWu/distro/actions/runs/40046372468)、
  [wasm64 40046376510](https://github.com/HighCWu/distro/actions/runs/40046376510)。

这只是通用 CPU 记账的前置实现，不是新增 CPU timer syscall。接入 vtime 前
当时还须将 syscall 的早期栈指针读取、参数保存和 RCU 操作置于正确 entry 边界
之后；第六十三组已修正这一顺序。仍须审查相位转换周围的 instrumentation、
跨 Worker 时钟与32位远端读。启用
context tracking 的内核还必须可靠拒绝不支持回调相位协议的旧执行层，不能仅
因新版导出存在就视为旧宿主安全。目前未选择 HAVE_CONTEXT_TRACKING_USER 或
VIRT_CPU_ACCOUNTING_GEN，后续按下节条件推进，不以模型通过代替记账能力。

## 第六十三组：syscall 早期 entry 与自动重启的上下文顺序

Linux `fa5f4a9694b6f61e76982cc16bdca4518145a957` 修复上一阶段留下的明确
顺序问题：原 dispatcher 在 generic entry 前就读取用户栈、写入寄存器帧，并
调用 rcu_note_context_switch。在启用用户 context tracking 后，这时可能仍处于
user/RCU EQS，不能把这些高层工作放在转换前。

现在主入口标为 noinstr，每轮先禁用 IRQ 并 enter_from_user_mode，再打开
instrumentation 区域、保存 kernel 模式和报告 RCU 静止点，随后启用 IRQ、
读取/保存初始栈与参数，并调用 syscall_enter_from_user_mode_work。进入退出
处理前关闭 instrumentation 区域。自动 restart 经 generic exit 后必须重新
enter；但只在首次入口读取栈和初始化参数，保留 ptrace 已编辑的参数及原有
restart 目标，不把它们重置为最初的调用参数。跳过、错误和正常返回仍统一走
原 Linux exit work，未增加 syscall、应用导入、musl 包装或记账配置。

精确 dispatcher 模型使用严格的 generic helper 替身，检查用户相位下不得
读取栈或调用 RCU、entry work 必须在 kernel/IRQ-enabled 状态执行。每个退出
含 restart 都有新的 entry/RCU 报告，而 restart 不重复导入原用户栈。分别
提前栈读取、提前 RCU、漏掉 restart entry 的三个负向控制均必须触发拒绝；
旧寄存器覆盖控制继续保留。Clang18/22 × Wasm32/64 执行与静态分析通过；
ptrace 与重入的原生参考/前端分析、机器字解码和原相位模型通过。宿主365项
仍通过。checkpatch 无错误/警告；本地替身不证明完整 RCU、instrumentation
或真实用户 CPU 定时器已验收。

源码预取 [40046825394](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40046825394)
成功，实际日志核实完整 fa5f4a9694b6f61e76982cc16bdca4518145a957 和
`sha256-3JqXVQr22fbhNzv4xkf9KYoFJUS3P3V5KWyXYxQ5K8g=`。distro `d743c90`
单独更新 pin，根仓库 `d9f4e21` 单独更新两个 gitlink 和已有轻量模型；
musl f949d1b1 与执行层代码均未新增变更。新版双位宽重入和 wasm64 fork/exec
runtime 针对性异步复验；上一组八项继续独立运行，不重复派发其完整矩阵。
本组记录为重入
[wasm32 40047166301](https://github.com/HighCWu/distro/actions/runs/40047166301)、
[wasm64 40047170664](https://github.com/HighCWu/distro/actions/runs/40047170664)，以及
[wasm64 runtime 40047174734](https://github.com/HighCWu/distro/actions/runs/40047174734)。
均须后续核实实际阶段、唯一 pass 与机器关闭，不以工作流状态代替这些证据。

后续时钟准入的小型诊断另直接调用现有 get_now_nsec：Node v25.9.0 两个 Worker
以 Atomics 串行交接2000次采样，未见倒退，1146次相等（现有导入量化至5µs）。
这只验证该 Node 运行中的有序时钟观测，不覆盖浏览器、CPU迁移、物理 CPU
精度或 Linux vtime；现有执行 ABI 没有宿主 steal-time 信息，宿主暂停/调度
造成的 elapsed time 不能据此宣称已排除。下一步继续审查低层 helper 的
instrumentation 及协议准入，再接入实际通用记账，仍不直接打开默认配置。

## 第六十四组：IRQ 编译回归与真实头文件的模型盲点

第六十二组的新 run_irq 调用 user_mode(&regs) 触发了已有宏的参数优先级错误：
`#define user_mode(regs) (regs->user_mode)` 将 &regs 错误展开，无法编译。
已核实 [wasm32 重入 40046344886](https://github.com/HighCWu/distro/actions/runs/40046344886)
的 Heavy job120728920679 与
[wasm64 取消 40046358498](https://github.com/HighCWu/distro/actions/runs/40046358498)
的 job120728953704 实际日志，均在 arch/wasm/kernel/irq.c:138/149 报告
struct pt_regs 不是指针及不能取得 int rvalue 地址。它们是内核编译失败，
没有运行目标程序，不是缓存保存告警或用户 syscall 阶段失败；同批其余 failure
状态未据此冒充逐项日志核实。fa5f4a969 也继承该宏，尚未完成的任务不作通过证明。

Linux `41299f06eb3acbfab9d0e67ef98b08dff5246f16` 将宏改为
`((regs)->user_mode)`，保留原值/lvalue 和 ABI，不通过修改调用点掩盖宏本身的
错误。没有引入公共函数或扩大支持范围。

原相位模型虽然执行真实 IRQ/helper 函数体，却在 fixture 中自己定义了正确的
user_mode 替身，因而漏掉真实头文件的错误。这一盲点已修正：模型及轻量 CI
直接读取/获取同一 pin 的 include/uapi/asm/ptrace.h，不再重定义 user_mode。
修改前用真实头文件在本地复现同样错误；修复后 Clang18/22 × Wasm32/64 执行与
静态分析通过。保留旧宏的负向编译控制在四种组合都拒绝，IRQ 缺少成对转换的
运行时控制也继续保留。fixture 对 inline 的 unused 属性匹配内核常规定义，
未修改生产编译警告策略，也不把未执行的 regs_irqs_disabled 桩说成已支持。

原 entry/restart 模型、ptrace 与重入参考/前端分析、actionlint、差异检查通过，
内核 checkpatch 无错误/警告。先修复此明确回归，再推进独立 vtime 配置；本轮
未打开记账配置。最终仍须新源码的真实编译、运行阶段及关闭结果，不把本地
模型通过直接当作整机恢复。

精确源码预取 [40047766795](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40047766795)
成功，实际日志核实完整 41299f06eb3acbfab9d0e67ef98b08dff5246f16 和
`sha256-NaRWXlgy7f0Y24PYcIoRqDbMNK1pMlqAGRxfbhF0eVc=`。distro `088fd6f`
单独更新构建 pin，根仓库 `a967b36` 更新两个 gitlink、精确头文件输入和负向
控制，musl f949d1b1 不变。新版只针对双位宽重入、wasm64 取消和 fork/exec
runtime 四项复验，不重复整个旧矩阵；仍运行的旧源码任务不取消，也不用于
验收新 pin。本轮尚无新版实际程序阶段或关闭的通过证据。
复验为重入
[wasm32 40048141644](https://github.com/HighCWu/distro/actions/runs/40048141644)、
[wasm64 40048146878](https://github.com/HighCWu/distro/actions/runs/40048146878)，
[wasm64 取消 40048151875](https://github.com/HighCWu/distro/actions/runs/40048151875) 和
[wasm64 runtime 40048157954](https://github.com/HighCWu/distro/actions/runs/40048157954)。

## 后续 CPU 时间记账准入审查（初始审查记录）

对固定 Linux bba354425 的源码审查区分了三条不能混为一谈的路径：

- CLOCK_PROCESS/THREAD_CPUTIME_ID 的 SCHED clock 通过 task_sched_runtime 取调度器
  运行时间；不能因用户态缺少异步 tick 就断言 CPU 总时钟没有实现。
- getrusage 的 cputime_adjust 会按 sum_exec_runtime 缩放 utime/stime；总量可能
  仍前进，不代表 user/system 分类准确。该基线 Wasm run_irq 使用零值 dummy regs，
  tick 的 user_mode 为0，account_process_tick 因而不会在该路径增加用户时间。
- ITIMER_VIRTUAL 使用 CPUCLOCK_VIRT/utime，而不是上述 SCHED 总时钟；不能用
  CLOCK_PROCESS_CPUTIME_ID 能读出非零值来证明虚拟用户 CPU 定时器正确。

这些是源码风险及后续实测要求，不宣称已在真实 Worker 中完整复现每个现象，
也不将本次审查算作新 syscall 能力。现有计时配置未修改，不添加 libc 包装。
相关固定源码为 kernel/sched/cputime.c、kernel/time/posix-cpu-timers.c、
kernel/time/itimer.c、kernel/time/tick-sched.c 和 arch/wasm/kernel/irq.c。

优先研究复用官方 VIRT_CPU_ACCOUNTING_GEN/context tracking，而不是自造一套
按宿主 wall time 累加 utime 的近似实现。但现在仅添加 Kconfig select 不安全：
原 bba354425/19e8fd0 基线的首次 wasm_user_call 前还没有完整的用户上下文转换，
分配器回调又可从仍在执行的内核帧重新调用 syscall；当时 call_kernel_entry 只
管理 C 栈与 IRQ。第六十二组已补上相位基础，但还不等于完成 context tracking
准入；第六十三组继续修正 entry 早期顺序，signal callback 的 SjLj 收尾、
exec 替换和 HALT_KERNEL 仍须共同审查。SMP 的 TREE_RCU 选择 CONTEXT_TRACKING_IDLE，
因此这些不是仅影响统计数字的局部开关，还涉及 RCU 是否在观察内核代码。

后续实施顺序与准入要求：

1. 先定义并实现内核/用户回调的相位与异常恢复契约，覆盖首次启动、普通 syscall、
   allocator 重入、两类 signal handler、exec/SjLj 和真实任务退出。保留 clone 的
   “C 栈/TLS 准备后才处理 pending signal/ptrace”边界，不能提前执行返回工作。
2. 再接入通用 vtime；检查调度切换、IRQ/idle、跨 Worker 时钟基准和远端读取。
   64位默认 HAVE_VIRT_CPU_ACCOUNTING_GEN 不等于32位已具备支持；后者需要审查
   64位字段的 seqcount/锁与读写规则，不因 Wasm 支持 i64 指令就直接宣布安全。
3. 用真实标准接口分别验证 SCHED CPU 总时钟、getrusage user/system、
   ITIMER_VIRTUAL/PROF、阻塞等待不计入用户 CPU，以及 signal handler 的计算。
   有限用户计算后在正常边界检查投递，不宣称可异步打断纯用户无限循环。
4. 与现有 callback 重入、信号栈、取消点、fork/exec、线程释放共同验收后再考虑
   默认启用。模型与 Kconfig 可选本身不能证明这些真实阶段或 RCU 生命周期。

## 第六十五组：默认关闭的通用 CPU 记账实验配置

Linux `fdd42ce1c` / `54807f1ab` 增加默认关闭的 WASM_VTIME，供独立配置选择
官方 VIRT_CPU_ACCOUNTING_GEN 与 CONTEXT_TRACKING_USER_FORCE。没有改默认
defconfig、CONFIG_MMU=n 或 musl；不是新增 libc 函数，也不直接另写 utime/stime
累加器。首次用户执行与信号回调统一经过 noinstr 相位 helper，低层 current/
IRQ helper 保持相应边界；IRQ 帧仅先准备 user_mode，完整清零在 generic entry
之后的受保护区进行，并用 barrier_data 阻止编译器将初始化移过边界。

启用 context tracking 的内核要求私有 `user_context_v1.abi` 宿主导入返回1；
缺失导入在实例化时拒绝，错误版本在启动早期拒绝，不以旧宿主静默进入 EQS。
主实例与 Worker 均提供同一实现，应用导入白名单不接纳该命名空间。默认内核
不要求这一新导入；这不是面向应用的 API。

distro `d4fea97` / `abb441e` 增加独立双位宽 cpu-accounting 配置，并复用既有
取消、替代信号栈及 fork/exec 检查，不修改默认 SDK。标准 C 工作负载分别检查：

- 线程/进程 CPU 时钟与 getrusage 用户计算时间；
- 阻塞等待不消耗虚拟用户 CPU 定时器；
- ITIMER_VIRTUAL/PROF 的一次投递及信号处理器的用户计算记账；
- 线程隔离、join 后的进程累计与处理器清理。

本地 GCC/Clang 原生参考及丢失用户记账/虚拟定时器的负向控制通过；Clang18/22
双位宽前端与静态分析通过。精确内核头文件/函数体模型验证首次调用、信号回调、
IRQ、ABI 拒绝及 JS 嵌套恢复，并保留错误宏、过早清零等负向控制。这些不是
Wasm Linux 整机验收，也不能证明所有并发读写、浏览器或调试配置。

[精确源码预取 40052609497](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40052609497)
实际日志确认 `54807f1abaec38bc751fe11e3de9554b51536c45` 与
`sha256-LtcA2aCw4LtKyHAEtVHF3LlX6VDivmbSPRZKClQcvzA=`。
distro `e0fe092` 单独更新 pin，根仓库 `89c0332` 集成源码 gitlink 与轻量模型。
musl 保持 `f949d1b1`，没有公共 API 增量。

同一 distro `e0fe092` 已异步派发以下六项，不重复启动相同构建：

- GEN CPU 工作负载：
  [wasm32 40052886299](https://github.com/HighCWu/distro/actions/runs/40052886299)、
  [wasm64 40052890214](https://github.com/HighCWu/distro/actions/runs/40052890214)。
- GEN wasm64 回归：
  [取消 40052894009](https://github.com/HighCWu/distro/actions/runs/40052894009)、
  [替代信号栈 40052898040](https://github.com/HighCWu/distro/actions/runs/40052898040)、
  [fork/exec 40052903871](https://github.com/HighCWu/distro/actions/runs/40052903871)。
- 默认记账配置 wasm32 [重入 40052908302](https://github.com/HighCWu/distro/actions/runs/40052908302)，补此前下载失败的缺口，不冒充 GEN 验证。

真实目标必须另核实四个阶段、唯一 pass 和固定运行器关闭门禁，当前尚未据此
接受 GEN 配置。旧 `088fd6f` 的 wasm32 重入 40048141644 实际日志失败于源码
下载持续 HTTP429，未编译/运行内核；三项 wasm64 工作流 success 尚不能代替
逐项阶段核实，也不覆盖本组实验配置。
随后已读取 wasm64 重入 40048146878 和取消 40048151875 的实际日志，均确认
完整三阶段及唯一 pass；并核对固定 088fd6f 的运行器必须等待 machine.closed，
关闭错误使派生失败，因此这两项通过关闭门禁。fork/exec 40048157954 的日志
随后也已补齐，确认 raw clone、clone3、信号隔离、continuation、失败 exec 恢复、
未转换 helper、成功 exec、线程/信号回调拒绝和后续恢复的完整阶段及唯一 pass，
同一固定运行器通过关闭门禁。三项结果仍仅接受旧版默认记账配置 wasm64，不能
扩展为 wasm32 或本组 GEN 的通过证据。

剩余边界包括32位远端读的 seqcount/字段规则、迁移/跨 Worker 时钟、浏览器和
tracing/lockdep 配置。当前执行 ABI 没有宿主 steal-time 数据，GEN 记录逻辑调度
区间，宿主暂停/GC 不保证扣除；不是原生物理 CPU 精度。纯用户无限循环仍不
支持异步抢占。未验证重复 CPU timers、全部 POSIX CPU timers 或所有调试组合，
不得据此默认启用。

后续已核实固定 e0fe092 / Linux 54807f1ab 的
[wasm64 GEN CPU 40052890214](https://github.com/HighCWu/distro/actions/runs/40052890214)
Heavy job120749313976 实际日志：上述四个阶段全部出现，唯一 pass，派生成功。
固定版本 run-test.js/shutdown.js/package.nix 与已审查的 088fd6f 运行器相同，
必须等待 machine.closed 且关闭错误使目标失败，因此通过关闭门禁。接受该版本
双 CPU、Node wasm64 的有界 GEN CPU 时钟/getrusage/ITIMER_VIRTUAL/PROF、信号
计算与 join 语料，不扩大到 wasm32、浏览器、后继 pin 或其它回归。GEN 仍不默认
启用，逻辑时间与物理宿主 CPU/steal-time 的限制不变。

同版 GEN wasm64 的取消 40052894009/job120749324782 与替代信号栈
40052898040/job120749342239 也已读取实际日志，分别完整三阶段和五阶段、
各唯一 pass，且通过相同固定运行器关闭门禁。接受该版本的这两组有界回归，
不以另外任务的 success 状态补齐尚未读取的阶段或后继源码结果。

## 第六十六组：syscall 早期 IRQ tracing 边界与 CI 输入修正

实际轻量 CI 40048130388 的 job120734412084 在 syscall-info 模型中报错
ValueError: substring not found；后继 40052907317 也停在同一步。原因是工作流
将 `arch/wasm/kernel/ptrace.c` 复制到需要通用 `kernel/ptrace.c` 的目录，不是
生产 ptrace helper 缺失。本地模型读取正确的通用文件，未覆盖该接线错误。
根仓库 `f43d4cd` 改为从同一精确 pin 单独获取通用文件，并在模型提取前校验
应有 helper。错误架构输入现被明确拒绝；Clang18/22 双位宽实际 helper 模型与
分析通过。不通过放宽检查或跳过 ptrace 模型来掩盖错误。

静态 review 另确认 syscall 入口在 generic enter 之前使用 local_irq_disable，
如果后续启用 TRACE_IRQFLAGS，它可能在 RCU 仍处于用户 EQS 时进入 tracing。
Linux `d22065aa3` 改为 raw_local_irq_disable：先仅屏蔽架构 IRQ，再由官方
enter_from_user_mode 完成 lockdep/context tracking/RCU/tracing 顺序。没有修改
syscall 号码、参数布局、返回值或 musl；当前 Wasm 不选择 TRACE_IRQFLAGS_SUPPORT，
这是一处准入边界修正，不是声称完整 tracer/lockdep 功能已实现。

实际 dispatcher 模型现在区分 raw 屏蔽与可触发 tracing 的 local 屏蔽，将旧写法
恢复的负向控制必须在 user phase 拒绝。Clang18/22 × 双位宽的执行和静态分析、
嵌套 frame/ptrace 编辑/自动重启、早期用户栈/RCU 负向控制、匿名 mmap 参数、
稀疏大文件原生/ABI 和 syscall-info 相关检查通过，内核 checkpatch 零错误/警告。
模型仍使用严格 generic helper 替身，不等同于完整 Linux tracing 配置的执行。

[精确源码预取 40053252353](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40053252353)
日志确认 `d22065aa31d2310e6faccead3654be14d8ebb8d1` 与
`sha256-CV6PqRZXYzTKoH9IhTNu1XG4z80iWwyELO81RWC12s4=`。
distro `087dc60` 单独更新 pin，根仓库 `1f65d23` 集成两个 gitlink 与模型控制，
musl 仍为 f949d1b1。新版只针对默认 wasm32 重入与 GEN wasm64 CPU 工作负载
异步验证：
[wasm32 重入 40053462532](https://github.com/HighCWu/distro/actions/runs/40053462532)、
[wasm64 GEN CPU 40053466632](https://github.com/HighCWu/distro/actions/runs/40053466632)。
旧版六项仍运行的任务不取消、不视为覆盖新 pin。

并发审查确认通用 vtime 的更新与远端 task_cputime/kcpustat 读取依赖 seqcount
及重试，不能凭64位字段的单条 i64 指令就宣布安全。Wasm 的
[共享内存模型说明](https://webassembly.github.io/threads/core/exec/relaxed.html)
区分访问对齐、宽度和竞争时的 tearing；实际屏障/发布与远端读取规则仍须整体
验证。当前不修改通用 seqcount 核心、不扩大 READ_ONCE 语义，也不将一轮并发
采样当作证明。GEN 配置继续默认关闭。

## 第六十七组：恢复 EROFS 镜像的标准扩展属性读取

固定内核的 fs/erofs/Kconfig 对 EROFS_FS_XATTR、其 POSIX_ACL 和 SECURITY 子项
默认 y，但 Wasm 两种 defconfig 明确关闭前者。Linux `0ace17791` 恢复双位宽
EROFS_FS_XATTR=y，后两项沿通用 Kconfig 默认条件解析，不另写 Wasm 文件系统
实现或应用接口。构建核对解析后配置，仍保持 CONFIG_MMU=n，musl f949d1b1 不变。
这补的是已挂载 EROFS 镜像的 getxattr/listxattr 等既有 syscall 后端，不是新增
libc 包装，也不声称已全面验收 ACL/LSM 权限策略。

distro `9ff3f5b` 接入普通 SDK C 程序及两张真实小型 EROFS 镜像：内联属性与
共享属性布局。语料验证带 NUL/高位字节的二进制值、空值和目录值，路径/描述符/
跟随与不跟随符号链接、名称列表和 size query，ERANGE/ENODATA/EBADF，实际目标
还要求替换/删除被 EROFS 拒绝、原值不变和文件/挂载收尾。不是把原生目录当成
EROFS 整机证据，也不是只验证 syscalls 返回成功。

创建镜像时显式保留属性。工具的 `-x0` 不会将所有只出现一次的属性自动放入
共享区；本地校验先发现了这一差别，随后增加跨 inode 重复属性。独立 on-disk
检查确认实际内联/共享条目及边界，不仅检查 mkfs 参数；小镜像可把共享条目放在
块0，因此不错误要求共享区块号非零。使用 erofs-utils 1.7.1 的本地两张镜像各
4 KiB，fsck 和布局检查通过，没有本地构建内核或工具链。

GCC/Clang 原生参考、EOPNOTSUPP 负向控制、Clang18/22 双位宽前端/静态分析、
格式与差异检查通过；Linux checkpatch 零错误/警告。这不证明真实 Wasm 上的
属性 decoder、只读拒绝或关闭结果，必须由双位宽目标进一步核实三个阶段、唯一
pass 和固定运行器 machine.closed 门禁。

[精确源码预取 40053795290](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40053795290)
实际日志核实 `0ace1779107cd575dced87315b66edf782d21056` 与
`sha256-QcD0PcWcZXnooENnIIg0Ky/Q+n6GlhZjiHHfFo9H8HQ=`。
distro 同一原子集成包含该 pin、解析后配置断言和镜像语料，避免发布要求新配置
却仍固定旧内核的中间状态。根仓库 `b48b620` 单独集成源码 gitlink 与轻量检查，
目标 CI 已派发，尚不据此宣布验收完成：
[wasm32 40054081528](https://github.com/HighCWu/distro/actions/runs/40054081528)、
[wasm64 40054086136](https://github.com/HighCWu/distro/actions/runs/40054086136)。

范围不包含通用 EROFS 压缩、file-backed EROFS 或 LSM 策略；原 mkFilesystem
打包流程仍显式使用 -x-1，不在此轮改动，也不声称已有构建产物会自动保留包的
属性元数据。此轮首先让内核正确读取本来就带属性的镜像。EROFS 的标准属性
布局见[官方说明](https://erofs.docs.kernel.org/en/latest/ondisk/xattrs.html)，
构建方法见[官方构建说明](https://erofs.docs.kernel.org/en/latest/mkfs.html)。

## 第六十八组：普通文件 EROFS 挂载与无宿主 xattr 的镜像构建

上一组双位宽目标均失败在镜像构建：wasm32 40054081528/job120753120168 与
wasm64 40054086136/job120753124357 实际日志均为
`setfattr: root/file: Operation not supported`。这是 Nix 沙箱构建文件系统不提供
user xattr，未执行 Wasm 目标程序，不能据此归因于内核 decoder 或声明已支持。

镜像改为不依赖构建宿主 xattr：内联镜像通过标准 PAX/SCHILY.xattr 元数据交给
mkfs.erofs，任意二进制值保留原字节；共享镜像使用 MIT 自有数据的确定性参考
镜像，保存为文本编码、验证固定 SHA256，并提供从 make-fixture.py 和标准
mkfs.erofs 1.7.1 再生成的方法。gzip 仅为仓库保存测试数据，不是开启 EROFS
压缩。两种镜像继续经 fsck、真实布局和根 inode 的二进制/空值/目录值核对；不
把共享测试改成内联，也不忽略沙箱失败。PAX 生成原生参考与双位宽分析通过。

独立源码审查同时确认 EROFS_FS_BACKED_BY_FILE 的官方 Kconfig 默认 y、只依赖
EROFS_FS，Wasm 却显式关闭。Linux `e7e5a27fa` 恢复双位宽配置。普通文件路径
从 erofs_fc_get_tree 转入 nodev superblock，metadata 使用 backing mapping 的
folio，payload 通过 ITER_BVEC 读取内核缓冲区，不建立用户 VMA；CONFIG_MMU=n
保持。关闭压缩的路径不调用仅 NOMMU 桩实现的 vm_map_ram/vmap，不顺便打开
EROFS 压缩。源文件系统仍需提供 read_folio，不能声称任意文件系统都可做后端。
当前 ramfs 的 ram_aops 提供该操作。实验文件 mmap 的 erofs_is_single_bdev
来源检查仍明确拒绝文件后端，因此没有扩大 mmap 来源准入。

目标语料增加普通 .erofs 文件的 mount/read/stat/xattr，不经过 loop 设备；
131089 字节 payload 用非整页读取并逐字节检查，跨越64 KiB边界。要求坏镜像
EINVAL 后可挂载有效镜像，源路径改名/删除后已挂载数据仍有效，持有文件引用
时 umount 报 EBUSY，释放后可卸载。保留只读拒绝及原始块设备镜像语料，总共
四阶段、唯一 pass 和固定运行器关闭门禁。原生模型不执行挂载，不用于替代
这些目标阶段。

[精确源码预取 40054635351](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40054635351)
日志核实 `e7e5a27fa4cfa28f9a3faae482b8770730c8bfaf` 与
`sha256-u14S/G0GJ2ro3uQ8FVtyaurU2Fhlud/ky/V2AnPrnDY=`。
distro `7471e91` 集成镜像修复、文件后端配置/pin 和同一语料，根仓库 `ca1851b`
单独更新 gitlink/轻量检查。musl f949d1b1 未改。原生参考、属性不可用控制、
双编译器/位宽前端和静态分析、实际两种布局/属性字节及 fsck、差异与格式检查
通过，内核 checkpatch 零错误/警告；新的真实目标仍待异步验收，不复用旧版本
的失败或其它 syscall 通过结果。新版固定 7471e91 已派发：
[wasm32 40055250737](https://github.com/HighCWu/distro/actions/runs/40055250737)、
[wasm64 40055254494](https://github.com/HighCWu/distro/actions/runs/40055254494)。

## 第六十九组：fanotify 标准调用与实际 wasm32 配置修正

复核第六十八组 wasm32 40055250737/job120756784563 的实际日志，镜像已通过
fsck/布局/属性校验，失败发生在 Linux 配置完成之后、编译内核之前。构建明确
调用 wasm32_defconfig，而前两组只修改了 defconfig 和 wasm64_defconfig，漏掉
独立的 wasm32_defconfig；解析后 EROFS 配置断言因此失败。之前“双位宽配置已
恢复”的描述只代表当时意图，不是事实，应以此修正为准，不能归因于 wasm32
内核编译或运行能力。没有删除失败任务或改写已发布历史。

Linux `5cb7904c5` 补齐真正被选中的32位 EROFS XATTR/BACKED_BY_FILE 配置，并与
通用/64位输入保持本组相关选项一致。轻量 CI 从精确 Linux pin 获取三个文件，
检查构建真正选择的 named defconfig，保留逐选项禁用反向控制；它仍只是输入
检查，不冒充 Kconfig 解析。真实构建保留解析后断言，并为缺少的选项明确输出
Missing required kernel config，不再只有安静的 grep 退出码。

同轮新增标准 fanotify_init/mark 支持：Linux `00489bd9d` / `5cb7904c5` 为配置
启用 FANOTIFY 与 FANOTIFY_ACCESS_PERMISSIONS，复用通用 fsnotify、文件描述符、
权限等待/响应和能力检查。这两项通用 Kconfig 默认 n，本次是增加标准能力，
不是声称恢复上游默认。保持 CONFIG_MMU=n，不加宿主事件模拟或项目应用 API。
tombl/musl 已有 sys/fanotify.h 和 src/linux/fanotify.c，本轮没有修改它们，也不
新增函数、头文件或包装；musl 继续固定 f949d1b1。

普通 SDK 双 CPU 语料要求四阶段：

- 子文件 OPEN/CLOSE_WRITE 事件、PID、事件 fd 的 inode/原始二进制内容与 CLOEXEC，
  短缓冲 EINVAL 不丢事件、非阻塞空队列 EAGAIN；允许事件合并，不假定一操作一条。
- 64位 mask 非法高位保留并被拒绝，remove 与 flush 后确实不再收到事件。
- pthread 的实际 open 等待权限答复；非法响应不消耗请求，普通 FAN_DENY 得 EPERM，
  FAN_ALLOW 后真实打开成功，处理器和工作线程全部收尾。
- 临时移除有效 CAP_SYS_ADMIN 时普通 fd 模式被拒绝并恢复原能力，最后移除文件/
  目录、关闭所有 group/事件 fd，再给出唯一 pass。

GCC/Clang 原生仅验证事件 framing 和错误输入，不在没有 CAP_SYS_ADMIN 的宿主
上假装执行真实权限事件，也不打印目标 pass。Clang18/22 双位宽前端与静态分析
通过；微型 Wasm 另直接编译原样 musl fanotify.c，核实 init 号码及 mark 的
64位 mask、后随 dfd/path，wasm32 六机器字连续拆字、wasm64 原生宽参数均正确。
这些不替代真实 Linux 阶段。接口语义见
[fanotify 手册](https://man7.org/linux/man-pages/man7/fanotify.7.html)。

[精确源码预取 40056366901](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40056366901)
实际日志核实 `5cb7904c5505cdbacc9b4702a8bc258ba2dc92cc` 与
`sha256-NEZpP2PZeRKEgpLTd9bbnVwFfeCxXRIF37OKEOxt3IU=`。
distro `f611358` 单独集成源码 pin、断言和 fanotify 语料，根仓库 `b72b255` 更新
gitlink/轻量检查。目标需四阶段、唯一 pass 及固定运行器 machine.closed 门禁；
尚不声称已验收浏览器、FID/mount/filesystem mark、队列溢出或全部权限模式。
新版固定 f611358 已异步派发：
[fanotify wasm32 40056667021](https://github.com/HighCWu/distro/actions/runs/40056667021)、
[fanotify wasm64 40056671716](https://github.com/HighCWu/distro/actions/runs/40056671716)、
[EROFS wasm32 40056676830](https://github.com/HighCWu/distro/actions/runs/40056676830)。

旧版 7471e91 / Linux e7e5a27fa 的 wasm64
[EROFS 40055254494](https://github.com/HighCWu/distro/actions/runs/40055254494) 已读取
job120756790181 实际日志：内联属性、共享属性、普通文件后端跨页数据/引用及
最终清理四阶段、唯一 pass 完整出现。运行器与先前审查版本的三个源文件相同，
关闭失败会使派生失败，因此通过关闭门禁。仅接受旧版 Node wasm64 的这组有界
EROFS 结果，不泛化为遗漏配置的32位或新版 fanotify/EROFS 集成。

## 第七十组：exec 提交后的安全元数据与 fanotify 断言修正

Linux `c41f48430` 修复 Wasm loader 的真实时序缺口：原 copy_args 在
begin_new_exec 之前保存 secureexec 和 execfd，但通用 exec 在后者内部才完成
凭据判定、安装新 mm，并分配解释器执行描述符。因此早期快照可能是旧值。
现在仍在提交前完成参数分配、字符串复制和可恢复错误处理，仅在成功返回后向
新 mm 的既有 exec_args 写入最终三个标量，再实例化用户程序；没有增加提交后
分配、私有应用接口或 musl 公共函数。musl 保持 f949d1b1。

同一 loader 的八字节 Wasm 头过滤改用 memcmp。原 strncmp 会在开头的 NUL
停止，未完整比较头部；宿主 WebAssembly 编译器本来仍验证模块，不能将该修正
描述为修复了可执行任意无效镜像的绕过。该检查现在能更早按 ENOEXEC 拒绝坏头。

新增 exec-security 独立检查：控制程序沿用可选单线程 fork profile，四种 exec
helper 使用普通工具链构建，要求普通执行、setuid 提权后的 AT_SECURE/UID/GID、
secure_getenv、no_new_privs 阻止提权，以及坏 setuid 镜像被拒后保留旧凭据并能
再次 exec。四阶段、唯一 pass 和既有运行器关闭门禁才构成目标验收，不扩大
多线程 fork 支持，也不改变默认 SDK。

本地检查执行提取的实际 loader/helper，模拟通用 exec 提交，覆盖准备失败及
陈旧快照、过早提交、NUL 头过滤三个反向控制；另以测试链接 shim 验证 helper
协议和错误 AT_SECURE。GCC/Clang 编译、Clang18/22 双位宽前端/静态分析和模型
通过，但这些不执行真实宿主 setuid，不替代 Linux/Wasm 凭据切换验收。

第六十九组 fanotify 两个目标的实际日志均通过前两阶段，随后失败于权限答复
断言。复查通用 fs/notify/fanotify/fanotify.c：普通 FAN_DENY 明确返回 EPERM，
不是语料错误要求的 EACCES；父线程打印的 errno=22 来自先前故意发送的非法
响应，不能视为工作线程 open 返回值。distro `38797dd` 修正精确 errno 并增加
join/open 结果诊断，未放宽为任意错误或更改内核语义。后续需真实目标重验。

[源码预取 40058085263](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40058085263)
实际日志核实完整 revision c41f48430682f23277d29dc6ebdc7523cb562219 和
sha256-FnZO6nLTS3HQMnkMISajOJ6b8UK6ouQ/AAA+gvig7+A=。
distro `573a610` 集成精确 pin 和独立检查，根仓库 `05174fb` 更新两个 gitlink
及轻量模型。真实目标异步验收，暂不声称已通过；binfmt_misc 仍未启用，解释器
execfd 的真实端到端用例仍待后续实现和验证。

固定 distro 573a610 的目标均已确认正在运行，没有重复派发：
[exec-security wasm32 40058728775](https://github.com/HighCWu/distro/actions/runs/40058728775)、
[exec-security wasm64 40058733335](https://github.com/HighCWu/distro/actions/runs/40058733335)、
[fanotify wasm32 40058737692](https://github.com/HighCWu/distro/actions/runs/40058737692)、
[fanotify wasm64 40058741398](https://github.com/HighCWu/distro/actions/runs/40058741398)。
旧 EROFS wasm32 40056676830 工作流已成功，但本轮实际阶段日志下载超时，仍不
以工作流状态补作阶段验收；应继续读取同一任务，不重新构建来替代证据。

## 第七十一组：标准 binfmt_misc 解释器执行

Linux `f8489177a` 在通用、实际 wasm32 和 wasm64 三个 defconfig 启用
CONFIG_BINFMT_MISC=y。这是增加官方默认 n 的可选能力，不是声称恢复默认 y。
通用 fs/binfmt_misc.c 不依赖 MMU，复用标准 mount、注册/控制文件和 execve
解释器重写；没有加入 JS 路径路由、用户模拟层、musl 包装或私有应用 API。
配置输入轻量检查及构建后的 .config 断言一起覆盖该选项。

独立 binfmt-misc 语料挂载文件系统，注册魔数 WBIN 的自有八字节载荷和普通
Wasm 解释器，验证实际 exec 而非只读取注册状态。控制器使用既有可选单线程
fork profile，解释器使用普通 SDK；不是实现跨架构指令翻译。要求五阶段：

- 未注册时 ENOEXEC，普通解释器 argv、单条/全局禁用后的 ENOEXEC 和重新启用。
- P 保留调用者 argv[0]，且 AT_FLAGS 的 PRESERVE_ARGV0 位与参数顺序一致。
- O 将实际载荷 fd 放入 AT_EXECFD，核实 inode、设备、八字节内容和非 CLOEXEC；
  setuid 载荷不改变依据普通解释器计算的凭据。
- C 隐含 O，按照 root 所有 setuid 载荷计算凭据，真实 uid1000/euid0、AT_SECURE
  及 secure_getenv 一致，父程序凭据不变。
- F 注册时持有解释器，改名后仍能执行；移除条目后载荷恢复 ENOEXEC，引用和
  文件/挂载点均清理，最后唯一 pass，沿用运行器 machine.closed 关闭门禁。

特意保证子进程 fd0 在 exec 后仍被占用，解释器要求 AT_EXECFD 非零，避免旧版
过早快照的零值恰巧命中实际载荷而误通过。setuid 仅发生在 Wasm 目标中；本地
仅 GCC/Clang 编译及 Clang18/22 双位宽前端/静态分析，不执行宿主 mount/setuid。
Linux 配置补丁 checkpatch 零错误/警告，格式与差异检查通过。distro `cfd8214`
集成精确源码 pin、解析后配置断言和双位宽语料，根仓库 `a47733c` 更新两个
gitlink 与轻量检查；真实目标仍待 CI，不能从静态检查推出五阶段已通过。

[源码预取 40059050287](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40059050287)
实际日志核实 revision f8489177a470eb9df5703fbcc897e97fa93862c7 与
sha256-Fa+OzlPMCThdwArWYRQyFf9Kawp0bPl9/+twyFvkSuM=；不使用猜测的归档哈希。

固定 distro cfd8214 已分别派发并核对检查名：
[wasm32 40059245471](https://github.com/HighCWu/distro/actions/runs/40059245471)、
[wasm64 40059249884](https://github.com/HighCWu/distro/actions/runs/40059249884)。
前者排队、后者运行中；均尚未核实实际阶段，保持异步，不重复派发或取消慢任务。

语义依据[官方 binfmt_misc 文档](https://docs.kernel.org/admin-guide/binfmt-misc.html)
及固定内核 fs/binfmt_misc.c、fs/exec.c；本增量仅使用固定源码已有 P/O/C/F，
不搬入在线最新版额外标志，不涉及新的标准提案。扩展名/掩码、注册错误全矩阵、
命名空间、浏览器和真实翻译器集成未在本组验收范围。

## 第七十二组：标准 Linux keyring 系统调用

Linux `a46fb8746` 在三个 defconfig 启用 CONFIG_KEYS=y，选择通用关联数组后端。
这是增加默认 n 的可选能力，不是恢复默认 y；原配置缺少该子系统，三个标准
add_key/request_key/keyctl 入口因此不可用。复用 security/keys 的密钥类型、
权限、凭据引用、回收和 syscall 实现，未建立 JS 密钥存储或 Wasm 专用密钥 API。
本组不启用 big_key、trusted/encrypted key、通知或持久 keyring 等额外选项。

musl 仍为 f949d1b1，无新增函数、公共头文件或 SDK 包装。测试通过现有 syscall
并显式提供六个 long 参数；cases.h 是不安装的私有语料辅助文件，不是库接口。
沿用可选单线程 fork 控制器，exec helper 为普通 SDK 程序。五个目标阶段要求：

- 匿名 session ring、二进制 user key 的 add/search，以及已存在 key 的 request；
  NULL 长度查询、短缓冲返回总长度且不越界，完整读回保留 NUL/高位字节。
- fork 继承同一 session，子进程更新载荷父进程可见；thread/process ring 不继承，
  子进程切换到新匿名 session 不改变父进程订阅，也找不到原载荷。
- 设为仅 owner 权限后，实际降为 uid1000 的子进程读被 EACCES 拒绝，owner 仍可
  读取；logon 类型即使可创建，也不能通过 KEYCTL_READ 导出载荷。
- 普通 exec 后 session ID 和更新后的二进制内容保留，局部 ring 仍未继承。
- revoke 后不再能搜索到有效载荷，清空 session 链接，最后唯一 pass，并通过
  固定运行器 machine.closed 关闭门禁。

revoked link 在 GC 移除前可返回 EKEYREVOKED，移除后为 ENOKEY；断言明确覆盖
这两个通用实现允许的状态，而不是假定异步回收时序。权限也不能只删除 READ
位就声称拒绝，因为内核对持有 key 的调用者存在读取路径；本组移除全部 possessor/
group/other 位，再使用不同 UID，审查对应 keyctl_read_key 和 key_task_permission。

本地 GCC/Clang 仅编译，不创建/更改宿主密钥。Clang18/22 双位宽前端/静态分析
通过；微型 Wasm 直接编译原样 musl src/misc/syscall.c，执行三种标准入口的
导入检查，核实 syscall 号码、字符串指针、负数 ring ID 和全部六机器字。
常量从精确 kernel UAPI 提取，本地不据此声称 headers_install 或真实 keyring
生命周期通过。实际目标仍需上述五阶段和关闭结果，不能用模型/工作流状态替代。

[源码预取 40059673113](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40059673113)
实际日志核实 a46fb874683d1b5405a4c51b530ad10970e4f9a0 与
sha256-EfYNthKeDFFMVQ8h3DvCTZICX0IehpBcgkGCGJZIAdc=。
distro `746ede4` 集成精确 pin、解析后配置断言及双位宽语料，根仓库 `a9effd1`
更新两个 gitlink 和轻量 ABI 检查；配置补丁 checkpatch 零错误/警告。
此前独立 distro `d5540b5` 另修正 fanotify 失败诊断路径：先确认 join 成功再读取
线程结果，避免在 join 失败时诊断代码本身发生数据竞争，不改变正常权限答复语义。

固定 distro 746ede4 已核对两项检查名与源码版本：
[keyrings wasm32 40059872419](https://github.com/HighCWu/distro/actions/runs/40059872419)、
[keyrings wasm64 40059876610](https://github.com/HighCWu/distro/actions/runs/40059876610)。
两者运行中，尚不作为目标阶段通过的证据。

同轮复查上一版 573a610 的 fanotify 两个任务：40058737692/job120767461553、
40058741398/job120767472463 均已成功，运行器 run-test.js 与 shutdown.js 和本轮
相同，静态门禁确实等待 machine.closed 并将清理失败计为失败。但实际阶段日志
下载本轮超时，故仍未将四阶段记为已验收；后续应读取原任务，不重复派发来替代
缺失日志。既有运行器关闭/错误收尾15项本地回归通过，不替代目标日志。

语义依据[官方 key retention 文档](https://docs.kernel.org/security/keys/core.html)
及固定源码。不宣称外部 request-key upcall、真实认证应用、超时/配额完整矩阵、
浏览器、其它 key 类型或全部 keyctl 子命令已验收。AIO/io_uring 虽为官方默认 y，
其共享 ring/映射与当前独立用户线性内存仍需正确实现；不以打开配置代替这一工作。

## 第七十三组：致命用户执行异常应结束线程组

Linux `11f1bb4d7` 修复 arch/wasm/kernel/process.c 的退出策略：wasm_run_user
在普通用户 entry 返回或执行桥捕获异常后返回，原先 do_exit(SIGSEGV) 只结束当前
任务，可能留下同一进程的其它线程和持续运行的用户状态。现在改用通用
do_group_exit(SIGSEGV)，由已有 signal->group_exit_code / SIGNAL_GROUP_EXIT 和
zap_other_threads 协调线程组收尾及父进程 wait 状态，保留原 local_irq_enable。
没有改变普通 SYS_exit、SYS_exit_group 或正常 pthread 返回的路径。

这仍沿用原执行边界把不可恢复的用户执行返回归为 SIGSEGV 的策略，不新增可恢复
Wasm trap handler，也不声称 unreachable 已按原生硬件精确分为 SIGILL。执行桥
对异常来源的既有分类未在本组重构；未增加应用 API、libc 函数或 softmmu。

独立 user-fault-group 语料让单线程控制器 fork 后 exec 普通 SDK helper，helper
才创建 pthread，故不扩大多线程 fork。要求三个阶段及唯一 pass/关闭门禁：

- worker 执行 unreachable，父控制器必须收到整个子进程的 SIGSEGV 终止状态。
- worker 读取当前线性 memory 末端之外的四字节，要求同样的进程级终止和单次回收。
- worker 直接调用原始 SYS_exit，兄弟线程以 tgkill(sig=0) 的 ESRCH 确认它已消失，
  自己仍能正常以37退出，父控制器继续 wait 成功；不使用 libc 的线程清理来替代。

主线程在前两个用例中定期进入 Linux，仍存活超过有界期限就明确以90失败；
不是靠 watchdog 超时算成功。标准原生 Linux 正向语料通过，host-only 反向
控制将致命 worker 改为原始线程级退出，GCC/Clang 均精确失败于 status=0x5a00
及 fatal worker must terminate its process，未输出 pass。本地仅子进程触发信号，
控制器设置 RLIMIT_CORE=0，以禁用常规 core 文件输出。

Clang18/22 双位宽前端、静态分析通过；汇编检查要求 memory.size 后仍生成 load
及 unreachable。轻量 CI 另从精确 pin 的 process.c 核对 fatal 路径选择，仍非
完整内核运行证明。配置、执行 ABI、musl f949d1b1 及 fork 支持范围均不变。
内核补丁 checkpatch 零错误/警告。

[源码预取 40060490377](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40060490377)
实际日志核实完整 revision 11f1bb4d7b664cb76a53fcdea8ffe5e9f5dcc795 和
sha256-CA0vSEAqcSujafbjjA3SmpKQFDrKZeU7TLv9RcAfXWA=。
distro `2b33c98` 集成精确 pin 和目标，根仓库 `79ecbec` 更新 gitlink 和轻量检查。
本地证据不代替 Wasm 真实三阶段与关闭验收，默认不据此宣称目标已通过。

固定 distro 2b33c98 已核对两路检查名和源码：
[wasm32 40060775430](https://github.com/HighCWu/distro/actions/runs/40060775430)、
[wasm64 40060780025](https://github.com/HighCWu/distro/actions/runs/40060780025)，均在运行。
旧版 573a610 的 exec-security wasm64 40058733335/job120767455438 已成功，
但本轮该日志与两路 fanotify 日志下载均超时（包括有界尾部请求），所以仍保留
“阶段证据待补取”，不把状态绿色当作实际阶段通过，也不因此重派已有目标。

重要边界：架构尚无异步用户抢占，本组只验证会进入 syscall 的兄弟线程被通用
致命信号收尾；无 syscall 的纯 Wasm 忙循环仍可能延迟终止，不能从该修正推出
任意用户线程均可被立即强制中断。浏览器、信号 handler 恢复和完整 core dump
亦未在本组验收。

## 第七十四组：binfmt_misc P 标志的一位截断修复与验收补录

第七十一组 cfd8214 的双位宽任务均实际运行到 P 模式，普通 argv、entry/global
禁用与恢复已通过，helper 以85退出。按 helper 的严格检查顺序，P 的 argc 和参数
内容此前已通过，失败的是 AT_FLAGS 的 PRESERVE_ARGV0 位，不是格式注册失败。
没有将这些失败任务或普通阶段通过改写成全部 binfmt_misc 已可用。

Linux `2e93dea45` 修复真实内核错误：BINPRM_FLAGS_PRESERVE_ARGV0 为1<<3，即8，
而 wasm_exec_args.preserve_argv0 是 unsigned int 的一位 bitfield。把掩码8直接
赋入会截断为0；现在显式 !! 归一化再保存，保持私有布局和执行 ABI 不变。其它
secureexec/have_execfd 的来源本来就是一位布尔字段，无需照搬此转换。

新增轻量回归提取实际两个结构体和赋值表达式，并读取精确内核头中的内部 bit
编号。GCC/Clang 及 Clang18/22 wasm32/64 执行无标志、P、其它位、组合位和全位
模式；恢复旧原始掩码赋值必须明确失败。静态分析、既有 exec commit 模型及
checkpatch 通过，仍需两路真实 binfmt_misc 重验，且不删除 P/AT_FLAGS 断言。

本轮改用可用的 GitHub 日志连接器补取完整已结束作业，解除此前下载超时导致的
证据缺口；未重新构建，也未将连接器取到日志本身当作测试通过：

- 573a610 的 exec-security wasm32 40058728775/job120767449329、wasm64
  40058733335/job120767455438：普通 exec、setuid/AT_SECURE、no_new_privs、坏
  setuid 镜像拒绝后的恢复四阶段，四个 helper 完成标记及各唯一 pass 均齐全。
- 同版 fanotify wasm32 40058737692/job120767461553、wasm64
  40058741398/job120767472463：事件字节/身份、mask/remove/flush、拒绝与允许
  权限答复、能力恢复和最终清理四阶段及各唯一 pass 均齐全。
- f611358 的 EROFS wasm32 40056676830/job120761116656：内联/共享属性、文件
  镜像跨页数据与引用、只读保持及清理四阶段、唯一 pass 齐全，补全真正命名32位
  defconfig 修正后的目标证据；此前仅接受的旧版64位记录仍按原版本保留。

这些作业均成功，实际完整日志无目标 fail/runner cleanup failed/kernel panic。
已核对 f611358 到本轮运行器 run-test.js、shutdown.js、protocol.js 和 Nix 运行
配方没有变化，成功返回仍以等待 machine.closed、清理成功及无后续失败为条件。
因此接受上述各自固定版本的有界 Node 结果；取代此前相应“日志待补取”状态，
不泛化为当前所有源码、浏览器、全部子命令或尚未跑完的其它能力验收。

同轮 keyring wasm32 40059872419/job120770919778 实际失败于第一个阶段之前的
sizing and bounded short read。审查固定通用 keyctl_read_key：user_read 先写入
临时内核缓冲，返回长度大于用户容量时外层直接退出，不执行 copy_to_user。
原语料误以为内部 user_read 的短前缀必然已写入用户区；官方内核
[KEYCTL_READ 说明](https://docs.kernel.org/security/keys/core.html) 明确说不足缓冲
的内容可能以未定义方式被覆盖，因此不能依赖前缀。distro 独立修正该测试：仍
严格要求所需长度、全部容量外哨兵不变及随后完整二进制内容，没有修改 Linux
通用实现或绕过权限/生命周期阶段。原版64位任务仍保留，不因推断会同样失败而
取消；新版需双位宽针对性验收。

测试修正独立提交为 distro `2df2ab4`，随后 `e7a3c3c` 单独更新 Linux 精确 pin，
根仓库 `f26ea71` 更新 gitlink 和位字段回归，均保留已发布历史。
[源码预取 40061310485](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40061310485)
实际日志核实 2e93dea45212407587c989c4567021efcee90f8b 与
sha256-RxjJoelROJI++wa3Dzm7VWBzGkOdwPWC9FodoSg1ddA=。未修改 musl 基线、公开
应用 API、MMU 或多线程 fork 范围；本轮新修正的真实目标仍待异步重验。

固定 e7a3c3c 已派发并核对检查名/源码，四项均在运行：
[binfmt_misc wasm32 40061610158](https://github.com/HighCWu/distro/actions/runs/40061610158)、
[binfmt_misc wasm64 40061614315](https://github.com/HighCWu/distro/actions/runs/40061614315)、
[keyrings wasm32 40061620353](https://github.com/HighCWu/distro/actions/runs/40061620353)、
[keyrings wasm64 40061624565](https://github.com/HighCWu/distro/actions/runs/40061624565)。

## 第七十五组：已有 syscall 接口的 Wasm64 调用点兼容

审查普通程序的调用方式时发现真实 ABI 缺口，而不是缺少新的 libc 包装函数。
musl 的现有 syscall(long, ...) 按六个 long 取参；Wasm64 调用者传连续 int 时，
Clang 将其紧邻存为四字节，而 long 为八字节。原样 musl 函数的微型 Wasm 复现
显示41和43被读取为0x2b00000029，其它参数移位；Clang22 的旧调用还可能在该
函数取参时越界。前几组显式传六个 long 的 raw 测试没有覆盖普通直接调用方式。

musl `015d1ac3` 在 f949d1b1 无新增公共函数的基线上，仅增加 Wasm64 条件下的
现有 syscall 函数式宏：0至6个 syscall 参数分别转为 long 并补零，再调用原有
同名链接符号。内部 syscall.h 在安装自己的既有分派宏前 undef 该宏。没有新增
函数、安装头文件、导出符号或 Linux 扩展包装，src/misc/syscall.c 本身不变；
也没有修改 Clang 全局变参 ABI。wasm32 不启用此宏，以保留显式拆分64位参数的
现有规则。未恢复 pidfd 公共包装，也未删除或改写已发布提交。

这属于已有接口的架构/ABI 调用路径兼容修正，不是把 syscall 实现搬进 libc。
内核仍使用同一标准 syscall 号/执行入口。直接调用需重新编译才能受益；已按
机器字调用的函数入口及已有二进制 ABI 不变。取函数地址、显式 (syscall) 或
绕过头文件的低级调用仍须使用原变参签名和正确机器字，不能声称自动修复任意
函数指针调用。函数式宏亦沿用标准预处理规则，含顶层逗号的复合字面量参数须
额外括号；未引入项目专用开关/调用接口来隐藏该边界。

Clang18/22 的实际 C/C++ Wasm 模块核实两种位宽、0至6参数、连续 int、负数、
unsigned int 高位、指针、单次求值、嵌套调用、C++ ::syscall/nullptr 及函数地址。
链接的是原样 syscall.c；64位反向控制移除新宏，必须出现明确机器字错位或该
取参函数的越界，不能以任意编译失败/超时当作检出。wasm32 正向保持原函数路径。
普通 SDK 的 C 语料另以 GCC/Clang 原生运行，并通过目标前端/静态分析；fork 补丁 dry-run 仍可
应用。它们不替代完整新 sysroot 的真实目标运行。

新增 public-syscall 普通 SDK 目标，不使用 fork profile，要求三个阶段：直接
getpid 和原函数符号、负 int/errno；普通 int 参数 close_range 只关闭指定 fd，
非法 flags 保留其它 fd；getcwd 的指针/int 容量及前后哨兵。最后唯一 pass 和
machine.closed 关闭门禁；没有把所有应用改成显式 long 来绕开 ABI 缺陷。

[源码预取 40063244038](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40063244038)
实际日志核实完整 musl revision 015d1ac3f4fd58059cfc911c2dd422d20924a62c 与
sha256-MabCOnf3A/ewGtWcKg51FOV5f86akgEhQvY9+f1F1l0=。
distro `e8967a9` 集成精确 pin 和普通目标，根仓库 `e0a12f3` 更新两个 gitlink 与
轻量检查。Linux 仍为2e93dea45，保持 NOMMU，不新增 softmmu 或多线程 fork。
新 musl/sysroot 的真实目标仍待异步验收。

固定 e8967a9 已派发并核对检查名与源码：普通目标
[wasm32 40063773897](https://github.com/HighCWu/distro/actions/runs/40063773897)、
[wasm64 40063778273](https://github.com/HighCWu/distro/actions/runs/40063778273)，以及
既有可选 fork profile 回归
[wasm32 40063781795](https://github.com/HighCWu/distro/actions/runs/40063781795)、
[wasm64 40063785076](https://github.com/HighCWu/distro/actions/runs/40063785076)。
四项运行中，不重派相同源码/检查，也不等待它们才继续独立工作。

本轮另补核实此前六项成功作业的完整日志，不以绿色状态代替阶段：

- e7a3c3c 的 binfmt_misc wasm32 40061610158/job120776194063、wasm64
  40061614315/job120776213331：五阶段完整，含 P/AT_FLAGS、O/实际 fd 身份字节、
  C/凭据及 F/改名后的解释器，注销/清理和各唯一 pass 均齐全。
- 同版 keyrings wasm32 40061620353/job120776220981、wasm64
  40061624565/job120776243713：五阶段完整，含实际权限拒绝、logon 不可读、fork
  共享/隔离、exec 保留和撤销清理，各唯一 pass 齐全。
- 2b33c98 的 user-fault-group wasm32 40060775430/job120773640428、wasm64
  40060780025/job120773655466：三阶段完整，致命故障结束进程、raw SYS_exit 保留
  兄弟线程和父进程后续 wait 各自通过，唯一 pass 齐全。

六个 Heavy/工作流成功，完整日志无目标 fail/关闭错误/panic；未变运行器仍在
成功前等待 machine.closed。仅接受这些固定版本的有界 Node 结果，不扩展到
新 musl、浏览器、纯忙循环抢占、其它 key 类型或任意解释器/完整认证应用。

## 第七十六组：恢复上游 util-linux 的 System V IPC 工具

内核已有 System V 消息队列与信号量支持，但 util-linux 配方仍保留旧的
`CONFIG_SYSVIPC` 关闭假设，显式禁用 ipcmk、ipcrm、ipcs、lsipc；生产程序检查
还要求 `/proc/sysvipc` 不存在。distro `175976e` 删除四项过期禁用配置及只为禁用
lsipc 添加的 configure 补丁，恢复上游默认探测，更新生产工具清单。`0c8e540`
修正检查脚本的 ShellCheck 问题，根仓库 `5103547`、`b26e3f1` 分别集成源码和
后续 pin。没有改 util-linux 的 C 实现、增加 musl 包装或伪造共享内存能力。

保持现有完整 util-linux 2.42.2 产品及其依赖，不构造仅供测试通过的裁剪包。
下载的官方归档 SHA256
`03a05d3adf9602ef128f2da05b84b3205ce60c351e5737c0370f74000679ce8a`
与 kernel.org 的 sha256sums.asc 相符；未核验 PGP 签名，不将此描述为签名认证。
版本及 Nix 解包 hash 不变，配置补丁对该源码 dry-run 通过。

新的私有 ipc 检查直接运行四个真实程序，要求四阶段：创建消息队列/两个信号量
并核对对象身份与元数据；smartcols 支持的 lsipc 输出；SysV SHM 返回 ENOSYS
且不破坏已创建队列；按精确 ID 删除并确认列表中不再存在对象。允许合法 ID 0，
只清理本次创建的对象，不使用 ipcrm -a/--all。这不限制已有 POSIX shm 文件路径。
检查必须有唯一 pass 并通过既有机器关闭门禁，不能只看工具 --version。

自有检查和主仓库模型为 MIT。ShellCheck、shfmt、Nix 格式检查、补丁 dry-run
与编排模型均通过；模型覆盖错误工具身份、错误信号量数量、错误 SHM errno 和
删除后残留，且绝不创建/删除宿主 IPC 对象。模型不是目标应用验收。
固定 `0c8e540` 的
[util-linux-check-ipc 40065795347](https://github.com/HighCWu/distro/actions/runs/40065795347)
与 [util-linux-check-programs 40065799646](https://github.com/HighCWu/distro/actions/runs/40065799646)
已异步派发，目标结果待核实。这次恢复现有 wasm32 完整产品；不宣称已有 wasm64
util-linux 或浏览器验收。双位宽内核 IPC 能力与工具产品覆盖分开记录。

同时补录第七十五组的真实结果：固定 e8967a9 / musl 015d1ac3，普通 Node
wasm32 40063773897/job120782670716、wasm64 40063778273/job120782684582
完整三阶段及唯一 pass 已核实；可选 fork wasm32
40063781795/job120782700683、wasm64 40063785076/job120782708368
完整十二阶段（含 raw clone、clone3、exec、拒绝与恢复）及唯一 pass 已核实。
四个 Heavy 均成功，日志无目标失败；未变运行器成功前等待 machine.closed，
据此接受这些固定版本的 Node 结果，不泛化到浏览器或新 IPC 工具。

第七十六组随后已验收：固定 0c8e540，IPC 40065795347/job120788729373 的
四阶段和唯一 pass 完整；生产工具集 40065799646/job120788732439 的普通
TERM/HUP、ALRM 与 INT 各24轮、其它 uuidd 收尾、unshare 四流程、fsck 五流程
及终端唯一 pass 均已从实际日志核实。两项 Heavy 成功且无目标失败/关闭错误，
未变运行器仍等待 machine.closed；只接受该版 wasm32 Node 产品，不泛化到
后续 seccomp 内核、wasm64 或浏览器。

## 第七十七组：接通通用 seccomp 严格模式及适配层入口

Linux `e3afb3e64` 声明 HAVE_ARCH_SECCOMP，沿官方 Kconfig 的默认 y 启用
SECCOMP，复用 kernel/seccomp.c 的严格策略、prctl/seccomp 入口、任务状态与
违规 SIGKILL 退出。没有自写 syscall 允许列表或启用 BPF 过滤模式。
Wasm 信号处理经既有执行桥返回，不存在 rt_sigreturn syscall；架构 seccomp.h
将该槽设为通用策略循环的负终止标记，只允许已有 read/write/exit，不借用别的
syscall 号码，也不把 139 变成可用接口。测试要求处理信号后仍能继续 read/write。

静态 review 发现不能只启用配置：fork/clone3 适配层会先校验参数、读取描述符，
甚至直接返回 EINVAL/EOPNOTSUPP，这会跳过严格策略应有的终止。Linux
`97d6ca9ea` 增加私有只读 seccomp_strict_v1 执行查询；配套运行器在受限状态下
直接将原调用交给普通内核入口，由既有 ptrace/seccomp 处理，再决定是否执行。
它不在宿主复制策略、不预读 clone3 指针，也不先启动 continuation。旧 checkpoint
路径同样先以对应的 clone 进入内核，不能利用坏描述符提前返回绕过策略。
该查询不是公共应用 import 或新的 Linux syscall；内核与运行器必须成对使用。
不以新内核搭配历史运行器作为已支持的安全配置。

distro `5a020c8` 集成固定内核与配套运行器、解析后 SECCOMP=y/SECCOMP_FILTER=n
断言及独立双位宽负载。musl 保持 015d1ac3，不新增函数、头文件 API 或包装。
根仓库 `ce948ae` 单独更新两个 gitlink 与轻量检查。普通应用仍使用标准 syscall/prctl；
仅验证用控制程序沿用已有可选单线程 fork
profile。没有扩大多线程 fork、内核 softmmu 或线性地址能力。

真实负载要求四阶段及唯一 pass/机器关闭：

1. 查询初始模式、拒绝坏 flags/参数和未支持的 filter，且失败不改变模式。
2. 分别用 seccomp 和 prctl 进入严格模式，实际 read/write/raw SYS_exit 成功，
   外部信号 handler 返回后仍能继续执行。
3. getpid、exit_group、试图解除限制、未实现的139，以及坏参数 clone/clone3/
   旧 checkpoint 均被终止，不能用错误返回冒充策略执行。
4. 父进程模式保持未受限，连续 fork/wait、单次回收与 fd 清理正常。

367 项宿主回归、源与测试两套 TypeScript 检查、固定 oxfmt/Nix 格式检查及
工作流静态检查通过。额外模型编译精确内核的严格策略函数与架构头，对全部本表
号码及负数/越界号码核对允许、模式转换与 SIGKILL；故意将一个普通 syscall
加入允许列表的对照被拒绝。GCC/Clang 仅编译真实负载，不在宿主执行 seccomp；
Clang18/22 双位宽前端与分析通过。模型、编译与绿色工作流均不能替代真实阶段。

[源码预取 40066542208](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40066542208)
完整日志核实 97d6ca9eadb53fdabb2e27b44e8ec90225e81415 与
`sha256-YkyeLleqv4/Qd9COdzyatXkYtCbIqqRurqVa8Nx6/wk=`；此前 e3afb3e64 的
预取不是最终适配入口版本，不用于集成。固定 distro 5a020c8 的
[wasm32 40066816471](https://github.com/HighCWu/distro/actions/runs/40066816471)
与 [wasm64 40066820823](https://github.com/HighCWu/distro/actions/runs/40066820823)
已核对源码和 seccomp-strict-check-runtime / seccomp-strict-wasm64-check-runtime
检查名，正在运行，真实阶段与关闭结果尚待验收。

依据[官方架构要求](https://kernel.org/doc/html/latest/userspace-api/seccomp_filter.html#adding-architecture-support)
与精确 kernel/seccomp.c。过滤模式仍缺架构标识等必要条件，不能用现有
syscall_get_arch 的0占位冒充正式 ABI。严格模式也不等于完整沙箱，不宣称处理了
所有执行桥边界、浏览器、任意线程组合或不受信任程序的整体隔离。

## 第七十八组：完整 util-linux 的匹配 wasm64 产品

此前接受的是 wasm32 完整 util-linux。distro `9d7712d` / 根仓库 `1b6e6fc`
补齐 util-linux-wasm64，直接 override 同一完整配方，不新增裁剪版、禁用额外工具
或替换成 BusyBox applet。五类原有检查 text/spawn/pty/programs/ipc 全部继承。
本轮没有修改内核或 musl，也不把构建属性的存在当成程序已可运行。

闭包逐项选择 stdenv、platform、file/libmagic、zlib、ncurses、readline、BusyBox
和 vm-test 的 wasm64 版本；SQLite 使用已经安装的 sqlite3-wasm64.dev 头文件、
静态库及可重定位 pkg-config 元数据，不借用 wasm32 库或只传 SQLite CLI 输出。
新增 file-wasm64 同样复用完整原配方，使用匹配 zlib、BusyBox 与运行器。
没有升级源码或修改上游应用 C 实现；file 的 libseccomp 集成仍关闭，内核严格
模式不能冒充应用需要的 BPF 过滤功能。

自有 MIT 构建检查在最终安装/strip 后读取所有 Wasm 模块，包括私有测试 helper，
要求共享 env.memory、正确地址位宽与平台上限，同时检查实际 file/BusyBox 依赖。
通过精确构建工具链的 llvm-readobj 读取本产品及五项库依赖的每个静态归档成员，
要求全部为相同位宽 Wasm，不允许只看首个成员便接受混合库。意外 ELF、无目标
模块、失败的目录枚举或读取都拒绝。它只检查文件，不执行目标程序。

本地对真实编译的 wasm32/64 小模块与对象运行同一安装检查，混合 helper、
混合依赖模块、混合静态库、ELF 及空输出对照均拒绝。原有二进制检查回归、IPC
编排模型、ShellCheck、shfmt、Nix 格式与工作流检查通过。这些不证明完整 Nix
构建闭包或目标程序已运行；需要公开 CI 的实际构建、运行阶段与机器关闭结果。

固定 9d7712d 已分别派发
[IPC 40067581710](https://github.com/HighCWu/distro/actions/runs/40067581710)、
[完整工具集 40067584929](https://github.com/HighCWu/distro/actions/runs/40067584929)、
[file 检测 40067588207](https://github.com/HighCWu/distro/actions/runs/40067588207)。
三项真实结果待验收，不据此替代旧版 wasm32 验收，亦不宣称其它三个 util-linux
检查或浏览器已经通过。本轮没有将默认 wasm32 发布仓库或 rootfs 改为混合位宽，
新增的是可独立构建并通过匹配 wasm64 安装工具组装的完整目标软件包。

前一组 seccomp 两项仍在运行，无明确失败，不取消、不重派，也不等待其结果才
推进本独立应用闭包。主仓库 ce948ae 的轻量 CI 40066837498 已成功，但它不是
seccomp 真实目标运行证据。

## 第七十九组：既有 clone 的固定可选参数位置

核对 tombl/musl 的 src/linux/clone.c，发现其按每个 flags 单独消耗变参，导致
正常 `parent_tid, tls, child_tid` 固定布局被压缩。CHILD_SETTID 单独使用时会把
第一个占位参数当 child_tid；PARENT_SETTID 与 CHILD_SETTID 同时使用时，会把
TLS 占位当 child_tid。旧 clone-tid 检查只传两个可选参数，恰好掩盖了这个错误。
这不是内核 TID/pidfd 写入未实现，也不应靠要求应用使用项目特有缩参约定解决。

musl `37ad2811` 只在已有函数内增加 Wasm 调用路径兼容：读取所需的固定参数
前缀，没有可选 flags 时不读取变参，仅需 parent_tid 时不多读后续参数，需要
child_tid 时消费前两项占位再取第三项。保留现有 CLONE_THREAD/SETTLS/
CHILD_CLEARTID 拒绝政策，非 Wasm 分支保持原样。没有新增公共函数、公共声明、
导出或 pidfd 包装，没有改变底层 Wasm callback clone syscall 布局。

musl 的项目上游仍是 tombl/musl，不切换为官方仓库。共享历史中的
fa4a8abd06a401822cc8ba4e352a219544c0118d 已包含正确的参数前缀处理，可与
[Linux clone 调用约定](https://man7.org/linux/man-pages/man2/clone.2.html) 交叉核对。
新模型移除 Wasm 新分支后的全文 SHA256 必须等于此前 015d1ac3 的文件，约束
非 Wasm 行为与函数集合不被顺带改写。使用旧缩参写法的源代码需补齐占位，
不通过猜测参数数量同时兼容两种相冲突的约定。

distro `4aaef0e` / 根仓库 `73cff39` 集成新 musl、修正旧 clone-tid 的 NULL TLS 占位，并增加普通
SDK 双位宽负载，不启用 fork continuation：无可选字、parent-only、child-only、
parent+child、pidfd+child 五种正常调用均沿真实公共 clone 及原内核路径。
要求 callback 执行前 TID 已写好、保留占位/相邻 guard 字节，pidfd 为 CLOEXEC，
waitid(P_PIDFD) 指向精确子进程，单次回收和 fd 清理正确。CLONE_VM callback
只访问共享数据并返回，不调用 libc、修改 TLS 或执行父进程 C 栈。

本地直接编译原样 musl clone.c 和 syscall_ret.c，只有底层 __clone/锁等为模型：
Clang18/22、Wasm32/64 都核对完整转发元组，旧压缩分支必须在 child-only 调用
失败，既有 NULL stack/SETTLS 拒绝不得进入底层。真实负载 GCC/Clang 原生参考
通过，Wasm 双位宽前端/静态分析、既有 syscall 字宽检查、fork profile 补丁
dry-run 和格式/工作流检查通过。这些仍不能替代真实 Wasm 目标及关闭验收。

[源码预取 40068655017](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40068655017)
日志核实完整 revision 37ad281149f20e32c41990205ba384c21af03ff0 与
`sha256-r+3SxsQRFJXa5+eXUvFWAmp3sLkswKMDjIu3FQNW7ow=`。
固定 4aaef0e 的
[wasm32 40069040600](https://github.com/HighCWu/distro/actions/runs/40069040600)
与 [wasm64 40069044706](https://github.com/HighCWu/distro/actions/runs/40069044706)
已核对 clone-arguments-check-runtime / clone-arguments-wasm64-check-runtime
及源码。两项现已完成：实际 Heavy 日志 job120798360914 / job120798371120
均核实三个阶段：无可选参数及 parent-only 前缀、固定位置的 child identity 与
未触碰占位参数、pidfd/child_tid 组合及精确 wait/描述符清理，各有唯一终端 pass。
工作流与 Heavy 均成功；固定运行器在成功退出前等待 machine.closed，关闭失败
会拒绝通过。接受固定 4aaef0e / musl 37ad2811 的双位宽 Node 结果，不扩大
多线程 fork、公开 clone 的被拒 flags 或浏览器范围。

另外已补录此前结果：固定 5a020c8 / musl 015d1ac3 的 seccomp 严格模式
wasm32 40066816471/job120791784487、wasm64 40066820823/job120791788549
四阶段及各唯一 pass 完整，两项 Heavy 成功，未变运行器关闭失败会拒绝成功且
等待 machine.closed，故接受这两项固定版本 Node 结果。它们不证明新 musl
或 BPF 过滤模式。固定 9d7712d 的 file-wasm64 40067588207/job120794049428
实际终端唯一 pass 已核实，对应固定脚本的文本/gzip/Wasm 三种检测及同一关闭
门禁；不将 file 单独成功当成完整工具集通过。随后 util-linux-wasm64 两项
40067581710/job120794015733、40067584929/job120794031118 已明确失败：
完整程序及静态库位宽门禁先通过，但 APK 检查报告 root/lib/liblastlog2.la 含有
Nix store 引用，尚未执行目标程序。需修正部署元数据，不放宽门禁或禁用 lastlog2。
主仓库 1b6e6fc 的轻量 CI 40067606246 成功也不替代这些真实阶段。

## 第八十组：完整工具集的 lastlog2 部署元数据修复

第七十八组固定 9d7712d 的 wasm64 IPC/完整工具集作业均实际失败在 APK 打包，
不是程序阶段失败：日志已输出完整模块与归档成员 ABI verified，随后拒绝
root/lib/liblastlog2.la 的 Nix store 引用。不能以成功编译或 file 单独通过，
宣称完整 util-linux 已运行；也不能通过去掉 lastlog2、删除静态库或放宽打包检查
取得绿色结果。

结合 SQLite 开发输出的可重定位 .pc，问题指向构建时展开的 SQLite 库目录被
libtool 记录到安装元数据。distro `56ed1d1` / 根仓库 `286d605` 将这一个已知
依赖的 canonical `/lib` 和 `lib/pkgconfig/../../lib` 两种构建目录形式，在
liblastlog2.la 中归一化为目标 `/lib`。既有已是 FHS 的内容保持不变；不改 SDK
原始 .pc，不删 `-lsqlite3/-lm/-pthread` 依赖，更不替换任意未知 Nix 路径。
使用 replace-quiet 是因为原 wasm32 配方已有正常 FHS 元数据，不应要求它出现
泄漏后再才能构建。

同一 postFixup 继续运行原 store-reference 拒绝脚本及全部模块/归档位宽检查，
APK 阶段的独立门禁也保留。元数据替换模型核对两种已知路径可修正、正常 FHS
无变化、未知来源仍被真实拒绝脚本拒绝；Shell/Nix 格式、既有位宽/错误混入
模型和 IPC 编排检查通过。实际 Nix 替换、完整打包与真实运行仍由新 CI 验收。

仅针对已失败的两项派发固定 56ed1d1 的
[IPC 40069738510](https://github.com/HighCWu/distro/actions/runs/40069738510)、
[完整工具集 40069743091](https://github.com/HighCWu/distro/actions/runs/40069743091)。
它们现在使用已集成的 musl 37ad2811；旧 file-wasm64 验收不能自动覆盖此版本。
第七十九组 clone 双位宽目标继续独立运行，不重复派发、不等待它们才修复此
明确失败，也不把修复模型通过写成目标通过。自有修复/模型为 MIT，内核和应用
C 实现、工具集与许可边界不变。

两项复验现已完成。IPC 40069738510/job120800477181 的实际日志核实四阶段：
创建/身份/信号量元数据、lsipc 活对象、SHM 拒绝不影响已支持对象、精确 ID 删除
及清理；完整工具集 40069743091/job120800471795 核实 uuidd TERM/HUP、ALRM
与 INT 各24轮、inactivity/long timeout/daemon shutdown，unshare 四阶段和
fsck 五阶段，最后各唯一 pass。两项 Heavy/工作流成功，同一未变运行器等待
machine.closed 且拒绝关闭错误。故接受固定 56ed1d1 / musl 37ad2811 的这两项
wasm64 Node 结果，打包修复未移除工具或放松门禁；不泛化为所有工具行为、
浏览器、其它检查或后续内核版本均已验收。

## 第八十一组：文件私有复制映射接受标准提示标志

Linux `cc8c3813d` 修正实验文件 mmap/mmap2 对 flags 的过严检查。此前要求
flags 完全等于 MAP_PRIVATE，令 MAP_POPULATE 等不改变私有映射类型的标准请求
直接 EINVAL。现在允许 MAP_POPULATE、MAP_NONBLOCK、MAP_NORESERVE、MAP_STACK、
MAP_DENYWRITE、MAP_EXECUTABLE 单独及组合使用。该路径仍在发布地址前完成有界
读取及复制：不存在尚待填充的页，提示不提供按需分页、无阻塞 I/O、额外保护、
文件写锁或执行权限；MAP_EXECUTABLE 不等于 PROT_EXEC。

这是执行模型已有能力的参数兼容修正，不是把全部文件 mmap 打开。仍要求
独立候选配置、认证的单设备 EROFS 不可变来源、每次至多128 KiB、独立私有副本；
共享、可执行、固定映射和 MAP_LOCKED 等未支持标志继续拒绝。原完整 flags 保留
给 security_mmap_file，不为通过验证而剥除安全检查参数。默认内核、musl 与
已发布应用接口没有变化。通用 Linux NOMMU 的复制式文件映射可参考
[官方文档](https://docs.kernel.org/admin-guide/mm/nommu-mmap.html)，但不能据此
认定本项目已具备其完整 VMA、可变文件或共享后备模型。

真实 C 函数的 GCC/Clang 模型覆盖各提示/组合、原参数送达 LSM、MAP_LOCKED
继续拒绝，以及原分配失败、短读、fatal signal、资源回收和预算边界。恢复旧的
精确 flags 检查会令新用例失败；Wasm32/64 前端与静态分析通过，异常退出真实
Wasm 小实验核实资源归零，其故意移除清理的反向控制仍检出泄漏。匿名 mmap
参数模型及 mremap/munmap/madvise/msync 十项本地回归也通过。这些不是目标 VFS
或启动验收。

公开源码预取 40160553549/job121071011202 已核实完整 revision
cc8c3813d235095231895e9f208593416eef313f 与
`sha256-0YRntovVLcWpfrAWpV1OxZmZOAgSqZebWziPPiaqiEA=`。distro `deea6fc`
集成该 pin，并让现有标准文件映射负载实际请求这些提示，核对内容、源文件及
fd position 不变、修改私有副本和 munmap 清理；新增独立阶段标记。根仓库
`a527315` 同步 gitlinks，并将该实际负载纳入既有双位宽前端/静态分析。
独立双位宽
[wasm32 40160719533](https://github.com/HighCWu/distro/actions/runs/40160719533)、
[wasm64 40160723110](https://github.com/HighCWu/distro/actions/runs/40160723110)
的 mmap-benchmark-check-file / mmap-benchmark-wasm64-check-file 异步验收
candidate、legacy module、default 配置与原生命周期回归；实际阶段
及关闭结果尚待核实，不以源码 hash 或宿主模型通过代替目标通过。自有负载及
测试沿用 MIT，必要内核改动沿用 GPL，未新增 musl 函数。

## 第八十二组：普通文件的 NOMMU 私有复制

Linux `0bbaf824b` 推进实际文件 mmap/mmap2 能力，不再把首批不可变 EROFS 来源
限制当作永久政策。对照当前 `mm/nommu.c::validate_mmap_request/do_mmap_private`
与[官方 NOMMU 文档](https://docs.kernel.org/admin-guide/mm/nommu-mmap.html)，
复制式私有映射可以读取普通文件，后续写入不必反映到已返回的副本。这不同于
共享文件映射、按需页缓存别名或保证读取期间绝对一致的快照。

候选标准入口检查普通文件、fd 读权限、can_mmap_file、FMODE_CAN_READ；文件系统
提供 mmap_capabilities 时须含 NOMMU_MAP_COPY，否则按上游普通文件默认 copy
能力处理。只有直接共享能力的驱动不可强制复制；不可映射/无读取/无 copy 能力
返回 ENODEV，原类型拒绝、旧用户模块能力拒绝与 LSM 检查保留。不存在从 Wasm
用户指针直接访问内核文件页的捷径，也不通过宿主路径读取文件。

标准入口的一次 kernel_read 返回多少有效字节，就仅把这些字节交给同步初始化器，
初始化器先清零全部目标区域；负读取错误不发布。短读、零读取、空文件和 EOF 后
区域遵循此 NOMMU 复制行为，不伪造 MMU SIGBUS/截断失效。已有副本保持独立，
后来映射重新读取文件；并发改写的观察语义仍由底层读取决定，不承诺一致性快照。
读取返回前继续持有生产者、文件引用、staging 与预算，初始化异常/退出收尾仍复用
原任务所有权记录。原私有测试入口通过严格模式保留认证来源、稳定大小和异常短读
报错语义，其来源认证未被标准入口的新能力绕过。

限制仍包括候选默认关闭、每次128 KiB/全局在途512 KiB、直接线性地址、RO/RW
无强制保护；没有共享、执行、固定映射、写回或完整通用 NOMMU VMA。musl、默认
SDK 导出与新应用 API 均未改变。生产者在途真实设备压力和默认执行协议发布门禁
仍未因本轮演进而完成。

真实函数 GCC/Clang 模型及双位宽前端/静态分析通过，涵盖文件能力拒绝、普通来源
接受、一次短读/零读取、严格模式不变、预算/fatal signal/分配及复制失败回收。
恢复旧来源白名单、恢复严格读取或恢复旧 flags 检查均会令正向模型失败。实际 C
复制函数和 JS 桥的小型 Wasm 异常回归双位宽资源归零，旁路清理的反向控制仍泄漏。
这不证明真实 VFS、文件系统或设备目标已运行。

distro `7134a84` 固定内核，并扩展标准目标：普通磁盘映射、可写文件修改后新旧
副本分离、截断/EOF/空文件补零、unlink/close 后存活、写入副本不回写、fd position
和清理。Zstd 仍强制原标准 mmap，普通磁盘与可写文件字典五种合规尺寸须与 malloc
交叉解码一致，超限仍报错；默认内核拒绝对照未取消。原生 Zstd 的13项编排/反向
检查、ShellCheck/shfmt、Nix/JS 格式通过，不将宿主 CLI 视为 Wasm 文件系统证据。
既有浏览器断言和精确测试名门禁同步更新，未在本地启动重型浏览器，也未把旧浏览器
验收升格为本次通过。

公开预取 40161284432/job121073194313 核实完整 revision
0bbaf824badf2a1a3c0119b2c3e1343e0b80b5a9 与
`sha256-BQT7mtESdCcLAgeWlLbo1C2/KXX+R3C77Jqx1bJD7Gg=`；根仓库 `33f3d55`
单独同步两个 gitlink。标准文件
[wasm32 40161527731](https://github.com/HighCWu/distro/actions/runs/40161527731)、
[wasm64 40161531608](https://github.com/HighCWu/distro/actions/runs/40161531608)，
Zstd 文件
[wasm32 40161534999](https://github.com/HighCWu/distro/actions/runs/40161534999)、
[wasm64 40161538383](https://github.com/HighCWu/distro/actions/runs/40161538383)
已异步派发，须分别核实
新增可变文件阶段、原候选/旧模块/默认配置/生命周期标记，以及 Zstd 的五种快照
尺寸、五种普通文件尺寸、超限拒绝、最终唯一 pass 和机器关闭。尚不宣称目标通过。
自有负载/编排/文档沿用 MIT，必要内核改动沿用 GPL，不新增 libc 公共函数。

## 第八十三组：已有 mmap64 别名的 Wasm 声明门控

musl `0771c6eb` 修正已有大文件兼容别名被错误包含在 `#ifndef __wasm__`
保护接口组内的问题。直接上游 tombl 的旧提交 `40851de5` 已有
`#define mmap64 mmap` / `#define off64_t off_t`，不是从官方 musl 另搬一个
新函数，也不是新增公共 API、包装或导出符号。源码仅移动该组的闭合条件，
原别名内容和 `_LARGEFILE64_SOURCE` 条件原样保留；mprotect/mlock/mincore 等
接口的 Wasm 门控不变，不改变默认文件映射政策或任何 syscall 实现。

宿主头文件检查在 Wasm32、Wasm64 和非 Wasm x86_64 目标核对原 mmap 原型、
64位 off64_t；缺少 feature macro 或故意隐藏 mmap64 时必须编译失败。
Wasm 的 LLVM IR 仍只引用 `@mmap` 而非 `@mmap64`，证明未引入新函数调用 ABI。
Wasm mprotect 引用继续编译失败，非 Wasm 则保持可见，防止顺便开放未实现的
保护接口。Ruff、既有文件映射真实 C 前端/静态分析和原函数模型通过；可选
fork-continuation 补丁在新源码 dry-run 也通过，不将这些本地证据写成启动验收。

公开预取 40161964800/job121075227622 已核实完整 revision
0771c6eb78319d7af6df3d7b27709345d2dd0fc2 与
`sha256-mvnSKVBj04ZOqYfALZO9pCMBc8J1/CT//T5+qq/FoVE=`。distro `9e8a6fd`
固定该源码，并让现有 EOF 映射 helper 实际使用 mmap64/off64_t；包含4 GiB文件
offset 的零填充检查，截断到低位后会读到非零源内容而不能误过。根仓库 `ae9251e`
独立更新 pin 和头文件/IR 回归。普通文件内核仍固定第八十二组的 `0bbaf824b`。

固定 9e8a6fd 的标准文件
[wasm32 40162090287](https://github.com/HighCWu/distro/actions/runs/40162090287)、
[wasm64 40162094045](https://github.com/HighCWu/distro/actions/runs/40162094045)
复验已异步派发，待实际阶段、唯一 pass 与关闭门禁核实；不能将上一个 musl
版本的运行结论自动用于新组合。原 7134a84 的标准/Zstd 检查仍独立在途，未取消
慢任务或重复派发同版本同检查。已有许可证与无新增 libc 函数约束保持。

补录：40162090287/job121075661515 的完整实际日志现已读取，确认 candidate
的可变文件/提示/不可变副本三个阶段及唯一 pass，default 与 legacy 各自拒绝
阶段及唯一 pass，vfs-lifetime 的并发预算/回滚阶段及唯一 pass，四次运行齐全。
该 Heavy 成功，固定运行器先等待 closeTestResources（含 machine.closed），
再以无启动/关闭失败决定成功退出，相关运行器源码未改变。因此记录 9e8a6fd 的
wasm32 标准文件组合验收；wasm64 的 success 元数据仍不能代替其未读取的阶段，
也不把这组旧源码证据用于后继默认 SDK 或 WRITE-only 新负载。

## 第八十四组：恢复官方默认的 FUSE passthrough 条件

核对官方 `fs/fuse/Kconfig` 后，FUSE_PASSTHROUGH 默认 y，依赖 FUSE_FS 并选择
FS_STACK。Wasm 三份配置却显式关闭此项。Linux `ad56d20e9` 仅删除这三处覆盖，
恢复上游条件选择，不复制或替换上游 FUSE/backing-file 实现，不启用 MMU 或
io_uring。Kconfig 没有直接 MMU 依赖不等于 Wasm 已通过编译/运行，仍须目标验收。
distro 的构建门禁核对最终 `.config` 中 FUSE_PASSTHROUGH/FS_STACK 均为 y，
保留原 MMU=n 检查，不仅凭输入 defconfig 宣称功能已启用成功。

根据[官方说明](https://docs.kernel.org/filesystems/fuse/fuse-passthrough.html)
和固定源代码审查，服务端须在 INIT 协商 FUSE_PASSTHROUGH 与 max_stack_depth，
通过标准 FUSE_DEV_IOC_BACKING_OPEN/CLOSE 管理后备文件 ID，再在 OPEN 回复中
选择 FOPEN_PASSTHROUGH。上游的 CAP_SYS_ADMIN、普通文件和堆叠深度检查均保留。
本轮不放宽权限，也不新增 libc 函数或应用专用 ioctl。

distro `d077527` 增加双位宽、普通 SDK 的实际用户态服务程序：挂载仅发生在
Linux/Wasm 目标系统，两个 Linux CPU，pthread 处理标准 /dev/fuse 协议。
初始化回复必须保留 FUSE_INIT_EXT 才会解析 flags2；不协商 writeback cache。
服务端对任何 FUSE_READ/FUSE_WRITE 数据请求返回 EIO 并记错，因此不能通过
模拟数据回退伪装 passthrough。实际目标要求三个阶段及唯一 pass/机器关闭：

1. 协商、未知注册 flags/无效 fd 的错误、注册后关闭原 fd 仍保有后备引用。
2. 标准 pread/pwrite 往返正确，数据请求未经过用户服务端，实际后备文件内容改变。
3. 撤销注册仅成功一次，已打开文件仍可读；关闭后等待实际 RELEASE 回复的管道
   确认，再卸载/停止服务线程并清理自身 fd、文件、目录。不能用固定 sleep 或
   RELEASE 请求刚到达时的计数代替完成，否则卸载存在竞态。

本地 GCC/Clang 及 Wasm32/64 前端、静态分析、Ruff、Nix 格式、actionlint 通过；
没有在开发机执行挂载、修改宿主 IPC 或启动重型构建。根检查读取固定版本 UAPI
与 Kconfig/defconfig，目标构建再检查真实解析配置；这些仍不是目标运行证明。
公开预取 40162599468/job121077105390 核实完整 revision
ad56d20e9efad8c68af565a79a2579d2fb872aca 与
`sha256-5TOSxy0OMuXgPivHdgXOFp65kwwzhfck4TIq0t9hA+U=`，根仓库 `bd3d878`
独立集成源码 pin 与轻量检查。

固定 d077527 的
[wasm32 40162875765](https://github.com/HighCWu/distro/actions/runs/40162875765)、
[wasm64 40162879286](https://github.com/HighCWu/distro/actions/runs/40162879286)
真实检查已异步派发，尚待实际阶段、唯一 pass 和关闭结果核实。不把它泛化为
FUSE mmap/splice、任意堆叠文件系统、非特权使用或浏览器验收，也不宣称完整
libfuse 软件栈已经移植。自有程序/构建/检查为 MIT，必要内核配置改动沿用 GPL。

## 第八十五组：普通 SDK 携带私有复制执行能力

distro `3da2bde` 推进默认 SDK 的执行侧准备，而非提前打开默认内核文件 mmap。
平台链接参数自动导出现有 musl `__wasm_mmap_init_v1`，普通 SDK 编译的标准文件
负载不再额外指定私有导出；Zstd 变体也移除专用链接参数。没有修改 musl/Linux
源码、添加公共函数或要求应用调用私有 API。profile.json 的
execution.initializedPrivateCopy 记载 v1、导出/import、必需内核清理导出及内核准入。
现有匿名映射 v2 参数、CONFIG_MMU=n、默认文件映射关闭、容量与共享/执行边界不变。

新模块需要支持 linux_mmap_init_v1.copy 的配套宿主，不承诺旧实验宿主兼容。
同时修正了更具体的安全边界：当前宿主不应仅因用户模块提供函数，就在缺少
abort_file_mmap_v1 的旧实验内核中激活无法清理非局部退出的复制。现在 capability
为0，直接 map 则在用户回调上下文转换之前返回正常 EOPNOTSUPP，原 C 返回路径
可以释放已产生的资源；复制桥自身也拒绝，无 lease 或用户分配器调用。缺失和
误导出为 global 的清理名字均不算支持，查询不调用用户或清理函数。

两个旧复制模块对照改用显式去除该导出的原链接配置，最终模块必须同时没有
初始化导出和 copy import，不能把普通新 SDK 产物冒充旧模块。标准负载改用安装
的 wasm-linux-cc 编译，并核对最终模块、SDK 元数据及共享内存位宽/上限；Zstd
继续强制标准 mmap。SDK 能力并不授权文件来源或绕过 kernel/LSM 条件。

本地369项内核组件检查、源与测试两个 TypeScript 工程、30项 SDK/Zstd 编排检查
通过。实际 musl 可选成员编译进 Wasm archive，在32/64位核对导出参数确实提取
它、无导出时真正不存在；检查空/非空长度的真实私有 scalar ABI。分配器是测试
替身，不作为其实现或 VFS 证明；反转能力期望、仅伪造导出而缺 import 都会失败。
实际复制 C/JS 小模型还核实：隐藏清理导出后正常拒绝、用户分配器不进入、资源
全零；正常异常清理归零，故意旁路清理仍泄漏。此处模拟的是当前函数体缺少导出，
不是重新启动整个历史内核的证明。Ruff、Nix/JS 格式和 actionlint 通过。

根仓库 `880c4e7` 独立更新 pin 与上述轻量模型。固定 3da2bde 的标准文件
[wasm32 40165368438](https://github.com/HighCWu/distro/actions/runs/40165368438)、
[wasm64 40165371968](https://github.com/HighCWu/distro/actions/runs/40165371968)，
Zstd 文件
[wasm32 40165376151](https://github.com/HighCWu/distro/actions/runs/40165376151)、
[wasm64 40165378816](https://github.com/HighCWu/distro/actions/runs/40165378816)
已异步派发，尚待实际阶段/唯一 pass/关闭门禁。普通 SDK、旧复制模块、默认内核
拒绝及先前生命周期回归须分别核实，不把本地归零当成设备在途或生产就绪。

同次定期检查另发现第八十四组 FUSE 两路明确失败：d077527 的
40162875765/job121077979742、40162879286/job121077990719 均已实际启动，
最终 initialized file lookup 返回 ECONNREFUSED(111)，尚无三阶段 pass。
已读取实际日志，正在核查 INIT 的页面固定复制路径与 Wasm 分离内存的兼容性，
不因构建/配置成功就宣称 FUSE 运行通过，也不重新关闭该功能来回避缺口。

## 第八十六组：FUSE 设备的 Wasm 跨内存复制

第八十四组两路真实目标都失败于 INIT 后的 lookup ECONNREFUSED(111)，不是
编译错误。审查发现设备原有 `iov_iter_get_pages2` 路径要求用户地址对应可固定
的内核页面；NOMMU GUP 会查 VMA、随后使用 virt_to_page，不能把 Wasm 独立用户
线性内存的偏移当成内核地址。INIT 复制失败会使连接进入错误状态，符合随后
lookup 的错误表现；是否已完整解决须由新目标运行确认。

Linux `963697df0` 对 Wasm 的普通用户内存迭代器改用已有 copy_to_iter/
copy_from_iter，让架构 uaccess 和同步、有界的宿主复制 import 完成跨内存传输。
不伪造页面、VMA 或 GUP 成功，不加 MMU/softmmu。原生架构、内核迭代器、管道和
io_uring 路径不变。保持请求锁和既有清理流程；短复制只累计已完成字节，并让
下一次 fill 解锁后返回 EFAULT，避免把负 errno 当字节数或零进展死循环。

新增 MIT 轻量模型提取实际四个复制函数体，替代页面/迭代器/锁外围，不是完整
内核运行。GCC/Clang 下核对 Wasm 双向跨页/非对齐复制、原生页面路径、空缓冲区、
短/零复制失败和跳过字节；移除架构分流必须失败，移除错误后的进展控制必须被
超时检出。目标消费者增加 INIT 回复完成确认，避免父线程 lookup 先失败而掩盖
服务线程的原始错误。消费者原生与 Wasm32/64 前端、Clang 静态分析、Ruff 和
actionlint 通过；未在宿主执行挂载。真实双位宽阶段和机器关闭尚未验收。

源码已独立推送；公开
[预取 40166798492](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40166798492)
的实际输出确认完整 revision `963697df02b504dd1a9ab7ee3e4fe5ae9f96f34a`，
SRI 为 `sha256-6bmMbvMi3aNRzbsuir1/9h9lo5Yfwlx/MXS9WtOquJM=`。
distro `edfa9ec` 更新固定源码和 INIT 确认，根仓库 `dfefb52` 单独集成两个 pin、
轻量模型与 CI 门禁。固定 edfa9ec 的
[wasm32 40166960469](https://github.com/HighCWu/distro/actions/runs/40166960469)、
[wasm64 40166960463](https://github.com/HighCWu/distro/actions/runs/40166960463)
已异步运行。仍须实际读取三个功能阶段、唯一 pass 与固定运行器的关闭结果；
不将源码哈希成功或模型通过代替该验收，也不宣称完整 FUSE/libfuse 已可用。

补录：40166960463/job121089940778 的完整实际日志已读取，三个规定阶段和唯一
pass 均出现：协商/注册错误/后备引用、标准读写不经过服务端数据请求、注册撤销
后打开文件引用/RELEASE/卸载清理。该 Heavy 成功，固定运行器先完成含
machine.closed 的资源关闭，再以无启动/关闭失败决定退出成功；相关运行器未改。
因此验收 edfa9ec/963697df0 的 wasm64 Node 这一 FUSE passthrough 范围，确认
此前的 INIT/lookup 失败在此组合已解决。wasm32 的 40166960469/job121089943362
完整实际日志也已读取，三个阶段及唯一 pass 齐全，Heavy 成功且固定关闭门禁相同。
因此这两个精确源码组合的 Node 双位宽范围均通过；浏览器、完整 libfuse、普通
FUSE 数据请求、splice/mmap 及后继内核版本均不据此自动验收。

## 第八十七组：文件私有复制接受单独 PROT_WRITE

Linux `97de895f0` 修正文件 mmap/mmap2 的保护位准入：此前只接受 PROT_READ
或 PROT_READ|PROT_WRITE，与已经接通的匿名直接映射及通用 NOMMU 私有复制路径
不一致。现在也接受单独 PROT_WRITE，不要求应用自行补一个 READ 位。这里表示
调用者只请求 WRITE，不表示内存会禁止读取；直接线性内存没有页权限隔离。
PROT_NONE、EXEC 和未知保护位仍拒绝，文件仍须以可读方式打开；私有复制不要求
源 fd 可写，也不因写副本而写回。LSM 继续收到原始保护位和标志，不偷偷添加
PROT_READ，不放宽共享/固定映射或文件来源能力检查。musl 完全没有变化。

GCC/Clang 的实际 C 函数体模型、双位宽调用单位、Wasm32/64 消费者前端与静态
分析通过，匿名 mmap 原有准入与文件分派回归通过。恢复旧保护位拒绝条件以及
人为给 LSM 增加 READ 位的反向控制都会失败。真实标准负载增加普通/提示请求、
副本可写而源文件和 fd position 不变、munmap 回收，并保留默认关闭和旧模块
拒绝分支；浏览器现有标准用例要求同一阶段标记。这些本地结果不代替目标运行。

公开预取 40167508053/job121091475411 的实际输出核实完整 revision
`97de895f04e15b5b185757c1f07ebcd87b7ba020` 与
`sha256-OYeOhOiW6/nkmtLb65QuAqx6VsDq9Y4NAvXUMZAh1mg=`。此前预取
40167500780 因输入 revision 误填而失败，没有用于源码 pin 或构建；正确预取使用
实际提交的完整 SHA。distro `8ba739f` 原子集成新内核和标准负载，根仓库
`8b199eb` 单独更新 pin。固定 8ba739f 的
[wasm32 40167729310](https://github.com/HighCWu/distro/actions/runs/40167729310)、
[wasm64 40167730535](https://github.com/HighCWu/distro/actions/runs/40167730535)
两路现均核实成功，完整日志分别为 10,263,013 与 8,315,714 字节，job
121092164705 / 121092154715 各出现11条预期阶段/结果：candidate 的四阶段
（含新的 WRITE-only）及唯一 pass，default/legacy 各自的拒绝阶段和唯一 pass，
生命周期的并发预算/回滚阶段及唯一 pass。固定运行器的清理代码与该版本无差异，
实际成功出口要求 await machine.closed 且没有启动/运行/清理错误，因此这四次
启动的关闭门禁也成立。此验收仅对应 Linux `97de895f0` / distro `8ba739f`，
不替代后续 VM 计数配置的目标验证。不重复派发没有改动请求方式的 Zstd，
也未把浏览器断言更新当成浏览器运行。

## 第八十八组：恢复官方默认的 VM 事件计数

Linux `9f827ba1a` 去除三套 Wasm defconfig 对 VM_EVENT_COUNTERS 的额外关闭，
继承 [Linux 官方 v7.1 的 default y](https://github.com/torvalds/linux/blob/v7.1/mm/Kconfig)。
该条件没有 MMU 依赖；复用原有 per-CPU 计数、在线 CPU 汇总和 proc seq-file，
不伪造计数器，不新增 syscall 号或 libc 函数。修复的是标准 read/proc 观察面的
实际能力缺口：关闭时 `/proc/vmstat` 仅有页状态、没有这些事件字段。Nix 构建
核对最终 CONFIG_VM_EVENT_COUNTERS=y，CONFIG_MMU=n 边界保持。

新增 MIT 消费者通过普通 fopen/read/write 等读取 pgalloc_normal、pgfree、
pgpgin、pgpgout；缺少字段、重复、非数字或溢出不能默认为零。目标在独立 ramfs
保留2 MiB数据，核对内容和内核分配计数增加，随后关闭、删除、卸载并核对释放
计数增加。不要求精确增量或把 SMP 近似汇总冒充原子快照。该内核统计只覆盖其
实际管理的页面，绝不把用户 WebAssembly.Memory 的 malloc/memory.grow 算作
同一种页事件，也不据此宣称页错误、swap、主机总内存或用户 CPU 记账已实现。

首版错误地把 vmstat 当作 BusyBox 已有 applet，加入不存在的 VMSTAT 配置，
后续真实构建已明确失败；此判断现已撤回，程序归属及修复见第八十九组。
安装式目标原计划运行 vmstat 取两次样本，检查数字列与实际退出并清理，最后要求三阶段和唯一 pass；
固定运行器仍须等待 machine.closed。新二进制的构建门禁会按最终字节核对共享 env.memory、
指针位宽和声明上限；包附带自有 MIT、musl 与 compiler-rt 许可，不改用户应用 API。

本地仅执行 GCC/Clang 的实际解析函数及样本反向控制、双位宽 Wasm 前端与 Clang
静态分析，未执行有 mount 的目标 main。缺字段、重复、64位溢出/截断、负数、
额外字段、缺换行和错误样本数均有检查；ShellCheck、shfmt、Nixfmt、Ruff 与
actionlint 通过。这不是 VM 计数路径或真实工具的运行证明，须等独立目标。

公开预取 40168349024/job121093904003 已从实际输出核实完整 revision
`9f827ba1a625389fc439a1ce7efb6f29a7382148` 与
`sha256-WLeM4V/SF8VphyOyQZBTllZ8JqOLaSmI6wKnrVJqb4Q=`。distro `7c83e87`
原子集成固定内核、最终配置门禁、普通双位宽消费者和上述错误的 applet 配置，根仓库
`df5a5ff` 独立更新 pin、精确 Kconfig 输入和轻量检查。固定 7c83e87 的
[wasm32 40168612175](https://github.com/HighCWu/distro/actions/runs/40168612175)、
[wasm64 40168613297](https://github.com/HighCWu/distro/actions/runs/40168613297)
已异步运行，尚待最终二进制门禁、三个实际阶段、唯一 pass 及关闭结果；不以配置
源码或预取成功替代运行验收。此前 WRITE-only 文件映射检查仍独立在途。

两路结果现已核实为失败，job121094746942 / job121094757975 均明确出现
`.config:1200:warning: trying to assign nonexistent symbol VMSTAT`；最终失败是
BusyBox 配置检查，目标系统未启动，也没有 VM 事件阶段。两路 Linux 的实际
日志均已进入 buildPhase completed / installPhase，不是内核编译失败。配置期间
还出现原有 llvm-gcc 探测提示，不能把它当成这次新增门禁失败的替代原因。

## 第八十九组：纠正 vmstat 程序归属并接入 procps-ng

继续核对固定 tombl BusyBox 的 procps 目录和官方 BusyBox 1.37.0 发行包后，
两者均没有 vmstat.c；不是上游删除了一个可直接恢复的同版本 applet。撤回
第八十八组中的错误判断，去掉 VMSTAT 配置及其 grep 门禁，不补造 BusyBox
程序，也不关闭已恢复的内核 VM_EVENT_COUNTERS。

distro `9b5a875` 接入真正提供 vmstat 的 procps-ng 4.0.7 原版程序，固定
[上游发行档案](https://sourceforge.net/projects/procps-ng/files/Production/procps-ng-4.0.7.tar.xz/)
与本地下载实际核对的 `sha256-nSAh9HpFAcZnhiyZQqktGVNpSyHRG80XAug+tZTj1n0=`。
只构建原版 src/vmstat 与静态 libproc2 依赖，不宣称整套 procps 已移植；无 C 源码
补丁，不为它增加 musl 公共函数或强制存在性探测。按实际 configure.ac 关闭本
配置不使用的 ncurses/systemd/elogind/NUMA、NLS 和 pidwait，使用普通 Wasm stdenv。
最终模块仍核对共享 env.memory、指针位宽和声明上限。

原版该版本包含18个输出字段，旧的16/17列门禁同样错误，已修正。验证还检查
procps-ng 版本身份、两次样本的全部数字列、实际退出和清理；原有实际 ramfs
分配/释放验证不降低。宿主 procps-ng 4.0.4 的真实两样本经新门禁通过，仅用于
核对格式，不作4.0.7或 Wasm 运行证据。解析反向控制、双位宽自有消费者前端及
Clang 静态分析、ShellCheck、shfmt、Nixfmt、Ruff 和 actionlint 通过。未在本地
重型构建 procps，也未在宿主运行含挂载的目标消费者。

上游 COPYING/COPYING.LIB 与 musl/compiler-rt 许可随运行包保留，自有集成代码
仍为 MIT。另提供精确原始源码档案、集成配方、说明与校验和的独立 sourceBundle；
二进制哈希在最终包 strip/fixup 完成后才生成，目标安装树会实际比较该哈希。
不以源码输入的校验和代替最终二进制身份，不宣称该小输出包含全部工具链来源或
完成整个发行的对应源码合规审计。Linux/musl pin 不变，根仓库 `85bce0f` 独立
更新 distro pin 与轻量门禁；新的双位宽目标尚待实际运行验收。

固定 `9b5a875` 已分别派发
[wasm32 40634677498](https://github.com/HighCWu/distro/actions/runs/40634677498) 和
[wasm64 40634678517](https://github.com/HighCWu/distro/actions/runs/40634678517)。
只有实际三个阶段、唯一 pass 和固定运行器关闭结果均核实后才记为通过；
构建成功或工作流绿色本身不替代这些证据。

wasm32 40634677498 的 job122638887522 已从完整实际日志核实失败：交叉配置
报告 GNU libc compatible malloc/realloc 为 no，随后 libproc2 链接缺失
`rpl_malloc` / `rpl_realloc`。这不是 Linux VM 事件故障，仍未启动目标。
上游 configure.ac 使用 AC_FUNC_MALLOC/AC_FUNC_REALLOC；固定 musl mallocng
对零尺寸使用正常最小 size class，realloc(NULL, 0) 直接调用 malloc(0)。
distro `37c7469` 因此在本包交叉配置中给出这两项精确行为的缓存答案，并在
真实目标消费者中通过 volatile 函数指针检查、释放两次零尺寸分配，防止只声明
支持却不检验目标 libc。不添加 rpl 替代函数、不改 procps C 源码或 musl API。
根仓库 `0dce261` 独立更新 pin 和门禁；双位宽前端/静态分析、解析回归及格式
检查通过，真实目标结果仍待验收。旧 wasm64 任务继续运行，不因耗时而取消。

修正后的 `37c7469` 已单次派发双位宽复验：
[40635414453](https://github.com/HighCWu/distro/actions/runs/40635414453) 与
[40635419389](https://github.com/HighCWu/distro/actions/runs/40635419389)。
此前已通过的文件映射与 FUSE 运行证据仍单独保留，不用于代替这次目标验收。

两路 `37c7469` 后续均失败，但已经进入实际目标：job122641254270 /
job122641283317 各完成前两个 VM 事件阶段，证明零尺寸分配检查及真实 ramfs
分配、内容保留、释放和清理均执行成功。失败紧接其后，实际日志是 BusyBox
sha256sum 的用法提示，不是文件校验和不匹配；它不接受 GNU `--check`。
distro `6184874` 改用已有 `-c`，根仓库 `e214a1e` 独立更新 pin 和轻量
门禁；未删除二进制身份检查。该修正随后随下组固定源码一起双位宽复验，不能
把前两个阶段通过记成 vmstat 完整运行通过。

## 第九十组：同步普通文件 O_DIRECT 的内核缓冲桥

实际源码路径表明，普通同步 read/write、pread/pwrite 和向量调用会把用户
ITER_UBUF/ITER_IOVEC 直接交给文件系统。ext4 的 direct I/O 经 iomap 提取页面，
而通用 NOMMU GUP 要求 find_vma；Wasm 用户线性内存并没有这些内核 VMA。
因此普通用户地址不能靠原页固定路径完成 I/O。不能把它们直接当内核地址，
也不能只清除 O_DIRECT 冒充支持。

Linux `c8f79667c` 在 fs/read_write.c 的三个既有同步分派点接入有界缓冲：
仅 Wasm、O_DIRECT、用户迭代器、非空普通文件请求使用它。保留原 kiocb 和
O_DIRECT 标志，交给原文件系统的 read_iter/write_iter 真正执行 I/O；文件
系统原有的拒绝或 fallback 政策仍由文件系统决定。本桥不强制改成 buffered。
普通 I/O、内核迭代器、非普通文件及其它架构保持原回调路径；没有新增 syscall
号、libc 函数、应用接口或内核 softmmu，CONFIG_MMU 仍为 n。

每次最多交付128 KiB，较大请求可以得到标准短读写，调用者需处理返回长度；
所有请求合计最多占用512 KiB缓冲预算，包含页对齐偏移开销，预算或分配失败
返回 ENOMEM。这是当前实现边界，不宣称无限长度、任意设备或零拷贝支持。
原始完整向量及完整请求长度的对齐信息在 PAGE_SIZE 范围内传播到缓冲地址，
避免截短恰好掩盖原请求未对齐。写入先复制到缓冲，用户错误前不提交文件写入；
读取后只推进已交付的用户字节及位置，全部/部分错误均释放页与预算。
NOWAIT 返回 EAGAIN，原子和 HIPRI 请求返回 EOPNOTSUPP，不把分块当作原子写。
本桥只接在同步调用点，不启用 AIO/io_uring，也不扩大多线程 fork 支持。

GCC/Clang 检查实际函数体，覆盖真实内容复制、短传输、完整请求未对齐、部分
用户读回故障、全故障、写前故障、分配/预算耗尽、文件系统 EIO、拒绝标志和
清理；禁用分派的反向控制可编译运行但必须断言失败。其它架构及普通/内核
迭代器 bypass 模型也通过，Clang 静态分析和真实消费者的双位宽前端通过。
模型使用替代页分配、迭代器和原子操作，不证明真实 GUP、并发竞争或磁盘 I/O；
没有在宿主执行会创建 direct 文件的目标 main。

MIT 消费者使用普通 SDK 和实际 ext4 安装根，要求三阶段：标量/位置读写；
向量短写、读回及独立 buffered fd 观察真实文件字节；未对齐、无效地址、
失败后恢复及文件清理。最终二进制仍核对共享 env.memory、指针位宽和声明
上限。完整三个阶段、唯一 pass 及固定 machine.closed 门禁均待真实目标核实。
Linux 必要修改保留 GPL，自有消费者、配方和轻量模型为 MIT；musl pin 不变。

[公开源码预取 40636592490](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40636592490)
的 job122644870218 实际输出核实完整 revision
`c8f79667ca853218399785b3a0851a44005a5de9` 及
`sha256-hqCOraJmuA5C/5GjKYi+YZL0FYrrKJD/rXkX7WyvxWs=`。
distro `f380221` 原子集成精确内核 pin、双位宽消费者；根仓库 `07696b2` 单独
更新 gitlinks、精确函数源获取和轻量 review。目标 CI 异步执行，未验收前不
宣称 ext4 direct I/O 已经可用，也不以较早 mmap/FUSE 结果替代。

固定 `f380221` 的检查名与源码已核对，四项均只派发一次：

- direct I/O [wasm32 40636944683](https://github.com/HighCWu/distro/actions/runs/40636944683)、
  [wasm64 40636955266](https://github.com/HighCWu/distro/actions/runs/40636955266)。
- VM 事件/vmstat [wasm32 40636963087](https://github.com/HighCWu/distro/actions/runs/40636963087)、
  [wasm64 40636968393](https://github.com/HighCWu/distro/actions/runs/40636968393)。

当前仅记录异步运行中；需要分别读取实际阶段及关闭结果，不把新内核源码预取
成功、模型或 CI 开始运行视为这些调用已经验收。

固定 f380221 的四路现已逐项核实通过：direct I/O 的 wasm32
job122646076449 / wasm64 job122646108483 实际完整日志各有三个功能阶段和
唯一 pass；VM 事件的 wasm32 job122646154886 / wasm64 job122646167632
各有三个阶段、`bin/vmstat: OK`、恰好两条18列全数字样本和唯一 pass。
四个 Heavy/工作流均成功，实际目标日志没有失败或清理错误。固定运行器仍在
成功出口前 await machine.closed，没有启动/运行/清理错误才返回0；该代码
在本次后继中没有变化。接受的是 Linux c8f79667c / distro f380221 的
有界双位宽 Node 结果，不是浏览器、裸块设备或后继内核的验收。

## 第九十一组：同步裸块设备 direct I/O 与原生磁盘末尾语义

继续核查 block/fops.c 后确认，裸块设备的同步 O_DIRECT 也走用户页提取，
不能使用独立 Wasm 用户偏移。现有上游 bio bounce 读取仍会提取用户 bvec，
不能仅换个名称便当成无需 GUP 的替代。Linux `54e4b1f97` 将同步缓冲桥准入
扩展到 S_ISBLK；仍由原块设备 read_iter/write_iter 执行实际 I/O，不伪造设备
内容，不新增 syscall、libc 函数、应用接口或 MMU。

块层的校验与普通文件不同：先按设备末尾截短，再检查有效总长度与文件偏移的
逻辑扇区对齐，不以用户缓冲地址对齐代替长度校验。因此桥在分块前按同一顺序
检查完整有效请求，过设备末尾的未使用尾部不复制；从设备末尾或之后读为 EOF，
写为 ENOSPC 的具体处理仍交给原方法。块缓冲使用页对齐地址，不能仅靠把原始
长度低位混入缓冲地址来指望块层拒绝。普通文件的对齐处理保持原样。
128 KiB单次短传输和512 KiB总预算由文件/块请求共同使用；NOWAIT、原子、
HIPRI、异步支持边界不扩大，也不宣称热扩容竞态或任意设备/文件系统已验证。

实际函数体模型新增块总长度、扇区偏移、允许的字节偏移缓冲、设备末尾及只复制
有效前缀的检查。移除完整块长度检查的反向控制可编译但明确断言失败；原普通
文件、用户部分故障、错误和资源收尾、其它架构 bypass 均继续通过。GCC/Clang
模型、静态分析、双位宽真实消费者前端、ShellCheck、shfmt、Nixfmt 和 Ruff
检查通过。这不是实际块设备运行证据，模型没有宿主磁盘 I/O。

MIT 目标消费者保留上一组全部普通文件阶段，另由 CI 构建一个全新的8 MiB空白
镜像，运行器复制可写并作为根盘之后的独立设备。消费者先核对 S_ISBLK、设备
号不等于当前根设备、容量恰好8 MiB及前128 KiB全零，才写入；不挂载该磁盘，
不触碰宿主磁盘。它检查标量/向量真实内容、无效长度/偏移、无效源、末尾和跨
末尾的截短、错误后恢复，最后 flush/close。PID1 自行挂载并卸载 devtmpfs，
不依赖引导器在 switch_root 前已经卸载的 /dev。轻量门禁核对独立磁盘生成和
这些写前保护；最终要求四个功能阶段、唯一 pass 及固定机器关闭门禁。

[公开预取 40637989702](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40637989702)
的 job122649303681 实际输出已核实完整 revision
`54e4b1f97972500e84ecdaf98b0890ad66725707` 与
`sha256-PVOGBr18PSWUZe7is8WY71Z0YAnKqY42GKmyPFQPFK0=`。
distro `e8190f2` 原子集成精确 pin 与独立磁盘消费者，根仓库 `1fd8a82` 单独
更新 gitlinks 和实际函数体模型。musl pin 仍为0771c6eb，不改写已发布历史。
新双位宽目标待实际验收，不复用 f380221 的三阶段结果声称新增块路径通过。

固定 e8190f2 的
[wasm32 40638312930](https://github.com/HighCWu/distro/actions/runs/40638312930)、
[wasm64 40638318850](https://github.com/HighCWu/distro/actions/runs/40638318850)
已各派发一次并核对检查名，仍在运行；不取消此前慢任务，也不重复派发同源码。

wasm64 40638318850/job122650460071 现已从完整实际日志核实通过：保留的三个
普通文件阶段、新增独立裸磁盘阶段及唯一 pass 均齐全，无目标失败或清理错误。
新阶段包括实际原始字节、向量顺序、无效请求不改写、跨设备末尾截短及恢复；
PID1 在 pass 前卸载自身 devtmpfs，固定运行器再等待 machine.closed，Heavy/
工作流均成功。接受 Linux 54e4b1f97 / distro e8190f2 的有界 wasm64 Node
结果。wasm32 40638312930/job122650439251 后续一次状态查询曾遇到传输 EOF，
再次查询确认仍运行；没有视为失败、重派或用 wasm64 代替它的运行证明。

## 第九十二组：启用上游 AF_PACKET 普通链路层收发

三套输入未请求 PACKET；本轮 Linux `b2130397a` 明确启用 CONFIG_PACKET=y，
接通上游 packet socket family 的普通 RAW/DGRAM 收发。net/packet/Kconfig
没有 default y，虽有“If unsure, say Y”建议，这里是按项目兼容性需求选择
功能，不称作恢复一个原本就为 y 的默认值。不重写 packet_create/sendmsg/
recvmsg，不添加 libc 包装函数或公共头文件 API，musl pin 完全不变。
最终 .config 另要求 PACKET=y，三套输入的禁用反向控制必须失败。

静态核查覆盖上游普通发送复制、packet_recvmsg 的地址长度和截断处理、
loopback 的 eth_type_trans 接收路径。普通收发不需要页表或把用户偏移当成
内核页；packet mmap ring 则不在本组支持范围，不能因 family 已编入就声称
共享环、零拷贝或 libpcap/tcpdump 已可用。PACKET_DIAG 保持其默认关闭，
CONFIG_MMU 仍为 n，无内核 softmmu 或多线程 fork 范围变化。

MIT 普通 SDK 消费者只对自己的 lo 使用本地实验 EtherType 0x88b5：先保存接口
标志，验证 RAW 帧发送、RAW 完整接收及 DGRAM 去头/MSG_TRUNC/scatter-gather
二进制数据，再由 DGRAM 发送核对内核构建的链路头和实际地址。接收要求
PACKET_HOST，不能仅靠 outgoing tap 的副本通过。所有接收均有单调时钟截止
时间和有限匹配次数，不使用外部网络或混杂捕获。恢复原接口标志并关闭 socket
后，才 setuid(65534) 检查 CAP_NET_RAW 拒绝；普通 UDP socket 仍须可创建。
要求三个功能阶段、唯一 pass 和固定关闭门禁。

本地仅做 GCC/Clang 编译、实际 musl 头文件的 Wasm32/64 前端与静态分析，
绝不执行会修改网络状态与凭据的目标 main；ShellCheck/shfmt、Nixfmt、Ruff
与 actionlint 通过。最终模块沿用共享 env.memory、指针位宽和声明上限门禁，
wasm64 的 stdenv、平台、musl、运行库、BusyBox 和运行器覆盖项另有轻量检查，
不以静态配方检查代替实际 Nix 闭包及最终字节的目标门禁。自有消费者、
配方和检查为 MIT，上游协议栈保留原许可证；没有应用专用接口。

[公开预取 40640755173](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40640755173)
的 job122658078368 实际输出已核实完整 revision
`b2130397a84a5370f11f823c7076c799f2be6f5f` 和
`sha256-nmkTTuddeyVlJC3KU/5mCtWMtyHmvW57APZtRYlJRLE=`。
distro `4d94634` 原子集成精确内核 pin、最终配置门禁及双位宽普通消费者，
根仓库 `02ddb25` 单独更新 gitlinks 和轻量检查。真实 AF_PACKET 阶段仍待
公开目标验收；本地编译或之前 direct I/O 的通过均不替代该证明。

固定 4d94634 的
[wasm32 40641343193](https://github.com/HighCWu/distro/actions/runs/40641343193)、
[wasm64 40641353200](https://github.com/HighCWu/distro/actions/runs/40641353200)
已各派发一次并核对源码及检查名；它们只验证普通 socket 路径，不覆盖 packet
mmap、外部网卡流量或浏览器。本轮没有取消或重派在途裸块设备 wasm32 检查。

固定 4d94634 的两路 Node 现已核实通过：wasm32 job122660058060 的完整
日志为5,612,009字节，wasm64 job122660096374 为3,708,098字节；各有
RAW/截断、cooked/地址/flags、恢复/降权/清理三个实际阶段与唯一 pass，
无目标失败或清理错误。两个 Heavy/工作流均成功，未变的固定运行器在成功
退出前等待 machine.closed，故关闭门禁也成立。仅接受 Linux b2130397a /
distro 4d94634 的普通 loopback socket 范围；不扩展为 packet ring、外部
网络、libpcap/tcpdump 或浏览器已经验收。

## 第九十三组：direct 写入先按通用文件限额截短，再复制用户前缀

继续静态 review 发现第九十组缓冲桥的一处缺口：它在原文件系统执行
generic_write_check_limits() 之前就复制用户源。若 RLIMIT_FSIZE 或通用文件
最大长度只允许请求的前缀，而未使用的用户尾部无效，原生顺序本可成功短写，
桥却提前 EFAULT；完整原请求的未对齐尾部也可能污染原本有效前缀的对齐。
有追加标志时，限额必须相对 inode 当前大小而不是调用者原始 ki_pos 计算。

先扩充实际函数体模型，在 b2130397a 函数体上可编译但明确断言失败于合法 PAGE_SIZE
前缀写入；初次模型的未用辅助函数编译诊断不作为功能复现。Linux `ad068df98`
随后为普通 direct 写入读取通用限额快照，先截短临时迭代器，再计算复制长度
和对齐。只读取当前资源/文件大小与 O_LARGEFILE 条件，不改调用者的 ki_pos 或
迭代器，不自行发 SIGXFSZ，也不提前获取文件系统 inode 锁。已达界限时直接
交回原 write_iter；实际写入、追加位置、锁、权限和进一步限额仍由原文件系统
处理。它不是任意文件系统私有限额或并发大小/rlimit 修改的原子快照承诺。
块设备原有的末尾/扇区校验和共享缓冲预算不变；无 MMU 或 libc API 变化。

GCC/Clang 模型覆盖资源限额、s_maxbytes、APPEND、未使用尾部、仍调用原方法
产生 EFBIG、对齐/故障/预算和块设备回归，移除新前缀选择的反向控制可编译
但必须断言失败。静态分析与真实消费者的双位宽前端通过；没有在宿主执行
含磁盘操作或资源限额修改的目标 main。

目标故障夹具只在 Wasm 消费者内新增一页线性内存，使一页源有效、请求尾部
实际越过当前 memory 容量且仍在架构 access_ok 范围内。分别通过普通 pwrite
与设置 O_APPEND 后的 write 验证限额截短、真实字节和位置；不把 musl 既有
RWF_NOAPPEND 的 pwrite 误当追加调用。夹具在任何后续分配前以 volatile 写
清零新页，并恢复原限额和 fd flags，避免破坏运行库对新 arena 的零字节约定。
这只是测试内存边界的方法，不要求用户程序采用新接口；普通 SDK 与 musl
pin 不变。消费者保留此前所有阶段，新增限额阶段后共五阶段及唯一 pass，
固定运行器仍需等待 machine.closed。

[公开预取 40643752496](https://github.com/HighCWu/linux-wasm-builder/actions/runs/40643752496)
的 job122667659740 实际输出已核实完整 revision
`ad068df98a9e6a2614027df4ef94a7ac2f1a1861` 与
`sha256-fGT90QSw32imI4DnFRK2D428mTkKhr+NXnYOrNjZPhI=`。
distro `09b3edd` 原子集成精确 pin 与目标边界夹具，根仓库 `9cbfb0f` 单独
更新 gitlinks、模型和反向控制。真实目标尚待验收；旧四阶段及 AF_PACKET
通过不替代新增限额分支的运行证明。

固定 09b3edd 的
[wasm32 40644971827](https://github.com/HighCWu/distro/actions/runs/40644971827)、
[wasm64 40644977325](https://github.com/HighCWu/distro/actions/runs/40644977325)
已各派发一次并核对检查名，仍在运行；不取消或重复派发此前慢任务。

后续验收：上述固定 09b3edd 的两个任务与 Heavy 均已成功。已读取 wasm32
job122671653477 的完整实际日志（3,634,149 字节）与 wasm64 job122671669962
日志（3,708,260 字节）；各确认普通文件标量、向量、文件限额/追加的真实
无效尾部、错误恢复/清理、独立裸块设备共五个阶段及唯一 pass，无目标失败、
panic、关闭错误或 watchdog 超时。核对该 pin 的 installedTest 固定运行器：
pass 后仍需 closeTestResources() 等待 machine.closed、关闭磁盘句柄，清理失败
会令检查失败；成功退出才生成检查结果，因此关闭门禁也成立。仅接受本版本
双位宽 Node 同步 direct I/O 范围，不据此扩展到浏览器、异步 I/O、任意文件
系统私有限额或并发修改文件大小/rlimit 的原子保证。

## 第九十四组：AF_ALG 哈希 socket 的跨内存输入

Linux 原有 crypto/algif_hash.c 的普通 sendmsg 使用 extract_iter_to_sg 固定
用户页；Wasm 用户地址属于独立线性内存，不能据此获得内核页。仅启用配置
不能打通这一条标准 socket 调用链。本组在 Wasm 用户 iterator 上改为逐页
copy_page_from_iter，每次活动调用最多持有一页带 __GFP_ACCOUNT 的内核缓冲，
交给原哈希实现处理；保留到 crypto_wait_req 完成后才释放，错误出口也释放。
不将复制页当作用户 pinned page 解 pin；其他架构及内核 iterator 保留原提取
逻辑。分段、MSG_MORE、accept 导出的哈希状态和结果仍由上游实现处理。

Linux 416342670 实现适配，后续 0f2b32f94 显式补齐父级 CRYPTO 菜单条件，
三份 defconfig 请求 CRYPTO、CRYPTO_USER_API_HASH、CRYPTO_SHA256、CRYPTO_HMAC。
这是新增选择的能力，不宣称这些选项是 Linux 官方默认开启。distro 对最终
解析配置检查四项均为 y；不开放尚无接收页适配的 SKCIPHER/AEAD，也不宣称
共享映射、零拷贝、异步 syscall 或浏览器已经可用。musl 不变。

MIT 轻量检查提取真实 SG 适配函数体，通过 GCC/Clang 模型和 Clang 静态分析：
覆盖多页输入的一页上限、非别名内容、部分复制、无效地址、分配失败和资源
释放；禁用 Wasm 复制分支后同一工作负载须断言失败。没有在宿主执行哈希
socket 或目标 main。普通 SDK 消费者使用标准 Linux if_alg.h 和既有 libc
socket 调用，核对 SHA-256 已知向量、空输入、增量状态克隆、1 MiB+17 二进制
向量、截断及 guard、真实线性内存末尾错误后恢复、RFC 4231 HMAC 和 fd 清理。
消费者的 GCC/Clang、双位宽 Wasm 前端和静态分析通过；这些不是目标运行证明。
公开源码预取 [41379621222](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41379621222)
的 job125067330439 实际输出已核实完整 revision
`0f2b32f944bef46652a4bc366e94b259d6a29999` 与
`sha256-DuJ3qu7AV0DYEajp6UNEyW8wpWthyIWOLfADvQoKF04=`；早期 416342670
预取不作为补齐 CRYPTO 后的 pin。distro `15d8fbf` 原子集成精确 pin、最终
配置检查和独立普通 SDK 消费者。真实运行待双位宽公开 CI，不能把模型或
配置检查当作 SHA-256/HMAC 目标完成证明。

根仓库 `1a73d0c` 单独更新 Linux/distro gitlinks 和轻量回归。固定 distro
15d8fbf 的 [wasm32 41379999933](https://github.com/HighCWu/distro/actions/runs/41379999933)
与 [wasm64 41380004730](https://github.com/HighCWu/distro/actions/runs/41380004730)
已各派发一次，分别请求 alg-hash-check-runtime / alg-hash-wasm64-check-runtime；
尚在运行/排队。验收须核对三个实际阶段、唯一 pass 及固定运行器等待
machine.closed 的关闭结果，不以工作流创建或成功规划替代目标运行。

## 第九十五组：AF_ALG 对称加密接收端的有界跨内存输出

继续检查原 crypto/algif_skcipher.c / af_alg.c 发现：普通 sendmsg 已复制输入，
但 recvmsg 的 RX SGL 仍提取并固定用户页，不能使用 Wasm 独立用户内存。
Linux `9b100aac9` 在原同步请求路径中加入接收暂存：等待排队数据后，按
min(实际排队输入、用户请求、一页) 读取目标的有效前缀作探测，不修改目标，
也不推进原 iterator；Wasm 线性内存的既有字节可读可写，不借此声称具有
原生页面权限。原 crypto 请求使用同一页的内核 KVEC，完成并释放 SG 资源
之后才向原用户 iterator 复制实际成功字节并释放页。

保留原 socket 锁、密钥/IV 解析、错误、块长检查、NOTFINAL 和状态/IV 续接。
探测使用源方向的临时 iterator；原目标方向及位置完整保存，避免触发
copy_page_from_iter 的方向检查或把块长取整后未产生的字节误当已交付。
完全无效的目标在提取 TX 输入之前失败，空 RX/TX 资源释放不消耗排队数据；
crypto 失败不复制暂存输出。页带 __GFP_ACCOUNT，一次活动请求最多一页，
只在原同步完成路径持有；不是启用 AIO，也没有把页面指针返回用户空间。
非 Wasm 和内核 iterator 保持原路径；不扩展为 AEAD 支持。

三份 defconfig 选择 CRYPTO_USER_API_SKCIPHER、AES、CBC、CTR，distro 对
最终解析配置逐项检查；这些是显式功能选择，不是声称恢复 Linux 官方默认。
普通 SDK 消费者使用现有 socket/sendmsg/recvmsg、ALG_SET_OP/IV/KEY 和
Linux if_alg.h：核对固定 CBC 加解密、65536+64 字节向量输出的独立边界
密文和解密、无效目标后原输入仍可读取、错误块长后的恢复、CTR 非整块
向量及 fd 清理，不增加 musl 函数或项目专有接口。

提取真实暂存函数体的 GCC/Clang 模型及静态分析通过，覆盖每页上限、探测
不写目标、排队输入限制、实际交付推进、故障/分配/crypto 错误和页生命周期；
禁用暂存、错误 iterator 方向、移除输入限制的反向控制均必须失败。消费者
GCC/Clang 与 Wasm32/Wasm64 前端和静态分析通过；有界 OpenSSL 独立计算
另核实固定向量与跨页边界，不在宿主执行消费者 main 或 socket 操作。这些
不是目标 crypto 运行证明，精确 pin 与真实双位宽阶段仍需独立记录。

## 第九十六组：修复全局导出开关误选预启动 SHA 精简实现

定期检查确认固定 15d8fbf 的 AF_ALG hash 两路均失败于内核链接，尚未运行
消费者：wasm32 job125068582933 完整日志 2,587,485 字节，wasm64
job125068646011 为 2,660,824 字节；实际错误均为 crypto/sha256.o 引用的
__hmac_sha256_init、hmac_sha224/256_final、hmac_sha224/256 及 preparekey
等符号未定义，不是 HMAC 向量已运行但失败，也不能用旧成功配置冒充验收。

原因是 arch/wasm/Makefile 给整个内核定义 __DISABLE_EXPORTS。本版本的
lib/crypto/sha256.c 也用此宏识别预启动环境，只保留精简 SHA、裁掉 HMAC
实现；正常 crypto/sha256.c 却引用完整库。Linux `d02917c85` 删除全局
C/汇编标志，在 include/linux/export.h 用 CONFIG_WASM 局部抑制不支持的
ELF 模块导出记录。完整内核不再伪装为预启动环境；原非 Wasm 导出规则和
真正 __DISABLE_EXPORTS 的预启动构建不变，也没有启用 Wasm 模块加载。
没有通过关闭 HMAC、补空实现或更改用户接口来掩盖错误。

审查该宏在 crypto 库、compiler.h 和 instrumented.h 的用途；CFI 仍受原
CONFIG_CFI 条件约束，不新增 CFI 配置，原子调试检查回到完整内核条件。
轻量检查直接预处理真实 SHA 库与导出头，GCC/Clang 确认双位宽 Wasm 的
HMAC 定义可见但无导出记录、原生仍有导出记录、预启动仍裁剪；旧 Wasm
宏组合复现定义缺失。真实导出头还通过双位宽 Wasm 小对象编译，不以此
代替完整内核链接。修复后的精确源码预取和公开目标重验另行记录。

公开预取 [41382248285](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41382248285)
的 job125075378070 实际日志核实完整 revision
`d02917c85066192596a7a9c70725531df8a3782d` 与
`sha256-UG29iYKYt3UTqCKOB+uzYTNOtQghANoTO2aMMxR9vlk=`。distro `20ff576`
集成此 pin、对称加密消费者和四项新增配置门禁；根仓库 `b4e5d71` 单独
更新 gitlinks 与精确源码轻量检查。联合目标按序执行 hash/HMAC 和 skcipher
两个普通 SDK 消费者，每个位宽要求三加三共六个功能阶段、唯一 pass 和
固定运行器 machine.closed；wasm64 明确携带 wasm64 hash 依赖，不能混入
wasm32 消费者代验。当前仍是候选，修复后的完整目标尚未验收。

固定 20ff576 的联合检查已各派发一次：
[wasm32 41382938776](https://github.com/HighCWu/distro/actions/runs/41382938776)
请求 alg-skcipher-check-runtime，
[wasm64 41382944884](https://github.com/HighCWu/distro/actions/runs/41382944884)
请求 alg-skcipher-wasm64-check-runtime，均已核对精确源码且在运行。
它们是新 pin 的重验，不重复派发 15d8fbf 的已知失败版本。

后续验收已补齐：上述固定 20ff576 两路工作流和 Heavy 均成功，已读取
job125077553304（wasm32）与 job125077575293（wasm64）的完整实际日志。
每路均确认 hash/HMAC 三阶段、skcipher 三阶段和唯一 pass；固定 20ff576
的运行器在成功退出前必须等待 closeTestResources/machine.closed 并关闭
磁盘句柄，关闭失败会令检查失败，故关闭门禁成立。接受 Linux d02917c85 /
distro 20ff576 的 Node 双位宽同步 SHA/HMAC、CBC/CTR 范围，原 HMAC 库
链接错误已得到实际目标修复证明；不代验后续 NETLINK_CRYPTO、libkcapi
接入、ELF/动态链接、AEAD、AIO 或浏览器。

## 第九十七组：启用 Linux 原有密码算法 Netlink 元数据接口

AF_ALG 计算通过不代表普通用户态密码库已经可用。libkcapi 的初始化在绑定
AF_ALG 算法后还使用 NETLINK_CRYPTO 查询算法属性；此前构建没有启用
CONFIG_CRYPTO_USER，缺少这一标准协议端点。Linux `b920e6b82` 在三个命名
defconfig 中启用该选项，复用 crypto/crypto_user.c 的查找、报告、multipart
dump 和 CAP_NET_ADMIN 检查。Kconfig 依赖 NET，不要求 MMU；本轮没有修改
查询结果、权限规则或加入项目专用 socket 协议，也没有新增 musl API。

预取 [41384903082](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41384903082)
的 job125083469806 实际日志核实完整源码
`b920e6b82c63eec3bf28a0281b832a0038e51305` 与
`sha256-oxHlxUULPw7Mxc14Wuu+dCGjRCNM4WTYwng5VMrmjmg=`。distro `fd54b54`
集成此精确 pin 和 resolved Kconfig 门禁，主仓库 `ce6b015` 随后单独更新
Linux/distro gitlinks；默认 LLVM 和 musl pin 不变。

独立 MIT 普通 C 程序通过已有 socket/bind/getsockname/sendmsg/recvmsg/poll
接口验证三个阶段：AF_ALG 实例化后的 SHA-256 与 CBC-AES 属性；不存在算法
的 ENOENT、未终止名称的 EINVAL 与同 socket 恢复；降到 uid/gid65534 后的
查询和完整 dump、管理请求 EPERM、恢复查询及 fd 清理。解析检查 kernel sender、
port/sequence、消息与属性边界、multipart 完成状态和 digest/block/key/IV 大小。
不在宿主执行这些 socket、凭据或算法操作。

review 核对上游实际 report/ack/dump 路径：查询不要求管理权限，变更先检查
CAP_NET_ADMIN；报告由内核缓冲生成，未将用户地址送入 crypto 散列表。算法
名不会因查询而任意自动加载，故消费者先按 libkcapi 的正常顺序绑定 AF_ALG。
GCC/Clang 严格前端、Clang 静态分析及双位宽 Wasm 前端/静态分析通过，后者
使用真实 Linux 协议声明与现有 musl 头；命名配置检查及禁用反向控制也通过。
这些轻量检查不代替内核链接、实际 Netlink 收发或非特权目标运行。

固定 fd54b54 已分别派发一次
[wasm32 41390763820](https://github.com/HighCWu/distro/actions/runs/41390763820)
的 netlink-crypto-check-runtime 和
[wasm64 41390769293](https://github.com/HighCWu/distro/actions/runs/41390769293)
的 netlink-crypto-wasm64-check-runtime。目标仍待验收：每路须确认三个实际
阶段、唯一 pass 和固定运行器关闭成功；排队/构建不算失败，也不以 workflow
状态替代阶段证据。尚未集成 libkcapi 或其应用专用符号补丁；通用 LLVM
符号版本候选独立验证，不把本轮协议支持视为 libkcapi、AEAD、AIO 或浏览器
已通过。

## 第九十八组：Wasm 同步 AEAD 接收与 AES-GCM

原 AEAD 接收路径使用 extract_iter_to_sg 把用户输出变为密码后端的 RX 页表；
Wasm 用户线性内存不能表示为这些内核 page。普通 skcipher 的单页暂存也不能
直接用于 AEAD：人为按页拆开请求会改变 AAD、密文和认证标签的关系。Linux
`c4420655e` 添加独立 MIT 内部头 include/crypto/wasm_aead_buffer.h，并在
原 GPL algif_aead.c 做必要接入；三个命名配置启用 CRYPTO_USER_API_AEAD/GCM。
原文件许可证保持不变，不新增 UAPI、libc API、内核 softmmu 或 MMU 配置。

Wasm 用户输出在原请求输出长度、iterator 容量和现有 RX 预算内分配有记账的
内核暂存区。探测合法前缀不写用户输出，也不推进其 iterator；原 RX SG、
TX 消耗、AAD 复制和 crypto_wait_req 路径继续处理同一请求。释放所有请求 SG
引用后，成功才把实际结果拷回；EBADMSG 等错误恢复原 iterator、丢弃暂存明文，
所有分配路径用 kvfree_sensitive 清理。不会添加单页的记录长度上限，但临时
内核内存和连续分配可能令资源紧张时返回 ENOMEM。保留原短输出语义，不把
不足的目标缓冲区伪装为完整记录已接收。

默认仍关闭 AIO；Wasm 用户 iterator 的非同步请求在分配前明确 EOPNOTSUPP，
避免异步任务引用本次同步调用拥有的缓冲区。非 Wasm 和内部 kernel iterator
保持原路径。本轮不启用 AIO，也不扩大 fork 或线程支持。

review 核对零输出解密、tag 错误、探测/分配失败、部分拷回、RX 预算、请求
完成与 SG/暂存区的释放顺序。GCC/Clang 直接执行真实暂存函数模型和 Clang
静态分析通过；模型覆盖跨两页的单请求、错误时无明文交付和 iterator 不推进、
资源释放等，并要求绕过暂存或在 EBADMSG 后发布输出的反向控制失败。
原 hash/SG 轻量检查和三个消费者的原生及双位宽 Wasm 前端/静态分析通过。
新消费者按 CMSG_SPACE 构造标准控制消息，不修改 musl。核查另发现现有
CMSG_NXTHDR 宏在严格 -Wsign-compare/-Werror 下的告警，本轮未修通用宏，
不将其算作已修复的源兼容能力。

普通 C 消费者覆盖三阶段：AES-GCM NIST 零块/空记录、无效 key/tag 长度；
跨 64 KiB 的 AAD 和跨页明文、独立密文摘要及认证往返；坏 tag 不改目标、
同 operation 恢复、无效目的地址不消耗已排队输入及 fd 清理。固定向量和
大记录常量另用独立 AESGCM/hashlib 核对；不在宿主运行 socket/凭据消费者。
联合目标先运行已有 hash/HMAC、CBC/CTR 和 Netlink 消费者，再运行 AEAD。

源码预取 [41391377143](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41391377143)
的 job125103320280 实际日志核实完整 Linux revision
`c4420655e524544a67ece9ca6cb8be66eda267b4` 和
`sha256-Zxe6Fb1K3WZ6XN0uQvxRFVgofYwEb5tTmAFTo8Ol4AM=`。distro `107b069`
随后集成该 pin、resolved Kconfig 门禁和双位宽联合运行目标；主仓库 `c98c591`
再单独更新 Linux/distro gitlinks 与真实源码轻量检查。musl/LLVM pin 不变。

固定 107b069 各派发一次
[wasm32 41391834357](https://github.com/HighCWu/distro/actions/runs/41391834357)
的 alg-aead-check-runtime 和
[wasm64 41391840143](https://github.com/HighCWu/distro/actions/runs/41391840143)
的 alg-aead-wasm64-check-runtime。目标结果尚待验收；每路必须核实 hash、
skcipher、Netlink、AEAD 各三阶段、唯一 pass 和既有 machine.closed 门禁。
静态模型、预取成功和排队/构建状态均不代替实际 AEAD 或关闭证据，也不代表
libkcapi、异步密码操作、浏览器、ELF 或动态链接已经可用。

后续 CI 检查发现第九十七组固定 fd54b54 的两个旧 Netlink workflow/Heavy
均已明确失败。已取得的完整实际日志含
`::vm-test::fail: NETLINK_CRYPTO: CBC-AES metadata errno=9`，不是功能阶段
通过；其它位宽的完整日志仍在补取，不能据 workflow 状态推定其具体阶段。
这里的 errno 是元数据断言时遗留的值，不能把它解释为 Netlink 返回 EBADF。

静态回溯确认 Linux crypto/lskcipher.c 的 crypto_lskcipher_report 使用
CRYPTOCFGA_REPORT_BLKCIPHER 且 type 为 lskcipher；crypto/skcipher.c 的
同类报告则为 skcipher。原消费者只允许后者，是一处会拒绝合法内核报告的
验证缺陷。distro `0aac780` 接受这两个明确类型，同时保留报告大小、算法名、
blocksize=16、keysize=16..32、ivsize=16 的检查；`b1724aa` 再输出实际后端
与上述长度，供后续目标证据核对。未改内核算法、权限或 ABI 来迎合检查。

MIT 轻量重放直接调用真实消费者的 report 函数：GCC/Clang 接受两类合法
报告，仍拒绝未知类型和错误 IV 大小；恢复旧断言必须重现 lskcipher 失败。
Clang 静态分析通过，无宿主 socket/凭据操作。这证明修正覆盖已发现的断言
遗漏，不证明旧目标故障的全部原因已经排除，仍需新目标验收。

源改动已推送后，主仓库 `84e9d21` 单独更新 distro pin 与重放门禁。固定
b1724aa 仅重新派发联合
[wasm32 41392740010](https://github.com/HighCWu/distro/actions/runs/41392740010)
和 [wasm64 41392746033](https://github.com/HighCWu/distro/actions/runs/41392746033)，
以同一轮同时重验 Netlink、hash/skcipher 回归和 AEAD；不再额外派发同版本
独立 Netlink 目标。旧 107b069 联合任务仍运行时保持运行，但不用于该修正
验收。新结果仍待核实十二阶段、唯一 pass 和机器关闭，不提前接受新内核能力。

### 第九十八组后续目标证据

旧 Netlink 的 wasm32/64 完整日志现均已补齐（分别 5,629,440 和 5,514,255
字节），两份都在 CBC-AES metadata 断言失败。旧 107b069 联合 wasm32
job125104824114 的完整日志另确认：新 AEAD 内核已链接并启动，hash/skcipher
六个旧阶段通过，随后停在同一 Netlink 断言；尚未进入 AEAD，不作 AEAD 功能
或关闭验收。

修正 b1724aa 的联合双位宽 workflow/Heavy 随后均成功。已读取 wasm64
job125107582198 完整实际日志 5,325,186 字节，确认 hash/HMAC、skcipher、
Netlink、AEAD 各三阶段及唯一 pass；实际报告明确为
`backend=lskcipher block=16 key=16..32 iv=16`。AEAD 包含空记录/NIST 向量、
跨页 AAD/明文、坏 tag 不输出明文、无效目标后恢复和 fd 清理。

固定 b1724aa 的 run-test.js 在返回成功前等待 closeTestResources，后者等待
machine.closed 并关闭磁盘；任何关闭失败会使退出码非零，Nix 运行检查又要求
退出码0。因此接受 Linux c4420655e / distro b1724aa 的上述 wasm64 Node 范围，
包括关闭门禁。wasm32 job125107557665 随后也已取得完整实际日志 5,466,875
字节，核实同样十二阶段、唯一 pass、lskcipher 的相同具体元数据及同一关闭
门禁。因此这两组 Node 位宽均已按实际目标结果接受，范围固定为 Linux
c4420655e / distro b1724aa；不代验后续 RNG、新内核、浏览器或 libkcapi。

## 第九十九组：接通标准 AF_ALG RNG 与原有 DRBG

Linux `19367bfc1` 在三个命名 defconfig 中启用 CRYPTO_USER_API_RNG 和
CRYPTO_DRBG_MENU，沿官方条件选择默认 HMAC_DRBG 及其 SHA-512 依赖。
crypto/algif_rng.c 原本通过内核临时数组生成、memcpy_to_msg 交付用户结果，
不要求将 Wasm 用户内存固定为内核 page，因此本轮复用原路径，无需新增转换桥。
不修改算法、熵源、健康检查或播种逻辑，不添加 libc API 或公开应用接口。

resolved Kconfig 门禁要求 RNG/DRBG/HMAC/SHA512 依赖实际启用，并保持
CRYPTO_USER_API_RNG_CAVP 关闭。程序先等待标准 getrandom 确认内核 RNG
准备好，再以 ALG_SET_KEY 的空 personalization 请求原有自动播种，不注入
测试熵。审查还核对 af_alg 的 parent refcnt/nokey_refcnt 规则：接受 operation
后修改父状态返回 EBUSY，必须先关闭它，再播种并重新接受；保持原内核约束。

独立 MIT C 消费者三阶段覆盖：未播种拒绝、播种/活动 operation 限制、128 字节
接收上限及分散输出尾部保护；无效线性地址、普通 RNG 拒绝 send 与继续生成；
降到 uid/gid65534 后重新播种、两个 operation 在 parent fd 关闭后继续使用、
最后关闭所有 fd。比较生成输出仅作交付和状态推进检查，不作为随机质量认证。
GCC/Clang 严格前端、Clang 静态分析、双位宽 Wasm 前端/分析、命名配置及禁用
反向控制、Nix 格式和 shell 语法均通过；不在宿主运行 socket、凭据或 RNG 消费者。

源码预取 [41393865593](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41393865593)
的 job125110885811 实际日志核实完整 Linux revision
`19367bfc1d6b501d85ad77724130f5187df4c92e` 与
`sha256-NbjHGv8/3iHT7XYUxQSisR4bgKoZcjFxNpTlM2GGq6E=`。distro `5ba5a18`
随后集成精确 pin、配置门禁与两个目标，主仓库 `af126ad` 再单独更新 Linux/
distro gitlinks 和轻量前端检查。musl/LLVM pin 保持原值。

固定 5ba5a18 的
[wasm32 41394417539](https://github.com/HighCWu/distro/actions/runs/41394417539)
请求 alg-rng-check-runtime，
[wasm64 41394429190](https://github.com/HighCWu/distro/actions/runs/41394429190)
请求 alg-rng-wasm64-check-runtime，已各派发一次。实际内核链接、播种、三个
RNG 阶段、唯一 pass 和机器关闭仍待验收；不以预取/轻量检查或旧密码接口的
结果替代它，也不扩大为全部 RNG 算法、浏览器或 FIPS/CAVP 支持。

### 第九十九组后续：runner 磁盘耗尽的环境修复

固定 5ba5a18 的 wasm32 workflow/Heavy 已成功，job125112657579 的完整实际
日志 5,641,171 字节随后已核实三个 RNG 阶段和唯一 pass：正常内核播种/未播种
拒绝/有界向量输出、无效目标与不支持写后的继续生成、非特权使用/parent 生命周期/
fd 清理。精确 5ba5a18 的运行器与已 review 的 b1724aa 关闭代码无差异，成功
退出仍要求 closeTestResources 等待 machine.closed；关闭失败或 watchdog 会
令 Nix 检查失败。据此接受 Linux 19367bfc1 / distro 5ba5a18 的 wasm32 Node
上述 RNG 范围，不代验浏览器或 wasm64。wasm64
[job125112709564](https://github.com/HighCWu/distro/actions/runs/41394429190/job/125112709564)
则在 Build isolated check 进行时终止，日志下载端点两次返回404；check-run
错误注解明确为 System.IO.IOException / No space left on device，连 runner
自己的诊断日志都无法写入。这是已确认的 runner 空间故障，尚无该任务的 RNG
运行结果，不能推测算法或接口发生错误。

distro `dafa1b8` 为 heavy-check 在 Nix 安装/缓存恢复前调用独立 MIT
distro/ci/reclaim-runner-space.sh。依据
[GitHub 官方 runner 变量](https://docs.github.com/en/actions/reference/workflows-and-actions/variables)
同时检查 GITHUB_ACTIONS=true、RUNNER_ENVIRONMENT=github-hosted 和
RUNNER_OS=Linux；非本次云端环境拒绝执行。只清理固定的预装 Android、.NET、
GHC 目录，记录清理前后 df，保留 workspace、runner/tool cache、Nix store、
GC roots、动作缓存与构建材料。未换付费 runner，也未通过删除已完成 LLVM
输出腾空间。实际可用空间及后续构建仍须新任务验证。

Bash 语法、非 CI/自托管/非 Linux 拒绝、显式 dry-run 和非法参数检查通过；
本地没有执行删除。工作流 YAML 和清理在恢复缓存之前的顺序已核实，既有十项
缓存/LLVM 保留合同检查通过。相对 5ba5a18，RNG 程序、内核 pin 和运行层源码
未变，仅修改 CI 环境；主仓库 `a90812e` 随后单独更新 distro gitlink。

固定 dafa1b8 仅为已失败的位宽派发
[wasm64 41396235576](https://github.com/HighCWu/distro/actions/runs/41396235576)
的 alg-rng-wasm64-check-runtime；不重复派发已成功的 wasm32。源码/轻量
检查通过不证明空间故障已经消除或 RNG 已完成，仍需三阶段、唯一 pass 与
machine.closed 的实际验收。LLVM 符号版本候选仍运行时保持运行，不因慢而取消。

第九十九组 wasm64 重验已核实：dafa1b8 的 job125118150587 完整实际日志
5,527,383 字节含 RNG 三阶段和唯一 pass；精确版本的运行器、RNG 消费者与
Linux pin 相对 5ba5a18 无差异，仍以 machine.closed 成功及关闭磁盘为退出码0
前提。因此接受 Linux 19367bfc1 的 wasm32（distro 5ba5a18）及 wasm64
（distro dafa1b8）Node RNG 范围。该次清理的实际 df 从已用59G/可用86G
变为已用42G/可用103G，约释放17 GiB；不据此保证任意未来缓存都不会耗尽。
日志中的源码请求429已由原有重试恢复，不能把恢复后的成功目标误记为运行失败。
不代验后续 socket-diag 内核、浏览器或其它 RNG 算法。

## 第一百组：标准 socket 诊断与未修改源码的 iproute2 ss

Linux `de746039d` 在三个命名配置启用 UNIX_DIAG、INET_UDP_DIAG，并明确保留
INET_DIAG 原有默认 y 与其 TCP 诊断条件。新能力来自 net/unix/diag.c 和
net/ipv4/udp_diag.c 原有处理器；socket-diag 核心已由 net/core/Makefile 编译，
没有虚构 CONFIG_SOCK_DIAG 或改写通用 Netlink、权限与数据格式。仍为 NOMMU
直接线性内存：请求/报告通过原有内核缓冲与用户复制，不要求固定用户页。

新增透明命名的 iproute2-ss 产品：构建完整上游 ss 及 libutil/libnetlink 依赖，
不宣称提供整个 iproute2 套件。固定官方 7.3.0 归档，SHA256
`5c1789d290bba048a6135ed1ab81b0402dd0fb528d1f1421765c42b1fc3d6289`
与 [kernel.org 发布校验表](https://mirrors.edge.kernel.org/pub/linux/utils/net/iproute2/sha256sums.asc)
相符，未核验 PGP 签名。没有应用 C 补丁或私有函数替换，使用上游 configure/
Make 目标和静态库选项，libbpf 通过上游选项关闭。libutil 原始代码包含 fork，
所以使用现有可选 static C fork 执行配置并完成既有 finalization，而不删除
该源文件或伪造 fork 声明；未改变默认 SDK、musl API 或 fork 的线程支持边界。
保留上游 GPLv2/COPYING，独立配方、检查与材料说明为 MIT；源包包含完整归档、
配方、SDK 材料链接与最终二进制摘要，运行前核对其版本与文件身份。

普通 C 检查使用默认 libc 的 posix_spawn/exec 路径运行真实 /sbin/ss，要求三个
阶段：按 fstat inode 和地址找到本次创建的抽象 UNIX listener、绑定 UDP4 socket
与 TCP4 listener；
关闭 fd 后新查询不再包含旧 inode；降为 uid/gid65534 后重复创建、核对 UID 与
清理。所有 fixture socket 为 CLOEXEC，不让被查询工具延长其生命；工具必须
正常退出且仅回收一次。标准输出有64 KiB上限，检查器按整行/完整数字 token
匹配，避免 inode/端口/UID 前缀或别的行误通过。

专用目标不挂载 procfs，检查器先确认 /proc/net/{unix,tcp,udp} 不可读，子进程
环境也不提供 PROC_* 覆盖。核对上游 ss 的 UNIX/UDP/TCP 路径均先查 Netlink、
失败才读 procfs，因此缺少诊断处理器不能靠回退或空列表冒充成功；不是通过
修改 ss 强制得到答案。核对既有 boot-init.sh 也不挂载 procfs。

GCC/Clang 严格前端、Clang 分析、双位宽既有 musl 头下的前端/分析、命名
配置与禁用反向控制、Nix 格式、shell 语法通过；真实检查器的纯解析重放拒绝
数字前缀、跨行与空输出。没有在宿主执行 socket、spawn 或凭据检查。上游工具
的完整目标构建/运行尚待 CI，不以这些轻量检查代替它。

源码预取 [41398333158](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41398333158)
的 job125124450960 实际日志核实完整 Linux revision
`de746039de4a61c44941dc30fad9e124ed001eca` 与
`sha256-RqMqVe7gF1yJ1HPsQbmmqOn+aSf/iKe/gy3JViw2OHk=`。distro `5fa0584`
随后集成该 pin、resolved Kconfig 门禁与匹配位宽的真实工具/检查闭包；主仓库
`43d18e4` 再单独更新 Linux/distro gitlinks 和轻量检查。musl/LLVM pin 不变。

固定 5fa0584 各派发一次
[wasm32 41400511214](https://github.com/HighCWu/distro/actions/runs/41400511214)
的 socket-diag-check-runtime 与
[wasm64 41400517248](https://github.com/HighCWu/distro/actions/runs/41400517248)
的 socket-diag-wasm64-check-runtime。实际工具链接、三个阶段、唯一 pass 和
machine.closed 仍待核实。不扩大为所有 ss 选项、BPF、socket 销毁管理、全套
iproute2、动态链接或浏览器支持，也不把旧内核的 RNG 验收泛化到新 pin。

上述两个 5fa0584 任务均在 formatting 门禁失败，尚未进入目标运行；实际日志
确认 treefmt 的 unexpected changes，而不是 socket syscall 失败。后续 distro
`94b4d3d` 按固定 shfmt 3.14.1 修正 shell case 分支格式，主仓库 `3deb86b`
单独更新 pin。新源码各派发一次
[wasm32 41402479096](https://github.com/HighCWu/distro/actions/runs/41402479096) 与
[wasm64 41402485337](https://github.com/HighCWu/distro/actions/runs/41402485337)，
仍待真实目标阶段和关闭结果，不能据格式修复宣布验收。

94b4d3d 两路任务随后均失败。实际读取 job125137200303 的7,866,753字节日志与
job125137211697 的7,587,779字节日志，均确认机器已启动，随后出现
`sh: can't re-execute the shell`，并因 init 退出触发 panic；不是 ss 编译失败，
也没有完成任何 socket 验收阶段。原因与后续修复见下一组，不重复派发该版本。

## 第一百零一组：标准 Netlink socket 监控与无 procfs 的 shell 执行

Linux `6c4cb40da` 在公共及双位宽 defconfig 启用 `CONFIG_NETLINK_DIAG=y`，
接通原有 net/netlink/diag.c 的 SOCK_DIAG_BY_FAMILY 处理器。此前它未启用，
标准 socket/sendto/recvmsg 无法得到该类 dump。这是启用实际 Linux 协议能力，
没有新增 syscall 号、用户 API、libc 包装或 Wasm 专有诊断实现。源码审查确认
它在内核 SKB 中构造记录，沿现有 uaccess 交付，不固定用户 linear-memory 页。
保留 CONFIG_MMU=n，未扩大 fork 或线程范围。

普通 C 检查创建并 autobind 一个 NETLINK_USERSOCK socket，使用 fstat 与
getsockname 取得 inode 和 port ID，再通过 NETLINK_SOCK_DIAG 请求同协议的
完整 multipart dump。校验序列、来源、截断、消息长度/对齐、完成状态，以及
唯一 inode/port/type 记录；关闭原 fd 后新请求必须不再包含它。循环与 datagram
容量均有上界，检查对齐剩余长度后才推进无符号游标，避免畸形消息导致下溢。
降为 uid/gid65534 后再次执行创建、监控、关闭与恢复查询。

同时执行未修改 C 源码的上游 ss 7.3.0 `-f netlink`。其 Netlink renderer
本来不打印 inode/UID，因此由原始 dump 核实 inode，再让实际工具独立核对相同
usersock/port token；不伪造它没有的输出。保持 procfs 不挂载，并确认
/proc/net/netlink 不可读，子程序环境没有 PROC_* 覆盖，不能靠 proc 回退或
空列表假通过。原来的 UNIX/UDP/TCP 检查保留。

上一组发现的启动失败也修复在通用 BusyBox 发行配置：固定源
`tombl/busybox@4ad91c87e7efeff15628bea7240b6055b2737644` 的 hush NOMMU 路径
调用 execve(bb_busybox_exec_path)，而上游 BUSYBOX_EXEC_PATH 默认依赖
/proc/self/exe。其 Config.in 明确提供无 procfs 时配置实际安装路径的选项。
distro `9a08b37` 设置该原有选项为 /bin/busybox，并在 oldconfig 后核实结果；
镜像与 boot initramfs 都包含这个安装路径。没有修改 BusyBox C 源码，也没有
删掉原检查脚本的子 shell、命令替换或改为挂载 procfs 规避问题。脚本新增真实
启动阶段标记，须在原校验子 shell 与 ss 版本命令替换都完成后才输出。

轻量检查通过：GCC/Clang 严格前端及静态分析，当前 musl 和该 Linux UAPI 下
wasm32/64 的本机 Clang18 前端/分析，实际 parser 对 inode/UID/address/Netlink
port 的完整 token 与跨行拒绝，三套配置及禁用控制，固定 Nix/shell 格式和语法。
本机 Clang18 不识别 fork 的 Linux target triple，双位宽检查使用它的 Wasm
target 与当前头文件；这不能替代配套编译器的链接和运行。没有在宿主执行 socket
或凭据检查，也未把静态审查写成畸形包目标运行验收。

[预取 41404651475](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41404651475)
的实际日志核实完整 revision `6c4cb40dabafc588f2b2cba01929d4b8ca185f35` 和
`sha256-FTSBUiNGIBgPig3MJf4jipovWamTguHtC+HPnf5CLH4=`。distro `659cc45`
集成处理器 pin 与检查，主仓库 `8d9b9f3` 单独更新 gitlinks 和轻量门禁；
后续 BusyBox 修复 `9a08b37` 由主仓库 `151a119` 单独更新 pin。musl 和默认
LLVM pin 未改，自有检查为 MIT，上游许可证保留。

固定 9a08b37 各派发一次
[wasm32 41405897272](https://github.com/HighCWu/distro/actions/runs/41405897272) 与
[wasm64 41405903429](https://github.com/HighCWu/distro/actions/runs/41405903429)。
必须核实无 procfs shell 启动阶段、原 UNIX/UDP/TCP 三阶段、新 Netlink 三阶段、
唯一 pass 和机器关闭，当前均待目标证据。新内核不能继承此前密码接口的验收；
也不扩展为 packet 诊断、socket 销毁、全部 ss 选项、浏览器或动态链接支持。

9a08b37 的两路日志现已实际核实：wasm32 job125147861740 为7,869,676字节，
wasm64 job125147851630 为7,589,514字节，都完成了无 procfs 的子 shell/命令
替换阶段，随后在 ephemeral loopback bind 返回 EADDRNOTAVAIL。专用 rootfs
尚未配置 loopback IPv4 地址，不是前一 shell 修复失效，也没有 socket 功能
阶段通过。distro `ab3f787` 在专用 init 中用普通 ifconfig 配置自身 lo 的
127.0.0.1，消费者结束后再将接口 down，清理成功才发布 pass；不改 ss 源码。
主仓库 `dbb7f95` 单独更新 pin。固定 ab3f787 的
[wasm32 41408752049](https://github.com/HighCWu/distro/actions/runs/41408752049) 与
[wasm64 41408758963](https://github.com/HighCWu/distro/actions/runs/41408758963)
各派发一次，仍待六个 C 阶段、shell/loopback 阶段、唯一 pass 与关闭证据。

ab3f787 的两路实际日志再次发现检查器错误：wasm32 job125156775972 为
7,289,428字节，wasm64 job125156809079 为7,367,568字节。shell 阶段均通过，
lo 初始化后已取得真实 ss 的 UNIX listener 行；失败是检查器错误要求 UNIX
输出含 socket 的 ino: 标签。上游 unix_stats_print 把 socket inode 放在本地
port 列；可选 ino: 细节属于文件系统 inode，抽象 socket 本来没有这一项。
unix_show_sock 也不打印 UID，不能照搬 INET 的标签规则。报错附带 errno=9
来自此前预期的 fd 关闭检查，不是此次 socket 返回 EBADF 的证据。

distro `44431ae` 改为严格匹配 UNIX 的本地 inode 列与完整 abstract-name 列，
INET 保留 ino:/uid: 校验。UNIX 另用原有标准 SOCK_DIAG_BY_FAMILY 请求
UDIAG_SHOW_UID，核对同一 inode、SOCK_STREAM 和创建者 UID，并在关闭后要求
raw dump 及 ss 都不再包含它，未删掉 UID 覆盖。复用有界 multipart 收发，
分别发送20字节 Netlink/24字节 UNIX request；属性解析拒绝错长、截断、
对齐不足和重复/带错误标志的 UID。ss 源码和输出保持上游原样。

宿主重放改用实际失败行的格式，拒绝数字前缀、peer/queue 伪 inode、文件系统
ino: 冒充本地列及跨行 token，并校验真实 UID 属性布局和坏包拒绝。GCC/Clang
严格前端、静态分析与当前 musl/UAPI 下双位宽本机前端/分析通过；没有在宿主
打开 socket 或改凭据。主仓库 `d11dae8` 单独更新 pin 与真实 parser 重放。
固定新源码的
[wasm32 41415525397](https://github.com/HighCWu/distro/actions/runs/41415525397) 与
[wasm64 41415532045](https://github.com/HighCWu/distro/actions/runs/41415532045)
各派发一次，实际六个 C 阶段、shell/lo 清理、唯一 pass 和关闭仍待核实。

44431ae 的两路完整日志已核实失败：wasm32 job125178440963 为7,839,831字节，
wasm64 job125178543375 为7,533,728字节，均停在 ss Netlink protocol/port
匹配。wasm64 日志还明确完成 shell、UNIX/UDP/TCP live 和 closed 三个阶段，
但未到非特权阶段、loopback 清理或 pass，不作为完整验收。上游 ss 的
nl_proto_n2a 在 numeric 模式返回数字，而消费者传了 -n 却期待 usersock 名称。
distro `7b40195` 改为匹配 NETLINK_USERSOCK 数字协议号及实际 signed port，
raw dump 的 inode/port/type 校验保持，失败时补充有界实际输出。宿主 parser
重放同步拒绝错误协议号、名称/数字混淆、前缀和跨行匹配。主仓库 `a3913eb`
单独更新 pin；固定源码的
[wasm32 41419482339](https://github.com/HighCWu/distro/actions/runs/41419482339) 与
[wasm64 41419490536](https://github.com/HighCWu/distro/actions/runs/41419490536)
各派发一次，完整阶段和关闭仍待核实。

固定7b40195的两路现已实际核实通过：wasm32 的完整压缩 run 日志为1,556,906
字节、Build isolated check 解压后7,815,497字节；wasm64 分别为1,479,094和
7,509,043字节。各包含六个实际 C 阶段、无 procfs shell 阶段、loopback
teardown 和唯一一次 pass，无目标 fail/panic；Heavy 与工作流均 success。
核对该版已发布 run-test.js/shutdown.js：退出0之前必须等待 closeTestResources
及 machine.closed，之后才关磁盘；Nix 也必须取得退出0。因此关闭门禁成立，
不是仅以工作流绿色代替实际阶段。接受该版 Linux d79048f56 的双位宽 Node
原版 ss/UNIX/UDP/TCP/Netlink 范围，不推广至新 cgroup 内核、浏览器或全部 ss
选项。该 runner 关闭实现与当前源码一致。

## 第一百零二组：接通标准 bpf syscall 与原有解释器

Linux `d79048f56` 在三套 defconfig 启用 `CONFIG_BPF_SYSCALL=y`，接通原有
bpf syscall 的 map、程序验证/装载及对象 fd 命令。NET 原本已选择 BPF 解释器，
这里不新增指令引擎或 Wasm JIT。BPF_SYSCALL 上游默认 n，本次按平台能力需求
选择启用，不称作恢复一个默认 y。resolved 配置要求 BPF、BPF_SYSCALL 与官方
默认的 BPF_UNPRIV_DEFAULT_OFF 为 y，JIT/JIT_ALWAYS_ON 保持关闭。没有降低
非特权创建政策、启用内核 softmmu 或扩大多线程 fork。

MIT 普通 C 消费者通过已存在的 syscall(SYS_bpf, ...) 使用 Linux UAPI，所有
标量可变参数显式使用机器字；没有新增 musl 包装函数或公共头文件 API。其三个
阶段要求：array 的初始/更新状态、真实对象 id/元数据、EFAULT 后状态及 fd 别名
生命周期；实际验证/装载一个 map-backed socket filter，由 helper 读取 map
控制 AF_UNIX datagram 的丢弃/接收，包含 NUL/二进制字节；map freeze 拒绝修改，
关闭原 program/map fd 后 socket 持有的程序仍能运行，非特权用户创建被拒绝，
最终所有测试 fd 关闭。fd 关闭与引用保持不等于已观测全部 RCU 对象物理回收。

该程序使用自己的 socketpair，不配置外部网络。手写11条标准 BPF 指令，包含
双槽 map fd 装载、栈 key、map_lookup_elem helper、空指针分支和 map value
返回。实际丢弃前的 readiness 检查与更新后的精确接收共同约束执行行为，不能
只凭 PROG_LOAD 返回 fd 假通过。程序元数据另需匹配 map id 且 jited_prog_len
为0。验证器失败时保留有界日志；没有绕过原有验证器或把用户代码直接作为 Wasm
内核函数实例化。

静态 review 覆盖 map fd 到程序再到 socket 的引用链、冻住后的值、权限默认、
__aligned_u64 指针槽和 instruction 布局，以及解释器/helper 都在内核 memory
运行、用户参数仅沿既有 uaccess 复制的边界。上游的 BPF map mmap 与需要内核
BTF/其它 attach 类型的能力没有因此验收。GCC/Clang 严格前端与静态分析、当前
musl/该 Linux UAPI 下 wasm32/64 的本机前端/分析、固定 Nix/shell 格式及三套
配置禁用控制通过；没有在宿主执行 bpf 主程序或降权，不替代配套编译器和内核
的真实链接/运行。

首次[预取 41407801470](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41407801470)
实际日志确认两个归档端点均 HTTP429，而非源码或编译错误。主仓库 `aa62abe`
为已有 Git 归档预取实验增加精确三套 defconfig 修改的允许范围，仍拒绝路径、
模式、属性、父版本和独立基线 hash 不符，原 futex 单文件范围保留，宿主控制流
验证通过。没有接受缺失 hash 或把传输改为不校验的 checkout。

[Git 预取 41408420756](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41408420756)
job125155641189 的实际日志核实基线 `6c4cb40dabafc588f2b2cba01929d4b8ca185f35`
与 `sha256-FTSBUiNGIBgPig3MJf4jipovWamTguHtC+HPnf5CLH4=` 一致，随后才得到
候选 `d79048f56263e88d585c86a38b6a1b0022fac53e` 的
`sha256-aHhvbJnFRb5YA0hOGNn8+llMHUs0Gk5cFdrK1oXccUQ=`。distro `641eb07`
原子集成精确 pin、配置门禁和双位宽产品，主仓库 `18f4976` 单独更新 gitlinks
及原始配置检查。musl/默认 LLVM pin 未变，上游许可证保留，自有消费者为 MIT。

固定 641eb07 各派发一次
[wasm32 41409004742](https://github.com/HighCWu/distro/actions/runs/41409004742) 与
[wasm64 41409010607](https://github.com/HighCWu/distro/actions/runs/41409010607)。
实际三个阶段、唯一 pass 与 machine.closed 门禁仍待核实。不将编译/宿主分析
泛化为所有 BPF map、BTF、tracing/kprobe、JIT、libbpf、浏览器或系统沙箱验收。

固定 641eb07 的两路 Node 现已实际核实通过：wasm32 job125157648958 的完整
日志为5,817,061字节，wasm64 job125157579939 为5,700,874字节；各出现上述
array/错误恢复、实际 helper 驱动 socket 丢弃与接收、冻结/权限/fd 生命周期
三个完整阶段，且唯一 pass 各一次，无目标失败或 panic。两个任务和 Heavy 均
success。核对该版已发布 runner：成功退出前等待 closeTestResources，内部
await machine.closed 后才关闭磁盘；Nix 必须取得退出0才完成。因此关闭门禁
也成立，不能只用工作流绿色替代阶段证据。接受 Linux d79048f56 / distro
641eb07 的双位宽 Node array/socket-filter 范围，保留前述其它 BPF 能力边界。

本轮另核查了固定 libpcap 源码
[固定 pcap-linux.c 源码][pcap-linux-fixed]：
其 activation 要求 TPACKET mmap capture，版本探测失败是错误，ring mmap
失败也直接退出。不能靠更换 errno 声称会回退到普通 recvmsg。当前未修改
AF_PACKET ring 选项、未加 libpcap 补丁；真正的共享 ring 仍为未完成能力。

[pcap-linux-fixed]:
  https://github.com/the-tcpdump-group/libpcap/blob/69733af23aa55f221aaa5e23053f13eb55af4d35/pcap-linux.c

## 第一百零三组：可选 fork 配置恢复正常 Autoconf 探测

静态 review 发现：显式 static C fork SDK 已有 fork syscall continuation，
但可选 Bash 配方仍加载默认 distro/config.site，其中 ac_cv_func_fork=no 和
ac_cv_func_fork_works=no 会直接否定这一接口，使应用跳过正常声明/链接探测。
这是已实现能力的构建发现错误，不是本轮新实现 fork syscall，也不以测试数量
或新增 libc 函数作为进度。

distro `19f7a7c` 为可选 SDK 生成独立 config.site：先复用默认策略，再仅 unset
两个 fork cache 变量，交回 Autoconf 正常探测，不预填 yes。默认 SDK 的策略
完全不变；vfork、固定/文件映射完整探测及动态加载仍保持否定。文件安装于
share/linux-wasm-fork-sdk/config.site，profile.json 记录路径，Nix 的 configSite
属性提供同一生成文件，材料包含默认策略及生成版本。应用使用标准 CONFIG_SITE
环境变量，无项目专有运行 API。

可选 Bash 仅切换所选策略文件，未新增 C 源码补丁；仍需 fork-enabled libc、
完整链接 finalization、单线程 static C 和配套 runtime。没有把 tombl/musl 中
存在但被 Wasm 门控的通用 vfork 回退恢复为共享 vfork 支持，Dash 的显式应用
回退不变；原始共享地址空间和父进程挂起语义仍是缺口。内核、musl、默认 SDK
及 LLVM pin 均未改变。

本地 sh/bash 实际执行默认策略和 profile 策略，覆盖宿主 yes cache 被清除、
只有两个 fork 变量未设置、其它六项仍为 no；原有 SDK finalizer 与 Bash 的
普通进程负载/失败依赖检查通过，固定 Oxfmt/Nixfmt、shell 语法与静态 review
通过。Nix fixture 同步复制两个策略源文件，避免只在仓库目录通过。以上不证明
新 configure 的 Wasm 输出或完整目标运行。

源码原子推送后，主仓库 `3f0c65d` 单独更新 distro pin。固定 19f7a7c 的
[wasm32 41412893217](https://github.com/HighCWu/distro/actions/runs/41412893217) 与
[wasm64 41412899722](https://github.com/HighCWu/distro/actions/runs/41412899722)
Bash 普通 fork 检查各派发一次；要核实四个实际阶段、唯一 pass 和既有关闭
门禁，当前待目标证据，不把宿主 Bash 通过视为 Wasm fork 验收。

wasm64 的 job125169990387 已实际读取完整7,801,788字节日志：configure 加载
fork-wasm64-config.site，随后标准 fork/作用域/管道、process substitution/
coprocess、后台 wait/信号/隔离、exec 错误与后续恢复四个实际阶段全部出现，
唯一 pass 一次，无目标失败。Heavy/任务均 success；该版未改的 runner 成功
返回仍必须等待 machine.closed 及磁盘关闭，接受该位宽的此 Bash 范围。wasm32
job125169904392 随后也完成实际核实：完整8,107,644字节日志加载匹配的
fork-wasm32-config.site，四个相同的目标阶段与唯一 pass 均出现，无目标失败，
且任务/Heavy 成功，关闭门禁同样成立。接受固定19f7a7c的双位宽 Node Bash
范围，不扩展为 vfork、多线程 fork、动态链接或浏览器验收。

## 信号栈缺口的前期核查记录

在 `a228fc8` 基线，sys_sigaltstack 被 Wasm 架构重定向到 ENOSYS，原因可追到
arch/wasm/include/uapi/asm/ptrace.h 的 user_stack_pointer 仍是 trap；不能直接
去掉 syscall 重定向就宣称支持。普通 SDK 配置没有显式请求导出 __stack_pointer，
可选 fork profile 则显式导出该全局；新执行契约还需核查最终模块的实际导出。
双位宽最小 C/JS 实验已核实：在暂停的 C 调用
之间切换该全局，handler 的 C 局部帧可进入独立替代缓冲区，正常返回恢复旧
全局后，原 C 局部帧内容不变。此实验不接入内核，也不证明 Linux sigaltstack
已实现，更不证明 Wasm VM 自身调用栈、trap 或栈溢出可由该机制恢复。

当时确定的实现约束是在内部执行 ABI 中提供可靠的用户 C 栈指针，保留双位宽地址和旧
模块拒绝行为，复用 Linux 的注册/查询/错误语义，并在信号回调中真正切换。
必须一起处理嵌套 SA_ONSTACK、SS_ONSTACK 查询、SS_AUTODISARM、正常返回和
SjLj 非局部退出，验证不会覆盖编译器在 catchpad 恢复的栈指针或破坏原掩码。
不是新增 musl 公共函数，也不能只保存注册状态却仍在原栈执行 handler。

同轮 wchan 审查撤回了尚未发布的工作负载和改动：当前 KALLSYMS 因 fork 的
wasm-ld 依赖条件被关闭，fs/proc/base.c 也未编译 wchan 项。__get_wchan 的
BUG 不能据此宣称为默认构建已可触发的 proc 读取漏洞；需先处理符号/展开支持
和可达路径，再设计真实目标验证。本轮未将返回0替代桩或不存在的 proc 接口
列为新能力，也未为该未实现项派发重型检查。

## 第一百零四组：标准 cgroup v2 PIDs 准入与 fork 回滚

Linux `3dc991222e5466857a5b85b0477d7905462020c6` 在三套 Wasm defconfig
启用 CGROUPS 与 CGROUP_PIDS，复用官方上游 kernfs/cgroup、pids_can_fork、
pids_cancel_fork 与 pids_release。两项均是上游可选能力，不宣称默认 y；
没有修改 MMU、内存映射或 fork 执行模型，没有自造限额 syscall/宿主替代品。
构建门禁核实 resolved CGROUPS/CGROUP_PIDS/KERNFS=y，原始配置检查含每项
关闭后的反向控制。

新增独立 MIT 消费者只用已有 libc 声明、普通 fork/waitpid、mount 和 fd 接口：

- 挂载 cgroup2，启用标准 pids controller，创建叶组并迁入调用进程；默认
  pids.max=max。设限1后 fork 必须返回 EAGAIN，pids.events 的 max 增加，
  current 保持1，waitpid 验证没有已发布或未回收子进程。
- 设限2后正常 fork，通过 pipe/poll 有界交接。子进程继承同组，current=2；
  子进程的后续 fork 也必须 EAGAIN，父端核对事件/current，释放并回收子进程，
  current 回到1且无剩余子进程。父子分别关闭无用/完成交接的 pipe fd。
- 恢复 max 后再次 fork/wait 并核对退出码，迁回根组、叶组 current=0、删除
  叶组、撤销控制器并卸载；全部清理成功后才发布第三阶段和唯一 pass。

三个 C 阶段分别为 standard hierarchy/membership/admission rollback、inherited
child limit/live accounting/wait cleanup、unlimited recovery/migration/teardown。
普通 stdout 设为不缓冲，防止 fork 复制缓冲导致重复阶段。每次控制文件写入
保持完整单次写；有界读取和数值解析拒绝截断或错误内容。

GCC 严格前端、Clang 静态分析及本机 Clang18 在当前 musl 头文件下 wasm32/64
前端与分析通过；临时头文件仅应用已有可选 fork SDK 的 fork/_Fork 声明门控，
不伪造应用声明，也没有修改默认 musl。没有在宿主运行 cgroup 消费者、挂载
或迁移进程。本地分析不代替配套 SDK 链接、真实内核运行或关闭验收。

[预取 41419307614](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41419307614)
的完整20,807字节日志核实先验证 d79048f56 的既有基线哈希，再得到候选
`sha256-DRtZ7x1yhKUNkQ8cI0ZZXmJJIs3EHUnAbk35ICuNgrw=`。只改三套 defconfig，
符合已有 Git archive 允许范围。distro `8ede319` 原子集成 pin、构建门禁和
双位宽消费者；主仓库 `e54105c` 单独更新两个 gitlinks 及轻量配置检查。
固定源码各派发一次
[wasm32 41419666514](https://github.com/HighCWu/distro/actions/runs/41419666514) 与
[wasm64 41419675485](https://github.com/HighCWu/distro/actions/runs/41419675485)。
三阶段、唯一 pass 及 await machine.closed 退出门禁均待目标证据。

范围依据[官方 cgroup v2 文档](https://docs.kernel.org/admin-guide/cgroup-v2.html)：
PIDs 计数单位是内核 task/TID，迁移等组织操作允许超过限额，不能宣称它们也被
fork 限额拒绝。本轮只验证既有可选单线程 static C fork 范围，不新增 libc API、
不开放多线程 fork，不代表 memory/CPU controller、容器隔离或浏览器验收。

## 第一百零五组：原版 util-linux setsid 使用普通 fork

现有 util-linux 的 setsid 仍带专用 callback-clone 补丁，即使可选 static C
执行配置已经具备普通 fork continuation。新增独立 setsid-fork 产品，直接
复用固定 util-linux 2.42.2 的原始 src/version，不应用默认 util-linux 的
任何 C 源码补丁。构建前后分别 cmp 原始 sys-utils/setsid.c，并发布源码哈希、
config.h/config.log、原始源码、编译器及执行支持材料。原版程序仍调用正常
fork、setsid、ioctl(TIOCSCTTY)、execvp 和 wait，不要求应用使用私有 callback。

构建使用现有可选 SDK 和正常 CONFIG_SITE；其 fork cache 已交回 Autoconf
探测，不预填成功。标准 --disable-all-programs/--enable-setsid 选择程序，
make setsid 后只对最终链接产物执行 continuation finalizer。安装独立 opt-in
镜像内的 /bin/setsid，沿用既有发行包的 BusyBox applet replacement 元数据；
没有更改默认 util-linux 配方或默认 SDK。独立消费者/构建代码采用 MIT，
util-linux 及所链接支持保留上游许可证和通知。

消费者以标准 posix_spawn 设置明确初始进程组，并通过继承的 stdout pipe
取得最终普通 C 程序的 PID/PPID/SID/PGID；不是仅检查工具退出0：

- -f -w 必须真实 fork，组长启动的 -w 必须走原版自动 fork，普通非组长
  启动则直接 exec。最终程序 SID/PGID 均为自身 PID；fork 后的 PPID 必须
  是工具 PID，直接 exec 的 PID 则必须仍是启动工具时的 PID。wait 传回37。
- -f -c -w 在独立 PTY slave 上运行，最终程序核对 stdin 是 tty，TIOCGSID
  与 tcgetpgrp 都指向自身新 session/group；master/slave 与交接 fd 均清理。
- 不存在的程序必须传回127、不得进入观察程序；随后正常子程序仍成功。
  每次只取得一条完整身份记录，用 poll 有界等候，工具只回收一次。

GCC/Clang 严格构建的消费者均在本机 util-linux 2.39.3 setsid 下通过三阶段，
Clang 静态分析及当前 musl 头文件下 wasm32/64 前端和分析通过。宿主结果仅
核对验证器和标准进程/PTY约束，不是原版2.42.2的 Wasm 执行证据。review 还
核对原始源码无应用补丁、fork 后身份、exec/wait 状态、CLOEXEC/dup2 继承、
有界报告及镜像 applet 冲突，未改变 session/tty 内核代码或新增 musl API。

distro `e8ac3c6` 发布原版工具构建和双位宽消费者，`36852d6` 补上与既有
util-linux 一致的 applet replacement 元数据；主仓库 `5976885` 单独更新 pin。
只对最终固定 `36852d6c28c73857be3a08530cf71d2ec778d923` 各派发一次
[wasm32 41420884648](https://github.com/HighCWu/distro/actions/runs/41420884648) 与
[wasm64 41420893833](https://github.com/HighCWu/distro/actions/runs/41420893833)。
原版工具真实编译、三个完整阶段、唯一 pass 与机器关闭均待目标日志，不据此
声称全部 util-linux 补丁已移除、多线程 fork 或浏览器已验收。

同轮只读审查确认 AIO 的 aio_setup_ring 仍通过 do_mmap(MAP_SHARED) 映射
内核 folios；其 completion/read-events 直接访问 ring_folios，而用户程序有
独立 Wasm linear memory。仅打开 AIO 配置或复制初始 ring 不能提供长期一致
的共享 ring，io_uring 也不能据此跳过相应前提。本轮未修改这些开关，继续
保留为需要真实映射/所有权方案的能力缺口，不把它们误归为 libc 包装缺失。

## 第一百零六组：原版 util-linux flock 的 fork/wait 与锁生命周期

现有默认 util-linux 的 flock 使用应用专用 posix_spawn 改写。本轮新增独立
flock-fork 产品，复用固定原版2.42.2源码，保留其普通 fork/waitpid 分支、
--close、--no-fork、标准定时器/信号和 exec 错误处理。它是源码兼容与实际
程序交付的增量，不声称本轮重新实现了已存在的 flock syscall，也不替换默认
util-linux 或扩大 fork 准入范围。

把 setsid 的独立构建配方移至 util-linux-fork/package.nix，两个产品共享
已有可选 SDK、正常 Autoconf 探测、静态链接/finalizer、构建前后原始 C 文件
cmp、源码哈希/许可证/构建材料及 applet replacement。program 只允许 setsid
或 flock，分别由普通 configure --enable-<program> 与 make 同名目标选择，
没有补丁、源码生成或应用 callback。先前 setsid 36852d6 的任务继续运行，
不因共享配方移动而取消或重复派发，也不将它们算作新配方已验收。

新增独立 MIT 消费者通过标准 posix_spawn 启动工具，子程序以 pipe/poll 有界
交接身份，父进程以不同 open file description 实际探测同一锁文件：

- 普通 exclusive 模式和 --close 均须真实 fork，子 PPID 为工具 PID。
  子进程按 stat/fstat 的 dev+inode 查找锁 fd：普通模式恰好一个、--close
  模式为零；即便子关闭锁 fd，工具父进程仍持锁，独立 LOCK_EX|LOCK_NB
  必须冲突。释放子进程并核对 wait 返回37后，锁必须可以重新获取。
- --no-fork 的最终程序 PID 必须仍为启动工具时的 PID，PPID 为消费者；
  同时检查继承的锁 fd、运行中冲突、退出后释放，而非只核对退出0。
- 父端持独立锁时，原版 -n -E42 返回42；-w0.1 -E43 经真实 timer/signal
  等待后返回43，单独核对经过时间，不能立即返回伪装超时。子完成等候有
  单调时钟截止时间，错误或超时会报告失败，不无限阻塞。
- 缺失可执行程序按原版 run_program 返回 EX_UNAVAILABLE（69），不是 shell
  的127；之后普通 fork、锁获取与子程序仍成功，最后关闭 fd、删除临时文件。

初次宿主运行暴露退出码预期错误，按2.42.2真实源码及本机2.39.3行为修正为
EX_UNAVAILABLE，未修改工具行为。最终 GCC/Clang 严格构建的消费者在本机
flock 下均通过四阶段；Clang 静态分析、当前 musl 头文件下 wasm32/64 前端
和分析、固定 Nix/shell 格式与脚本语法通过。宿主仅验证消费者和标准约束，
不是目标2.42.2已构建/执行的证据。review 覆盖 CLOEXEC/dup2、父子锁引用、
--close 的真实 fd 关闭、超时 signal/EINTR、正常与错误退出及共享配方参数。

distro `ef0ef00` 发布共享配方和双位宽原版 flock 产品。独立 review 另发现
cgroup 消费者的失败标记缺少冒号，实际 runner parser 不识别它；`bab75b6`
修为 ::vm-test::fail: 格式，并直接用该 parser 核对，不改变成功阶段或内核。
先前 cgroup 两路仍固定8ede319，不能因此称新报告格式已获目标验证。
主仓库 `c324530` 单独更新 distro pin，Linux/musl/默认 LLVM pin 未变。

固定 `bab75b6e3963e605ad183f7c4e2de659aca40ae5` 各派发一次
[wasm32 41422383773](https://github.com/HighCWu/distro/actions/runs/41422383773) 与
[wasm64 41422392887](https://github.com/HighCWu/distro/actions/runs/41422392887)。
原版 flock 实际构建、四阶段、唯一 pass 和机器关闭待真实日志；不扩大为全部
util-linux、浏览器、OFD/全部锁选项或多线程 fork 支持。自有新增代码 MIT，
上游许可保留，没有新增 musl 公共函数或应用 API。

## 第一百零七组：运行包与独立构建材料输出

cgroup 的8ede319两路已明确失败于运行包转换，尚未启动消费者。完整压缩
run 日志 wasm32 为1,657,442字节、wasm64 为1,629,201字节，实际错误均为
root/share/cgroup-pids-materials/sdk 指向 Nix store，并触发
APK payload contains Nix store references。不是 cgroup syscall 的运行失败，
不能把已完成的构建依赖推为三个功能阶段通过。

distro `78e85db` 为 cgroup-pids 和共享原版 util-linux 配方分别声明 out 与
buildMaterials 两个输出。默认运行输出只携带可执行文件和许可证，SDK/source
链接及 config.log/config.h/源码哈希/配方移到独立 buildMaterials 输出，仍
可供重建；不从可部署文件链接回 Nix store，也不删除出处或放宽原 payload
门禁。工具使用现有材料相对目录，Nix 消费者通过对应产品的 buildMaterials
属性取得该输出。该变化不修改 kernel、musl、LLVM 或应用 C 源码。

主仓库 `b38bdcd` 单独更新 pin，增加轻量实际安装检查并接入现有 CI：提取
并执行三种产品的真实 installPhase，使用不执行的透明 payload fixtures 和
标准工具安装，调用原 check-store-references.sh。默认运行输出须通过、独立
材料须保留 source/compiler 路径和 SDK 链接。把材料目的地重新改回 out 的
反向控制必须被同一门禁拒绝。不是仅匹配配方字符串或取消许可证/材料检查；
也不以这些轻量 fixtures 代替真正的 Wasm 编译或运行。

固定 Nix 格式、Python 语法/ruff、安装正反控制、workflow YAML 解析和仓库
元数据检查通过，review 核对默认输出选择、材料闭包和许可证边界。固定
78e85db 各派发一次
[wasm32 41423865267](https://github.com/HighCWu/distro/actions/runs/41423865267) 与
[wasm64 41423875215](https://github.com/HighCWu/distro/actions/runs/41423875215)，
仍待标准 cgroup 三阶段、唯一 pass 与关闭证据。其它旧工具任务保持原版本，
不把材料布局修复当成它们已成功运行。

## 第一百零八组：原版工具的上游默认构建条件

setsid 的36852d6两路也已确认失败，原因与 cgroup 打包错误不同：完整压缩
run 日志 wasm32 为1,582,104字节、wasm64 为1,514,219字节，实际 configure
警告 --enable-setsid 不被支持，随后 make setsid 报 clang: no input files。
原配方使用 --disable-all-programs，UL_BUILD_INIT 把 BUILD_SETSID 关闭；
原 Makefile 的同名链接规则仍在，但条件化的 SOURCES/OBJECTS 为空。
libtool 的 CXX 探测也有诊断，但 configure 继续完成；实际终止点是空输入
链接，不能据此误诊为已经运行 fork 或 PTY 失败。

静态核查固定2.42.2的 m4/ul.m4、configure.ac、生成 configure 和 Makefile.in：
setsid 没有单独 AC_ARG_ENABLE，flock 同样使用带默认值的 UL_BUILD_INIT。
distro `7081904` 去掉全局 disable 与不存在的单工具 enable 选项，保持官方
默认配置及真实依赖探测，仅由 make setsid/make flock 选择需要构建的目标。
不手工设置 BUILD_* 或伪造 HAVE_*，不修改任何应用/Makefile/configure 源码。
直接执行真实生成 configure 的对应 shell 条件，证明默认条件选入两个目标，
旧全局 no 会排除；该轻量条件检查不等于配套 SDK 的实际目标编译。

共享配方已同时保留独立构建材料输出，轻量真实 installPhase 正反控制再次
通过；主仓库 `826d2d2` 单独更新 distro pin。固定
`7081904be50465e84d6e164c72ae48fcfc9b76e6` 的目标各派发一次：

- setsid：[wasm32 41424407062](https://github.com/HighCWu/distro/actions/runs/41424407062)、
  [wasm64 41424423025](https://github.com/HighCWu/distro/actions/runs/41424423025)。
- flock：[wasm32 41424438616](https://github.com/HighCWu/distro/actions/runs/41424438616)、
  [wasm64 41424448974](https://github.com/HighCWu/distro/actions/runs/41424448974)。

setsid 三阶段、flock 四阶段、各唯一 pass 和机器关闭都仍待真实日志，不将
构建修复当作新 syscall 或已接受的 fork 功能扩展。此前 flock 的 bab75b6
任务若仍运行则继续等待，不因耗时取消，也不改写旧源码的结果。

## 第一百零九组：标准 clone3 命名空间标志交给 Linux

原执行适配层只接纳 flags=0 或 CLONE_PIDFD，即使内核已具备标准命名空间，
clone3 的请求也被宿主提前 EOPNOTSUPP。distro `7273efc` 增加命名空间标志
传递：有界 clone_args 解码允许0x7e020000内的 NEWNS/NEWCGROUP/NEWUTS/
NEWIPC/NEWUSER/NEWPID/NEWNET，可结合 CLONE_PIDFD；其余结构与 default-stack
单线程 fork 准入不变。只从一次复制取得 namespace/PIDFD 选项，不读取被
unwind 改写后的用户参数。Linux 决定实际配置、权限与标志组合是否合法。

新增的是 MIT 执行对象的可选内部传输 helper，不是 musl 或应用 API。它把
namespace 标志、SIGCHLD 和可选 CLONE_PIDFD 交给原 Linux callback clone，
没有新内核 syscall 号、内核 softmmu 或宿主命名空间实现。旧执行对象缺少
helper 则在 descriptor 初始化前拒绝；与 PIDFD 组合仍要求现有内核 abort
能力。clone 负值/异常均清除捕获的两类选项，下一次普通 fork 不受污染。
Linux 的 USER_NS 默认 n 继续保留；允许传递不表示强制启用或已经验收全部类型。
NEWTIME 的0x80与旧 clone CSIGNAL 位冲突，因此明确拒绝而非悄悄丢失；
CLONE_INTO_CGROUP、自定义栈、tid/TLS、线程和多线程 fork 仍不开放。

独立 MIT 标准 syscall 消费者使用原 clone_args u64 结构和正确机器字参数：

- NEWUTS|NEWIPC|PIDFD 子进程修改自身 hostname、不能访问父 IPC queue，
  可创建/删除自身 queue。父端核对原 hostname、内存和 queue 保留，以及
  PIDFD CLOEXEC、退出可读及清理。子端 PIDFD 槽仍为-1。
- NEWPID 子进程看到 PID=1、外部父进程 PPID=0；父端取得外层 PID，wait
  核对退出37且只回收一次。
- 普通 fork worker 降权后请求 UTS|PIDFD，必须由 Linux 返回 EPERM、PIDFD
  保留-1且没有子进程；随后普通 fork/wait 仍正常，证明权限失败不污染恢复。

原 resolved 配置门禁再核对 NAMESPACES/UTS_NS/IPC_NS/PID_NS=y，未修改 Linux
源码或配置 pin。程序材料单独输出，使用可选 SDK/finalizer，成功后发布三阶段
和唯一 pass并等待机器关闭，不改变默认 libc/SDK。未在宿主运行降权/namespace
主程序。GCC/Clang 严格前端、静态分析，当前头文件下双位宽 Wasm 前端/分析、
执行支撑对象编译、两套 TypeScript 项目检查、371项内核宿主检查及8项SDK/raw
clone检查通过。review 覆盖 bit mask、i32/i64 标志、完整 PIDFD 指针、旧对象
能力门禁、参数捕获和失败清理；宿主状态机检查不替代实际 Linux 权限/隔离。
主仓库 `7a728ac` 单独更新 distro pin，固定7273efc各派发一次
[wasm32 41428995973](https://github.com/HighCWu/distro/actions/runs/41428995973) 与
[wasm64 41429003026](https://github.com/HighCWu/distro/actions/runs/41429003026)。
尚待三阶段和关闭证据；不据此宣称完整容器、全部 namespace 或浏览器支持。

## 第一百一十组：已核实的32位进展与 setsid 设备前提

cgroup 的78e85db wasm32已核实完整压缩日志1,469,639字节、构建步7,442,272
字节，三个功能阶段和唯一 pass各一次；Heavy/workflow success。原版 flock
的7081904 wasm32完整压缩日志1,449,342字节、构建步7,510,928字节，四阶段
和唯一 pass各一次；Heavy/workflow success。两者均无目标 fail/panic；其
已发布 runner 在退出0前等待 machine.closed，Nix也要求退出0，关闭门禁成立。
这里仅接受各自指定源码的 Node wasm32 范围，wasm64仍需独立实际日志。

setsid 的7081904 wasm32已实际编译并打印 util-linux 2.42.2，随后消费者
child input 返回 ENOENT；完整压缩日志1,526,607字节、构建步7,507,552字节。
这是首个非TTY场景所需 /dev/null 不存在：专用镜像只建了 /dev 目录，没有
挂载设备文件系统，尚未到普通 fork 或 PTY 阶段，不是该 syscall 运行失败。
distro `47b4e74` 在专用 init 按既有标准 util-linux 设备前提挂载 devtmpfs 和
devpts；消费者结束后全部卸载、发布 fixture teardown 阶段才允许 pass。
不修改应用 C 代码、内核设备实现或生产 init。脚本语法与固定 shfmt通过，
主仓库 `c39cb13` 单独更新 pin，固定47b4e74的新两路
[wasm32 41428159206](https://github.com/HighCWu/distro/actions/runs/41428159206) 与
[wasm64 41428166924](https://github.com/HighCWu/distro/actions/runs/41428166924)
已派发，完整阶段与关闭待核实。

## 第一百一十一组：标准 flags-first clone 与 Linux 参数规则

distro `1bf7c36` 修复220号 v2入口仍只接纳普通 SIGCHLD、拒绝 namespace/PIDFD
的缺口。显式 import 继续确定布局，不按数值猜测 callback；clone 与 clone3
各自解码，再共用可选执行 helper、PIDFD 内核能力与恢复状态机。无 alternate
stack、无 TID/TLS 更新标志、单线程 fork 的边界不变。不是新增 libc 包装或
应用 API，Linux/musl/默认 LLVM pin 均未修改。

核对真实内核 arch/wasm/kernel/fork.c 的 lower_32_bits(clone_flags)：legacy
flags 只用低32位，不能照搬 clone3 保留 u64 的规则。PIDFD 指针仍保留完整
模块位宽并验证范围。未请求相关标志时，parent_tid/child_tid/TLS 寄存器按
Linux 忽略；若 CLONE_PIDFD 设置，则只把 parent_tid 作为输出地址验证。
默认栈与 SIGCHLD 仍必需，第六寄存器忽略。这样短 syscall 调用未使用的
寄存器不必人为清零；不把忽略寄存器误称为已支持 tid/TLS 语义。

flags-first 的 parent/child rewind 完成已接纳请求，不因重放时参数改变而
重做解析或创建另一个进程。与 clone3 共用一次捕获、旧 helper 能力拒绝、
禁止回调/信号重入、负值/异常后清除 namespace/PIDFD 的流程。宿主检查覆盖
EPERM/EAGAIN/异常后普通 fork、未知形态、缺少 helper、指针高位不被截断，
以及显式 import、未用寄存器和不重新解析的恢复。

原独立消费者改为分别运行 clone3 和标准 clone 三阶段：两种调用各验证 UTS/
IPC隔离+PIDFD、PID namespace身份、权限拒绝和普通 fork恢复。clone 形式还
刻意传入未使用的-1 TID/TLS寄存器及999号第六寄存器，64位再传入1<<40的
flags高位，验证是 Linux 的忽略规则；不截断有效 PIDFD 地址。成功标记仍唯一，
六个阶段包含各自 API 名称，不能把此前7273efc的三阶段视作新六阶段通过。

375项内核宿主检查、8项SDK/raw检查、两套TypeScript项目、GCC/Clang严格前端
和分析、当前头文件下wasm32/64前端/分析、固定格式和源码检查通过。没有在
宿主运行 namespace/降权消费者。review 核对按 flags 决定参数用途、word与u64
结构的区别、完整指针、能力门禁与恢复后的选项清理；不以宿主模型代替内核。
主仓库 `de07d1f` 单独更新 distro pin，固定1bf7c36的新六阶段目标各派发一次：
[wasm32 41432143238](https://github.com/HighCWu/distro/actions/runs/41432143238) 与
[wasm64 41432152547](https://github.com/HighCWu/distro/actions/runs/41432152547)。
现已核实两路真实六阶段与唯一pass各一次：wasm32完整压缩日志1,407,166字节、
构建步7,310,671字节；wasm64对应713,658字节、3,933,487字节。每路 clone3
与 flags-first clone 均完成 UTS/IPC/PIDFD、NEWPID/wait、EPERM回滚和后续fork。
该版 runner 在退出0前等待 closeTestResources/machine.closed，实际任务成功
包含此关闭门禁。仅接受固定1bf7c36/旧 callback 传输，不推广为后续原生
clone3、TID 选项或浏览器支持。

## 第一百一十二组：cgroup 与原版 flock 的双位宽 Node 验收

cgroup78e85db的wasm64也已核实：完整压缩run日志1,480,642字节，构建步
7,521,559字节，三阶段和唯一pass各一次，Heavy/workflow success；与已核实
的wasm32共同接受该版Linux3dc991222的PIDs准入、继承、回滚、计数及清理。
原版flock7081904的wasm64完整压缩日志1,488,790字节、构建步7,589,988字节，
四阶段和唯一pass各一次，Heavy/workflow success；与已核实wasm32共同接受
该版原程序的fork/wait、close/direct-exec、真实锁冲突/释放、超时和错误恢复。

两个wasm64目标无fail/panic；各版已发布runner均在退出0之前等待machine.closed，
Nix也要求退出0。它们与当前runner源码一致，关闭门禁成立，不只是工作流绿色。
这些结果不推广到新 namespace 代码、浏览器、全部 cgroup controller 或全部
util-linux。setsid7081904的wasm64完整压缩日志1,505,394字节、构建步
7,586,446字节，确认同样在child input ENOENT停止，没有功能阶段；已发布的
47b4e74设备挂载修复仍待新目标结果，不把flock/cgroup通过用于替代它。

## namespace 验收与 setsid 身份诊断

固定7273efc的 clone3 namespace 两路 Node 实际日志已核实：
[wasm32 41428995973](https://github.com/HighCWu/distro/actions/runs/41428995973)
完整压缩日志1,502,989字节、构建步7,309,662字节；
[wasm64 41429003026](https://github.com/HighCWu/distro/actions/runs/41429003026)
对应1,467,636字节、6,983,211字节。每路 UTS/IPC 隔离和 PIDFD、PID namespace
身份和回收、内核 EPERM 回滚及后续 fork 三阶段与唯一 pass 各一次。
已核对该版 runner 在退出0前等待 closeTestResources/machine.closed，任务成功
包含此关闭门禁；不推广为更新1bf7c36的 flags-first clone 六阶段或浏览器验收。

setsid47b4e74双位宽均在成功挂载设备、打印原版2.42.2版本后，失败于
direct exec without unnecessary fork；尚未完成第一阶段。原先 child input
ENOENT 已越过，但不能据此认为 setsid 能力完成。distro e238c83、主仓库 pin
2c74cad 保留原身份断言，增加失败时实际 controller/group、spawned PID、
observer PID/PPID/session/group，并检查 posix_spawn 保留控制进程身份。
单次回收检查留下的 ECHILD 不再是唯一诊断信息。未改原版程序或放宽预期。
GCC/Clang 原生消费者三阶段与 Clang 静态分析通过；目标双位宽复验
41435361278、41435371030已派发，身份原因及修复仍待实际日志，不宣称已解决。

后续41435361278实际日志确认在 controller identity before spawn 失败，未到
功能阶段。检查启动路径发现，早期 init 树可继承进程组0，而消费者把该组号
传给 POSIX_SPAWN_SETPGROUP 时，0按标准表示新子进程自己的PID，会意外让
预期非组长的子进程成为组长；原版setsid因此选择fork符合其源码逻辑。
distro46b0b87 / 集成39c746a只修正测试控制进程：当继承组号为0时先以
setpgid(0,0)建立自己的正进程组，再构造spawn属性。原版setsid、libc和Linux
未因此改动，三阶段及全部身份断言保留。GCC严格构建及原生三阶段、Clang
前端和静态分析通过；已针对该版重新派发双位宽目标，修复效果待真实日志。

## 原生 clone3 返回路径与 Linux TID 输出

Linux `60908a2593afdad4bb0d885d6553818a8b68c8b0` 修复通用 clone3 的无回调
copy_thread 路径：以已暂停的单线程用户现场建立子任务返回入口；缺少入口、
共享 mm、非默认栈或 SETTLS 时在创建 Worker 前拒绝。旧 callback clone 不变。
原有快照发布、schedule_tail 和未发布 Worker 回收继续复用，没有内核 softmmu。
公开[源码哈希任务41436227897](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41436227897)
实际确认基线3dc991222与已验收SRI一致，再得到候选
`sha256-gaSivg78riq1JJln1J+yDDgCZgKdP4CuuPl9zFhgCxw=`。

distro `92d79a5` / 集成 `04725a8` 固定该内核和运行层。clone3 要求内核原生
能力与执行 helper 同时存在，才通过原 syscall435 进入 Linux；legacy clone
用原 callback syscall220传递选项，不因新能力而换号。新增 PARENT_SETTID、
CHILD_SETTID、CHILD_CLEARTID 的传递，Linux 决定 TID 写入和错误行为；clone3
保留独立 PIDFD/parent/child 地址，legacy 共用槽的冲突仍交给 Linux 拒绝。
不新增 musl 函数、公共头或应用接口，musl/默认LLVM pin均未变。

review 覆盖旧对象/旧内核回退、缺少 helper 时先拒绝、原 syscall 选择、kernel
调用深度/信号深度、规范化结构不复用活动 Asyncify 栈、异常清除选项、地址
位宽、私有内存隔离和后续回收。379项运行层检查、10项SDK/raw/helper检查、
两套TypeScript项目、GCC/Clang前端和静态分析、当前头文件下双位宽 Wasm
前端/分析通过。生成的真实 C helper 已在 Node 实例化，验证220/435与完整u64
结构，但导入返回由夹具提供，不能冒充 Linux fork 成功。

固定92d79a5的十阶段 namespace/TID 目标各派发一次：
[wasm32 41438616476](https://github.com/HighCWu/distro/actions/runs/41438616476)、
[wasm64 41438630395](https://github.com/HighCWu/distro/actions/runs/41438630395)。
既有六阶段之外新增 parent/child TID、legacy TID、NEWPID TID 和 PIDFD/TID
别名拒绝四阶段。另派发完整 fork 回归
[wasm32 41438638854](https://github.com/HighCWu/distro/actions/runs/41438638854)、
[wasm64 41438646687](https://github.com/HighCWu/distro/actions/runs/41438646687)。
阶段、唯一pass与关闭均待实际日志；不扩大为共享 futex、TLS、自定义栈或
多线程 fork。详见[执行 ABI](fork-continuation-abi.md#原生-clone3-返回路径与-tid-输出)。

## 原版 setsid 验收、原生 clone3 结果与源码限流

固定46b0b87的[wasm32 41437631434](https://github.com/HighCWu/distro/actions/runs/41437631434)
和[wasm64 41437640521](https://github.com/HighCWu/distro/actions/runs/41437640521)
现均核实原版setsid三阶段、设备 fixture teardown 和唯一pass各一次。
32位完整压缩日志1,570,796字节、构建步7,893,234字节；64位对应873,101字节、
4,536,636字节。该版发布runner与当前run-test/shutdown一致，在退出0前等待
machine.closed，两项实际任务均成功，关闭门禁成立。接受的是该版3dc991222内核
上的原程序fork/exec/wait、ctty/session/foreground、错误恢复与设备清理，不推广
到新内核或任意交互式作业控制。

固定92d79a5 / Linux60908a259的
[wasm64 namespace/TID 41438630395](https://github.com/HighCWu/distro/actions/runs/41438630395)
已核实完整十阶段与唯一pass：压缩日志1,469,056字节、构建步6,987,675字节。
其中三个TID阶段及PIDFD/TID别名拒绝实际通过，不是仅基础namespace通过。
同版[wasm32 fork 41438638854](https://github.com/HighCWu/distro/actions/runs/41438638854)
核实全部十二个fork/fork-exec阶段、唯一pass，压缩日志1,550,922字节、构建步
7,311,485字节。相同发布runner的等待关闭门禁成立。
同版[wasm32 namespace/TID 41438616476](https://github.com/HighCWu/distro/actions/runs/41438616476)
随后也已核实全部十阶段、唯一pass及关闭门禁：完整压缩日志1,413,198字节，
构建步7,314,054字节。至此接受固定92d79a5/60908a259的双位宽namespace/TID
十阶段；完整fork回归仍只有32位通过，64位受下述源码下载失败影响。
这些结果不覆盖后续7233d8c的宽flags传输或浏览器。

92d79a5的wasm64 fork41438646687明确失败在源码获取：两个archive端点均连续
HTTP429，最后source.drv失败，尚未编译或运行。distro e6b13da / 集成8363f53
改为fetchgit精确rev，去掉.git且不取子模块，保持同一已核验递归内容哈希。
Nix仍必须拒绝内容/模式/链接差异；未降低哈希约束。六项构建材料正反检查通过。
固定e6b13da针对性复验[41440786848](https://github.com/HighCWu/distro/actions/runs/41440786848)，
未取消仍运行的其它任务，也不把下载失败解释为clone3语义失败。

## clone3 的高位标志与信号处理器重置

distro7233d8c / 集成eb8d3a2在相同内核上新增CLONE_CLEAR_SIGHAND传递。
可选helper的flags在双位宽均为i64，旧helper签名和低位范围保留。Linux原
copy_sighand完成重置，JS不代改处理器。381项运行层检查、两套类型检查、
真实生成的双位宽C helper传输/拒绝检查、GCC/Clang前端与双位宽Wasm静态分析
通过。原生消费者未在宿主执行，不把导入夹具返回值当作真实fork。

独立目标[wasm32 41441174223](https://github.com/HighCWu/distro/actions/runs/41441174223)
和[wasm64 41441190314](https://github.com/HighCWu/distro/actions/runs/41441190314)
已各派发一次，仍待实际三阶段、唯一pass和关闭：子进程清除自定义处理器、保留
SIG_IGN并被真实默认信号终止；SIGHAND冲突拒绝；后续普通fork继承父处理器并
正常回收。没有新增libc函数，也未扩大共享处理器、线程、自定义栈或其它高位flags。

## 信号重置及64位完整fork回归验收

固定7233d8c的宽flags目标实际日志已核实：
[wasm32 41441174223](https://github.com/HighCWu/distro/actions/runs/41441174223)
完整压缩日志1,531,439字节、构建步7,309,632字节；
[wasm64 41441190314](https://github.com/HighCWu/distro/actions/runs/41441190314)
对应1,478,201字节、6,982,868字节。每路三个完整阶段和唯一pass各一次，确认
真实默认信号终止、SIG_IGN保留、冲突拒绝及后续fork恢复。发布runner与当前
run-test/shutdown一致，成功退出要求等待machine.closed；两路关闭门禁成立。
接受的是该版Node结果，不推广为浏览器或其它高位标志。

源码获取修复e6b13da的[wasm64 fork41440786848](https://github.com/HighCWu/distro/actions/runs/41440786848)
也已核实完整十二个fork/fork-exec阶段与唯一pass及关闭：压缩日志1,462,950字节，
构建步6,986,246字节。已核对92d79a5到e6b13da的运行层和fork消费者源码未变，
变化仅为源码获取/材料说明；因此补齐原生clone3底层的64位完整回归，原429任务
仍记为未运行，不改写其失败结果。后续宽flags版本按自己的独立目标验收。

## 远端复制后端准备：尚未接入syscall

AIO仍有共享ring folio与用户独立linear memory的真实障碍；本轮没有只打开
配置。文件mmap候选也保留生产者、发布和默认准入门槛。审查转向现有远端访问：
其所有者邮箱需要目标Worker在内核/停放路径服务请求，持续用户Wasm执行会阻止
这一检查点。distro5126c72新增机器端Memory引用与同步RPC，6251480进一步保护
排队请求的采样异常与阻塞agent错误；主仓库3e9d7f0单独更新pin。

389项运行层检查和两套TypeScript工程通过。新增八项检查含真实Worker/Wasm
忙循环、跨Worker内存增长后的复制、有效前缀、撤销后拒绝、迟到请求取消，以及
接管后超时/调度错误/发送观察器错误必须等待写入完成。源与测试均为MIT。
尚未添加内核mm注册、权限/引用接入或真实process_vm_*语料，默认syscall行为未变。
不得把上述Node数据面实验解释为Linux syscall或共享ring支持已经完成。

## 远端复制接入候选：目标无需进入内核检查点

Linux f090bca6a、distro608809b、主仓库集成6264819将上述后端接入
access_remote_vm。新mm身份单调分配且不复用，达到INT_MAX后保留旧邮箱路径；
fork不继承身份，CLONE_VM共享身份。运行层确认机器端持有Memory后发布ready，
context_mm阻止exec过渡期将旧Memory绑定到新mm。mm_access权限和引用检查仍
由Linux执行，mm_users排空后异步释放机器端引用；全部Worker成功停止后才清空
机器引用。旧邮箱发布与ready重叠时，先撤销未接管请求才能改走机器端，已接管的
请求必须完成。复制最多64KiB，沿用NULL、机器字地址和有效前缀规则。

现有process-vm消费者新增第四阶段：子进程通过标准匿名mmap扩大内存，在新增
区域发布控制地址后进入纯原子忙循环；父进程使用既有process_vm_readv/writev
读取、写回、核对再释放循环，等待子进程实际观察并退出。GCC/Clang原生对照及
ASan/UBSan、伪造写入成功的反向控制、双位宽Wasm前端与Clang静态分析通过。
389项运行层检查、两套类型检查、20项浏览器契约检查和实际C地址边界检查通过。
这些是本地证据，不作为Linux/Wasm目标通过声明。

[公开源码预取41454957184](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41454957184)
核实直接父修订60908a259及已知hash，再核实精确候选f090bca6a的递归hash
`sha256-gzNoovXFxQ5zWc2d3ZRgkVybiKY436pNeZBh1RBVK4Y=`。未放宽固定内容校验。
已派发双位宽process-vm、四路浏览器remotevm及双位宽完整fork回归；目标结果
待实际阶段、唯一pass及machine.closed门禁核实。浏览器要求同页两次启动和关闭，
不以工作流成功替代输出。musl与默认LLVM pin保持不变，没有新增公共应用接口、
内核softmmu或多线程fork能力；AIO共享ring与ELF加载仍是独立未完成事项。

本候选的异步任务（均固定608809b）：

| 检查 | 位宽 | 任务 |
| --- | --- | --- |
| Node process-vm | wasm32 | [41455374334](https://github.com/HighCWu/distro/actions/runs/41455374334) |
| Node process-vm | wasm64 | [41455374737](https://github.com/HighCWu/distro/actions/runs/41455374737) |
| Node 完整 fork | wasm32 | [41455374880](https://github.com/HighCWu/distro/actions/runs/41455374880) |
| Node 完整 fork | wasm64 | [41455375528](https://github.com/HighCWu/distro/actions/runs/41455375528) |
| Chromium remotevm | wasm32 | [41455376462](https://github.com/HighCWu/distro/actions/runs/41455376462) |
| Chromium remotevm | wasm64 | [41455376746](https://github.com/HighCWu/distro/actions/runs/41455376746) |
| Firefox remotevm | wasm32 | [41455375713](https://github.com/HighCWu/distro/actions/runs/41455375713) |
| Firefox remotevm | wasm64 | [41455377791](https://github.com/HighCWu/distro/actions/runs/41455377791) |

## 原生 clone3 接纳时间命名空间

distro a630876 / 主仓库pin390297e修正早期callback传输留下的限制：clone3
的CLONE_NEWTIME不再因与旧clone的CSIGNAL重叠而一律拒绝。请求仍是标准
SYS_clone3，flags保留完整u64，exit_signal独立为SIGCHLD；Linux原来的
copy_time_ns/timens_on_fork负责创建、进入、偏移复制/冻结和权限检查。
当前TIME_NS已按官方默认启用，本轮不改内核、不增加libc接口。

配套独立执行对象新增内部features查询，固定i32返回值bit0表示NEWTIME准入。
运行层同时要求该位、宽flags helper和原生内核能力，旧对象/旧内核在descriptor
初始化前拒绝；legacy clone及旧pointer-width helper继续拒绝0x80，不改变
退出信号。可组合现有PIDFD、TID、namespace和CLEAR_SIGHAND，未知标志继续
拒绝，负值后清除当次参数，不扩大CLONE_VM、TLS、自定义栈或多线程fork。

新MIT消费者clone-timens使用标准syscall、procfs、unshare/setns和时钟接口：
先核对clone3子任务获得不同时间namespace，父任务不变，PIDFD/TID由内核发布；
再配置future-child namespace的monotonic120秒、boottime180秒偏移后clone3，
核对新身份、独立偏移及绝对clock_nanosleep的时钟转换；最后降权子任务必须得到
EPERM、保持输出不变且无子进程残留，之后普通fork与namespace/挂载清理成功。
不在宿主运行这个命名空间消费者；GCC/Clang前端、双位宽Wasm静态分析通过。
391项运行层检查、两套类型检查、8项SDK/实际编译对象检查和2项raw消费者检查
通过，涵盖缺失/错误能力、旧内核、flag组合、失败恢复及旧CSIGNAL拒绝。

固定a630876的[wasm32 41457372023](https://github.com/HighCWu/distro/actions/runs/41457372023)
与[wasm64 41457373412](https://github.com/HighCWu/distro/actions/runs/41457373412)
已各派发一次，仍待真实三阶段、唯一pass和机器关闭。此前608809b的远端复制
八路任务仍运行，未取消或重复派发，也未沿用它们的未完成结果作为此版验收。

## 远端复制的双位宽Node与四路浏览器验收

固定608809b/Linux f090bca6a的八项目标均已核实实际完整日志，不以绿色工作流
替代阶段证据。以下大小为压缩日志/实际构建步字节：

| 检查 | wasm32 | wasm64 |
| --- | --- | --- |
| Node process-vm | 41455374334：1,433,257 / 7,312,741 | 41455374737：1,331,797 / 6,986,261 |
| Chromium remotevm | 41455376462：1,707,392 / 7,394,943 | 41455376746：1,652,059 / 7,067,311 |
| Firefox remotevm | 41455375713：1,477,336 / 7,394,497 | 41455377791：1,619,941 / 7,067,049 |
| Node 完整fork | 41455374880：1,421,613 / 7,314,215 | 41455375528：1,326,622 / 6,987,632 |

运行链接见上文同版本任务表。Node process-vm各出现四个完整阶段和唯一pass，
包括目标在纯用户忙循环中、内存增长后的实际读写与退出。四路浏览器分别为
Chromium149.0.7827.55/Firefox151.0、双位宽，每个同页两轮都完整出现四阶段与
唯一pass、machine shutdown pass，并最终出现both iterations and browser
shutdown pass。Node完整fork各核实十二个fork/fork-exec阶段及唯一pass。

已核对该发布版run-test/shutdown及浏览器runner与审查源码一致：Node退出0要求
closeTestResources等待machine.closed成功；浏览器每轮在等待machine.closed后
才校验完整输出，最后关闭浏览器并检查迟到pageerror。相关任务/Heavy均success，
上述关闭门禁成立。仅接受此版的process_vm有界读写及相应回归，不推广为所有
ptrace操作、单CPU纯用户抢占、共享ring、任意exec竞态或后继版本已验收。

固定a630876的时间namespace[wasm64 41457373412](https://github.com/HighCWu/distro/actions/runs/41457373412)
也已核实三个完整阶段、唯一pass和相同Node关闭门禁，压缩日志1,326,859字节、
构建步6,986,747字节。[wasm32 41457372023](https://github.com/HighCWu/distro/actions/runs/41457372023)
独立日志随后也已核实相同三阶段与唯一pass，压缩日志1,419,436字节、构建步
7,313,166字节，相同已发布关闭门禁成立。接受固定a630876的双位宽Node范围，
不扩大为浏览器时间namespace验收。

## Wasm既有时区文件读取路径的资源与取消边界

musl7b077a6d只修改tombl上游原已存在的src/time/__map_file.c的Wasm分支，
没有新增函数、公共头文件/API或通用Linux包装。由于默认文件mmap仍未开放，
这个内部helper保留读入副本的实现，但修复确定的兼容问题：分配失败也关闭fd；
负值/零大小和wasm32不可表示的st_size在分配前拒绝；EINTR和短读继续读取，
EOF/读取错误释放副本，完整成功才发布size。使用原有非取消内部syscall宏，
避免在时区锁下进入公共read的取消点；O_NONBLOCK与原生mmap路径一致，避免
TZ指向FIFO时在open处卡住。非Wasm函数体保持不变。

真实源码经双位宽musl头文件前端/静态分析，实际函数体在双位宽Wasm模块中
执行有界故障模型，核对短读、EINTR、OOM、fstat/读取错误、提前EOF、大小
截断与所有fd关闭；省略close或改回可取消read的反向控制必须失败。这不是
完整libc或VFS验收。独立MIT标准C消费者使用TZ/tzset/localtime_r/mktime/
strftime验证2040年纽约夏令时和东京时区、64次换源及fd复用，并在Wasm内验证
FIFO不阻塞、UTC回退和之后恢复正常文件。原生GCC/Clang及ASan/UBSan对照
通过前两阶段，不在宿主执行FIFO路径；双位宽Wasm前端和静态分析通过。

[公开预取41460465248](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41460465248)
已核实精确musl修订7b077a6d549f1cbe97b22545e37cf1919dd6a641与SRI
`sha256-5tD0pAVUpnvC8B3jbZNp/B3lzbsRu8xttlnUHQrwTME=`。distro3cd41a3及
主仓库pin5c116fb已分开发布；新双位宽真实Node三阶段与关闭仍待验收。
对应[wasm32 41461466995](https://github.com/HighCWu/distro/actions/runs/41461466995)
和[wasm64 41461467807](https://github.com/HighCWu/distro/actions/runs/41461467807)
均固定3cd41a3。首次派发在GitHub工作流查询阶段遇到EOF，核对没有创建任务后
才补发；现有目标不重复派发，不取消慢任务。
本轮没有扩展文件mmap上限、开放默认file mapping或实现动态链接。

## 时区复制路径的双位宽目标验收

固定3cd41a3/musl7b077a6d的两项Node日志已核实三个完整阶段和各唯一pass：
[wasm32 41461466995](https://github.com/HighCWu/distro/actions/runs/41461466995)
压缩日志1,057,059字节、构建步5,284,315字节；
[wasm64 41461467807](https://github.com/HighCWu/distro/actions/runs/41461467807)
对应510,275字节、2,456,609字节。包括2040年纽约冬夏偏移和东京时区、64次
切换/fd复用、实际FIFO不阻塞、UTC回退及正常文件恢复。发布版runner/shutdown
与审查代码无差异，退出0要求等待machine.closed；两项任务/Heavy均success，
关闭门禁成立。接受该版默认SDK的上述Node范围，不推广为浏览器、所有时区/
取消竞态或默认文件mmap已开放。

## 标准私有文件映射复用既有 libc 内部加载器

文件 mmap 的默认 streaming 路径已实际验收后，musl `ce9c4c50` / distro
`73c266a` / 集成 `d283b03` 移除 __map_file 中独立的 malloc/read 副本循环，
既有时区、消息目录等内部消费者改走 __mmap(PROT_READ, MAP_PRIVATE)，释放
改走 __munmap。保留 O_NONBLOCK/O_CLOEXEC、正且可表示的长度校验、EINTR
重试、失败不发布 size 及非取消 close；非 Wasm 函数体不变。MAP_SHARED 别名
仍不支持，没有用这个改造声明页保护或惰性映射。

src/include/sys/mman.h 中 __mmap/__munmap 的隐藏声明原仍被 Wasm 门控；
现在仅恢复这两个已存在内部函数的声明。没有新增函数、公共头文件、公共 API
或通用 Linux 包装，比较基线仍是 tombl/musl。这条替代路径收敛依赖配套内核的
私有文件映射能力，不保证旧的显式关闭配置还能加载时区文件。

公开预取 [41579166436](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41579166436)
核实精确源码哈希。Clang18/22 双位宽实际 helper/消费者前端、静态分析和函数体
故障模型通过；省略 close、改用可取消 close、误用 MAP_SHARED 的反向版本分别
在预期断言失败。GCC/Clang 原生参考仍通过 TZif/time64 与64次换源两个阶段；
本机未执行 seccomp/FIFO 的 Wasm 专用分支。

真实 timezone 语料在原三阶段后新增第四阶段：标准 seccomp BPF 拒绝 SYS_read，
先确认拒绝发生在 fd 校验之前，再切换东京与纽约文件并核对时间和 fd 回收。
旧 malloc/read 路径不能靠原字节内容或同一时区缓存通过该断言。两项目标为
[wasm32 41579425956](https://github.com/HighCWu/distro/actions/runs/41579425956)、
[wasm64 41579431820](https://github.com/HighCWu/distro/actions/runs/41579431820)，
均固定73c266a；真实四阶段、唯一 pass 与关闭仍待核实。它不代表所有消息目录、
截断竞态或新 musl 下全部应用回归已经完成。

首轮两项随后都失败，实际 Heavy 日志分别5,343,988和5,172,471字节。前三阶段
均已完成，第四阶段在安装 filter 时返回 EINVAL，尚未执行拒绝 read 后的断言。
这是验收前提选错：本项目只接通 strict seccomp，filter 仍缺正式架构标识等
条件，HAVE_ARCH_SECCOMP_FILTER/SECCOMP_FILTER 明确关闭，不能用现有 arch=0
占位冒充可用 ABI。前三阶段不单独冒充四阶段目标通过。

distro `53a8100` / 集成 `4da0f8d` 去掉这个不可用的 filter 前提，改在测试
二进制用 --wrap=__mmap/--wrap=__munmap 观察后继续调用真实目标。换源两次必须
新增至少两次匹配参数的私有文件映射及解除映射，仍核对时区数据、fd 恢复与
前三阶段；旧 malloc/read 路径不能只凭正确文件内容通过计数门禁。观察函数只
存在于测试二进制，不进入 musl、SDK 公共头文件或应用 API。

Clang18/22 双位宽前端/静态分析与原生参考通过。另把真实 helper 编成独立
Wasm 对象，验证隐藏符号引用确实经过 wrapper 再到原目标；去掉 wrapping 的
版本恰在观察门禁失败。后端在这个轻量检查里是模型，仍不算 VFS 验收。新两项
[41582384057](https://github.com/HighCWu/distro/actions/runs/41582384057)/
[41582391405](https://github.com/HighCWu/distro/actions/runs/41582391405) 固定53a8100，
需实际四阶段、唯一 pass 与机器关闭。内核配置和真实映射实现没有因这个测试
修正而更改。

53a8100 的新两项现已成功。实际 Heavy 日志 wasm32 为5,338,384字节、wasm64
为2,075,676字节；各四阶段有序且唯一 pass，包括真实私有映射/解除映射的换源
观察。固定 run-test.js/shutdown.js 与核对版本一致，成功退出必须等待
machine.closed 并拒绝清理错误，双位宽关闭门禁成立。接受该组合的时区内部
加载范围，不据此宣称 seccomp filter、所有 locale/catalog 文件或新内核组合
已经验收。

## 文件mmap的有界分块填充候选

Linux1b81174a8、distro5d47cf7、集成ee42f64接入新的默认关闭分块配置。
应用仍调用标准mmap，SDK原初始化器不改；内核保留file引用和游标，每次读取
最多一页staging，生产者返回后才复制到尚未发布的用户backing。在既有单次填充
调用中完成循环，不新增Linux syscall、应用import或musl函数。读期间撤销先
关闭发布资格，生产者返回前不释放staging/file；返回后拒绝提交。kernel异常
展开作为机器失败，不转换成普通用户错误。每请求128KiB保守额度覆盖单页
staging及元数据，512KiB全局额度最多四个请求，不声称涵盖全部用户副本；
用户容量仍由direct memory/allocator限制。完整协议见
[分块候选](file-mmap-candidate.md#分块私有复制候选)。

395项运行层、两套类型检查、GCC/Clang实际C函数模型和ASan/UBSan通过。
模型核对短读/EOF、后续读取错误、复制故障、可见fatal signal、读取内部撤销
后的所有权与回滚；删除读取中保护必须失败。该模型不是实际VFS/设备验收。
消费者要求4MiB+7字节、offset/私有性/fd位置、截断后零尾、源关闭/unlink、
错误后拆分unmap与分配恢复；双位宽前端和静态分析通过，Node实际三阶段和
关闭仍待验收。后续需要浏览器及真实设备在途取消，不开放默认发行文件mmap。

[公开预取41465939113](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41465939113)
先核实直接父修订f090bca6a及已知递归hash，再得到精确候选
1b81174a8c93bbfa4a630851ee6f17da4926a5d6的SRI
`sha256-4Lhcn73OWFLtb32hhSp+9w8yQfWPelZWwSax/duxsvk=`，保留固定内容校验。
Linux改动沿用GPL，独立host/测试/集成/文档MIT；musl7b077a6d和默认LLVM
137009e不变，不加入softmmu、共享映射或多线程fork。

固定5d47cf7的[wasm32 41467105444](https://github.com/HighCWu/distro/actions/runs/41467105444)
与[wasm64 41467101649](https://github.com/HighCWu/distro/actions/runs/41467101649)
已各派发一次，Heavy正在进行，实际三阶段、唯一pass及机器关闭仍待核实。

## 分块文件 mmap 的 Node 结果与真实在途生产者

固定distro5d47cf7/Linux1b81174a8的
[Node wasm32 41467105444](https://github.com/HighCWu/distro/actions/runs/41467105444)
与[Node wasm64 41467101649](https://github.com/HighCWu/distro/actions/runs/41467101649)
均已核实完整三个阶段和各唯一pass，任务/Heavy成功。压缩日志分别1,738,622和
1,677,537字节，实际构建步骤7,956,269和7,792,136字节。包括4MiB+7字节、非零
offset、私有副本/fd位置、短读/EOF/截断、源关闭/unlink及拆分unmap后恢复。
该版run-test/shutdown与已审查的发布代码一致，退出0要求等待machine.closed并
拒绝收尾错误，关闭门禁成立。这是分块配置的Node证据，默认文件映射仍关闭。

distro a60ed18 / 集成6170efa补充浏览器入口，全部固定同一源码并各派发一次：

| 位宽/引擎 | 任务 |
|---|---|
| wasm32 Chromium | [41470377725](https://github.com/HighCWu/distro/actions/runs/41470377725) |
| wasm32 Firefox | [41470374684](https://github.com/HighCWu/distro/actions/runs/41470374684) |
| wasm64 Chromium | [41470363932](https://github.com/HighCWu/distro/actions/runs/41470363932) |
| wasm64 Firefox | [41470376508](https://github.com/HighCWu/distro/actions/runs/41470376508) |

运行器要求同页两个独立启动的完整三阶段、各唯一pass、机器关闭及最终浏览器
关闭。当前结果仍需按实际日志分别核实，不将其中一项工作流成功泛化为四路通过。

其中Chromium两项现已逐项核实：wasm32压缩日志1,587,312字节/构建步8,027,357
字节，wasm64对应1,015,889/5,202,101字节；两项各有完整三阶段两轮、各唯一pass、
两次machine shutdown及最终browser shutdown pass。引擎均为149.0.7827.55。
接受该源码在这两路的范围，Firefox仍待核实。

后续distro7dd14ab58820f08b848c11af60bff3ad4994bcae / 集成83810d8加入真实
FUSE在途生产者门禁，Linux/musl/LLVM pin不变。生产者以FOPEN_DIRECT_IO返回
普通文件，确保同步kernel_read指向分块staging，而不是独立后台缓存读取。
控制器收到READ后SIGKILL读取者，再等内核INTERRUPT握手，检查waitpid(WNOHANG)
仍未退出且来源未RELEASE；显式释放原读取响应后，才核对SIGKILL回收、无用户
发布标记及最终FUSE_RELEASE。每轮再映射另一个真实FUSE文件并核对内容/零尾，
共八轮，超过四个请求的staging额度容量；最后卸载并回收服务进程。

这验证实际请求的完成/引用边界和后续额度可用性，不把管道标记当作任意用户
代码均未执行或精确heap计数的证明。标准单线程fork配置仅用于独立进程编排。
新增消费者/Nix为MIT，未加入musl函数、私有应用API或内核测试syscall。
wasm32/64头文件前端和Clang静态分析、GCC/Clang宿主前端、Nix格式与diff检查
通过；没有在宿主执行挂载。固定7dd14ab的
[wasm32 41472492037](https://github.com/HighCWu/distro/actions/runs/41472492037)
和[wasm64 41472495062](https://github.com/HighCWu/distro/actions/runs/41472495062)
已各派发一次，实际四阶段和关闭仍待验收。

## 分块文件 mmap 的设备与 Firefox 验收

固定7dd14ab的FUSE两项已核实实际四阶段和各唯一pass：wasm32压缩日志
1,923,650字节/构建步9,977,641字节，wasm64为1,280,366/6,987,830字节。
包含独立生产者挂载、八次扣住READ/中断握手/SIGKILL收尾/迟到响应/来源释放、
超过staging请求容量的恢复映射、卸载及服务进程reap。发布run-test/shutdown
不变，作业退出0要求等待machine.closed且收尾错误会失败，两项关闭门禁成立。
这接受指定FUSE同步路径，不证明所有设备、任意异步I/O或精确用户heap计数。

固定a60ed18的Firefox两项也已逐项核实两轮三阶段、各唯一pass、两次machine
shutdown及最终browser shutdown pass，版本151.0。wasm32压缩日志1,636,985
字节/构建步8,026,900字节，wasm64为1,600,689/7,867,464字节。至此分块候选
的四路浏览器和双位宽Node/真实FUSE门禁均有上述实际证据，不沿用早期128KiB
配置来证明大映射，也不宣称共享、执行或任意fork/多线程组合已支持。

## 普通 SDK 复制能力组合的历史结果补核实

固定3da2bde的40165368438/40165371968现已补核实各四个独立启动：候选实际
内容/短读/私有生命周期、默认关闭对照、真正缺导出的旧模块拒绝，以及VFS
预算并发/回滚；每次启动各有唯一pass。两项压缩日志1,014,269/844,537字节，
完整Heavy日志10,041,173/8,088,013字节。40165376151/40165378816也核实Zstd
五个边界的强制映射、超原上限拒绝、普通/可变来源私有副本及独立关闭配置的
malloc/字典恢复，两次启动各唯一pass；压缩日志890,422/712,269字节，完整
Heavy日志8,133,547/6,202,396字节。上述历史任务的runner关闭契约单独核对，
不将旧内核或旧128KiB阈值推广成新分块配置的容量/设备证据。

## 根仓库验收脚本修复

41474068045的Repository metadata/job125374896472明确失败于五处文档行超过
120字符，实际日志已读取；独立LLVM构建仍运行，没有取消或重复派发。763a939
修复行长，同时修复本地复验发现的两个过期契约：内核模型门禁漏掉分块配置，
源码获取检查还要求已被固定rev/hash的Git获取替代的HTTP重试语法。没有删除
hash或版本检查；文档/源码pin检查、五项pin模型和六项Git预取故障检查通过，
新根仓库CI异步复验。这里修的是验收脚本，不作为syscall运行能力新增。

## 默认构建接入标准私有文件映射

Linux59937da2c / distro ec78632b0145ca2e8beb32121ff635b94bbf81ec / 集成ce06ee1
把已验收的分块复制路径接到普通内核构建。应用仍用标准mmap/mmap2/munmap及
默认SDK，无需添加应用接口或私有链接参数。musl7b077a6d和默认LLVM137009e
不变；本轮Linux改动仅澄清Kconfig的执行ABI配对和容量说明，功能代码仍是
已验收的1b81174a8。独立内核的Kconfig继续显式启用，发行构建默认打开分块
路径。Nix检查最终配置，保留关闭与128KiB整块两种显式对照，不靠继承默认值。

源码SRI由[41477939842](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41477939842)
先验证1b81174a8及其既有hash，再核对直接父子关系、唯一Kconfig路径和模式后
生成，完整压缩日志12,653字节、预取步骤3,560字节。固定59937da2c的hash为
`sha256-Ki1YF+Jk7YHX/WXdfs10KzTs4je+hR7GvLDwll5OOhY=`，没有移除内容校验。

Python语料改为通过CPython原有mmap模块映射超过128KiB的普通文件，核对文件
位置、只读Python API、私有flush无回写及关闭来源后的存活；共享匿名/文件请求
仍须拒绝，不承诺硬件只读保护。未修改CPython源码或补造musl函数。
Zstd普通roundtrip现在强制私有映射压缩/解压，与malloc路径交叉解码，覆盖原
页边界及4MiB+7字节字典。显式关闭控制通过测试脚本模式要求真实EINVAL拒绝；
旧128KiB应用和浏览器配置仍分别保留原容量断言，不让默认改变悄悄改写历史测试。

本地28项应用/编排检查通过，包含实际原生Python与Zstd正向、共享回写错误及
空输出假成功拒绝；原生结果不是Wasm证明。Nix/JS/shell格式、shell语法、Python
AST与diff检查通过；7项Git预取故障模型、5项source pin检查与文档检查也通过。
以下八项均固定ec78632，各派发一次，实际阶段与关闭仍待核实：

| 检查 | 位宽 | 任务 |
|---|---|---|
| Zstd普通默认内核 | wasm32 | [41478944684](https://github.com/HighCWu/distro/actions/runs/41478944684) |
| Zstd普通默认内核 | wasm64 | [41478943764](https://github.com/HighCWu/distro/actions/runs/41478943764) |
| Python mmap普通默认内核 | wasm32 | [41478944407](https://github.com/HighCWu/distro/actions/runs/41478944407) |
| Python mmap普通默认内核 | wasm64 | [41478946240](https://github.com/HighCWu/distro/actions/runs/41478946240) |
| 128KiB/旧模块/关闭/预算对照 | wasm32 | [41478948425](https://github.com/HighCWu/distro/actions/runs/41478948425) |
| 128KiB/旧模块/关闭/预算对照 | wasm64 | [41478944068](https://github.com/HighCWu/distro/actions/runs/41478944068) |
| 普通C runtime回归 | wasm32 | [41478946989](https://github.com/HighCWu/distro/actions/runs/41478946989) |
| 普通C runtime回归 | wasm64 | [41478943612](https://github.com/HighCWu/distro/actions/runs/41478943612) |

此处完成的是默认构建接线，不把此前候选阶段、开关启用或本机语料当成上述新
组合已验收。CONFIG_MMU=n、有界direct地址、无内核softmmu及单线程fork边界
均未扩大；共享/执行/文件固定映射、映射后截断失效与MMU页保护仍不提供。

## 默认映射组合的应用与 C runtime 验收

固定ec78632的Zstd两项目标已逐项核实默认内核强制私有映射与malloc交叉往返、
七个尺寸（含4MiB+7字节）、唯一pass及关闭。wasm32压缩日志1,284,200字节/
构建步5,650,924字节，wasm64为1,144,481/5,510,497字节。C runtime两项也各有
唯一pass；实际生成的C程序在argv/env、statfs、malloc、匿名映射拆分/解除、
固定范围拒绝、pthread/TLS及信号断言全部完成后才输出它。其压缩日志为
1,139,242/1,032,747字节，构建步5,121,105/4,960,564字节。

Python两项已逐项核实匹配位宽的ABI/sysconfig、安装路径和七个mmap阶段：
匿名buffer、resize、flush、madvise、提示位、普通私有文件副本和共享拒绝。
包括只读Python API、无文件回写及关闭来源后存活。wasm32压缩日志1,459,741
字节/构建步7,615,243字节，wasm64为1,454,324/7,620,960字节，各唯一pass。
run-test/shutdown与核查过的发布版本一致，作业成功要求等待machine.closed并
拒绝收尾错误，以上六项关闭门禁成立。接受固定ec78632的上述Node范围，不
推广到浏览器、新Git或尚在运行的显式关闭/旧模块组合。

## Git 恢复标准文件映射读取

distro1abe1e87b158107443277d49982b1d6ac17cae97 / 集成39941ff移除NO_MMAP，
恢复Git原有只读私有文件映射，未改写Git对象/索引/pack读取实现。构建必须
核实生成的GIT-CFLAGS及compat/mmap.o未选择fallback；已有进程启动补丁与
许可材料不变，musl/Linux/LLVM源码也未因这一增量改动。

packing沿用原语料，再提交1.25MiB及二进制尾部内容，使用Git原有窗口配置
要求大于1MiB的真实pack、无对应松散对象回退、完整读回及gc后数据不变。
30项宿主检查及格式通过，包含原生实际数据断言与损坏cat-file输出拒绝；
这是编排证据，不是目标Git2.55或Wasm的运行证明。六项新检查各派发一次：

| 检查 | 位宽 | 任务 |
|---|---|---|
| Git workflow | wasm32 | [41482555691](https://github.com/HighCWu/distro/actions/runs/41482555691) |
| Git workflow | wasm64 | [41482554251](https://github.com/HighCWu/distro/actions/runs/41482554251) |
| Git packing | wasm32 | [41482555292](https://github.com/HighCWu/distro/actions/runs/41482555292) |
| Git packing | wasm64 | [41482554321](https://github.com/HighCWu/distro/actions/runs/41482554321) |
| Git remote | wasm32 | [41482553471](https://github.com/HighCWu/distro/actions/runs/41482553471) |
| Git remote | wasm64 | [41482553386](https://github.com/HighCWu/distro/actions/runs/41482553386) |

六项均已核实实际构建门禁、对应阶段及唯一pass。发布的runner未改变，退出
成功要求等待machine.closed且无清理错误，关闭门禁成立。大仓库的复制窗口仍消耗
真实direct内存，不把标准mmap调用恢复当作MMU按需映射或性能已经改善。
详细源码判断与边界见[Git运行记录](git-runtime.md#恢复上游文件映射路径)。

## 默认映射对照验收与 curl 线程解析

ec78632的剩余两项41478948425/41478944068现已读取实际日志：每项四次独立启动，
分别完成128KiB候选的四阶段、显式关闭拒绝、旧模块拒绝、并发预算/回滚，
各自唯一pass；发布的runner关闭门禁成立。至此该版本八项Node全部验收，
不扩大为新Git或浏览器版本。

distro94a9f3e / 集成db73c48启用curl8.21原有线程解析器，去掉强制同步解析的
构建限制。没有修改curl应用源码、补造musl函数或扩大fork。配置后必须确认
USE_RESOLV_THREADED且未启用c-ares，运行时再次核对AsynchDNS及后端身份。
独立标准libcurl消费者同时发起延迟DNS与数字地址HTTP；真实UDP查询等待时，
另一个multi传输必须完成，之后释放DNS、校验精确数据，再执行新域名查询。
multi清理后要求解析线程退出，两个服务器线程join、fd恢复及正常返回。
详细验证与异步任务见[curl记录](curl-runtime.md#上游线程-dns-解析器)。

94a9f3e的解析目标41486875380/41486866009现已逐项核实三个真实阶段、唯一pass
及发布runner的关闭门禁；双位宽transfers和HTTPS回归也已核实相应源脚本/
完整阶段、唯一pass及关闭，接受该源码的六项Node范围。58b087c / 集成60a1ede将
同一安装镜像接入双位宽、双引擎的两轮浏览器验收，独立根盘不复用修改，
真实目标结果待核实；没有将Node结果代验浏览器或新增libc包装。

## 独立符号版本 SDK 接入

真实程序源码兼容性增量677cf9e / 集成363f770将9035266编译器接到现有SDK配方。
默认LLVM137009e、musl7b077a6d、内核59937da2不变；独立配置复用已有运行库。
它不新增syscall或libc函数，而是让包含普通.symver的源码进入正常Linux/Wasm
进程的编译/链接/执行验收路径。公开预取41487600049已取得精确候选源码哈希。

单一公开任务41488752556聚合双位宽SDK配置、既有C++运行语料和新C消费者，
共享一次LLVM构建。C消费者覆盖不同版本签名、long宽度、同单元引用、真实
函数/数据重定位身份和写入隔离；宿主参考及双位宽前端/静态分析通过，目标
阶段和关闭仍待验收。ELF入口、动态libc加载、AIO共享ring仍未因此实现。
见[实施记录](elf-dynamic-linking.md#独立-sdk-与-linux-进程验收接线)。

后续41488752556在SDK驱动检查失败，原因是独立候选禁用宿主后端，而完整
SDK检查需要该后端。3762d29 / 集成3f2f209恢复既有后端选择，41529152599
正在针对性复验；没有删除检查，目标语料和关闭仍未验收。

## clone3 的 CLONE_INTO_CGROUP 标准传输

distro2c48032 / 集成c868659在已有原生clone3路径传递CLONE_INTO_CGROUP及
u64 cgroup fd。Linux59937da2的CGROUPS/PIDs和通用clone3实现原已具备该
能力，适配层此前提前EOPNOTSUPP；本轮不修改Linux或musl，也不新增公共API。
fd/权限/控制器检查由Linux完成，没有用父进程创建后再迁移来冒充出生归属。
适配层保留VER2最小长度与INT_MAX检查、未请求字段忽略，以及旧对象准入。
新helper与feature bit独立于旧宽helper，防止改变签名或静默传递fd0。

标准C消费者在目标组为空时分别验证短结构、超宽fd、真实EBADF和pids.max=0
的EAGAIN；原语料要求输出槽不变，但该断言不符合Linux，修正见下文。放宽为1后组合CLONE_PIDFD，
子进程第一次读取procfs即在/work，父端核对组成员、原归属、PIDFD状态和reap。
再验证普通fork仍继承原组，随后继续已有三阶段cgroup继承/限制/卸载语料。
初始化脚本显式挂载proc；工作负载禁止在宿主直接执行，避免修改宿主cgroup。

静态review覆盖u64/机器字区分、一次捕获、fd0、旧对象拒绝、错误后状态清理
及C规范结构字段复用时清零。运行层397项、两套TypeScript检查、8项实际执行
对象/SDK检查、GCC/Clang与双位宽前端/静态分析通过，不替代目标运行。
双位宽cgroup和既有fork runtime各派发一次；新cgroup每路需完整六阶段、
唯一pass与机器关闭，既有fork语料按原完整阶段验收。任务结果仍待核实。

| 检查 | 固定2c48032的任务 |
|---|---|
| cgroup wasm32 | [41492418782](https://github.com/HighCWu/distro/actions/runs/41492418782) |
| cgroup wasm64 | [41492435069](https://github.com/HighCWu/distro/actions/runs/41492435069) |
| fork runtime wasm32 | [41492446819](https://github.com/HighCWu/distro/actions/runs/41492446819) |
| fork runtime wasm64 | [41492457442](https://github.com/HighCWu/distro/actions/runs/41492457442) |

## clone3 未请求字段按 Linux 忽略

3a77133 / 集成66f4f99修复解析器把非零、未请求的PIDFD/TID/TLS字段当成
不支持形态的问题。核对固定kernel/fork.c的copy_clone_args_from_user及
copy_process/copy_thread后，移除这些字段的额外拒绝；仅按已请求标志捕获
相关输出。超宽无效值未请求时不验证、不截断、不写入；请求时保留原规则。
set_tid的结构性错误、真实set_tid选择与非默认栈的拒绝不变。没有新增函数
或应用API，也没有修改Linux/musl或放宽多线程fork。

现有raw clone3语料扩展为零字段、UINT64_MAX和可写哨兵，检查真实父子身份、
局部/全局隔离、哨兵不变及单次wait；相应fork阶段加入ignored fields字样。
397项运行层、两套TypeScript、86项针对性parser/执行/宿主负向/浏览器契约
和双位宽静态分析通过；原生fork shim只证明工作负载断言，不证明Linux clone3。
新双位宽fork runtime独立派发，实际阶段及机器关闭仍待核实；旧2c48032的
cgroup与fork任务继续运行，不重复派发或用旧语料替代本组结果。

固定3a77133的新目标为
[wasm32 41493736877](https://github.com/HighCWu/distro/actions/runs/41493736877)、
[wasm64 41493747070](https://github.com/HighCWu/distro/actions/runs/41493747070)。

## PIDFD 失败输出与 set_tid PID 选择

固定2c48032的cgroup两项目标41492418782/41492435069均已读取实际日志，
在“failed creation leaves output and target unchanged”断言失败，errno=11。
核对固定kernel/fork.c：copy_process先pidfd_prepare并put_user预留编号，
之后才cgroup_can_fork；失败通过fput/put_unused_fd撤销预留，不回滚用户输出。
2b6a078修正语料：目标计数为0、无子进程、fd数量不变，若输出已写编号则
fcntl必须EBADF；成功用例前重置输出槽，避免将错误路径的旧值当成子快照。
没有修改正确的Linux行为，也不把此次测试修正说成内核能力修复。

同轮独立源码04ee178修正执行对象链接夹具的最小stdint.h，补充上组语料所用
UINT64_MAX；用已发布HEAD源码的临时副本复验双位宽链接/碰撞拒绝均通过。
它单独提交，并由根仓库e17a5ba单独pin；真实musl头文件原本已有该宏。

ab76dcf新增clone3 set_tid PID选择传输，c937e5a同步SDK元数据，最终2b6a078
/ 集成c388cb5。解析器先拷贝最多32个有符号pid_t，C执行对象在静态区承载
向量；Linux原copy_clone_args_from_user/alloc_pid处理范围、命名空间深度、
权限及EEXIST。没有补造musl函数、修改Linux或改成宿主PID分配。旧对象通过
独立feature/export准入；旧签名不变，每次普通请求清零指针/count，错误后
清除捕获向量。默认栈、单线程与无内核softmmu边界不变。

新独立标准C消费者只在隔离目标运行，验证有符号无效值、越界向量与命名空间
深度拒绝、无输出/fd泄漏；创建PID10000并核对TID/PIDFD/输出隔离，保持存活
时再请求同PID必须EEXIST。新PID命名空间中[1,10001]必须分别成为内层PID1和
父可见PID10001；随后测试普通clone3、降权后的EPERM、普通fork与观察资源清理。
该输出不变要求只针对PID分配前后已核对的失败点，不泛化到cgroup的后期失败。

399项运行层、两套TypeScript、10项实际执行对象/SDK/原生工作负载检查和双位宽
前端/静态分析通过；不是Linux整机证明。两项PID选择与修正后cgroup目标各
派发一次，前者每路要求三阶段，后者六阶段，均须唯一pass和机器关闭。

| 检查 | 固定2b6a078的任务 |
|---|---|
| PID选择 wasm32 | [41496549167](https://github.com/HighCWu/distro/actions/runs/41496549167) |
| PID选择 wasm64 | [41496558372](https://github.com/HighCWu/distro/actions/runs/41496558372) |
| cgroup wasm32 | [41496568042](https://github.com/HighCWu/distro/actions/runs/41496568042) |
| cgroup wasm64 | [41496577146](https://github.com/HighCWu/distro/actions/runs/41496577146) |

## PID 选择、cgroup 及字段忽略的已核实结果

固定2b6a078的PID选择两项目标现已读取完整实际日志，每路三个阶段和唯一pass，
覆盖有符号范围/向量故障/深度、指定PID/TID/PIDFD与EEXIST、命名空间顺序、
EPERM及普通clone3/fork恢复。压缩日志/构建步：wasm32为1,404,356/7,313,987
字节，wasm64为730,476/3,927,632字节。运行器必须等待machine.closed，收尾
错误使任务失败，双位宽关闭门禁成立。仅接受该源码的Node范围。

同源cgroup wasm64的41496577146也核实六阶段、唯一pass及相同关闭门禁，
压缩日志891,581字节/构建步4,468,943字节；PIDFD后期失败检查修正已通过真实
目标，不将原先错误的“不改输出槽”要求移入内核。wasm32的41496568042现也
已读取实际六阶段、唯一pass及相同关闭门禁，压缩日志1,557,001字节/构建步
7,835,545字节，接受该源码的双位宽范围。

固定3a77133的41493736877/41493747070已核实完整fork语料，包括新增ignored
fields阶段、exec拒绝/替换、信号与多线程拒绝恢复、各唯一pass及发布runner
关闭门禁。日志/构建步分别为1,412,000/7,314,428与748,619/3,928,114字节。
这些结果不代替后继源码或浏览器范围。

## clone / clone3 共享 Linux fs 与文件表

6350acf / 集成40e7aa2接纳CLONE_FS/CLONE_FILES，保留独立用户地址空间与
单线程父进程边界。Linux原copy_fs/copy_files路径已具备实际能力，原执行
适配层拒绝这些位。现在分别捕获sharingFlags，经原options/native参数传输
交给Linux；两入口均要求features bit3及正确helper。旧对象在descriptor
初始化前拒绝，旧签名保留。错误/trap后清除分享选项，普通fork不继承它们。

标准C语料分别用clone3和flags-first clone创建共享cwd/umask的子进程，
验证修改对父可见、用户变量仍独立；共享文件表时子close使父fd成为EBADF，
而close_range的UNSHARE先分离后关闭，父fd及精确文件内容保留。两入口还
验证FS/NEWNS冲突由Linux返回EINVAL，最后普通fork必须隔离cwd/close并清理。
语料仅在隔离Wasm机器运行，不在宿主改变cwd、umask或创建根目录。

403项运行层、两套TypeScript、10项执行对象/SDK/工作负载检查、GCC/Clang
前端及双位宽Wasm静态分析通过。共享资源由Linux维护，没有新增musl函数、
内核softmmu或共享用户内存支持；每个新目标须实际三阶段、唯一pass和关闭。
双位宽各派发一次，目标结果待核实。

固定6350acf的目标为
[wasm32 41500407394](https://github.com/HighCWu/distro/actions/runs/41500407394)、
[wasm64 41500420663](https://github.com/HighCWu/distro/actions/runs/41500420663)。

两路现已读取实际完整日志，各确认上述三个阶段及唯一pass。压缩日志/构建步
分别为1,394,921/7,314,164和696,644/3,927,728字节。固定6350acf的发布
runner与已审计版本的run-test.js/shutdown.js无差异：必须等待machine.closed，
关闭异常使任务失败，双位宽Node关闭门禁成立。该结果只接受对应源码与Node
范围，不扩大为浏览器、多线程fork或共享用户地址空间。

## 标准 brk 与 LSM 注册表的架构接线

Linux `abf31db96`、`a21b84296` 接入标准号214，由原进程分配器管理直接堆，
并校验实时 RLIMIT_AS/DATA、TASK_SIZE 和 errno 保留地址。拒绝增长返回原 break，
不新增内核 MMU。内核不跨用户回调持锁；回调完成后的 mm 信息按高水位发布，
避免较早帧覆盖后来增长。没有完整 VMA/RSS 记账，也保留原共享 mmap 堆不收缩的
约束。musl 架构和调用路径边界见[musl 记录](musl-compatibility.md#标准-brk-的独立-syscall-调用路径)。

新独立 SDK 配置先让既有 brk/sbrk 走标准 syscall；默认 libc 路径尚不切换。
真实消费者检查 raw/libc 堆状态一致、errno、实时限额后的 malloc 失败与恢复、
双线程堆分配及大 TLS、mmap/mremap 数据和清理。它不扩大多线程 fork 支持。
Clang18/22 双位宽小型模型执行实际内核/libc 函数体和生产执行适配器，验证独立
内存、回调重入、地址溢出、限额拒绝与恢复；这些不是 Linux 启动验收。

此前 `9250e0c` 的默认组合以及 `3dc5c82` 的 wasm64 动态加载，在内核链接阶段
因缺少 `__start/end_lsm_info` 及 early 对应符号失败。已读取实际 Heavy 日志，
包括41555454796、41555461464、41555481442和41557119503；尚未执行应用语料，
不能解释成 fork、动态加载或符号版本运行失败。Linux `5fcef04ca` 沿用现有
Wasm section 收集与启动初始化，把真实普通/early LSM 注册表保留下来并设置
边界，不关闭 SECURITY/Landlock，也不使用空表掩盖遗漏。Clang18/22 双位宽实际
Wasm 产物、原始注册宏与生产收集脚本通过，涵盖 table64、空 early 表及非空表
函数指针执行；完整 Linux 初始化仍待目标确认。

公开预取41565925510核实立即父版本 a21b84296 的既有哈希及5fcef04ca源码树
哈希。distro `5ef5878`、集成 `2e04906` 固定上述 Linux 与 musl `4bad222d`。
CI 41566249073 的 `brk-syscall-check-both` 合并双位宽独立 brk、默认
C++/符号版本、Landlock、
fork、动态加载及跨库符号版本回归，共用构建图减少重复内核构建。实际阶段、
唯一 pass 与关闭结果仍待逐项核实，不把派发或宿主检查当作目标通过。

后续静态产物 review 发现消费者自身的优化问题：Clang18/22 在 O2 下可删除
只比较返回值是否为 NULL 的 malloc，进而删除整个后续线程/TLS 路径。不能因此
用原语料证明 OOM 或大 TLS。distro `43195e4` / 集成 `6044f91` 仅修正消费者：
测试专用 `-fno-builtin-malloc` 保留实际调用，逐字节 volatile TLS 读写确保触及
完整数组；构建时检查优化后的实际对象包含 malloc、pthread_create 和8192字节
TLS 数据段。Clang18/22 双位宽对象及分析通过，去掉编译选项的反向控制四路均
被门禁拒绝。该增量没有新增 syscall、libc 函数或更改默认程序编译选项。
CI 41567015097 的 `brk-syscall-check-runtime-both` 验收修正消费者，原合并任务继续运行，
其独立回归结果可分别核实，不能将旧 brk 语料当作本修正的运行证据。

## 直接匿名映射的 MADV_FREE

Linux `d988da3b9` / musl `cd7dc871` / distro `1ebb4ea` / 集成 `e4d74e0`
接入已有标准 madvise 的 MADV_FREE 建议。Linux 允许已建议的匿名内容立即丢弃，
或延迟至内存压力出现；本直接内存实现选择在调用内立即清零，保留地址预约，
后续写入照常保留，不设置延迟丢弃状态。只接受登记的完整私有匿名映射范围；
支持相邻拆分记录，文件副本返回 EINVAL，空洞返回 ENOMEM。所有记录先校验，
失败不会清零前面的合法匿名部分。它不启用页表、共享映射或内核 softmmu，也不
缩小 Wasm 内存容量、降低已保留的堆高水位或保证向宿主归还物理页。
语义依据[Linux madvise 手册](https://man7.org/linux/man-pages/man2/madvise.2.html)。

新增代码没有公共 API 或包装函数；标准常量和 madvise 入口原本已经存在。
Clang18/22 的 wasm32/64 实际内核准入和分配器函数体执行、静态分析通过，覆盖
立即清零、相邻页保留、之后写入、文件/匿名混合失败、空洞及零长度。禁用实际
清零的反向控制四路均失败。GCC/Clang 原生消费者检查标准允许的延迟或立即回收
行为；Wasm 消费者额外要求本实现的立即清零。真实文件复制语料检查 EINVAL 后
原数据、fd 及 split-unmap 清理。前端与分析通过不等于真实 Linux 已验收。

公开预取41567625770核实 Linux 立即父版本和新源码树哈希，41567626517核实
musl 的精确 revision/hash。CI 41567995019 的 `toolchain-smoke-check-madvise-free-both` 合并
双位宽 madvise 四阶段及文件流三阶段目标，复用构建图；真实阶段、唯一 pass
和机器关闭仍待逐项核实，不沿用旧 DONTNEED 的运行结果。

41567995019（1ebb4ea）随后已失败，7,685,329字节实际 Heavy 日志确认仍是
musl 共享链接缺少堆边界和 SjLj tag，未执行 madvise 语料。对应配置修复已纳入
后继合并回归41572697826，不重复派发或将该旧失败解释为 MADV_FREE 运行失败。

## LLVM 22 下保留的共享 libc 构建配置

实际读取41566249073（5ef5878）7,770,060字节和41567015097（43195e4）
2,176,662字节的 Heavy 日志，均在 musl-wasm32 的 libc.so 链接阶段失败，缺少
堆边界 __heap_end/__global_base/__data_end 和 SjLj 的 __c_longjmp。
尚未运行 brk 消费者，也不能据此判定先前 LSM 修复的启动结果。

小型实际 Wasm 产物复现了版本差异：Clang18 的共享链接允许这些外部符号，
Clang22 默认严格策略会拒绝。distro `0bd6c1b` 在既有 musl 构建配置中显式指定
import-dynamic，配合共享导入内存及平台既定最大值，保留 libc.so 输出。
这些 LDFLAGS_AUTO 仅用于 musl 自身的共享链接，不传入普通应用的 SDK 链接。
没有关闭共享库构建、填入假堆边界、另造异常 tag，或新增 libc 函数/头文件 API。

小型检查编译实际 brk 布局回调和 wasm_longjmp.c，使用生产 Nix 配置的链接参数；
Clang18/22 双位宽均核实 GOT 数据重定位、宿主提供的同一个 SjLj tag 及异常
payload，缺少真实堆导入会拒绝实例化，Clang22 严格反向控制明确链接失败。
这不等于完整共享 libc 已能在 Linux 进程中动态装载，也不宣称跨库 C++ 异常或
完整 ELF 入口已实现。完整 musl/内核启动仍由真实目标验收。

后继 `6c6ac0a` / 集成 `ebbc71d` 将 MADV_FREE 匿名/文件目标纳入既有
brk 合并回归，CI 41568722379 共用构建图定向复验构建修复后的组合。
旧任务不取消；不同源码的
阶段与关闭结果分别核实，尚未成功的任务不能视为能力验收通过。

## 独立 USER_NS 配置与标准进程凭据路径

固定 Linux 的官方 Kconfig 将 USER_NS 默认为 n，本项目默认配置继续保持该值。
distro `0417e65` / 集成 `d8ae363` 增加默认关闭的 userNamespaceCandidate
内核构建参数；独立镜像显式启用 CONFIG_USER_NS，olddefconfig 后核对实际结果，
并将所选配置记入构建材料。普通内核仍检查 USER_NS 关闭，所有配置检查 MMU
未开启。此增量复用 Linux 通用实现，没有修改 Linux 源码、执行 ABI 或 musl，
也没有新增公共函数、包装或扩大多线程 fork 支持。

普通 SDK 构建父程序和独立 helper。helper 在普通 posix_spawn/exec 之后调用
既有 unshare(CLONE_NEWUSER)，验证命名空间身份变化、写入单个 UID/GID 映射和
setgroups=deny；检查映射不可重写、未映射 UID 被拒绝、setns 不允许重入自身或
返回祖先命名空间。普通 exec 后再次核对身份、映射和 setgroups 策略，再退出。
父程序检查原命名空间与组数保持、标准 wait 单次回收和关闭收尾。接口语义依据
[user_namespaces](https://man7.org/linux/man-pages/man7/user_namespaces.7.html) 与
[setns](https://man7.org/linux/man-pages/man2/setns.2.html)，拒绝顺序亦核对固定
kernel/user_namespace.c 的实际实现。

Clang18/22 双位宽实际消费者的前端和静态分析通过，GCC/Clang 原生编译通过；
没有把宿主命名空间设置或权限策略当作 Wasm 目标证据。独立双位宽
CI 41569680820 的 user-namespace-check-both 需核实各四阶段、唯一 pass 与机器关闭，尚未接受
完整目标通过。它不证明容器运行时、全部 namespace 组合或宿主安全隔离已经完成；
USER_NS 未提升为默认构建选项，后续依据实际工作负载和目标结果决定。

上述0417e65的41569680820已失败；读取15,710,311字节 Heavy 日志，确认
wasm64 已进入用户程序，在 initial root namespace 检查中因 /proc 路径不存在
返回 ENOENT。原始 initramfs 不自动挂载 procfs，这不是 unshare 的 ENOSYS
或权限语义结果。distro `49c86fa` / 集成 `77cd647` 给 fixture 显式建立 /proc、
挂载 procfs，并在子进程回收和父状态核对后卸载。Clang18/22 双位宽前端/分析
通过，同一四阶段目标用已集成启动修复的新组合复验
[41575757161](https://github.com/HighCWu/distro/actions/runs/41575757161)；真实
namespace 语义仍待核实，尚未计为通过。

49c86fa 的41575757161随后已成功，实际读取13,775,264字节 Heavy 日志，
wasm32/64 各核实四阶段：unshare 与单条 UID/GID map、重写和 unmapped ID/
setns 拒绝、普通 exec 后凭据和 setgroups 策略、父 namespace/groups 不变及
单次回收/清理；每个目标唯一 pass。run-test.js/shutdown.js 与核对版本无差异，
作业退出成功要求等待 machine.closed 且无清理失败，关闭门禁成立。接受该独立
USER_NS 配置的上述双位宽 Node 范围，默认仍按官方 USER_NS=n，不推定容器、
浏览器、全部 namespace 组合或安全隔离已验收。

## 启动 FDT 覆盖预载 initrd 的实际缺陷

6c6ac0a 的合并 CI 41568722379 已失败；实际读取21,903,713字节 Heavy 日志，
本次已进入 Linux 启动并出现 landlock: Up and running，但在 Landlock 的
wasm32 镜像中，外部 initrd 被报告为 invalid magic，随后 FDT CRC 检查失败，
最终无法挂载根目录。没有进入应用阶段，不能将其当作完整 LSM、brk 或动态加载
验收，也不把正常的 CMake 不支持特性探测误记为编译失败。

Linux `1c15622fa` 修复 bootstrap FDT 的分配范围。原实现临时把所有已物化
线性内存视为可分配 RAM，此时尚未读取 FDT 中的 initrd 保留区；当 __heap_base
后空隙不足时，FDT 的清零/复制会覆盖已预载 initrd。之后释放 initrd 页也会
破坏重叠 FDT。现在仅临时描述当前已物化内存之后的区域，使用已有 memblock
materialization hook 在清零前增长内存，解析后再安装权威内存/保留区布局。
不需要修改 host 文件、调大固定间隙、关闭 LSM 或隐藏 CRC 错误。

Clang18/22 双位宽检查执行实际 load_devicetree 函数体，以 memblock/libfdt
模型验证0、1296、65535字节空隙、预载 initrd 保持和释放后 FDT 生命周期。
恢复旧前缀分配时，0与1296字节空隙明确破坏 initrd，而65535字节空隙的对照
保留内容；反向检查要求精确匹配这些结果，不把任意 trap 当作复现。
正常分配及静态分析通过。模型不等于真实
内核启动，完整目标仍待复验。公开预取41572289993核实父版本 d988da3b9 既有
哈希及新源码树哈希；distro `6b1777e` / 集成 `e8b6ab5` 完成固定输入接线。
CI 41572697826 定向复验合并内核/libc/普通消费者矩阵，仍待真实阶段及关闭。

## 原版 GNU split 的标准 fork 路径

distro `46ca3dc` / 集成 `0e3102b` 新增独立 coreutils-split-fork 构建。
它引用既有固定 GNU coreutils9.7 原始源码，不应用默认包的 split-posix-spawn
或其它 fork 回避补丁。配置使用独立静态 C fork SDK，让 Autoconf 正常探测；
构建前后 cmp 原始 split.c 并保存 SHA256，最终按现有执行 ABI 完成整个程序的
链接后转换。GNU 源码及构建材料保留原 GPL 许可，自有包装和测试为 MIT，
没有向 musl 或内核添加新接口，也尚未删除默认包的应用补丁。

语料调用实际 GNU split：顺序过滤的文件前缀证明过滤命令执行，round-robin
同时创建三个子进程并检查 pipe/EOF，验证退出码7、缺失 shell 的 exec 失败，
再执行一次成功过滤并清理。宿主 GNU split 的四阶段通过；忽略 --filter 而
进行普通分割的反向实现会失败。ShellCheck、shfmt、Nix/JS 格式和手工静态
review 通过。这些不是新版本 GNU 程序已在 Wasm 编译/运行的证据。
原版调用路径依据[固定 split.c](https://github.com/coreutils/coreutils/blob/v9.7/src/split.c)。

双位宽真实构建/运行 CI 41572698904 使用含启动修复的6b1777e，
分别核对各四阶段、唯一pass和
机器关闭。此项保持单线程进程 fork 范围，不扩大多线程 fork、动态快照或默认
SDK。它用于判断已有标准系统能力能否移除应用改造，尚未宣称该目标已通过。

后继 `6a69459` 的 [41580829257](https://github.com/HighCWu/distro/actions/runs/41580829257)
现已完成。实际 Heavy 日志逐项确认 wasm32/64 各四阶段、各唯一 pass；该固定
运行器等待 machine.closed，关闭失败会令作业非零退出，目标作业成功。接受
原版 GNU split 的上述双位宽 Node 范围，不推定浏览器、默认 SDK 或多线程 fork。
此前两次失败分别发生于生成头文件准备和 config.h 材料归档，没有作为运行通过。

## 纯计算循环检查点的编译组件原型

现有信号/定时器路径仍依赖程序进入内核，纯计算循环的异步交付缺口尚未关闭。
distro `53be296` / 集成 `61154e5` 加入独立 MIT 编译执行组件：用现有 Clang
trace-pc、no-prune、edge 插入编译器回调，应用循环源代码不用手工调用检查点。
原理依据[Clang SanitizerCoverage](https://clang.llvm.org/docs/SanitizerCoverage.html)。
不需要修改 LLVM 源码，也不使用尚未落地的引擎提案。

隐藏的编译器 hook 通过原生 Wasm TLS 每4096次回调才调用宿主，TLS 初始化前
直接返回；在进入宿主前重置计数，使非局部控制流退出后仍可再次进入。没有增加
公共 libc 函数或头文件。在这个原型版本中尚未接入 Worker/SDK；后续独立配置
接线见下文，真实目标验收仍待完成，默认执行路径保持原状。

Clang18/22 的双位宽实际 Wasm 产物及组件静态分析通过：纯计算语料导入中没有
syscall，两实例共享 memory 但使用不同 TLS，分别经过三次批量宿主入口结束
计算；验证初始化前不写内存、宿主非局部异常后计数恢复及拒绝返回值的可见失败。
移除编译插入后，相同循环只耗尽迭代上限，反向检查明确失败。该结果不证明真实
SIGALRM、pthread 信号、siglongjmp、并行 Worker 或性能开销已经验收。

完整源码核对发现，musl 的 pthread_create 已为新线程分配独立原生 TLS，
start/start_c11 在调用应用入口前执行 __wasm_init_tls。clone 早期暂存父
__tls_base 不代表应用线程一直共享它，不应据此补写已有初始化。
scripts/check_clone_native_tls.py 编译真实 clone.c 及从当前源码提取的 C11
启动体，在共享 memory 的两实例间调用真实函数表入口。Clang18/22 双位宽
产物确认：首次 gettid 边界仍暂用父 TLS，应用回调前已初始化独立区域，子写入
不影响父数据；删除初始化的反向版本明确因父数据污染失败。两份 C 函数体静态
分析通过。syscall 传输与线程退出由模型承担，故此证据不替代并行 Worker、
完整 pthread_create 分配/回收或 Linux 目标运行验收。

检查点接线必须避开原生 TLS 初始化窗口；base 非零本身不能证明属于当前线程。
编译组件原型显式初始化不同区域的结果也不证明这一启动边界已被交付配置保护。

后续接线与验收必须保持 pt_regs、用户栈、RCU/IRQ 状态以及
现有回调/非局部退出边界；不能用伪造 gettid 等 syscall 代替，以免改变 seccomp
或 ptrace 行为。实际 Linux 要覆盖纯计算定时器、线程定向信号、siglongjmp、
strict seccomp 与关闭。未插桩库循环、应用自己的 coverage hook、动态加载和
fork 组合也需要明确处理，不据当前原型扩大已支持范围。

## 计算检查点的内核中断返回入口

Linux `56e041088` / distro `696e67f` / 集成 `0ddd166` 增加私有固定 i32
user_poll_v1 导出，不分配 Linux syscall 编号。入口拒绝内核阶段调用；从用户
阶段进入后保存 pt_regs，清除本次 syscall/restart 状态，获取当前 C 栈，再处理
定时器与远程请求，调用通用 irqentry_exit_to_user_mode_prepare。原寄存器在
instrumentation_end / exit_to_user_mode 之前恢复，避免进入用户上下文后再调用
可能由编译器生成的 memcpy。栈查询失败仍平衡上下文退出，但不运行待处理信号。

该入口不执行 syscall entry/exit tracing 或 seccomp 检查，不用伪造 gettid
突破纯计算循环；真正的应用 syscall 继续由原有策略路径处理。宿主仍须保证没有
活的内核回调或信号帧，并避开用户栈/TLS 的初始化窗口；当前尚无 Worker 导入
和 SDK 配置，因此不能用入口存在推定这些调用前提已经满足。

公开预取 [41576709235](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41576709235)
核对前驱归档哈希后得到新源码哈希。Clang18/22 双位宽实际函数体检查及静态分析
通过：验证 entry/IRQ 顺序、完整寄存器恢复、栈错误和内核阶段拒绝；保留旧
restart 返回值、误走 syscall 专用返回工作分别由反向版本拒绝。通用 Linux
工作在此检查中由模型承担，不算真实信号交付。新双位宽内核构建/既有 brk
回归 [41577075102](https://github.com/HighCWu/distro/actions/runs/41577075102) 已成功。
读取12,198,642字节 Heavy 日志，双位宽各核实标准 brk 三阶段与唯一 pass；固定
运行器的关闭门禁通过。这接受新内核构建、启动和既有 brk 路径，不以此代替
user_poll_v1 的真实调用验收。

## 计算检查点的 Worker 与独立 SDK 接线

distro `0d02ed7` / 集成 `e148d11` 将上述内核入口接到 Worker，独立增加
sdk-cooperative-poll / sdk-cooperative-poll-wasm64。它们保留普通 wasm-linux-cc
等命令，应用源代码无需插入检查点；现有 Clang 编译配置自动插入 trace-pc 回调，
链接独立 MIT 执行对象。默认 SDK、musl pin 和公共 API 不变，没有伪造 syscall。
执行组件源代码、配方、说明及 MIT 许可随该 SDK 安装。

Worker 在活的内核回调或信号处理器期间延后检查点；调用前核对当前用户阶段和
C 栈，内核入口异常经过已有非局部退出恢复，exec 更换实例后停止旧用户调用。
模块须有显式 ABI/TLS/stack 导出；动态加载与 continuation fork 组合拒绝准入，
没有新内核入口的旧内核在 exec 阶段拒绝这个配置。没有扩大多线程 fork 范围。

这个候选只给应用编译单元插桩，复用未插桩的现有 libc/启动库：普通 pthread
先初始化自己的原生 TLS，再进入应用回调。禁止用该配置重编 libc/startup 或在
TLS 初始化前插入应用回调；base 非零无法证明 clone 早期的所有权。自定义 raw
clone 启动、未插桩库的纯循环、处理器内嵌套信号循环、自有 coverage hook、
C++ 异常及动态/fork 组合仍须分别处理，不据此声称整个执行空间可异步抢占。

普通 C 语料只调用现有 libc/Linux 接口，独立 raw initramfs 双 CPU 目标要求：

1. 无 syscall/sleep/读钟的纯计算循环收到 setitimer 的 SIGALRM。
2. handler 用 siglongjmp 离开检查点，再次计时/循环仍收到信号。
3. pthread_kill 向正在纯计算的线程交付信号，核对原生 TLS 和父线程未被改写。
4. posix_spawn 的子程序进入 strict seccomp 后仍可纯循环接收定时信号，用标准
   raw SYS_exit 退出，父进程只回收一次。

Clang18/22 双位宽消费者的真实插桩/SjLj 编译及静态分析、GCC/Clang 原生编译
通过；原型真实 Wasm 产物现也通过生产模块准入检查，移除插桩的反向版本仍在
纯循环断言失败。435 项宿主检查、两个 TypeScript 项目、Nix/JS/workflow 格式
检查通过，包含 live callback 延后、无效 C 栈拒绝及非局部异常后状态恢复。
这些均不代替真实 Linux 运行。

已派发同源码的 [41578142626](https://github.com/HighCWu/distro/actions/runs/41578142626)
cooperative-poll-check-both，需逐项核实上述四阶段、各唯一 pass 与机器关闭。
0d02ed7 的该任务随后已成功，读取8,355,929字节 Heavy 日志，wasm32/64 各
核实四阶段与唯一 pass：计算定时信号、siglongjmp 后恢复、线程定向信号/TLS、
strict seccomp 子程序的定时信号与 raw exit/单次回收。run-test.js/shutdown.js
与核对版本一致，必须等待 machine.closed 且无清理错误，关闭门禁成立。接受该
独立静态 C 配置的对应双位宽 Node 范围，不推广到未插桩库循环、浏览器、动态
加载/fork 或整个系统的异步抢占；没有提升为默认 SDK。

## 计算检查点与 GEN CPU 定时器的独立组合

distro `b7b8b4a` / 集成 `e10e9f1` 新增 cooperative-poll-cpu / wasm64 独立
配置，把已有插桩 SDK 与现有 WASM_VTIME/VIRT_CPU_ACCOUNTING_GEN 内核连接，
不新增 syscall、libc API 或默认 Kconfig 变更。旧 GEN 验收使用有 syscall 的
有界计算，本组合要验证无 syscall/读钟/睡眠的循环仍能交付 ITIMER_VIRTUAL
与 ITIMER_PROF，并用 getrusage 确认用户 CPU 时间增长。GEN 仍记录逻辑调度
区间，不保证扣除宿主暂停/GC 或达到原生物理 CPU 精度。

静态 review 还修正接受语料的早到信号漏洞：线程从循环内部才发布 ready，
handler 核对当前已处于计算区间，避免信号恰在线程启动或循环前收到也算作循环
交付。siglongjmp 离开时清除这个区间标志。后继普通配置四阶段与 CPU 配置
六阶段仍须重新验收，不直接沿用0d02ed7的较早语料结果。

普通/CPU 两种 C 语料在 GCC/Clang 编译，以及 Clang18/22 双位宽插桩/SjLj
编译与静态分析通过；Nix 格式和源码 review 通过。这些不是目标运行证明。
[41580416330](https://github.com/HighCWu/distro/actions/runs/41580416330)
cooperative-poll-cpu-check-both 同时包含双位宽普通四阶段与 GEN 六阶段，均须
唯一 pass 与机器关闭。该新组合仍在异步验收，没有扩大多线程 fork 或动态模块
范围。

## 计算检查点的浏览器交付接线

distro `b6b9911` / 集成 `b56c63e` 将普通四阶段程序的同一 raw initramfs 接到
process-poll 浏览器配置；双位宽、双引擎均使用两 CPU，同页两次独立机器，
要求有序完整四阶段和唯一 pass、每轮 machine.closed、最后 browser shutdown，
拒绝 RCU stall/panic、迟到页面错误及关闭失败。复用固定 Playwright/引擎与原
运行器，没有新应用 API，也未选择 GEN CPU 记账、动态加载或 continuation fork。

本地53项合同检查及 Nix/JS 格式通过，覆盖该 corpus 的缺阶段/重复/乱序拒绝、
两轮与迟到错误；控制器替身不是浏览器证据。此前0d02ed7 Node已核实，不代验
本轮较强的计算区间门禁和新源码组合。四路公开任务均各派发一次：

| 位宽 | 引擎 | 任务 |
|---|---|---|
| wasm32 | Chromium | [41581546885](https://github.com/HighCWu/distro/actions/runs/41581546885) |
| wasm32 | Firefox | [41581553944](https://github.com/HighCWu/distro/actions/runs/41581553944) |
| wasm64 | Chromium | [41581561393](https://github.com/HighCWu/distro/actions/runs/41581561393) |
| wasm64 | Firefox | [41581566942](https://github.com/HighCWu/distro/actions/runs/41581566942) |

目前实际目标轮次和关闭仍待核实，不据接线或工作流状态宣称浏览器能力通过。
Node GEN 六阶段与普通四阶段聚合41580416330仍独立异步验收，不取消慢任务。

b6b9911 的四路现已读取实际日志并逐项核实：各两轮完整四阶段、每轮唯一pass、
两个 machine shutdown 及最终 browser shutdown。实际 Heavy 日志字节数依次为
wasm32 Chromium 5,410,121、Firefox 5,409,686，wasm64 Chromium 2,146,921、
Firefox 2,146,481。引擎为 Chromium149.0.7827.55、Firefox151.0，双CPU。
接受该独立配置的双位宽、双浏览器四阶段范围；后继 handler 嵌套第五阶段不在
这个结果内，也不扩大为未插桩库循环或默认 SDK。

固定 b7b8b4a 的41580416330也已核实实际15,885,040字节 Heavy 日志，双位宽
普通配置各四阶段、GEN配置各六阶段及每台唯一pass，阶段顺序逐项匹配。固定
运行器未改变，必须等待 machine.closed 且无清理错误，四台机器通过关闭门禁。
接受该版本普通计算区间/循环内ready门禁，以及 GEN 纯循环 ITIMER_VIRTUAL/
PROF、用户CPU累计的双位宽Node范围。GEN仍不默认启用，后继嵌套阶段及宿主
物理CPU精度不在此验收内。

## 处理器纯计算中的嵌套信号检查点

此前 Worker 一概延后 signal_depth 非零的检查点，导致 handler 的纯计算可能
永远等不到另一个未屏蔽信号。Linux已有 signal frame/mask 链和嵌套 syscall
返回工作；不能因此直接开放任意活的内核回调，尤其不能穿过分配器锁路径。

Linux `5ab71f5d7` / distro `9973866` / 集成 `db482fb` 为经过该检查的内核
增加私有固定i32 user_poll_nested_v1=1 能力，不分配syscall号或用户头文件。
Worker 只在实际 signal callback 中允许嵌套，并要求该能力；旧内核继续延后。
另行跟踪 allocator/startup 用户回调深度，这类回调及其中的 handler 仍全部延后，
正常返回和非局部异常都恢复标记。原 pt_regs 保存、通用IRQ返回、用户相位与
IRQ恢复继续使用原路径，不伪造 syscall 或放宽 seccomp。

实际C语料新增第五阶段：SIGALRM handler 用已有 timer_settime 启动 SIGUSR2，
随后在无syscall/读钟的循环等待它；内层处理器必须在这个循环中被调用，外层
返回后删除timer并再次验证普通定时信号。GEN版本对应七阶段。普通Linux API
与 libc 不变，没有新增公共函数或扩大fork/动态模块范围。

466项相关宿主检查及两个TypeScript项目通过，包含旧/错误能力拒绝、普通内核
嵌套延后、实际handler准入、allocator重叠拒绝及非局部退出后的恢复。Clang18/22
双位宽的普通/GEN消费者插桩与SjLj编译/静态分析、入口真实函数体模型通过。
公开预取 [41583244548](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41583244548)
核实前驱归档及新源码hash。新聚合
[41583750935](https://github.com/HighCWu/distro/actions/runs/41583750935) 已派发，
需双位宽普通各五阶段、GEN各七阶段及各机器关闭，尚未计为真实能力通过。
浏览器合同已同步到五阶段，待新Node结果后再定向验收，不沿用旧四阶段结论。

9973866 的41583750935现已完成，实际Heavy日志逐项核实普通双位宽各五阶段、
GEN双位宽各七阶段、各唯一pass，包含嵌套处理器和后续恢复。发布运行器等待
machine.closed，关闭失败非零退出，四个目标均通过关闭门禁。接受Linux5ab71f5d7
对应独立Node范围，不扩大到之后的libc插桩或新内核。

同语料的后继74cb9fe已派发四路浏览器，分别为
[wasm32 Chromium 41587774709](https://github.com/HighCWu/distro/actions/runs/41587774709)、
[wasm32 Firefox 41587782692](https://github.com/HighCWu/distro/actions/runs/41587782692)、
[wasm64 Chromium 41587791495](https://github.com/HighCWu/distro/actions/runs/41587791495)、
[wasm64 Firefox 41587800703](https://github.com/HighCWu/distro/actions/runs/41587800703)。
均需同页两轮完整五阶段及机器/浏览器关闭；未沿用旧四阶段浏览器结论。

上述四路74cb9fe浏览器现已全部完成并核实实际日志：Chromium149.0.7827.55、
Firefox151.0各双位宽、各两轮五阶段，含嵌套handler阶段，每轮唯一pass、机器
关闭及最终浏览器关闭标记均齐全。接受该固定Linux5ab71f5d7组合的浏览器范围，
不推广到GEN浏览器、新内核或libc插桩配置。

## 库内检查点的线程所有权门控原型

已有应用插桩不能覆盖未插桩 libc 的长循环。直接重编译 libc 还不安全：早期
clone 入口暂时沿用父实例的 native TLS，base 非零不等于子线程已经就绪。
distro `127d3a8` / 集成 `36b4654` 增加默认不选用的编译组件分支，用私有
可变、指针宽度 global 表达当前线程身份；零值在访问 TLS 内容前延后检查点。
native TLS 内的所有者字只认领一次，且必须在 clone 发布共享块前完成；临时
指向父 TLS 的子实例身份不同，因而不读写父线程预算。避免每次 hook 都重写
所有者字，使其不会与早期子实例的读取形成并发写入。

Clang18/22 的 wasm32/64 实际模块和静态分析通过，核对启动前不写 TLS、继承
父块时不改父预算、独立新 TLS 的预算、暂停后恢复，以及 global 位宽/可变性
错误被引擎拒绝。现有 ABI1 插桩纯循环、异常恢复和反向控制也重新通过。根 CI
加入小产物检查；Clang18 采用文本汇编后单独组装，避开其内联汇编导入名生命期
问题，发布工具链的 LLVM22 已有字符串所有权处理，不重复修改 LLVM。

这尚未接入 Worker、SDK 或 libc 构建，现有 loader 明确拒绝 ABI2。下一步必须
把宿主线程就绪发布、独立 libc 插桩配置和真实 pthread/库内循环验收配套接通。
不将组件模型当作 Linux 并行启动、库内信号或新增 syscall 已经通过；默认配置、
musl 公共 API 和 fork 支持范围不变。

本轮检查另发现根仓库 db482fb 的41583668933失败于宿主 madvise 包装检查：
旧 fixture 仍要求 MADV_FREE 被拒绝，和已接通并验收的 discard 能力冲突。
集成 `28845bb` 改以仍不支持的 MADV_REMOVE 检查拒绝，并显式核对 MADV_FREE
的 advice 原值、长度取整及后端错误/成功传递。GCC/Clang十项实际包装检查通过，
不修改内核或放宽验收条件；新的根 CI 仍需结果。
后续28845bb的41585921563继续定位到allocator fixture的同类旧断言。1045200
同步该fixture，改用MADV_REMOVE验证拒绝，新增MADV_FREE内容清空及地址预约
仍存在的断言。GCC/Clang六项检查通过，包含ASan/UBSan、实际分配器分析和原
拷贝丢失反向控制；未修改已验收实现。新的根CI仍为异步验收。
另据c95758c的41587156253实际日志，terminal检查仍按两种可选补丁配置匹配
recipe，未识别新增的第三种独立poll配置。bf7fdbf同步该检查，同时要求poll
默认关闭、禁止与fork/dynamic组合，并保留原有错误配置反向控制。Clang18/22
双位宽前端/分析及GCC/Clang原始daemon/forkpty/login_tty宿主参考通过。

## 独立 libc 插桩配置与真实库循环候选

distro `74cb9fe` / 集成 `c95758c` 配套接通原型：每实例私有 TP global 从零
开始，只在标准 set_thread_area、clone 的 gettid 返回边界或已有 TP 读取后
采用内核实际值，不采用传入参数。其他 exec 启动 syscall 不发布旧映像遗留 TP。
ABI2 同时要求 checkpoint 和 thread_pointer，拒绝与 ABI1、动态加载或 fork
continuation 混合；实例化核对导出版本、global 位宽和可变性。

`sdk-cooperative-poll-libc` / `sdk-cooperative-poll-libc-wasm64` 使用相同固定
musl 源码重建，不增加函数/声明。clone 与 pthread/C11 过渡单元不插桩，避免
native TLS 初始化前触碰继承的父块及其生命周期；其它 libc C 单元使用覆盖率
检查点。分离线程自身回收的独立 Wasm 补丁在 free 发布栈/TLS 前清空 native
TLS base，保留 Linux/musl TP。宿主 allocator/startup 回调将 global 暂置零，
阻止检查点读取 TLS，嵌套和非局部退出后恢复，内部 TP 读取不能重新启用它。
原 SDK、应用插桩配置、C++/编译器运行库及支持的 fork 范围保持不变。

真实消费者保留普通五阶段，并加第六阶段：不插桩的调用循环经 volatile 函数
指针调用实际 memchr，在库搜索期间收到 SIGALRM，随后普通计算信号继续正常。
Clang18/22 双位宽实际 IR 确认调用循环/启动单元没有检查点、memchr 有检查点，
回收代码在 free 前清除 native TLS；消费者插桩/SjLj 编译与静态分析通过。
440项宿主检查、两个 TypeScript 项目和原 ABI1/所有权组件回归通过。

[41587166248](https://github.com/HighCWu/distro/actions/runs/41587166248) 已异步
派发双位宽六阶段及机器关闭验收，未计为真实库内信号支持通过。尚不推定所有
第三方库、原始自定义 clone、动态模块、C++ 异常或浏览器组合已经覆盖。

74cb9fe的41587166248随后已完成，实际Heavy日志逐项确认双位宽各六阶段及
唯一pass，包含真正libc搜索循环内的timer交付、嵌套handler和后续恢复。运行器
与该固定发布版一致，等待machine.closed且收尾失败非零退出；两路通过关闭门禁。
接受Linux5ab71f5d7/muslce9c4c50的此Node独立配置，不将其视为后继musl或浏览器
libc插桩组合已经通过。

## exec 提交时清理架构线程指针

Linux `94d6741a0` / distro `58eee0d` / 集成 `7f08c44` 修复实际架构缺口：
Wasm 的 flush_thread 原为空，标准 begin_new_exec 提交新映像后仍留下旧 TP。
现在只在通用 exec 提交点清零当前线程的 tp_value，保留其它线程/架构状态。
编译模块、复制参数失败等提交前错误仍返回原映像，不提前清空其 TLS。
参考同一固定官方源码的 fs/exec.c 调用点及 arm64 TLS flush 路径；没有引入
MMU、额外 syscall 号或新的 musl 函数。内核修改沿用GPL，消费者/构建/检查MIT。

新增普通SDK消费者验证ENOENT、有效Wasm头但无内存导入的准备失败保持原TP
和TLS；随后posix_spawn执行不链接CRT/libc的观察程序，在任何TLS初始化前
通过已有get_thread_area执行导入观察零TP，非零则exit_group(31)。父线程TP和
native TLS保持不变；普通libc子程序须初始化自己的TLS，之后再次原始入口仍成功。
不能只观察main中的TLS，因为libc会覆盖原指针而掩盖内核问题。

Clang18/22双位宽运行实际flush函数、当前线程隔离和重复清理；删除重置的
反向控制失败。真实libc-free模块的零/继承TP输入分别正确退出和拒绝，父程序
使用固定musl头文件编译/SjLj和静态分析通过。此处是组件证据，不是Linux exec
已经验收。公开预取41588100308曾因Git归档实验尚未允许processor.h而退出64；
6e2eb57补齐精确路径后，
[41588397321](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41588397321)
重新核实父版本hash和新源码hash，未跳过基线等价校验。

[41588670745](https://github.com/HighCWu/distro/actions/runs/41588670745) 已异步
派发双位宽各三个新阶段及机器关闭，并包含同一新内核的普通检查点与fork/exec-fd
回归。未核实实际目标日志前不接受新的内核组合；默认libc及MMU配置不变。

58eee0d的41588670745现已完成。实际14,251,453字节Heavy日志逐项确认双位宽
exec-thread-state各三阶段、普通检查点各五阶段、fork/exec-fd各八阶段及各唯一
pass。三个语料每个位宽均通过发布运行器等待machine.closed的关闭门禁，运行器
与固定58eee0d一致，收尾失败非零退出。接受Linux94d6741a0/muslce9c4c50对应
Node组合，不由此接受后继muslf09c21d9的timer路径或浏览器新内核组合。

## 原有 SIGEV_THREAD worker 的 Wasm 收尾与 TLS 重置

musl `f09c21d9` / distro `bbdd8f3` / 集成 `1af6a1f` 修复两处实际调用路径
缺口，没有添加公共函数、头文件API或Linux扩展。原timer_create.c的SIGEV_THREAD
分支在通知回调返回后，经cleanup_fromsig无条件longjmp回start的setjmp循环，
但arch.mak未给这个原有编译单元启用Wasm SjLj，因而会走未转换longjmp的trap。
现在把其.o/.lo纳入已有SjLj列表，保留原逻辑和LLVM执行机制。

另一个缺口在原__reset_tls：它只重置ELF DTV模块，Wasm linker独立native TLS
没有重新初始化。现在在Wasm分支调用已有__wasm_init_tls，恢复同一已分配块的
初值，使同一逻辑通知worker的后续回调能得到新TLS。增加的只是既有内部helper
声明和架构路径，非Wasm函数体及公共接口保持不变。

Clang22双位宽真实timer worker、cleanup push/pop、setjmp/longjmp helper和
TLS-reset函数体在小模块中执行三次通知，检查callback正常返回、标记清理及
每次native TLS初值。递送/线程状态和分配器为测试模型，不冒充Linux调度。
去掉SjLj必然trap，去掉native TLS重置则后续初值断言失败；模块拒绝Emscripten
JS异常shim。普通消费者前端/SjLj编译、实际函数与消费者静态分析通过。公开预取
[41590127079](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41590127079)
核实固定musl源码hash，两种既有独立profile补丁dry-run通过。

新消费者使用已有timer_create/settime/delete、pthread、TSD和semaphore API，
验证坏clock创建后的helper回滚，三次one-shot通知中的正常返回/pthread_exit/
正常返回、每次TLS和TSD析构、删除后的proc task列表收敛，以及后续定时器恢复。
不依赖需CHECKPOINT_RESTORE的/proc/self/timers，不凭线程数宣称全部timer资源
无泄漏。使用普通SDK和独立libc插桩SDK各跑双位宽，并带普通检查点回归。

[41590872805](https://github.com/HighCWu/distro/actions/runs/41590872805) 已异步
派发上述真实三阶段及各机器关闭；仍待目标日志，不把组件模型当作kernel timer
递送、pthread_exit回调或新musl组合已通过。内核继续94d6741a0，MMU和fork范围不变。

bbdd8f3的41590872805实际失败于首个坏clock断言，报告errno=EAGAIN，尚未进入
通知回调阶段。musl651ebf65 / distro2eede83 / 集成0858811修复Wasm调用路径的
错误保留：保留原始SYS_timer_create负返回值，待helper semaphore握手结束后
才经既有__syscall_ret转换errno。组件真实create函数复现了握手sem_wait先失败
一次而把错误覆盖为EAGAIN的路径；恢复旧返回方式则无法保留原kernel EINVAL。
这与目标现象相符，但不只凭该errno推定helper创建一定成功。因此目标加入透明
pthread_create link wrapper记录实际返回值，继续严格要求EINVAL，不放宽预期。
非Wasm路径与公共API不变，公开预取41595369149核实源码hash；Clang22双位宽
实际函数/错误转换及三个反向控制通过。
[41596167405](https://github.com/HighCWu/distro/actions/runs/41596167405) 定向复验中，
仍须实际通知/TSD/TLS/退出和关闭证据，不将组件错误复现当作原CI已修复通过。

## exec 提交前校验宿主供给的线程指针 global

distro `a0dcd2b` / 集成 `1b9ba2b` 修复实际执行准入缺口：此前只核对导入名和
kind，合法Wasm模块仍可请求immutable、相反位宽或浮点thread_pointer，而宿主
实际供给mutable且匹配进程地址宽度的global。这样可能在Linux提交exec后才出现
LinkError，无法保留原程序。现在复用已有有界导入段读取器收集global类型，在
pending memory分配和exec提交前拒绝不兼容global，按原通道返回ENOEXEC。
不实例化生产模块做探测，也不套用动态链接的numeric函数类型限制。

新增四种引擎合法映像，导入名/执行ABI marker/入口/shared memory完全相同，仅
global契约不同。Node双位宽真实模块验证类型匹配者可通过标准exit_group退出，
其余三种在旧名称检查下仍被接纳且实际实例化会LinkError，新检查提前拒绝。
440项内核宿主检查、源码/测试TypeScript、Clang18/22双位宽消费者前端/SjLj编译
和静态分析通过；根CI接入这些真实映像检查，未更改kernel或musl源码/API。

普通SDK消费者重复execve不兼容映像，要求ENOEXEC且原实际TP、native TLS、
CLOEXEC fd与offset保留；正确映像必须实际spawn/exit/wait，随后错误与成功路径
继续恢复。[41592334251](https://github.com/HighCWu/distro/actions/runs/41592334251)
已异步派发双位宽各三阶段和机器关闭，尚不接受目标运行已通过。本轮只修复这项
global契约，不宣称所有import/function签名或其它执行ABI错误已得到完整校验。

a0dcd2b的41592334251现已成功，实际10,310,673字节Heavy日志逐项确认双位宽
各三阶段及各唯一pass，包括三种不兼容global的ENOEXEC、原TP/TLS/CLOEXEC fd
与offset保留、正确映像实际退出及后续恢复。发布runner与该固定版一致，等待
machine.closed且关闭失败使目标非零退出，两路通过收尾门禁。接受该Node范围，
不据此推定后继musl定时路径或浏览器执行准入已通过。

## 内核独立 robust-list 死亡清理候选

distro2039315 / 集成33eadd3新增独立普通SDK消费者，明确区分现有pthread
退出测试的musl用户态清理和Linux内核独立robust-list路径。使用已有公共clone
callback、CLONE_VM|SIGCHLD和独立C栈，在父进程创建waiter pthread前创建owner；
owner只使用原始syscall，不经过pthread退出/robust用户态清理，不访问native TLS
或libc allocator/errno。未修改内核/musl实现或扩大continuation fork支持。

- 查询真实set/get_robust_list注册身份，原始SYS_exit后要求TID清零且保留
  FUTEX_OWNER_DIED/WAITERS；缺少注册的反向控制必须明确失败。
- 用proc标准task状态确认waiter已经在futex中睡眠后，SIGKILL owner；要求内核
  死亡清理唤醒它，不能仅改word或靠超时通过。wasm32显式选SYS_futex_time64，
  两位宽都传精确64位sec/nsec数组，避免偶然匹配旧time32布局。
- 验证list_op_pending、坏next链接、无效注册head及后续有效退出。无效head不得
  凭空把无注册项变成OWNER_DIED；所有案例只回收一次，释放stack/pipe，无残留waiter。

GCC/Clang真实原生Linux三阶段与跳过注册反向控制通过。Clang18/22双位宽使用
当前musl公共头和固定Linux futex UAPI声明编译/分析通过；轻量前端仅模拟UAPI
scalar/compiler包含文件，目标使用完整安装头。根CI接入此参考和前端，不将它们
当作Wasm kernel退出清理证据。
[41597155614](https://github.com/HighCWu/distro/actions/runs/41597155614) 已异步派发
双位宽三阶段及机器关闭。此项仍是候选，不宣称独立mm的共享映射、PI、任意链表
损坏、所有竞争交错或应用数据自动恢复已经支持。

## 启动修复后的合并 syscall 回归结果

固定 `6b1777e` 的 [41572697826](https://github.com/HighCWu/distro/actions/runs/41572697826)
已成功，实际读取23,174,279字节 Heavy 日志。两种位宽分别完成 brk 三阶段
（标准 query/growth 与 errno、实时 AS/DATA 限额与真实 malloc 拒绝、共享分配器
线程/8KiB TLS/mmap 恢复），madvise 四阶段（含 FREE 后写入与保留预约），
Landlock 三阶段及各唯一 pass。动态加载十阶段包括字节文件名/BOM/Unicode，
动态符号版本三阶段、文件 mmap 三阶段、fork 主体/exec/拒绝恢复也有对应实际输出。

已核对该源码的 run-test.js / shutdown.js：作业成功必须在 pass 后等待
machine.closed、处理迟到错误且无清理失败；这些文件与当前发布版本一致。
据此接受上述固定组合的双位宽 Node 范围，确认 FDT/initrd 启动修复可运行，
不推定新增 user_poll_v1、USER_NS、GNU split 或新浏览器组合已经验收。

GNU split 的同源码 [41572698904](https://github.com/HighCWu/distro/actions/runs/41572698904)
失败，读取14,323,543字节实际日志：gnulib 编译缺少 mbszero/c32tolower 等生成
头文件声明，尚未进入应用。独立配方从干净目录直接构建 src/split，跳过了
Automake 对 all/check/install 的 BUILT_SOURCES 准备，见
[官方说明](https://www.gnu.org/s/automake/manual/html_node/Built-Sources-Example.html)。
distro `b7c5028` / 集成 `00fbe73` 先通过补充 make 目标构建原始 BUILT_SOURCES，
再构建单个程序；不改 split.c、gnulib 实现或 musl 公共 API。格式及已有宿主
工作负载合同通过，定向 [41577019058](https://github.com/HighCWu/distro/actions/runs/41577019058)
正在复验，仍须确认实际 Wasm 构建、四阶段和关闭。

b7c5028 的41577019058也已失败，但失败点不同。实际读取12,023,398字节
Heavy 日志，确认 config.status 创建 lib/config.h，编译、最终变换和 wasm32
共享内存/4GiB声明边界检查已通过；安装阶段归档错误地引用根目录 config.h，
因此没有进入运行。distro `6a69459` / 集成 `ab88cd2` 只修正构建材料复制路径
为 lib/config.h，保留输出材料中的 config.h 文件名，源码指纹和应用实现不变。
Nix 格式及静态 review 通过，新的双位宽目标
[41580829257](https://github.com/HighCWu/distro/actions/runs/41580829257) 继续定向
复验，不重发原任务，完整四阶段和关闭仍待核实。

## 静态 review 与异步验收原则

标准dlfcn接线9cbe7d0的文件操作继续使用Linux syscall，未新增公共libc函数。
内核356fb863f补充执行层私有文件引用：Wasm代码没有原生可执行VMA，因此读取
快照后仍须持有真实file引用，避免inode复用。引用归mm所有，与应用fd表分开，
由VFS getattr核对身份，失败释放，exec/退出统一清理；没有新增应用syscall。
独立动态SDK及Worker均已接线，双位宽Node的四阶段和关闭仍待实际日志，见
[动态装载记录](elf-dynamic-linking.md#标准-dlfcn-调用路径与独立-sdk-接线)。

9d15937 / 集成d23e13f修复真实库搜索错误：已打开的损坏文件、读取/分配错误
不再被后续目录的同名库掩盖，只有特定open失败继续搜索，清理后可恢复。
1ec430b / 集成1087117依据实际构建失败补齐共享链接位宽和动态未解析符号
策略；独立候选驱动同步修正。新增语料仍使用既有dlfcn和Linux文件操作，
不补造libc函数。双位宽Node和驱动最终版本已异步派发，尚未验收，详见
[搜索与链接修正](elf-dynamic-linking.md#搜索优先级与共享链接参数修正)。

3c3246e / 集成65f4a60进一步允许真实循环共享库依赖：先建立全部实例和
重定位，再按去重DFS后序执行构造函数；重新打开对等库复用状态。普通C
两库产物的双位宽引擎/进程模型和旧行为反向控制通过，Linux镜像增加真实
循环装载阶段，双位宽Node异步验收中，尚未接受真实运行或关闭。该增量没有
新增syscall或libc函数，也不扩大线程/fork边界，详见
[循环图接线](elf-dynamic-linking.md#循环共享库依赖接入)。

固定1ec430b的Node wasm32 41530620340、wasm64 41530620735现已读取实际
四阶段、唯一pass及发布runner关闭门禁，接受标准dlfcn接线的对应双位宽
Node范围。后续de74734 / 集成0164c9d修复Wasm start回调dlsym主程序新
函数时覆盖模块表项的缺陷，双位宽轻量真实Wasm模型和旧行为反向控制通过，
后继组合目标仍异步验收，不沿用旧版结论。见
[已核实结果与表项隔离](elf-dynamic-linking.md#标准dlfcn的双位宽node已核实结果)。

37c5ed4 / 集成7c6f72a将同一Linux动态加载镜像接到四路浏览器：wasm32/64
各Chromium/Firefox，单CPU、同页面两次独立机器，每轮严格五阶段及等待关闭，
最后核对浏览器关闭与迟到异常。当前计划及Heavy均已开始，真实结果待核实；
本地控制器替身通过不作为浏览器支持证明。见
[浏览器镜像接线](elf-dynamic-linking.md#浏览器进程镜像接线)。

8c2a568 / 集成d08d209接通C/SIMD共享库的数值函数ABI：v128签名不再被
直接拒绝，循环前向调用使用精确类型的Wasm跳板，避免JS无法传递SIMD值的
真实错误。提供者就绪即绑定，规范函数指针仍指向提供者。轻量双位宽循环C
产物和table32/table64引擎fixture通过，旧JS转发反向控制失败；新六阶段
Node及四路两轮浏览器异步验收中。此前3c3246e的wasm64 Node五阶段、唯一
pass及关闭已核实，只接受对应循环装载范围，不扩大为SIMD或浏览器。见
[数值函数前向调用](elf-dynamic-linking.md#数值及simd函数的原生前向调用)。

浏览器37c5ed4四路实际日志均在首次main_add检查失败。先以e0ccd29修正
消费dlerror后丢失原因的诊断，再在本机已有Chrome的小型API对照中复现生产
加载器的shared解码异常。4d13d79改为自有字节快照，当前文档整理版05e9dbb
/ 集成8484b31已派发四路针对性复验。真实Wasm32/64共享内存及函数表的
生产类对照、Node模型浏览器限制及旧行为反向控制均通过；完整六阶段、两轮
和关闭仍待CI，不以本地小型验证代替。见
[浏览器字符串修复](elf-dynamic-linking.md#浏览器共享字符串解码修复)。

固定05e9dbb的四路浏览器41537955279/41537955806/41537956051/41537955781
现已逐项核实六阶段各两轮、每轮唯一pass及机器关闭、最终浏览器关闭。接受该
独立动态SDK的单CPU wasm32/64 Chromium/Firefox范围，不扩大为ELF、线程或
动态fork；见[已核实范围](elf-dynamic-linking.md#浏览器动态加载已核实范围)。

## 普通共享编译参数的真实进程接线

distro13b54fe / 集成08fa383把已核实的Linux共享Clang驱动接到独立双位宽
动态加载镜像，共享库不再手写wasm-ld命令，应用C源码不改。复用既有六阶段
语料和关闭门禁，41542937012/41542944612异步验收，默认SDK及musl不变。
这推进构建兼容性，不记为新增syscall，见
[驱动集成记录](elf-dynamic-linking.md#标准共享编译驱动接入真实进程候选)。

符号版本SDK任务41529152599的实际失败在运行包打包前：许可证目录保留构建机
store符号链接。446dbef / 集成df469d7物化原通知字节并核验其SHA256SUMS，
不放宽包边界检查；定向复验已派发，程序语义及关闭尚待核实。这是交付修复，
不计为新增syscall，见[运行包修复](elf-dynamic-linking.md#符号版本消费者的独立运行包修复)。

## 根仓库既有终端检查适配互斥配置

根仓库41541804023及41542928714失败，已读取后者125611306738的实际失败
步骤：check_terminal_process.py仍断言旧的单一fork补丁属性；musl配方已改为
fork/dynamic互斥的两个可选补丁，旧文本匹配在前端及宿主工作负载运行前中止。
这不是新的Linux终端语义失败，也不影响已单独核实的BPF重型结果。

主仓库e6bef27更新检查以识别实际互斥配置，保留默认fork关闭、条件宏及条件补丁
约束。格式变化正向控制通过；默认开启、无条件补丁及删除互斥条件均必须拒绝。
本地Clang18双位宽的默认声明拒绝/可选声明及原始函数体前端和静态分析通过，
GCC/Clang实际musl daemon/forkpty/login_tty函数体的宿主终端参考通过。轻量根
仓库CI由新源码触发，仍待云端结果，不以这些宿主检查替代Wasm终端验收。

根仓库终端检查修复e6bef27的41544362361随后已完成，完整轻量CI通过；没有
为旧版失败任务重复派发，也不将此结果解释为新的Wasm终端运行验收。

## 共享库的首线程本地 TLS

distro eeebcd0 / 集成92cff8c修复动态加载器对已定义hidden/local TLS的一律
拒绝，并补上实际遗漏的TLS指针重定位，后者曾在真实C产物中得到零指针。
只有禁止Worker创建的独立动态模式启用；全部GOT及TLS重定位先于构造函数，
复用不重置状态。Clang/LLD18及22的双位宽生产类模型和反向控制通过，LLVM22
的wasm64包含table64；七阶段真实Linux Node/四路浏览器异步验收中。
这改善普通程序构建/运行兼容性，不计为新增syscall；未改musl或内核，仍不支持
外部TLS绑定及C++异常。见[TLS接线记录](elf-dynamic-linking.md#首个线程的库内-tls-与指针重定位)。

eeebcd0的wasm32/64 Node 41546646208/41546653644均已核实七阶段、各唯一pass
及机器关闭，接受该源码首线程库内TLS范围，不扩大为浏览器或后继构造函数重入。

## 构造函数中的已有 dlfcn 调用

distro35ea6c0 / 集成b34347f把全部重定位后的图先发布，再执行构造函数，
允许构造函数通过标准dlopen装载新库或重新打开父库；各图共享模块初始化状态，
保证一次执行及失败后不可重试。I/O/分配器/start重入仍拒绝。真实C双位宽生产
模型及旧busy控制、共享依赖/失败状态检查和静态分析通过；Node八阶段已派发，
真实Linux和浏览器验收仍待核实。没有新增syscall或libc函数，见
[构造函数接线](elf-dynamic-linking.md#构造函数中的标准-dlopen)。

## 通用 Landlock syscall 与文件规则接线

独立distroaf63fe8 / 集成5934ac3另增加跨共享库版本绑定实验：复用原始
提供者，检查强版本缺失拒绝、跨库旧/默认签名、long宽度、GOT数据及函数指针、
普通dlsym默认定义和失败恢复。没有改Linux/musl或新增syscall，真实Wasm
链接/执行仍待验收，不能用已有静态结果代替，见
[独立动态绑定实验](elf-dynamic-linking.md#跨共享库的符号版本绑定实验)。

后续distro3dc5c82 / 集成23a091f修复已有dlopen的非UTF-8路径和前导BOM，
保留Linux文件名字节、link_map名称及严格Wasm元数据边界。新十阶段组合待验收，
不计为新增syscall。此前1894258六路九阶段现已全部核实，浏览器各两轮及机器/
浏览器关闭完整通过；不扩大为默认编译器/内核新组合或Landlock通过，见
[字节路径与对应验收](elf-dynamic-linking.md#linux-文件名字节与前导-bom)。

Linux45a10e599 / distro5eb9dbe / 集成9a460d4在三套Wasm defconfig启用
SECURITY和SECURITY_LANDLOCK，复用Linux已有的landlock_create_ruleset、
landlock_add_rule、landlock_restrict_self及凭据/文件LSM钩子。它们是官方
可选功能，不宣称这些选项default y；未修改通用安全实现、MMU或应用API。
构建门禁要求resolved SECURITY/SECURITY_NETWORK/SECURITY_PATH/
SECURITY_LANDLOCK=y及最终LSM列表确实包含landlock，未覆盖官方LSM默认列表。

独立MIT消费者使用普通SDK、已有libc声明及标准syscall编号；所有可变参数均按
机器字传递，不新增musl函数或头文件。父端以posix_spawn启动独立消费者，
不用可选fork SDK，也不扩大多线程fork范围。规定三个完整阶段：

- 查询标准ABI；空规则集、坏用户指针和无效规则/限制fd按Linux返回错误，
  随后仍可创建规则集。目录规则只授予READ_FILE/READ_DIR，处理WRITE_FILE
  以确保写打开被拒绝；未列目录的读/写及目录读取返回EACCES，允许目录内
  指向拒绝目录的symlink也不能绕过。规则目录fd和ruleset fd关闭后策略保留，
  之前打开的拒绝目录文件fd仍可读取，符合既有fd不被追溯撤销的语义。
- 再启动独立消费者，设置no_new_privs并限制自身，使用普通execve切换到同一
  静态程序验证入口后重复权限检查。显式授予程序文件READ_FILE；EXECUTE未
  被本规则集处理，不把该场景描述为执行权限控制的验收。
- 两个消费者各退出37且只回收一次；父进程仍可读写两目录的文件，最后删除
  symlink、文件、目录，全部成功后发布第三阶段和唯一pass。

GCC/Clang静态宿主程序已实际通过完整三阶段及symlink/exec检查；Clang18/22
的wasm32/64前端与静态分析通过，使用当前musl头文件和原始Linux Landlock
UAPI，轻量分析仅为linux/types.h提供固定宽度标量定义。它不代替最终Linux
headers_install、链接、Wasm内核运行或关闭。review核对未依赖宿主路径访问、
规则生存期、关闭的fd、exec静态程序读取、长整型参数及父子策略隔离。

[公开预取41554571667](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41554571667)
的实际日志先核实c7b4f97ef的既有哈希，再得到45a10e599的
`sha256-zWc7zqO5BohnH61GHYRK8og0J1W6dSsZ2xeNwt/oVWI=`；只有三套
defconfig改变，符合已有Git归档允许范围。双位宽Node检查各派发一次：
wasm32为41555124028，wasm64为41555131902，均固定5eb9dbe；目标
三个阶段、唯一pass及runner等待machine.closed的关闭门禁仍待核实。
这两路后来均失败；32位实际日志确认是前一轮普通SDK接线的statix写法门禁，
未进入Landlock程序。9250e0c / 集成90888ba修正inherit (self) sdk后，
各派发一次41555487998（32位）、41555494487（64位），仍待真实目标结果。
当前只验收上述基础文件规则范围，不宣称Landlock所有网络、线程同步、日志和
作用域特性均已在Wasm验证，也不把宿主通过算作浏览器通过。后续浏览器需使用
同一镜像独立核对阶段及两轮关闭。语义依据
[官方Landlock文档](https://docs.kernel.org/userspace-api/landlock.html)，能力范围
仍由固定内核源码及实际目标证据决定。

## 既有 dlinfo 的真实句柄与对象范围

后续591d8bf / 集成9c41615已将验证过的LLVM9035266接入普通SDK，移除
符号版本检查的独立编译器覆盖，运行库按相同源码pin重建。新默认组合的符号
版本/C++、动态加载和fork回归仍待验收，不将此前独立配置通过冒充默认通过。
这是应用构建兼容性增量，没有新增libc函数或syscall，见
[普通SDK接线](elf-dynamic-linking.md#普通-sdk-启用已有符号版本绑定)。

此前独立符号版本SDK的41543946241已核实双位宽各六个C++阶段、两个符号版本
阶段及唯一pass、机器关闭门禁。标准共享驱动41542944612已核实wasm64六阶段
及关闭，32位41542937012仍运行。它们是编译/加载兼容性进展，不计为新syscall，
不等于ELF入口或默认编译器切换，见
[实际目标结果](elf-dynamic-linking.md#符号版本候选与标准共享驱动的目标结果)。

distro1894258 / 集成59b1ff5修复musl原始dlinfo将小整数句柄误当link_map
指针返回的问题；加载器改为真实用户内存对象，保留完整依赖链表和稳定别名，
依赖句柄只搜索/初始化自身子图。直接复用原始musl函数体，没有增加或修改公共
函数及头文件，也不计为新增syscall。Wasm没有ELF动态节，l_ld为NULL；私有ABI
能力导入拒绝旧宿主误接。双位宽Clang真实产物、原始C函数体及静态分析通过，
九阶段Node/四路浏览器已派发，真实目标结果仍待核实，见
[句柄修复](elf-dynamic-linking.md#原始-musl-dlinfo-与实际对象句柄)。

此前eeebcd0四路浏览器七阶段各两轮及机器/浏览器关闭现已全核实；35ea6c0
的双位宽Node八阶段、各唯一pass及关闭也已核实。不将旧源码通过泛化到新的
句柄组合，见[对应验收](elf-dynamic-linking.md#已核实的七阶段浏览器与八阶段-node)。

## 单线程 fork 与应用计算期信号的组合候选

distro `ee278a8` / 集成 `d4db62b` 提供独立的
`sdk-fork-cooperative-poll[-wasm64]`，让普通静态 C 程序同时使用已有 fork 和
应用计算检查点。没有增加应用 API、musl 公共函数或内核 syscall；这一增量补齐
两个执行配置之间的兼容缺口，不计为新增 syscall 数量。默认 SDK 和原独立配置
保持原有选择。

新的私有执行标记只允许 poll ABI 1 与 continuation fork 组合。运行库在
Asyncify 展开、快照描述符仍被持有和恢复期间延后检查点，空闲时才进入既有
Linux 信号交付路径，并记录活的内核调用深度。信号回调中的 fork 继续拒绝，
嵌套信号和 allocator 回调仍受既有门禁约束。完整链接产物统一经过 Asyncify，
支持对象和 libc 不被这个配置插桩；没有启用 libc poll ABI 2、动态加载、
C++ EH/SjLj 组合或多线程 fork。

轻量验证包括 442 项内核运行库测试、源码及测试 TypeScript 项目、真实双位宽
支持对象链接/标记、Clang18/22 双位宽消费者前端与静态分析。最初新测试将
i64 模式下固定 i32 checkpoint 返回误写为 bigint，已修正测试期望；实际指针
参数仍按机器字位宽传递。模型检查不能证明真实 Asyncify 或 Linux 运行通过。
`fork-poll-check-both` 的真实目标要求两位宽各依次完成 fork 前计时信号、父子
孙进程纯计算及私有 TLS/数据/重复回收、回调 fork 拒绝后正常恢复三阶段，
各唯一 pass 和机器关闭；公开 CI
[41599761764](https://github.com/HighCWu/distro/actions/runs/41599761764)
异步验收，尚未接受目标通过。

## 定时通知错误修复的目标验收

[41596167405](https://github.com/HighCWu/distro/actions/runs/41596167405)
固定 distro `2eede8325cadbb3e264b5af7c588af2050f4f7fc`，实际读取
14,463,989 字节 Heavy 日志。wasm32/64 的普通与独立 libc 插桩配置各精确完成
三个阶段和唯一 pass：错误时钟的 helper/内核计时器回滚、正常返回及 pthread_exit
回调的全新 native TLS/TSD、删除后的线程收敛和后续创建恢复。另有普通计算
检查点双位宽各五阶段和唯一 pass。复核该源码 runner 等待 machine.closed，
关闭错误会使检查失败；Heavy 和工作流均成功。

接受固定 Linux `94d6741a0` / musl `651ebf65` 的这一 Node 范围，确认原错误
保留及原有通知调用路径可用；不将其泛化为浏览器、fork/poll 组合或所有线程
计时场景。

内核独立 robust-list 的 `41597155614` 随后失败。实际 Heavy 日志确认 wasm32
原始 syscall 退出清理、SIGKILL 唤醒已睡眠 futex 等待者两个阶段通过，后续在
查询注册头处失败，未得到第三阶段、最终 pass 或双位宽验收。审查固定源码发现
测试用 `-8` 表示坏地址，而当前 Linux 的 get_robust_list 将 ERR_PTR 范围内的
注册头值按错误返回；本地旧内核参考没有检出这一差异。主仓库 CI `41596925169`
的原生参考也在同样的前两阶段后失败，确认问题不限于 Wasm 运行目标。

distro `04951a3` / 集成 `28deb16` 改用错误编码范围外的 `-8192`，仍是本目标
线性内存之外的地址，并为查询失败加入 mode、原始返回值和长度诊断。没有修改
Linux 的错误判定或放松 owner-death、真实唤醒和资源回收要求。GCC/Clang 原生
正反控制和 Clang18/22 双位宽前端/分析再次通过；公开目标
[41600067842](https://github.com/HighCWu/distro/actions/runs/41600067842)
定向复验，仍待实际三阶段与关闭证据。

## exec 提交前校验宿主函数导入类型

distro `a471b65` / 集成 `242a070` 修复函数导入的另一条 exec 失败路径：
JS 函数作为 Wasm 导入时，不会要求模块声明的函数类型与宿主实际执行契约一致。
因此名称、导入种类和内存位宽均合法的映像，仍可能将 syscall 声明为错误的
参数位宽、返回类型或数量，替换旧映像后才在调用边界出错。

现在在 pending memory 分配和 Linux exec 提交前，把原始类型段逐字保留到仅含
函数导入的临时模块，以具有固定类型的惰性 Wasm 函数进行链接。参数/结果类型
由引擎核对，覆盖当前所有准许的宿主函数导入，包括机器字 syscall/指针和固定
i32 控制结果；不复制用户代码、启动段、内存或数据，不在准入时执行新程序。
原类型段中的递归/引用类型仍交由引擎处理，不套用动态加载配置的数值类型限制。
不兼容则按既有加载失败路径返回 ENOEXEC，不增加 libc API 或 syscall 编号。

真实双位宽引擎正反控制确认旧 JS 导入会链接四种错误函数类型，新准入拒绝，
匹配映像仍可执行；带启动段的控制确认只有实例化原映像才会执行其用户代码。
额外保留无关 externref 签名验证类型段不被数值化。已有真实 Clang fork 支持
对象也通过类型准入；442 项运行库测试、源码和测试 TypeScript 检查及
Clang18/22 双位宽消费者前端/静态分析通过。

扩展后的 exec-imports-check-both 要求双位宽各四阶段、唯一 pass 和关闭：旧
global 错误回滚、新函数类型错误回滚、匹配映像执行，以及重复拒绝/后续 spawn
与单次 wait 恢复。回滚仍检查真实 TP、native TLS、CLOEXEC fd 和文件偏移。
[公开 CI 41601839652](https://github.com/HighCWu/distro/actions/runs/41601839652)
异步验收；旧 a0dcd2b 的三阶段结果不覆盖这次函数类型修复。导出 ABI
标记的返回值和任意程序初始化错误仍不在这一类型门禁的保证范围内。

## exec 提交前拒绝缺失或类型不符的程序入口

distro `166de77` / 集成 `259f43e` 进一步检查 Wasm 执行入口。原来的准入路径
只检查导入；即使映像没有 `_start`，或把它导出成 global、带参数函数，仍可能
通过 compile_end，在 begin_new_exec 后才由宿主调用入口时报错。现在必须存在
符合既有 `() -> void` 契约的函数入口，否则在提交前返回 ENOEXEC。

类型读取按导入函数和本地函数的统一索引解析 `_start`，把其类型加入已有惰性
函数链接检查；仍不执行用户代码、启动段或数据初始化。没有新增应用 API，
没有改变正确程序的入口契约，也不计为新 syscall。未加入任意导出版本函数
返回值、启动代码行为或其余运行期错误的保证。

双位宽真实引擎控制确认旧的 import-only 门禁接受四种错误入口，新 exec 门禁
拒绝；Clang18/22 实际生成的裸 `_start` 通过并保持原有 TP 检查行为。442 项
运行库测试、源码和测试 TypeScript 检查、双位宽消费者前端/静态分析通过。
新目标复用 exec-imports-check-both，要求各五阶段（global、函数导入、入口、
匹配执行、重复失败与恢复）、唯一 pass 和机器关闭。此前三/四阶段源码的
结果不能替代这一增量的目标验收；
[公开 CI 41602628886](https://github.com/HighCWu/distro/actions/runs/41602628886)
异步进行。

## clone 与 clone3 共享 System V semaphore 撤销记录

distro `189068e` / 集成 `128d0e6` 打通已有 Linux `CLONE_SYSVSEM` 标志。此前
通用内核已有 copy_semundo/exit_sem 路径，Wasm continuation 参数过滤和执行
对象掩码却拒绝该标志，程序无法请求共享 SEM_UNDO 记录。这次保留它并交给
原始 clone/clone3 内核实现，不新增 syscall、musl 公共 API 或用户内存共享。

私有执行对象能力 bit 4 独立表示 SYSVSEM 支持；旧 bit 3 仍只表示 FS/FILES。
新宿主配旧对象会在展开 continuation 前拒绝新标志，不能静默丢弃。组合标志
分别核对所需能力；负返回、恢复和下一次普通 fork 清除之前捕获的资源标志。
自定义栈、CLONE_VM 和多线程 fork 的拒绝边界不变。

真实语料扩展已有 clone-sharing：外层观察者创建值为5的 semaphore；中间所有者
用 SEM_UNDO 减为4，再以普通或 SYSVSEM clone 创建子进程，子进程也减1。
私有列表在子进程退出后恢复为4；共享列表仍为3，直到最后所有者退出才恢复5。
两种传输各验证这一差异、精确单次 wait 和 semaphore 删除；Linux 自己检查
SYSVSEM/NEWIPC 冲突并必须返回 EINVAL。原 cwd/umask、共享关闭、close_range
UNSHARE 和普通 fork 隔离/清理阶段保留，共五阶段及唯一 pass、机器关闭。

GCC/Clang 实际原生 clone 正控制和故意漏传共享标志的反向控制通过；本地主机
会在命名空间冲突检查前拒绝 NEWIPC，因此原生参考不冒充该 EINVAL 门禁的
证据，Wasm 隔离目标仍严格要求。失败清理会删除测试拥有的 semaphore，原生
正反控制后核实没有残留 IPC 对象。Clang18/22 双位宽真实 Linux clone UAPI
消费者前端/分析、真实 Wasm 支持对象转发、450 项运行库测试、两套 TypeScript
检查及工作流静态检查通过。这些不代替目标 Linux 的 SEM_UNDO 验收；
[clone-sharing-check-both 41604324578](https://github.com/HighCWu/distro/actions/runs/41604324578)
已异步派发，尚未接受五阶段通过。

## fork 计算期信号与内核 robust-list 的目标验收

[41599761764](https://github.com/HighCWu/distro/actions/runs/41599761764)
固定 ee278a8，实际读取14,196,446字节 Heavy 日志，wasm32/64 各精确三阶段、
唯一 pass：fork 前纯计算计时信号；父子孙进程计算、私有 TLS/数据、重复 fork
和 wait；回调 fork 拒绝后正常 fork/计时器恢复。接受这一独立应用插桩静态 C
组合的双位宽 Node 范围，不扩大为 libc 插桩、浏览器、动态或多线程 fork。

[41600067842](https://github.com/HighCWu/distro/actions/runs/41600067842)
固定04951a3，实际读取10,310,435字节 Heavy 日志，两位宽各精确三阶段和唯一
pass：原始 syscall 退出的内核 owner-death 清理；SIGKILL 唤醒已睡眠 futex
等待者；pending/坏地址遍历和后续有效退出恢复。接受该普通 SDK 的内核独立
robust-list 清理范围，不扩大到所有 PI 或跨独立内存共享映射。

两项 Heavy 和工作流均成功；逐一核对固定源码 run-test.js/shutdown.js 与当前
无差异，runner await machine.closed 且关闭错误为非零退出。它们固定 Linux
94d6741a0/musl651ebf65，不证明后继 SYSVSEM 或新的 exec 类型门禁已经通过。

## native clone3 在子进程运行前设置 no_new_privs

distro `c4bb6f7` / 集成 `be0a5ac` 接通固定 Linux 7.1.5 已有的 CLONE_NNP。
此前 clone3 的 u64 标志过滤和支持对象掩码拒绝它，现在完整传递给原始内核，
由 copy_process 在子进程运行前设置 no_new_privs；不以子进程返回后补一次
prctl 代替。没有新增 musl 函数、syscall 编号或内核实现代码。

该标志要求原生 clone3 和执行对象 capability bit 5；旧对象、缺失原生传输
或畸形 capability 在展开 continuation 前拒绝，不能截断高位或回退为普通
fork。原 flags32 入口的语义不改变。错误后的宽标志状态清除仍通过原路径。

扩展 clone-flags64 目标为五阶段：保留 CLEAR_SIGHAND 的真实信号及冲突检查；
新增子进程首次观察即为 NNP=1、不能清除、孙进程 fork 继承；新增 exec 后仍
为1且不能清除；父进程和后续普通兄弟进程均保持0，原信号继承和资源清理保留。
所有 prctl 测试只调用标准 syscall，参数显式使用完整机器字；没有新增包装。

真实双位宽 Wasm 支持对象确认 0x800000000 保存在 clone_args.flags 中，旧能力
拒绝与错误恢复控制通过；运行库/实际对象共454项检查、两套 TypeScript 通过。
Clang18/22 使用实际固定 Linux UAPI 对两个消费者做双位宽前端/静态分析通过。
本地原生参考验证的是此前 SEM_UNDO，不作为新 NNP 的实际内核证据。
[clone-flags64-check-both 41605449203](https://github.com/HighCWu/distro/actions/runs/41605449203)
已公开异步派发，仍待五阶段、唯一 pass 和机器关闭。
没有扩大多线程 fork、共享用户映射、MMU 或默认 SDK。

## exec 函数导入类型的目标验收

[41601839652](https://github.com/HighCWu/distro/actions/runs/41601839652)
固定 a471b65，实际读取10,312,053字节 Heavy 日志，wasm32/64 各精确四阶段及
唯一 pass：global 类型拒绝；syscall/检查点函数参数、结果和数量拒绝；匹配
映像执行且父状态保留；重复错误后 spawn/wait 恢复。错误路径检查真实 TP、
native TLS、CLOEXEC fd 及偏移。Heavy 和工作流均成功，固定源码 runner 等待
machine.closed，关闭错误会导致非零退出，已核对这两个文件与当前没有差异。
接受固定 Linux94d6741a0/musl651ebf65 的这一双位宽 Node 范围，不覆盖后继
166de77 的五阶段入口检查、SYSVSEM、CLONE_NNP 或浏览器。

## native clone3 的退出通知与 Linux 等待类别

distro `5949088` / 集成 `4b0d1b5` 移除 native clone3 适配器只准许 SIGCHLD 的
限制。合法 exit_signal 字段按0..64捕获，SIGCHLD 保持原默认；其它值要求原生
传输、执行对象 capability bit 6 和固定 i32 的私有字段准备函数。旧对象或缺失
原生传输在展开前拒绝；legacy clone 两种入口仍保持原 SIGCHLD 子集。没有
新增公共 API 或 syscall，也没有扩大共享内存或多线程 fork。

每次原生请求都准备自己的退出信号，适用于普通宽标志、cgroup 和 set_tid
传输。支持对象在校验/调用内核前取走该值并恢复 SIGCHLD，宿主也在 finally
清除捕获状态；错误和后续普通请求不能复用旧值。通知和等待类别都由原始 Linux
clone3/wait 实现决定，宿主不合成信号、不代回收进程。

新 clone-exit-signal-check-both 的双位宽目标各三阶段：零通知、PIDFD 就绪、
普通 wait 排除而 __WCLONE 精确单次回收；SIGUSR1 恰好一次且没有 SIGCHLD；
后续 SIGCHLD 普通回收、无效信号不发布 PIDFD、所有等待类别无剩余子进程及
fd/处理器清理。各唯一 pass 和机器关闭仍需实际目标日志。

GCC/Clang 实际原生 legacy clone 参考通过通知/PIDFD/__WCLONE 正控制，强制
SIGCHLD 的反向控制失败。原生参考不代验 clone3 的无效信号校验：本地 legacy
clone 对该字段的验证与 clone3 不同，后者仍在隔离目标严格要求 EINVAL。
Clang18/22 使用固定 Linux UAPI 完成三个消费者的双位宽前端/静态分析。实际
Wasm 支持对象验证零值、非法值拒绝及失败后恢复默认；456项运行库/支持对象
检查和两套 TypeScript 检查通过。
[公开目标41607396846](https://github.com/HighCWu/distro/actions/runs/41607396846)
异步验收，尚未接受运行通过。

## exec 入口检查的目标验收

[41602628886](https://github.com/HighCWu/distro/actions/runs/41602628886)
固定166de77，实际读取10,313,159字节 Heavy 日志，wasm32/64 各精确五阶段和
唯一 pass：global 类型、宿主函数导入类型、缺失/不兼容入口均在提交前拒绝；
匹配映像正常执行；重复失败后 spawn/wait 恢复。失败路径保留真实 TP、native
TLS、CLOEXEC fd 和偏移。Heavy 与工作流均成功，固定源码关闭门禁仍等待
machine.closed 且关闭错误会非零退出，已核对 runner/closer 与当前无差异。
接受固定 Linux94d6741a0/musl651ebf65 的双位宽 Node 范围，不代验后继 clone
资源、NNP、退出通知或浏览器。

## 原生 clone3 的自动回收与 PIDFD 最后关闭终止

distro `44ec8bc` / 集成 `1e3d2b6` 打通固定内核已有的 CLONE_AUTOREAP 和
CLONE_PIDFD_AUTOKILL。u64 标志完整保留，分别要求执行对象 capability bit 7、
bit 8；零退出信号和 NNP 仍需各自的能力。原始 Linux 检查组合、权限并处理
自动回收和 SIGKILL，宿主不合成回收或终止消息。没有新增 libc API、syscall
编号、共享用户映射或多线程 fork。

静态 review 同时修复 capability 数值校验：它是非负 C int，负 errno 或大于
i32 正范围的数值不能通过 JS 按位截断伪装成能力位。此检查统一应用于已有
各处 capability 位检查；合法已发布对象的正数位掩码保持兼容。

clone-lifecycle-check-both 的双位宽目标各四阶段：普通零信号子进程保持 zombie
直到 __WCLONE wait；AUTOREAP 不经 wait 释放任务，PIDFD 出现 HUP 且所有
等待类别 ECHILD、signal-0 探测 ESRCH；持有 dup 时第一次关闭不终止暂停中的
NNP 子进程，最后关闭才终止，并由独立 pidfd_open 观察任务释放；无效信号/
标志/PIDFD 组合不发布 fd 或子进程，随后普通 fork 保持 SIGCHLD 及可等待性。
观察 PIDFD 是独立 file description，不保留自动终止描述的引用。

双位宽真实 Wasm 支持对象验证 u64 标志、PIDFD 地址和零退出信号；缺少任一
能力、负数/越界 capability 拒绝及错误后恢复通过。运行库与实际对象共458项
检查、两套 TypeScript、Clang18/22 四个消费者双位宽前端/静态分析通过。
本地原生正反控制仍只验证已有 SEM_UNDO/退出通知，不能代验新内核生命周期。
四阶段、唯一 pass 及 machine.closed 仍待
[公开目标41609990548](https://github.com/HighCWu/distro/actions/runs/41609990548)
实际日志。

## CLONE_SYSVSEM 资源共享的目标验收

[41604324578](https://github.com/HighCWu/distro/actions/runs/41604324578)
固定189068e，实际读取14,200,861字节 Heavy 日志，两位宽各精确五阶段及唯一
pass：原生 clone3 的 cwd/umask、共享关闭/UNSHARE；其 SEM_UNDO 共享、私有
控制和最后退出恢复；legacy clone 的对应两阶段；普通 fork 隔离及清理。
完整语料还严格检查 Linux SYSVSEM/NEWIPC 冲突 EINVAL 和精确单次回收。
Heavy、工作流成功；固定源码 runner/closer 与当前无差异，等待 machine.closed，
关闭错误会非零退出，已复核。第一次日志下载网络失败，随后同任务取证成功，
没有重复派发构建。接受固定 Linux94d6741a0/musl651ebf65 的这一双位宽 Node
范围，不代验后继 NNP、退出通知、自动回收/终止或浏览器。

## CLONE_PARENT 的真实父子关系与等待者

distro `b0db175` / 集成 `c88c5ed` 打通标准 CLONE_PARENT。此前 flags-first clone
和 clone3 参数过滤拒绝它；现在独立捕获低位父关系标志，并要求私有 capability
bit 9 及对应的 legacy options/native helper。旧对象在展开前拒绝，捕获字段
在返回或错误后清除，不污染普通 fork。Linux 自己分配 real_parent、继承通知、
验证 init/标志限制并决定可等待者，宿主没有重挂接任务。

原生 clone3 使用零 exit_signal 并保留该字段的独立能力要求；legacy 请求仍
使用 SIGCHLD。新子进程的通知由 Linux 从调用者线程组继承，因此测试由外层
真实父进程用普通 wait 回收，不能把输入零信号误当作普通无 PARENT 子进程的
__WCLONE 等待规则。独立用户内存、单线程 fork 和默认 SDK 的边界不变。

新 clone-parent-check-both 各位宽三阶段：原生 clone3、legacy clone 分别让
新进程检查实际 getppid，调用者 wait sibling 得 ECHILD，外层控制者按报告的
PID 精确回收；最后 namespace init 创建 sibling 必须 EINVAL，普通 fork 的
父关系/单次 wait 和 pipe 清理恢复。调用者必须在控制者回收 sibling 后收到
release token 才能成功退出，排除“调用者先死，普通孤儿重挂接”的假通过。

GCC/Clang 实际原生 legacy clone 参考通过调用者存活期间的父子关系与等待。
Clang18/22 使用固定 Linux UAPI 对五个消费者做双位宽前端/静态分析；真实 Wasm
支持对象验证 legacy 标志和 native clone_args 字段。缺失能力拒绝、错误后默认
恢复、运行库/实际对象共462项检查及两套 TypeScript 通过。
[公开目标41612535629](https://github.com/HighCWu/distro/actions/runs/41612535629)异步验收，
仍待三阶段、唯一 pass 和 machine.closed，不把原生参考代为 Wasm 通过。

## CLONE_NNP 的目标验收

[41605449203](https://github.com/HighCWu/distro/actions/runs/41605449203)
固定c4bb6f7，实际读取14,201,253字节 Heavy 日志，wasm32/64 各精确五阶段及
唯一 pass：清除/保留 signal disposition 和真实默认信号、冲突拒绝、NNP 首次
子进程观察和 fork 继承、exec 后保留且不能清除、普通兄弟及父进程保持未限制
和原 handler/资源恢复。Heavy 与工作流成功；固定源码 runner/closer 与当前
无差异，等待 machine.closed，关闭错误为非零退出，已复核。接受固定
Linux94d6741a0/musl651ebf65 的这一双位宽 Node 范围，不代验退出通知、自动
回收/终止、PARENT 或浏览器。

## 原生 clone3 的空挂载命名空间

distro `341f7f7` / 集成 `e6f6d57` 接通 CLONE_EMPTY_MNTNS。已核对
[官方 Linux UAPI](https://github.com/torvalds/linux/blob/master/include/uapi/linux/sched.h)
及固定内核实现，该标志已经存在。执行对象新增 capability bit 10，完整保留
u64 标志；旧对象/缺失原生传输在展开前拒绝。Linux 自己隐含 CLONE_NEWNS、
选择根挂载、重置子进程 root/cwd 并检查 CLONE_FS 冲突，宿主不做后置 unshare
或挂载更改。固定内核 copy_namespaces/copy_mnt_ns 及其声明均使用 u64，未在
wasm32 调用链上发现高位截断，不额外改内核或添加 musl API。

新 clone-empty-mount-check-both 各位宽四阶段：普通 NEWNS 保留两个 ramfs
挂载和其内 cwd；EMPTY_MNTNS 移除子挂载、暴露原根文件 inode 并重置 cwd；
显式 NEWNS 组合具有相同行为；共享 FS 冲突返回 EINVAL、不改变父视图，后续
普通 fork 和文件系统清理恢复。每个成功子进程另建自己的 ramfs 和 marker，
父进程必须仍看到原 mount inode，不能看到 child-only 文件；挂载、根 inode、
cwd、精确单次 wait 和清理均检查。使用 ramfs，不依赖 NOMMU 未提供的完整
shmem。测试有原生编译拒绝保护，本地不执行任何挂载。

真实双位宽 Wasm 对象确认传递原始 EMPTY_MNTNS，NEWNS 仅在显式输入时由
适配器携带，隐含规则留给内核。旧能力拒绝、失败后恢复、运行库/实际对象
464项检查和两套 TypeScript 通过，Clang18/22 六个消费者双位宽前端/静态分析
通过。[公开目标41614528618](https://github.com/HighCWu/distro/actions/runs/41614528618)
异步验收，仍待四阶段、唯一 pass 与 machine.closed；既有原生
参考不能代验此挂载行为。默认 SDK、独立内存和多线程 fork 边界不变。

## clone3 退出通知的目标验收

[41607396846](https://github.com/HighCWu/distro/actions/runs/41607396846)
固定5949088，实际读取14,201,092字节 Heavy 日志，wasm32/64 各精确三阶段和
唯一 pass：零通知/PIDFD/__WCLONE；所选 SIGUSR1 恰好一次、无 SIGCHLD 且
普通 wait 排除；后续 SIGCHLD 普通回收和无效请求清理。源程序还检查 PIDFD
不被无效信号发布及 __WALL 下无剩余子进程。Heavy、工作流成功；固定源码
runner/closer 与当前无差异，等待 machine.closed，关闭错误为非零退出，已
复核。接受固定 Linux94d6741a0/musl651ebf65 的这一双位宽 Node 范围，不代验
后继自动生命周期、PARENT、空挂载命名空间或浏览器。

## CLONE_IO 共享已有 Linux I/O context

distro `152e015` / 集成 `b8c9e0e` 打通标准 CLONE_IO，独立 capability bit 11
防止旧对象丢弃该标志。legacy clone 保留低32位含符号位的精确位模式，原生
clone3 保留 u64；native/legacy options helper 均支持。I/O context 分配、权限、
引用和复制由原始 Linux 实现处理，不增加 musl ioprio 包装或新 syscall。

固定源码的 copy_io 在当前任务没有 io_context 时直接返回，因此语料先通过
标准 ioprio_set 把父进程设为 BE/4，确保 context 存在；共享子进程改为 BE/6
后退出，父进程必须观察到6。普通 clone 控制中子进程改6，父进程仍为4；最后
恢复原值。两种传输均验证独立用户内存、精确单次回收和原有资源清理。这是
Linux 内核的 I/O 优先级状态，不宣称浏览器宿主或物理存储遵循该调度提示。

扩展 clone-sharing-check-both 为各七阶段：原生的 FS/FILES、SEM_UNDO、IO，
legacy 对应三阶段，以及普通 fork 隔离与清理。旧189068e的五阶段
结果不覆盖新 IO 路径。目标还需各唯一 pass 和 machine.closed。

GCC/Clang 实际原生共享/私有 IO 正控制和省略 CLONE_IO 的反向控制通过，原
SEM_UNDO 正反控制保留。真实双位宽 Wasm 对象核对含32位符号位的 callback
寄存器及 clone_args.flags，旧能力拒绝和错误后恢复通过；运行库/实际对象
共472项检查、两套 TypeScript 和 Clang18/22 六个消费者双位宽前端/分析通过。
检查使用固定原始 sched/ioprio/stddef UAPI，仅本地 Linux 标量类型建模；目标
仍使用完整安装头文件。源码、pin 已推送，
[公开目标41616290441](https://github.com/HighCWu/distro/actions/runs/41616290441)
异步验收，未接受七阶段通过。

## 自动回收与 PIDFD 最后关闭终止的目标验收

[41609990548](https://github.com/HighCWu/distro/actions/runs/41609990548)
固定44ec8bc，实际读取14,201,614字节 Heavy 日志，wasm32/64 各精确四阶段及
唯一 pass：普通零信号 zombie 等待控制、AUTOREAP 自动释放/HUP、dup 最后关闭
触发暂停子进程释放且独立 PIDFD 不保留拥有引用、无效组合无子/fd并恢复普通
fork。源程序还核实 ESRCH、所有等待类别 ECHILD、NNP 和 fd 清理。Heavy 与
工作流成功；固定源码 runner/closer 与当前无差异，等待 machine.closed，关闭
错误为非零退出，已复核。接受固定 Linux94d6741a0/musl651ebf65 的这一双位宽
Node 范围，不代验 PARENT、空挂载、CLONE_IO 或浏览器。

## 内核 nofault 访问的实际线性内存边界

Linux `c7b4f97ef` / distro `1753810` / 集成 `7fe1593` 修复 Wasm 架构的
kernel nofault 读写：原宏直接解引用不可信内核地址，超出线性内存会触发 Wasm
trap，不能按 Linux 的异常表机制返回。现在先校验完整类型宽度、加法溢出和当前
memory.size，再进入原有错误出口；合法未对齐访问使用已有 unaligned 操作。
按页比较避免 wasm32 满 4GiB 时字节容量溢出，增长后按实际容量判断。
这不是页表、MMU 或内核地址对象权限检查，不改变用户内存访问契约。

实际调用路径包括标准 bpf syscall 装载的 socket filter 所调用的 bpf_snprintf：
其 `%pI4` 参数经 copy_from_kernel_nofault 读取，失败时 Linux 原 helper 将
四字节临时结果清零。新独立消费者依次检查有效内核栈地址、无效地址的
`0.0.0.0` 回退、有效重试，以及报文、输出边界和 fd 清理。BPF 验证器、权限
及 GPL-only helper 策略保持不变；原创测试字节码提供 Dual MIT/GPL 许可，
C 加载程序保留 MIT，没有向应用链接 Linux 实现代码或增加 musl 接口。

轻量检查提取实际头文件宏，编译并执行 wasm32/64，覆盖有效未对齐读写、边界、
溢出、失败写无副作用、指针单次求值和 memory.grow；取消保护的反向控制实际
触发越界 trap。两位宽前端及静态分析、格式、差异和元数据检查通过。这些结果
不是 Linux 启动验收。公开预取 41540116632 已核实父版本及源码树哈希；
双位宽真实 Linux/BPF 检查 41541813856、41541820839 已异步派发，三阶段、
唯一 pass 和机器关闭仍待实际日志，尚不接受目标运行通过。

上述1753810两项目标随后已完成。分别读取3,697,917字节的wasm32和3,710,445
字节的wasm64 Heavy日志，均确认有效内核栈读取、无效地址零填充且无内核trap、
有效重试/精确报文/输出边界/fd清理三个阶段及各唯一pass。已复核该源码的
run-test.js等待closeTestResources，后者await machine.closed，关闭错误会使
目标失败；两路Heavy和工作流均成功。接受c7b4f97ef内核在双位宽Node的这一
标准BPF/nofault范围，不扩大为浏览器、所有helper、任意内核地址有效性或MMU。

review 覆盖执行 ABI 版本选择、clone3 有界解析与重入、资源 syscall 的参数位宽、
fd 与 limit 的 fork/exec 生命周期、错误后的原状态和默认模式兼容边界。此前纯
语料增量没有修改内核；第八组发现的必要内核修复单独记录。没有把“未发现缺陷”
解释成完整系统正确性的证明。

发现并修正了具体的验收盲点：原 close_range 有界上界是已关闭的空洞，无法检出
把上界误当不包含的实现。`d37732f` 增加首末相同的单 fd 区间、包含仍打开末端的
带空洞区间，以及原 UINT_MAX/UNSHARE 分支；故意把末端减一的反向控制必须失败。
该修正已包含在 `04724e7`，旧 CI 不作为新末端分支的验收证据。

后续 CI 作为异步验收：正在构建的增量不阻塞下一项独立实现和静态 review；明确
失败时读取日志修复，不把等待或耗时长当作失败。实现、本地验证与各目标验收分别
记录；对重型任务合并必要批次，不重复派发同版本同检查，不为测试数量无限扩展。

Dash 的 wasm64 Node 结果和浏览器/wasm32 进度独立记录在
[Dash 接入记录](dash-processes.md)，不将其中的 shell 通过泛化到 pidfd。

## CLONE_PARENT 的目标验收

[41612535629](https://github.com/HighCWu/distro/actions/runs/41612535629)
固定 b0db175，实际读取 14,201,561 字节 Heavy 日志：wasm32/64 各精确三阶段和
唯一 pass，覆盖原生 clone3 和 legacy clone 的真实父关系、调用者存活期间由
外层控制者回收、调用者不能等待兄弟进程，以及普通 fork 恢复与清理。Heavy 和
工作流成功；固定源码 runner/closer 与当前没有差异，等待 machine.closed，
关闭失败导致非零退出，已复核。接受固定 Linux94d6741a0/musl651ebf65 的该
双位宽 Node 范围，不代验后继标志、空挂载或浏览器。

## CLONE_UNTRACED 的内核跟踪策略

distro 218e10f / 集成 937e5ef 打通 flags-first clone 和 native clone3 的标准
CLONE_UNTRACED。此前适配层直接拒绝；现在独立捕获 tracingFlags，通过私有
capability bit 12 检查执行对象支持，再原样传递给 Linux。旧对象在展开前拒绝，
错误后字段清除；不将它归入共享资源标志，不在宿主模拟 ptrace。固定内核
kernel_clone 已负责在该标志存在时抑制强制子进程跟踪事件，因此无需内核更改。

新增 clone-untraced-check-both：每个位宽分别验证原生与 legacy 的普通 fork
事件、GETEVENTMSG 的实际子 PID、子进程继承的跟踪停止，以及带 UNTRACED 时
事件消失而真实父进程仍能精确回收。最后再次验证普通跟踪恢复和全部子进程清理。
只转发普通 SIGCHLD 停止，不能把 fork 事件误当作退出。默认 SDK、musl 公共 API、
单线程独立用户内存边界均不变。

GCC/Clang 原生 legacy 正控制通过；刻意去掉 UNTRACED 时必须在抑制事件断言处
失败。实际双位宽 Wasm 支持对象核对原始标志和 clone_args 字段，旧能力拒绝及
错误恢复通过；476 项运行库/实际对象检查、两套 TypeScript、Clang18/22 七个
消费者双位宽前端和静态分析通过。原生参考不覆盖 clone3 或目标 Wasm 的运行。
[41617718807](https://github.com/HighCWu/distro/actions/runs/41617718807)
已异步派发，仍待双位宽各三阶段、唯一 pass 与关闭结果，不计为目标通过。

## virtio-fs 共享目录上的标准硬链接

distro 09eeeae / 集成 7695d73 修复共享目录标准 link/linkat 的执行缺口。固定
Linux 已有 FUSE_LINK 路径，但宿主设备没有解码 opcode 13，一直按不支持返回。
现在按固定内核 fuse_link_in 读取 oldnodeid、使用请求 nodeid 指定目标目录，
调用后端添加名字，再返回原节点的 entry 和 lookup 引用。未修改 Linux syscall
或添加 musl 包装；普通软件继续使用原 link/linkat 或 ln。

Node 后端实际调用 node:fs 的硬链接操作，在同一串行路径操作内验证源及目标
目录。新增名字绑定原 Node；unlink 只移除对应名字，rename 按实际路径键搬移，
其余别名仍可访问同一节点。最后一个名字删除后，原打开描述符保留旧 inode，
同名重建得到新节点。符号链接源不跟随最终目标；目录硬链接拒绝，保持只读和
跨后端对象检查，并传递 EEXIST、EXDEV、EMLINK 等实际错误。此处是现有宿主
文件系统协议的后端能力，不要求 Linux 程序调用项目专有接口。

本地核对固定 Linux 的 FUSE_LINK 请求格式和父目录选择；协议验证 LINK 与后续
LOOKUP 返回同一 inode，FORGET 计数不会提前释放，并保留重新查找的身份。
真实 Node 文件系统验证新增别名、nlink、共享写入、原名删除、跨目录 rename、
最后名字删除后的打开文件及同名重建、符号链接源、只读/跨后端拒绝。上述检查
针对通过适配器建立的别名，不扩展为外部预先建立的全部宿主硬链接身份归并。
宿主并发改动目录树的既有限制不变。

474 项内核运行库检查、当前源码打包的24项 Node 文件系统检查通过，kernel
源码/测试两套 TypeScript 通过；guest 库及其全部测试使用当前 kernel/plugin/
bytes 源码重定向后类型检查通过，避免本地旧 dist 产生两套类型身份。

[41618857077](https://github.com/HighCWu/distro/actions/runs/41618857077)
原定独立执行共享目录挂载检查，新增真实 Linux ln 场景检查
相同 inode/nlink、原名删除及跨目录重命名、描述符写入宿主可见、最后删除与
同名重建后的旧文件内容。现有所有共享目录回归一并执行，fixture 的 finally
关闭机器并等待 machine.closed。目标仍在异步验收，不把本地 Node 或工作流
状态当作 Linux 端通过。

该次41618857077实际在计划阶段失败：派发名称漏掉package层级，日志明确报
`unknown heavy check: linux-guest-check-tests-node-filesystem`，未构建或执行测试。
核对导出路径和既有 host-storage 文档后，以正确的
`linux-guest-package-check-tests-node-filesystem` 在同一09eeeae源码派发
[41619155293](https://github.com/HighCWu/distro/actions/runs/41619155293)，已确认
Heavy任务正在运行；没有重复派发仍在运行的同版本正确检查。

## 宿主预先存在的硬链接身份

distro bfc0f8c / 集成4774f06进一步修复lookup/readdir按路径分别创建节点的
问题：固定宿主设备与inode相同的非目录节点复用同一Node，符号链接使用lstat
身份而非目标。目录保留原路径拓扑，宿主不提供有效inode编号时不作身份归并。
路径被替换为不同inode时，仅分离对应旧名字；旧描述符继续指向原inode。

身份索引由已知名字和打开文件拥有：最后已知名字消失且无打开描述符时删除
索引，避免宿主复用inode编号时合并到已删除节点；仍打开的无名inode保留索引，
以后发现其另一硬链接时恢复同一节点及有效路径。最后描述符关闭也清理索引。
create在获取文件身份失败时关闭已打开描述符。readdir在发布节点前读取lstat
身份，不能先发布不同inode、等下一次stat才归并。既有宿主并发目录修改限制
仍然适用，本项不把Node路径操作宣称为沙箱。

审查更新了旧参考中“删除一个硬链接使该Node失效”的错误预期，要求剩余别名
仍能访问同一inode。真实宿主26项检查和两项设备关闭检查通过；新增先删除
原名再发现未查找别名、enumeration身份、打开旧inode后宿主替换路径等场景。
guest库和全部测试使用当前kernel/plugin/bytes源码的TypeScript检查通过。
目标新增普通Linux `test -ef`、`ls -i` 对宿主预建硬链接的身份验证，随后检查
原名删除、剩余名字的inode和nlink、已打开描述符写入共享内容。目标结果仍待
异步CI：[41619658360](https://github.com/HighCWu/distro/actions/runs/41619658360)
固定bfc0f8c使用正确的共享目录检查。旧09eeeae结果不能覆盖这一身份增量；
无musl公共API或内核MMU变更。

## 空挂载命名空间的 nullfs 根校正

[41614528618](https://github.com/HighCWu/distro/actions/runs/41614528618) 固定
341f7f7，实际读取14,194,574字节Heavy日志：wasm32普通NEWNS第一阶段通过，
随后在EMPTY_MNTNS的“exact backing inode visible in selected namespace”
断言处失败，errno为ENOENT；没有最终pass，也未完成双位宽验收。

审查固定Linux源码发现旧语料预期错误。init_mount_tree把不可变nullfs作为
mnt_namespace.root，另将可变rootfs挂在其上，并让普通进程root/cwd指向rootfs。
copy_mnt_ns的EMPTY_MNTNS分支只克隆ns->root并将子root/cwd重置到它，因此
子进程看见空nullfs，不应保留/init或任一initramfs目录。旧语料将可见rootfs
误当成命名空间根，不能据此修改通用Linux的正确行为。

distro d1b0c47 / 集成280079e修正这一语料：先检查cwd=/、statfs的固定
NULL_FS_MAGIC以及/init、两个fixture目录均不存在。父进程在clone前通过
open_tree准备可见rootfs的非递归分离挂载；子进程确认空根后使用标准move_mount
附到自己的命名空间，再fchdir/chroot明确选择新根。之后才检查原底层文件
inode、父子挂载分离以及子私有挂载；父端保持原cwd和两处已挂载marker，关闭
传入挂载描述符并精确回收子进程。带显式NEWNS的组合也执行相同验证；冲突、
普通fork和文件系统清理要求保留。

这没有放宽断言或改变内核/适配器：先增加空根契约，再显式执行原来漏掉的
命名空间填入步骤。open_tree、move_mount仍用原syscall及机器字参数，不新增
musl包装。本地Clang18/22七个消费者双位宽前端和静态分析通过，不在宿主执行
挂载；原生资源/进程参考也通过，但不代验本项。
[41620440385](https://github.com/HighCWu/distro/actions/runs/41620440385) 固定d1b0c47
定向异步复验，仍待各四阶段、唯一pass及machine.closed。后继1857809仅更新
对应README，主仓库c952318已单独pin，不能以该文档更新推定运行成功。

## virtio-fs 时间秒数的 signed time64 解码

distro bc2f407，测试类型修正4ea796f / 集成065d920，修复标准utimensat/futimens
经过共享目录时拒绝负时间的问题。固定Linux iattr_to_fattr把有符号time64秒数
按补码写入FUSE u64槽；此前适配器直接把该槽解读为无符号大整数，再传给已经
支持负时间的后端。现在仅对SETATTR的atime/mtime/ctime秒数执行64位有符号
还原；文件size、inode标识等仍无符号，NOW标志仍传递为now。返回属性保留
原补码位模式，Linux按自己的time64类型接收，不增加syscall或libc API。

协议检查覆盖零、正数、负数和signed64两端、属性回传、NOW与高位unsigned size
互不污染；撤去解码修正的反向控制在-1被误读为18446744073709551615处失败。
GCC/Clang真实宿主参考验证标准utimensat和futimens的负秒/小数、无效纳秒不改
原时间、UTIME_OMIT保留atime以及后续正时间更新。Clang18/22基于实际musl头
做双位宽前端和静态分析，本地不替代FUSE/Linux目标执行。

475项运行库检查通过，kernel源码/测试两套TypeScript和guest库/全部测试的
当前源码类型检查通过。初始测试夹具调用泛型this.getattr未传参数，在本地
测试项目及公开41621211316的backing步骤报TS2554；4ea796f改用独立属性函数
并重新通过检查。主仓库pin选择修复后的4ea796f，没有为错误版本派发重型目标。

新增MIT静态C消费者通过普通utimensat/futimens，目标必须精确输出三阶段：
负time64秒及小数；描述符负时间与非法纳秒无变化；OMIT和正时间恢复。它只
在Node共享目录套件中按需装入，已有浏览器资产不要求携带这个新文件。
[41621357543](https://github.com/HighCWu/distro/actions/runs/41621357543) 固定4ea796f
已启动正确的linux-guest-package-check-tests-node-filesystem；仍待该三阶段、
全部共享目录回归及fixture关闭machine.closed，不宣称目标或浏览器已通过。

## CLONE_IO 的目标验收

[41616290441](https://github.com/HighCWu/distro/actions/runs/41616290441) 固定152e015，
实际读取14,206,530字节Heavy日志：wasm32/64各精确七阶段和唯一pass，与固定
源码字符串及执行顺序逐项匹配。包括native/legacy各自的FS/FILES、SEM_UNDO和
CLONE_IO共享优先级/私有控制，以及普通fork隔离、错误恢复和清理。工作流与
Heavy成功；固定runner/closer与当前无差异，等待machine.closed且关闭失败为
非零退出，已复核。接受Linux94d6741a0/musl651ebf65的该双位宽Node范围，不
把内核io_context状态解释为宿主物理I/O调度，也不代验UNTRACED、空挂载或浏览器。

## 无 FH 的 SETATTR 保留已删除打开文件

distro25c5be7 / 集成d72e9fd修复Node共享目录中fchmod/fchown处理无名打开
inode的路径。固定Linux的vfs_fchmod调用chmod_common，后者只设置ATTR_MODE
和ATTR_CTIME，不保证ATTR_FILE；FUSE因此可发送不带FH的inode SETATTR。
原Node后端没有FH就按路径修改，文件unlink或被替换后返回ENOENT。

现在在原有串行路径操作内校验Node所有权；节点已无已知名字时，从它自己的
仍打开描述符选择目标，再使用原来的文件描述符元数据操作。不会按旧路径修改
同名新文件，不跨后端取用描述符，也不保留额外FD。最后一个描述符关闭后，
无名节点仍不可通过路径复活。默认只读拒绝及显式FH调用路径不变；没有增加
musl API或Linux syscall，没有改动权限决策与内核inode生命周期。

27项真实宿主文件系统检查通过：新增无FH的模式/owner修改、unlink后同名重建
的隔离、只读旧描述符保留内容、跨后端拒绝、最后关闭后拒绝。撤去描述符回退
的反向控制在该SETATTR场景按预期报ENOENT。GCC/Clang原生C参考程序各三阶段
通过，Clang18/22对时间及无名元数据两个消费者做双位宽前端和静态分析，guest
库与完整测试使用当前kernel/plugin/bytes源码的TypeScript检查通过。

新增独立MIT消费者只使用标准open/unlink/fchmod/fchown/futimens等接口，目标
必须精确完成三阶段：只读FD的fchmod修改无名旧inode而保留同名新文件；owner/
时间修改及原、新内容分离；关闭FD报EBADF并保留新文件权限。程序通过既有
测试资产按需装入，不修改应用或libc接口。现有时间、硬链接及其它共享目录
回归一并执行。
[41622279466](https://github.com/HighCWu/distro/actions/runs/41622279466) 固定25c5be7
已异步派发linux-guest-package-check-tests-node-filesystem，仍待实际阶段、
完整套件及machine.closed证据；不以本地宿主通过或旧源码CI代验。

## 创建权限不重复套用宿主 umask

distro b66bcb4 / 集成58056f5修复Node共享目录新建文件/目录的权限。FUSE的
create_context已按Linux调用者的umask过滤mode，Node的open/mkdir随后又应用
宿主进程的umask，导致Linux的umask=0等请求仍被额外收紧。

新建文件现在通过O_EXCL尝试原子确认创建，再按原FD恢复请求的低九位权限。
实际内核保留/过滤的特殊位继续保留，不修改生产宿主进程的全局umask。非排他
O_CREAT遇到已有名字时用不带创建标志的open保留原mode；若名字在两次操作间
消失，则重试创建，不能把新建mode套到旧inode。O_TRUNC等原请求仍传给实际
open。目录创建后同样恢复已过滤的请求权限并保留实际继承的setgid位；路径
验证、串行操作与既有宿主并发目录变动边界不变，不宣称POSIX ACL完整支持。

28项真实宿主检查通过；新用例在隔离测试进程中设宿主umask=077，核对新文件
0666、新目录0777、继承setgid、旧文件0640不变和排他冲突，以及后端没有改动
测试进程的umask，finally恢复原值。撤去修正的反向控制按预期得到0600而非
0666并失败。GCC/Clang普通C程序各三阶段参考通过；Clang18/22对三个文件
元数据消费者做双位宽前端/静态分析，guest库及全部测试的当前源码TypeScript
检查通过。测试进程改变umask不是生产实现的一部分。

新的普通C消费者用标准umask、open、mkdir、stat等接口验证：Linux零umask
保留0666/0777；已有O_CREAT保留mode且排他冲突无变化；Linux自身umask=027
仍正确生成0640/0750并完成清理。没有新增musl函数或应用接口。
[41623399624](https://github.com/HighCWu/distro/actions/runs/41623399624) 固定b66bcb4
异步验收三阶段、全部共享目录回归及machine.closed，尚未接受目标运行。

## UNTRACED 目标失败：首次子进程停止待修复

[41617718807](https://github.com/HighCWu/distro/actions/runs/41617718807) 固定218e10f，
实际读取14,197,396字节Heavy日志，wasm32在普通对照的“ordinary child inherits
ptrace stop”断言失败，errno=0；尚未通过第一个阶段，更未接受UNTRACED或
双位宽运行。该断言前已检查父端FORK事件及GETEVENTMSG中的子PID；现有失败
输出没有展开waitpid实际返回值和原始status，不推定具体退出信号。

审查固定内核ptrace_init_task在跟踪子任务中加入初始SIGSTOP，而Wasm启动路径
为等待CPU、schedule_tail、选择用户入口、wasm_run_user；它明确推迟返回工作，
避免用户C栈/TLS未恢复时运行处理器。这指出首次返回工作的执行时机缺口。
安全修复应在Asyncify停止rewind、C栈/TLS已恢复、但fork结果尚未返回程序时
执行现有私有user_poll返回工作；不得在switch_entry初始化回调中提前递送，
也不通过虚构gettid等syscall制造额外ptrace/seccomp事件。此为下一项修复方向，
尚未作为实现或通过结论；原初始停止断言保留，不能删去以让目标变绿。

## fork 子进程完成 rewind 后的首次返回工作

distro1fafa42 / 集成3693661落实上述失败修复：ForkContinuation完成子端
asyncify_stop_rewind、清除descriptor/result并恢复C栈/TLS后，返回fork的零结果
之前，执行独立的首次返回回调。Worker通过已有user_poll_v1运行Linux待处理
返回工作，不添加gettid等syscall，不改变SIGSTOP/ptrace策略，也不在启动回调
或正在展开/恢复的栈中递送信号。schedule_tail已按通用Linux计算SIGPENDING，
此处补齐原来漏掉的返回工作消费点，而非另写停止状态机。

该回调不依赖编译器轮询标记，也不等同于可忽略的计时回调；异常、任务退出、
exec和非局部处理器控制转移必须传播。初始返回若仍处于内核/用户启动回调则
失败，不能像普通计算期轮询那样静默推迟。嵌套内核深度继续阻止信号回调fork，
父恢复和之后普通分叉不重复执行首次子返回。原Linux/musl信号掩码保持不变。
exec提交前检查内核私有user_poll_v1和user_context_v1导出及签名，缺失则
ENOEXEC；默认未链接fork执行对象的程序不受此额外准入条件影响。

481项运行库测试、kernel源码/测试两套TypeScript通过。新检查覆盖默认无编译器
轮询标记的子进程、停止rewind后的栈/TLS与状态、严格一次、计时异常不妨碍
返回工作、返回工作控制转移不被吞掉，以及内核/启动回调拒绝且不制造syscall。
GCC/Clang实际ptrace正反参考仍通过；Clang18/22七个clone消费者双位宽前端和
静态分析通过。原目标的“ordinary child inherits ptrace stop”断言保留，另在
失败时输出实际waitpid返回值、期望PID、原始status和errno，便于区分后续问题。

[41625499845](https://github.com/HighCWu/distro/actions/runs/41625499845) 固定1fafa42，
使用clone-untraced-check-return-work合并同一构建图：wasm32/64各运行UNTRACED
三阶段、普通fork完整语料、子端信号和恢复期信号语料，共八次独立启动。各自
完整阶段、唯一pass及machine.closed均需核实；旧218e10f失败及本地参考都不
代验本次目标，尚未接受修复运行通过。单线程静态C、默认SDK与无softmmu边界
没有扩大，musl没有新公共API。

## CLONE_PTRACE 显式继承跟踪关系

distro d4b557c / 集成912e507接通被适配层拒绝的标准CLONE_PTRACE。固定
Linux copy_process通过ptrace_init_task处理显式继承，kernel_clone另决定
是否报告强制fork事件。适配器分别保留PTRACE和UNTRACED实际输入，要求私有
capability bit13和bit12；组合需两位，旧执行对象在展开前拒绝。实际C对象的
legacy、pointer-width native和wide native均保留PTRACE，不改Linux策略。

这两个标志不能互相覆盖：调用者已被跟踪时，显式PTRACE可在未开启TRACEFORK
时让子进程继承；UNTRACED禁止强制事件，但不会取消显式继承。没有tracer的
调用者不会因该标志被宿主强行跟踪。父子PID、初始停止、detach和真实父进程
回收仍由Linux负责，捕获字段在错误后清除，保持单线程/默认栈/独立用户内存。

GCC/Clang真实原生legacy验证普通强制事件、UNTRACED抑制，以及未开启TRACEFORK
时PTRACE单独/与UNTRACED组合的初始SIGSTOP、detach、调用者自己回收和清理。
测试显式阻塞调用者SIGCHLD以完成有界PID握手，不由宿主改信号掩码。刻意丢弃
UNTRACED或PTRACE各自的反向控制均失败。Clang18/22七个消费者双位宽前端/
静态分析、两套TypeScript通过；491项运行库/实际Wasm对象检查通过，含纯
PTRACE和组合的精确字段、缺失能力拒绝及失败后的普通请求恢复。

clone-untraced每个位宽扩为五阶段：原生/legacy各自强制事件与抑制；原生/legacy
各自显式PTRACE的两种组合；后续普通跟踪恢复。原生主机参考仍只覆盖legacy，
不能代验Wasm clone3。
[41626641361](https://github.com/HighCWu/distro/actions/runs/41626641361) 固定d4b557c
使用既有clone-untraced-check-return-work，连同双位宽普通fork、子端信号、恢复
期信号共八次启动异步验收，各自完整阶段、唯一pass与关闭仍待核实。旧1fafa42
只覆盖三阶段UNTRACED候选，不能代验本增量；无新musl API或内核softmmu。

## signed time64 与硬链接共享目录的目标验收

[41621357543](https://github.com/HighCWu/distro/actions/runs/41621357543) 固定4ea796f，
实际读取11,092,125字节Heavy日志：wasm32 Linux中八个子用例和外层套件共9项
通过，fail/cancelled/skipped均0。具体包括标准utimensat/futimens负时间、宿主
预建硬链接的同inode、普通ln后的别名/重命名/打开生命周期，以及双向读写、
FSYNCDIR、自身rename、替换旧描述符和unlink/recreate回归。

时间消费者stdout由测试收集；已复核固定源码在真实进程status成功后精确比对
三条阶段字符串，包含负秒及小数、非法纳秒不改原时间、UTIME_OMIT与正时间
恢复，不能只凭外层workflow成功接受。原程序源码和资产构建绑定均已核对。
固定fixture与当前无差异：finally关闭machine并等待machine.closed及console
排空，外层套件成功说明这条关闭门禁已完成。Heavy与workflow均success。
接受Linux94d6741a0/musl651ebf65的上述wasm32 Node固定源码范围，不代验后续
无名元数据、创建mode、fork首次返回、wasm64或浏览器。

## 保留路径开头的 U+FEFF

distro9d6b563 / 集成f6eb53b修复标准文件操作中的UTF-8名字身份混淆。共享
二进制Reader.cstring使用TextDecoder默认BOM处理，会把开头EF BB BF吞掉。
Linux文件名中的U+FEFF是有效字符；因此带该字符的名字曾可能被LOOKUP、
RENAME、UNLINK当作不带字符的另一个名字，符号链接目标也会丢失字符。

协议字符串现在用fatal UTF-8加ignoreBOM=true解码，保留U+FEFF作为数据；目录项
getdents64和readLink/realPath的路径解码作同样修正。只修改路径/协议字符串，
不改变readTextFile的文本文件BOM处理。非法UTF-8仍严格拒绝，没有增加替换
字符容错或声称支持JS后端的任意非UTF-8文件名字节；Linux syscall和libc均不
需要新接口，也不要求普通程序改写文件操作。

Reader直接源检查覆盖单个/重复U+FEFF、连续C字符串边界和非法UTF-8。实际FUSE
请求检查带前缀与普通名字返回不同inode，并核对符号链接名/目标、READLINK
返回字节及rename/unlink不误操作普通名字。去掉修正的反向控制会把两个FUSE
节点合并并在身份断言失败。getdents64检查还要求带U+FEFF的点号名字不被误当
成“.”而过滤。bytes构建包含Reader检查，主仓库CI增加独立路径源检查。

当前bytes源码重定向下，运行库与目录解析共491项检查通过，另有两项Reader
检查通过；bytes、kernel源码/测试、guest库及全部测试TypeScript通过，工作流
静态检查通过。没有以本地旧dist代替新解码器执行。
[41628363222](https://github.com/HighCWu/distro/actions/runs/41628363222) 固定9d6b563
异步验收真实Linux共享目录：同时保留普通和前缀名字，读取正确内容、列举前缀、
创建并读取相对链接目标、重命名和删除前缀文件后保留普通文件，并要求原链接
变为ENOENT而不误指普通名字。全部共享目录回归及machine.closed仍待核实，
不以协议/宿主检查或旧4ea796f结果代验，不宣称浏览器已通过。

## 创建权限与无名 inode 元数据的目标验收

[41623399624](https://github.com/HighCWu/distro/actions/runs/41623399624) 固定b66bcb4，
已读取实际Heavy日志并复核固定源码：wasm32 Node十个子用例及外层套件共11项
通过，fail/cancelled/skipped均0。新增创建权限与unlink后描述符元数据消费者
各自要求进程成功并精确匹配三条阶段输出，覆盖Linux umask不被宿主二次过滤、
既有O_CREAT及排他碰撞，以及fchmod/owner/timestamp仍作用于旧inode、替换文件
不被修改和关闭后错误。此前时间与硬链接回归同时通过。

固定fixture在finally关闭机器，等待machine.closed及控制台排空；外层套件、
Heavy和workflow均成功。只接受该版本Linux94d6741a0/musl651ebf65的wasm32 Node
范围，不代验后续BOM、只读访问、fork首次返回或wasm64/浏览器。

## 只读共享后端的标准访问探测

distro9651f58 / 集成1baa33d修复NodeFS只读策略与access(W_OK)不一致的问题。
原实现把探测交给宿主，宿主文件可写时报告成功，但该共享后端已拒绝写入。
现在先保留节点存在性及符号链接检查，再对含W_OK的请求返回EROFS；F_OK、
R_OK仍按原路径处理，不改变标准syscall或新增libc接口。

这里修复的是后端ACCESS hook。后续0b35521的真实目标否定了下述旧验收假设：
virtio-fs默认default_permissions会绕过该hook，Linux只读挂载仍需MS_RDONLY。
具体失败证据和修正门禁见[只读挂载准入修正](#virtio-fs-只读挂载准入修正)。

现有28项实际源后端检查通过；移除策略判断的反向控制会在只读断言失败。
既有三个元数据消费者的GCC/Clang原生参考通过，Clang18/22双位宽前端与静态
分析还覆盖新的readonly-access消费者。新消费者只允许Wasm构建，本地没有
以宿主文件权限或只读挂载模拟其目标执行。

[41630231326](https://github.com/HighCWu/distro/actions/runs/41630231326) 固定9651f58
异步运行完整Linux共享目录检查。新增共享目录由后端设为只读，刻意不使用
内核只读挂载标志，以核对真正的后端访问策略。要求精确三阶段：存在/读取
探测成功；文件、目录、混合及AT_EACCESS写探测均EROFS；实际写open拒绝后
仍可读且缺失路径保持ENOENT。全套回归和机器关闭仍待核实，不把本地检查
或此前b66bcb4成功当作本次目标通过。

## 共享后端资源错误保留

distro0b35521 / 集成e66d51b修复Node后端把标准资源或I/O错误改成EIO的问题。
FUSE错误表和宿主转换白名单补齐EINTR、ENXIO、EAGAIN、ENOMEM、EBUSY、ENODEV、
ENFILE、EMFILE、ETXTBSY、EFBIG、ESPIPE、EPIPE、EOVERFLOW、EDQUOT；数值已逐项
对照固定Linux asm-generic UAPI。未知宿主异常仍返回EIO，不透传宿主数字errno，
也不改变Linux自身资源限制、重试策略或musl公共API。

独立子进程的RLIMIT_NOFILE设为96，真实打开/dev/null直到宿主EMFILE，然后
通过实际共享Wasm memory/virtqueue发起FUSE OPEN，要求回复-24。释放一个fd后
同一节点OPEN/READ恢复，关闭设备后/proc/self/fd计数回到基线。限制仅作用于
测试子进程，未改变开发者或CI主进程限制。去掉EMFILE白名单的反向控制得到
-5而失败；该验证已加入主仓库轻量CI，不需伪造OS错误或启动重型内核构建。

kernel现有490项及Node后端28项回归通过，源码/测试与当前源guest类型检查通过，
workflow静态检查通过。真实资源耗尽证据只覆盖EMFILE及协议恢复，其余新增错误
为数值和转换路径审查，未声称实际触发磁盘配额、系统级ENFILE或所有设备故障。
[41631033684](https://github.com/HighCWu/distro/actions/runs/41631033684) 固定0b35521
异步运行Linux共享目录回归及关闭，目标仍待核实；该任务不主动耗尽CI宿主fd，
也不能代验浏览器或所有资源压力。

## 旧 clone 的退出通知接通

distro9577599 / 集成f075c32接通flags-first旧clone此前被适配器拒绝的非默认
CSIGNAL。Linux/Wasm原回调clone已把低字节送入kernel_clone.exit_signal，真正
缺口在用户执行适配及其只允许SIGCHLD的helper。新增MIT可选执行helper与
capability bit14，沿用号220、默认栈和独立用户内存；没有新增Linux syscall、
musl公共函数、共享VM或多线程fork支持，也不改写为clone3。

旧clone的信号字节先从选项中剥离，bit7不会误变成CLONE_NEWTIME。整个字节
保留供Linux旧接口处理，不强加clone3的信号字段验证。新旧helper有显式门控，
不完整或旧对象在展开前拒绝；负返回及trap后清除捕获值，普通SIGCHLD继续
使用原helper。旧import的空callback checkpoint范围不变，v2不猜数字布局。

494项运行库/实际Wasm C对象检查通过，kernel源码与测试两套TypeScript通过。
真实双位宽C对象检查号220、信号0/10/17/255、PIDFD/child槽位及无效helper输入，
状态检查覆盖缺失能力、负返回、trap及普通请求恢复。GCC/Clang宿主运行既有
legacy通知/PIDFD/__WCLONE参考和强制SIGCHLD反向控制，Clang18/22七个clone
消费者双位宽前端及静态分析通过；原生参考不证明Wasm现场恢复或clone3执行。

[41631999976](https://github.com/HighCWu/distro/actions/runs/41631999976) 固定9577599
运行clone-exit-signal-check-both：每个位宽先clone3、再flags-first旧clone，各
要求零通知/PIDFD及WCLONE回收、选定SIGUSR1及普通wait排除、后续SIGCHLD和
实际libc fork/wait恢复三阶段，共六阶段、唯一pass及机器关闭。clone3仍单独
检查65号退出信号拒绝；不把该规则施加到旧clone。目标阶段尚待核实，旧三阶段
通过不能代验本次六阶段，更不代表浏览器或完整clone选项已支持。

## fork 首次返回与 ptrace 的双位宽目标验收

[41626641361](https://github.com/HighCWu/distro/actions/runs/41626641361) 固定d4b557c，
已读取14,593,036字节Heavy日志，并从固定源码提取阶段字符串逐项比较：
wasm32、wasm64各完成四次独立启动，共八次。每次完整有序阶段及唯一最终
pass均已核实，不只依据workflow状态。

| 每个位宽的工作负载 | 已核实阶段 |
| --- | --- |
| clone-untraced | 5：原生/legacy强制fork事件与UNTRACED抑制、原生/legacy显式PTRACE的两种组合、后续普通跟踪及清理恢复 |
| fork-continuation | 12：原始clone/clone3、身份/内存/TLS/atfork/信号隔离、失败exec恢复、成功exec的三条子程序阶段、回收、线程/信号回调拒绝与恢复 |
| fork-child-signals | 2：child pre-rewind pending及父隔离；两次恢复的栈/TLS及单次投递 |
| fork-resume-signals | 2：父端post-clone pre-rewind pending及子隔离；两次恢复的栈/TLS及单次投递 |

固定版本的程序、运行器和关闭助手与当前对应文件无差异。运行器在成功标记
之后调用closeTestResources，等待machine.closed后才关闭磁盘；任何启动、
迟到运行错误或清理错误均令退出码非零。该Heavy及workflow均success，因此
上述八次启动也通过对应关闭门禁。

接受Linux94d6741a0、无新增公共包装的musl651ebf65及d4b557c执行对象组合的
Node双位宽范围：原218e10f的初始ptrace子端停止失败已由首次返回工作修复，
显式PTRACE/UNTRACED及原fork/信号回归获得实际目标证据。不据此代验后续
9577599旧clone退出通知、浏览器或多线程fork；1fafa42的较早三阶段候选无需
再用workflow成功状态泛化验收。

## ptrace 与退出通知的浏览器组合门禁

distrof0ecfb5 / 集成15d22e1把上述clone消费者接入既有process-browser运行器。
复用原clone-untraced和clone-exit-signal的runtimeAssets，不重新编写浏览器版
syscall或消费者，不修改默认SDK/内核、musl API或fork支持范围。

每个位宽/引擎有一个聚合检查，分别执行clonetrace五阶段和clonesignal六阶段。
每组在同页启动两次独立机器，精确要求有序阶段和唯一pass、机器关闭、控制台
排空，最终浏览器断开及无迟到页面错误。两组各自启动并关闭浏览器；全部通过
才完成聚合检查。新退出通知必须同时包含clone3与旧clone三阶段，旧三阶段
结果不能单独放行。

本地34项轻量门禁检查通过，含新组的CPU配置、乱序/缺失/重复/混入其它组、
两轮和关闭后错误拒绝，并核对阶段对应原C源码与双位宽资产。使用宿主模拟
浏览器驱动，没有本地启动浏览器，不将这些结果当作浏览器目标证据。

已各派发一次固定f0ecfb5的公开CI，Plan已发现相应Heavy检查，实际运行尚待验收：

| 组合 | CI |
| --- | --- |
| wasm32 Chromium | [41633035041](https://github.com/HighCWu/distro/actions/runs/41633035041) |
| wasm32 Firefox | [41633045847](https://github.com/HighCWu/distro/actions/runs/41633045847) |
| wasm64 Chromium | [41633073381](https://github.com/HighCWu/distro/actions/runs/41633073381) |
| wasm64 Firefox | [41633084979](https://github.com/HighCWu/distro/actions/runs/41633084979) |

需逐项核实两组各两轮的完整阶段、对应机器关闭及两次浏览器关闭，不能用
workflow成功状态、Node八次启动或本地模型替代，也不重复派发慢任务。

## 宿主替换路径后、再次 LOOKUP 前的 fd 元数据

distro134f7f7 / 集成9a168a0修复Node共享后端剩余的打开inode身份问题。此前
无FH的GETATTR/SETATTR只在节点已标为detached时使用活跃描述符；宿主先用
rename替换名字，而Linux尚未重新LOOKUP时，缓存节点仍为attached，因而可能
把fstat结果取自替换文件，或把旧fd的fchmod操作应用到替换文件。

现在两类无FH请求都优先使用该inode持有的活跃描述符，不要求先发现名字变化。
显式FH、只读拒绝和没有描述符时的路径行为保持原有边界。没有增加syscall或
libc包装，仍不把Node路径API当作抵御外部并发重构目录的安全沙箱。

原后端28项回归通过，其中替换场景故意把元数据检查/修改放在新LOOKUP之前。
分别撤回GETATTR或SETATTR的描述符优先逻辑，两项反向控制均实际失败。
新的标准C消费者先open/fstat旧文件并输出ready，控制器宿主rename替换文件
后通过stdin释放程序；它先核对旧fd的inode/nlink/size，再执行fchmod/futimens
和读取，最后才stat/open新路径，核对替换文件内容和权限不变及关闭清理。

GCC/Clang实际原生握手及三阶段通过；Clang18/22双位宽前端/静态分析、当前源
guest及测试类型检查通过。原生结果只证明标准程序预期，不替代Wasm后端。
现有元数据参考也同时通过，新资产保持lazy读取，不改变浏览器资产要求。
[41634318694](https://github.com/HighCWu/distro/actions/runs/41634318694) 固定134f7f7
异步验证Linux真实进程三条精确阶段、宿主替换文件状态及全套共享目录回归和
machine.closed，目标尚待核实，不沿用旧b66bcb4或纯宿主结果接受本增量。

## 陈旧 inode 拒绝与验证后的截断

distro906f5dd / 集成5d24cc1修复已完成宿主替换后，旧节点OPEN、无描述符
GETATTR/SETATTR、ACCESS及READLINK误绑定新文件的问题。路径属性按dev/ino
核对缓存身份，移除失效名字；如果仍有已知硬链接，则重试该inode的其它名字。
新LOOKUP可以得到替换文件的新节点，已有打开fd继续保留原inode元数据。

普通OPEN在打开后再次fstat确认身份才发布句柄。regular file的O_TRUNC延迟
到该确认之后，通过已验证fd执行，避免在拒绝旧绑定前已截断替换文件。
O_RDONLY|O_TRUNC保持逻辑只读，write仍EBADF；显式只读fd修改长度按Linux
do_ftruncate返回EINVAL。路径truncate则可借用已有可写fd，或临时打开并验证
可写fd，不再因任意选中已有只读fd而误报失败。句柄回收同步移除可写记录。

32项后端实际文件回归、当前源guest/测试类型及workflow检查通过。临时实际源
bundle在预检查与host open之间受控执行真实rename：只读、只读TRUNC及只写
TRUNC都拒绝旧绑定、保留替换数据、关闭未发布fd，随后新LOOKUP/read恢复。
恢复原先提前O_TRUNC的反向控制会实际破坏替换数据并失败；关闭身份检查的
控制也检出错误成功及硬链接别名误绑定。生产代码未加入测试hook或应用API。
真实EMFILE到FUSE回复、释放后恢复及fd回到基线仍通过。

标准external-file-metadata消费者从三阶段扩为四阶段：新增持有新文件只读fd
时的路径truncate、显式只读fd的EINVAL及写入恢复，最终替换数据仍恢复原值。
GCC/Clang原生四阶段、Clang18/22五个元数据消费者双位宽前端/静态分析通过。
这些是后端/宿主证据，不是Linux/Wasm验收，也不建立任意外部并发目录重构下
的沙箱或所有命名操作原子性保证。最新目标由下节32eb392组合统一复验，旧
134f7f7三阶段结果不能代验新四阶段。

## virtio-fs 只读挂载准入修正

[41631033684](https://github.com/HighCWu/distro/actions/runs/41631033684) 固定0b35521
已明确失败。实际11,101,487字节Heavy日志中，readonly-access在file write probe
处报告errno=0，父测试断言失败；不能将后端unit通过当作Linux access已拒绝。

已核对[官方Linux v7.1 virtio-fs默认配置](https://github.com/torvalds/linux/blob/v7.1/fs/fuse/virtio_fs.c)：
default_permissions=1；固定内核fuse_permission因此在本地检查inode权限，不
调用后端ACCESS。后端readOnly拒绝实际修改，并不自动设置Linux挂载只读状态。
没有删除该标准内核默认条件，也没有伪造权限mode位来替代只读挂载。

distro32eb392 / 集成f80eeb6修正消费者和装配：保留普通挂载上的backend-only
分支，明确检查根用户的本地权限探测成功而实际写open仍由后端返回EROFS；
另用独立tag和标准MountFlags.RDONLY挂载同一只读后端，要求file/directory/
mixed/AT_EACCESS写探测均EROFS。两种模式各自还要求存在/读探测、拒绝写后
读恢复及缺失路径ENOENT，均精确三阶段。后端选项注释说明此配置边界，没有
新增SDK应用接口、musl包装或内核修改。

新四阶段元数据原生参考、双位宽编译/分析和类型检查通过；只读C分支按原有
约束仅做Wasm前端/分析，本地不执行特权只读挂载。已一次派发固定32eb392的
[41637667371](https://github.com/HighCWu/distro/actions/runs/41637667371)，统一验收
906f5dd的四阶段、上述两种只读模式及全套共享目录和关闭。排队/运行期间不
重复派发。目标仍待实际阶段证据，0b35521失败不被删除或重写为已通过。

## clone 通知与 ptrace 浏览器矩阵已核实

固定f0ecfb5的四路目标现已读取实际Heavy日志，与固定版本processStages精确
比较完整有序输出。相关C消费者、装配、运行器和关闭逻辑与当前对应文件无
差异。四路Heavy及workflow均success，接受范围如下：

| 组合 | 已核实目标 |
| --- | --- |
| wasm32 Chromium 149.0.7827.55 | [41633035041](https://github.com/HighCWu/distro/actions/runs/41633035041) |
| wasm32 Firefox 151.0 | [41633045847](https://github.com/HighCWu/distro/actions/runs/41633045847) |
| wasm64 Chromium 149.0.7827.55 | [41633073381](https://github.com/HighCWu/distro/actions/runs/41633073381) |
| wasm64 Firefox 151.0 | [41633084979](https://github.com/HighCWu/distro/actions/runs/41633084979) |

每项均以cpus=2运行两组，各自同页两轮：clonetrace每轮五阶段，覆盖原生
clone3/legacy clone的强制fork事件、UNTRACED抑制、显式PTRACE单独及组合、
后续跟踪与清理；clonesignal每轮六阶段，覆盖两种clone的零通知、SIGUSR1、
SIGCHLD、PIDFD就绪、__WCLONE与普通wait区别、单次回收及普通libc fork恢复。
所有16次启动各有唯一pass和机器关闭标记，8次浏览器运行均有最终关闭标记。

固定runRuntimeSmoke只有在等待machine.closed并处理最终控制台回调、迟到
运行错误后才返回；浏览器控制器逐轮严格校验输出，最终等待浏览器断开、
拒绝迟到页面错误并关闭服务进程，才输出最终成功标记。已检查实际日志中的
这些门禁结果，没有用工作流绿色替代阶段验收。wasm32 Chromium首轮日志
下载曾URLError，重读同一已完成任务后取得完整证据，没有重新派发CI。

独立Node [41631999976](https://github.com/HighCWu/distro/actions/runs/41631999976)
固定9577599也已读取实际日志：wasm32/64各完整六阶段、有序且唯一pass，
固定运行器等待machine.closed并将关闭错误转为失败，Heavy及workflow均成功。
这补齐旧clone退出通知在Node双位宽的准入，不只复用原生参考。

上述接受Linux94d6741a0、musl651ebf65与固定可选单线程静态C fork配置，
退出通知实际场景限0/SIGUSR1/SIGCHLD及语料中的选项组合；不泛化到所有
CSIGNAL字节、clone标志交叉、多线程fork、默认SDK、动态fork或后续NodeFS
陈旧inode/只读挂载修复。32eb392的41637667371仍按自己的阶段单独验收。

## pidfd_getfd 跨进程文件描述符消费者

distroa72cc09 / 集成5058334新增独立pidfd-getfd配置，接入固定Linux已存在的
标准号438，不冒称新写了内核实现。程序使用已有musl syscall()，显式传入
六机器字参数；不提供pidfd公共包装、头文件API或项目自有syscall。仍使用
可选单线程静态C fork配置，内核、musl及默认SDK未改。

子进程在fork后才创建普通文件，父进程不能通过继承获得该打开描述。双方用
标准pipe握手，依次要求三个阶段：

1. pidfd_getfd取得真正的子文件，复制fd为CLOEXEC而子fd保持原描述符flags；
   父读ab使子读cd，子设置O_APPEND使父可见，证明共享打开描述的offset/status。
2. flags=1、坏pidfd、普通文件冒充pidfd和坏远端fd分别EINVAL/EBADF；失败不
   消耗fd槽，后续复制仍成功并共享原offset。
3. 子进程关闭源fd后复制返回EBADF，回收后ESRCH；父复制fd在unlink/源关闭/
   子退出后仍可读ef且nlink为0，最终关闭所有fd并正常fork/wait恢复，无遗留子进程。

GCC/Clang实际原生三阶段通过。把真实远程复制替换为本进程dup(target_number)
的反向控制失败，避免把碰巧相同的fd编号或继承文件误当作复制成功。原生
参考只使用显式临时路径；若其它宿主策略阻止真实调用，会以77且无pass退出，
不记为原生或目标通过。Clang18/22双位宽前端及静态分析通过，既有clone参考
仍通过。原生结果不证明Wasm寄存器、进程上下文与copy_to_user路径。

一次派发固定a72cc09的
[41640837136](https://github.com/HighCWu/distro/actions/runs/41640837136)，选择
pidfd-getfd-check-both，要求wasm32/64各完整三阶段、唯一pass及machine.closed。
首次派发在获取workflow元数据的GET阶段EOF退出；核对没有该源码的已建任务
后才重试，最终仅一项派发成功。实际目标仍待核实，不扩大为其它凭据、命名空间、
全部pidfd flags或浏览器已支持。

## 仍待解决的宿主目录句柄定位

本轮实际源NodeFS轻量复现：opendir持有旧目录后，宿主把目录rename到新名字，
再在旧名字创建含不同条目的目录；旧句柄readdir返回了替换目录的条目。
当前NodeFS保存的FileHandle可用于旧inode属性与fsync，但枚举仍按parts路径，
因此普通文件身份修复不能被描述为完整目录句柄生命周期支持。

该缺口未在本轮假称解决。后续需要同时处理目录相对定位、子节点身份及引用
回收，单纯重走路径或只验证错误返回不能代替原目录的正确语义。它属于宿主
共享后端，不据此否定Linux内部ramfs/ext4的目录语义，也不阻塞独立pidfd目标。

## 描述符验收与共享目录控制器修复

固定a72cc09的[41640837136](https://github.com/HighCWu/distro/actions/runs/41640837136)
已读取实际14,211,403字节Heavy日志：wasm32/64各完整有序三个pidfd阶段和唯一
pass；固定运行器等待machine.closed，关闭失败使检查失败，Heavy及workflow均
success。这接受上文三个跨进程FD场景，不代验后续Unix辅助数据消费者。

6c5d14c新增两阶段标准Unix socket消费者：SCM_RIGHTS排队的文件在发送者关闭、
unlink及退出回收后仍可接收，SCM_CREDENTIALS保留发送者PID/UID/GID；另检查
单FD控制空间截断、MSG_CMSG_CLOEXEC及多余接收FD清理。原生GCC/Clang五阶段、
错误本地dup/去掉CLOEXEC/错误扩大控制空间的反向控制与双位宽静态分析通过。
这是既有内核syscall的真实消费者准入，不冒称新增了内核实现或musl接口。

32eb392的[41637667371](https://github.com/HighCWu/distro/actions/runs/41637667371)
实际失败于测试控制器：virtio-fs-node-guest.test.ts在读过stdout就绪行后再次
new Response(process.stdout)，触发“Response body object should not be disturbed
or locked”。两种只读模式子测试已通过，不能据此接受整个共享目录套件。

8d4d9a3 / 集成5579f0c使握手及后续输出保留同一个reader，保留四阶段与宿主
文件状态断言，stdin仍在finally关闭。分块/合并输出、UTF-8、就绪先于EOF、
错误传播和解锁检查及完整测试目录类型检查通过。没有改动Linux或musl。
该固定版本一次派发两项，均尚待真实阶段与关闭验收：

- [41648941984](https://github.com/HighCWu/distro/actions/runs/41648941984)：共享目录四阶段元数据、两种只读模式及全套回归。
- [41648987859](https://github.com/HighCWu/distro/actions/runs/41648987859)：双位宽pidfd三阶段加Unix辅助数据两阶段。

## 目录打开后的 inode 核验

4480642将NodeFS.opendir接入已有验证后发布FD路径，避免宿主在预检与open之间
替换目录时，把新目录FD绑定到旧Linux节点。打开后dev/ino不匹配返回ENOENT并
关闭未发布FD；后续lookup可取得新目录并正常打开、枚举、关闭。Windows原有
无目录FD分支保持原有边界。

实际源码临时bundle在host open前插入测试暂停，真实rename旧目录并在原名创建
新目录，验证拒绝、FD基线、旧目录内容保留和恢复。仅临时bundle有测试钩子；
绕过inode核验的反向控制失败。32项后端回归、原文件截断交错正反控制及类型
检查通过。root CI配置已接入该原生检查；固定4480642单独派发
[41649317994](https://github.com/HighCWu/distro/actions/runs/41649317994)，尚未接受
该版本的真实Linux/Wasm共享目录套件。这不修复上一节所述“已经打开的旧目录句柄在替换后枚举新目录”问题，
不把拒绝错误inode发布当作完整目录生存期支持。

## 父目录身份与相对操作

实际源码原生复现发现另一处错误：缓存parent节点后，宿主把它rename到moved，
在旧名建立新目录及同名victim；旧节点unlink请求删除了新目录的replacement，
而旧目录文件仍在。这是误作用于无关inode，不能作为路径已支持的表现。

distro d9f3ea8 / 集成afb1710为lookup、create、mkdir、symlink、unlink、rmdir、
link目标及rename两端统一核对父目录inode和目录类型，再解析子路径。已完成
的宿主目录替换返回ENOENT，避免修改新目录；先保留实际目录路径的包含性
检查，维持符号链接越界EACCES。普通后端内部rename更新缓存的行为仍可用。

33项实际源码后端回归及完整测试目录类型检查通过。九种操作逐项保留旧/新
文件内容、源文件及目录状态，要求错误后新lookup/打开/读取恢复。移除父目录
inode核验的临时bundle反向控制会重新暴露unlink误删，没有生产测试钩子。

该修复防止错误对象被修改，尚不实现已打开旧目录的完整POSIX相对寻址：
openat/unlinkat等通过原目录FD继续访问旧目录，以及readdir的稳定定位，仍需
目录相对宿主能力、子节点身份和引用回收一起实现。标准Node目录枚举不能直接
使用现有FileHandle，不能用预先缓存目录列表代替实时目录语义。本轮未引入
私有应用接口、内核softmmu或musl新包装，也未将原生回归当作Linux/Wasm验收。
固定d9f3ea8一次派发[41650336204](https://github.com/HighCWu/distro/actions/runs/41650336204)
共享目录目标套件，尚待实际阶段和关闭结果。既有8d4d9a3与4480642任务保持
运行，不因新版本而取消，也不代验本版本。

## 已完成的共享目录与描述符验收

既有四项任务已核对固定源码、实际Heavy日志及关闭门禁。

| 固定源码与任务 | 已核实范围 |
| --- | --- |
| 8d4d9a3 / [41648941984](https://github.com/HighCWu/distro/actions/runs/41648941984) | wasm32 共享目录，14项通过 |
| 4480642 / [41649317994](https://github.com/HighCWu/distro/actions/runs/41649317994) | 同一共享目录完整套件与关闭 |
| d9f3ea8 / [41650336204](https://github.com/HighCWu/distro/actions/runs/41650336204) | 同一共享目录完整套件与关闭 |
| 8d4d9a3 / [41648987859](https://github.com/HighCWu/distro/actions/runs/41648987859) | 双位宽 pidfd 与 Unix 辅助数据五阶段 |

共享目录包含13个子用例和外层套件，零失败、零跳过。描述符任务的双位宽各
有序通过pidfd三阶段、Unix辅助数据两阶段和唯一最终pass。

三份共享目录日志分别为11,128,056、11,128,651和11,193,326字节。成功的固定
控制器严格比较四阶段元数据输出、两种只读模式各三阶段，以及宿主文件内容
和权限。外层套件在finally等待machine.closed及console管道后才成功。
描述符日志为14,237,929字节，两个位宽逐项比较五阶段及唯一pass，固定运行器
等待closeTestResources并将关闭错误转成失败。四项Heavy及workflow均success。
这些结果限相应固定版本，后续目录恢复及SDK变更各自验收。

## 活目录句柄恢复与失效硬链接回退

distro bc99a87 / 集成92433d7补齐2a33cc2的共享根内目录恢复。Linux Node宿主
通过活目录FD的procfs定位核对新路径dev/ino，恢复目录绑定与缓存子节点。
父子关联采用弱引用，内部rename/link/unlink同步维护别名，祖先改名后的首次
子文件属性请求也可恢复。三种查找顺序都要求保留原子文件身份，包含先观察
替换目录的情况。35项实际源码后端回归、类型检查及标准C五阶段原生参考通过。

标准C消费者在宿主握手改名后，通过旧目录FD枚举原条目，再使用openat、
renameat和unlinkat操作原目录。替换目录内容独立保留。固定bc99a87的
[42551885607](https://github.com/HighCWu/distro/actions/runs/42551885607)已派发，
真实Linux/Wasm五阶段及关闭尚待验收。共享根外移动和宿主并发重构仍有路径
定位边界。

distro10abe93 / 集成639f4d4另外修复选中硬链接别名被宿主删除后的错误ENOENT。
父目录恢复未改变路径时，只针对ENOENT/ENOTDIR移除失效别名，重试同inode
的其它已知名字。权限与资源错误继续传播。实际源码36项回归、移除回退的
反向控制和类型检查通过，覆盖存活别名读写、父目录变为普通文件、旧名重建
及所有旧inode别名消失。

## 原版 GNU sort 的外排压缩配置

distro031b890 / 集成0ac09bf新增coreutils-sort-fork及wasm64配置。固定GNU9.7
源码保持原样，复用可选静态C fork配置，普通configure与上游生成规则构建
src/sort，并保留源码比较、材料及许可证。目标使用标准--parallel=1和小内存
缓冲，实际调用gzip助手压缩和解压外排文件，检查两种助手失败及随后恢复。
宿主GNU9.4的四阶段及去掉压缩参数的反向控制通过，目标GNU9.7仍需独立验收。

[42552275208](https://github.com/HighCWu/distro/actions/runs/42552275208)固定031b890
明确失败于构建前ShellCheck SC2209，环境赋值SORT_FAIL=compress需要引用字符串。
distroe0b6cd7 / 集成c324ccd修复四处赋值并保留全部运行断言。该失败未执行
Wasm sort，不能描述为压缩、fork或错误回收的目标结果。

## 动态 SDK 的普通共享库编译入口

distro288d022 / 集成a34715a将可选动态SDK接到已有Linux Clang共享链接分支。
同一个wasm-linux-dlopen-cc接受普通对象、主程序及-shared，响应文件由Clang
解析，现有真实动态加载产品也通过该入口构建所有DSO。

派生sysroot的crt1.o使用保留原对象的archive装配CRT与私有执行支持。主程序
默认库另按驱动规则强制libc导出归档，共享库跳过这些输入，三个标准启动/
默认库开关分别控制选择。部分链接试验发现-r会丢失export_name重命名，
因此没有用-r组合启动对象。LLD18/22双位宽微型引擎检查核实重命名入口、TLS、
宿主导入和归档选择。新SDK真实编译检查包含现有信号入口导出及嵌套响应文件，
需要构建后的编译器执行，本地跳过结果不计通过。SDK的-r链接仍受共享内存和
growable-table默认配置限制。

底层Clang补丁另外核对-nostdlib/-nostartfiles/-nodefaultlibs与共享链接的输入
选择，避免当前目录同名libc-exports.a被自动注入。补丁在固定LLVM90352668上
零fuzz应用检查通过，Nix、Python和JS静态语法检查通过。
[42553259515](https://github.com/HighCWu/distro/actions/runs/42553259515)固定288d022
同样被上述sort脚本的SC2209全局门禁阻断，尚未构建新编译器或运行动态程序。
后续以修复版本的单项聚合检查同时构建双位宽SDK驱动、底层Clang检查及双位宽
Linux动态加载十阶段，复用同一工具链构建。

## 宿主删除空目录后的真实 EOF

distroe1f4f91 / 集成c6376af使Linux Node后端在活目录FD的nlink为0时，通过该FD
真实枚举procfs路径并保留错误。FUSE READDIR按句柄属性省略已删除目录的合成
点条目，仍调用后端枚举。普通目录的偏移、分页及typed条目属性调用计数保留。

C消费者在首次握手前持有host-empty目录流，由宿主在握手期间删除，再要求
fstat零链接、首次readdir严格EOF且errno为0和成功关闭。另保留程序自己删除
空目录的场景。宿主删除场景用于避免Linux S_DEAD检查及musl对ENOENT的EOF
转换绕过新后端路径，总输出仍为五阶段。

492项内核运行层回归、36项实际源码NodeFS回归、三套类型检查、GCC/Clang原生
五阶段及Clang18/22双位宽C前端和静态分析通过。修复版本e0b6cd7包含本增量，
真实Linux/Wasm共享目录验收等待该固定版本的新任务结果。

随后固定e0b6cd7的三项复验均明确失败于全局statix格式门禁。
[sort 42553873045](https://github.com/HighCWu/distro/actions/runs/42553873045)、
[共享目录42553873152](https://github.com/HighCWu/distro/actions/runs/42553873152)及
[动态SDK 42553873284](https://github.com/HighCWu/distro/actions/runs/42553873284)
实际日志都指出sdk.nix的冗余列表括号和startup.nix的未使用lib参数导致自动
修改，尚未进入对应目标。58cb26b / 集成106df07按实际差异修复，并同步移除
startupRoot调用处的lib传参，避免删除形参后出现Nix调用错误。该版本重新
请求三项独立检查，旧失败保留，新版本仍须完整目标阶段和关闭证据。

已核对新任务均固定58cb26b，计划生成的Heavy检查名正确，当前仍在运行。

| 检查 | 任务 |
| --- | --- |
| 双位宽GNU sort四阶段及关闭 | [42554769711](https://github.com/HighCWu/distro/actions/runs/42554769711) |
| 双位宽动态SDK驱动、底层Clang及Linux十阶段 | [42554769847](https://github.com/HighCWu/distro/actions/runs/42554769847) |
| wasm32 Node共享目录五阶段及完整套件关闭 | [42554769831](https://github.com/HighCWu/distro/actions/runs/42554769831) |

## 原版 sort 与共享目录的实际验收

已读取固定 `58cb26b` 的上述 sort 和共享目录完整 Heavy 日志。sort 的 wasm32/64
各按顺序完成真实压缩外排、压缩助手非零退出、解压助手非零退出和后续恢复四阶段，
各有唯一最终 pass。运行器在结束前等待 closeTestResources 和 machine.closed，
关闭错误令任务失败，两项 Heavy 及 workflow 均成功。

共享目录实际完成13个子测试与外层套件，14项通过、零失败、零跳过。其中元数据
消费者精确比较五阶段输出，并执行宿主 rename、删除旧目录内已打开空目录和
同名替换目录操作；通过旧目录枚举、子节点身份、相对操作及 EOF 断言。两种
只读模式及其余回归均通过。固定 fixture 使用一个 CPU，关闭并等待 machine.closed，
控制台结束错误传播到检查。此证据接受该固定版本的 Node 共享目录范围。

动态 SDK 的旧版本任务 `42554769847` 随后失败于检查脚本的省略启动文件用例。
修复和复验状态另见[SDK 复验](elf-dynamic-linking.md#动态-sdk-省略启动文件的复验)。新 `RTLD_NEXT` 增量另见
[调用者所属对象](elf-dynamic-linking.md#rtld_next-与真实调用者所属对象)，不使用
上述 sort 或共享目录结果代替动态链接目标验收。

## 标准 WIPEONFORK 与 KEEPONFORK

Linux `006bd8489` 放行 madvise 的 MADV_WIPEONFORK/MADV_KEEPONFORK。musl
`2579fbcd` 增加 Wasm 私有映射标记，`69141218` 补齐锁外分配前的布尔需求保存。
distro `4786175` 接通执行适配和双位宽产品，最终 pin 为 `1165894` / 集成
`d0e9b09`。现阶段可用范围是登记的私有匿名 mmap，页大小为64KiB。

父进程只更新标记。部分区间先完整核验覆盖及来源，再在锁外准备最多两条记录，
重新核验后拆分边界。KEEP 无变化时保持原记录，恢复相同标记后合并同 backing
的连续匿名记录，保留完整范围的 mremap 能力。munmap 拆分和 mremap 的缩小、
增长、移动及固定移动保留相应标记，普通固定新映射使用初始标记。文件初始化
副本的 WIPE 返回 EINVAL，失败保留已有字节和标记。

新 __wasm_madvise_v2 仅在宿主识别版本化数据描述表时使用，旧回调对18/19
返回 EOPNOTSUPP。描述表由 Global 导出，包含版本、记录大小、链头变量地址及
各字段偏移。子 Worker 在复制和实例准备后、发布完成状态前，纯 JS 核验整条
链并清零指定范围。此阶段避免调用用户 C 代码，保护复制的活动 C 栈；清零也
先于内核后续 child_tid 初始化。标记保留到子进程，后续 fork 再次清零，
CLONE_VM 使用原共享内存路径。

主会话完成实现审查，修复 KEEP 分裂记录影响 mremap 的回归，并调整边界指针
和锁外分配的衔接。现有及新增实际 allocator 的7项检查通过，覆盖 ASan/UBSan
和 Clang 静态分析。529项运行层检查及两套 TypeScript 通过。Clang22 双位宽
实际 allocator 数据导出与 JS 选择性清零 ABI 已联通；该微型引擎检查使用宿主
分配和锁 shim，证据限定于 ABI。GCC/Clang18 的普通 Linux 四阶段参考通过，
消费者使用标准 mmap、madvise、fork、waitpid、mremap 和 munmap。

Linux 输入的公开预取42589915363已核实原基线和候选 NAR 哈希；musl 新输入
计算前复验已发布基线，构建仍由固定输出哈希校验。自有适配和消费者采用 MIT，
Linux 修改沿用 GPL，产品保留 musl 和 compiler-rt 通知。
[内核输入预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/42589915363)。

固定 `1165894` 的聚合任务要求双位宽新四阶段、已有 fork continuation 完整语料
和 madvise 回归，各自唯一 pass 及机器关闭。真实 Linux/Wasm 与浏览器验收
仍待相应执行日志，未使用上述宿主或微型引擎结果替代。
[双位宽目标检查](https://github.com/HighCWu/distro/actions/runs/42594481341)。

该任务随后失败于 wasm32 启动脚本，BusyBox hush 报 `set: -eu: invalid option`，
尚未执行新消费者。同期已有 fork continuation 语料在双位宽均输出完整阶段和
唯一 pass，不能据此接受新内存建议能力。distro `2af5ef1` / 集成 `40cd085`
改用显式退出状态检查，失败输出 fail 并阻止成功标记。原生 BusyBox 成功、失败
和目标等待路径及 ShellCheck 通过，已请求同一聚合目标复验，真实阶段仍待核实。

## 原版 GNU find、xargs 与 tar 的普通进程路径

distro `5aabc63` / 集成 `86e1476` 新增独立 findutils-fork 与 tar-fork 产品。
复用原版 findutils4.10.0、tar1.35 固定输入，使用已有静态 C fork SDK 构建。
构建前后逐项比较旧补丁涉及的原文件，保存源码哈希、配置、SDK 材料和许可证。
最终程序才执行 continuation finalizer，外部观察助手使用默认 SDK 编译。
该增量接通普通程序的原始调用路径，没有新增 libc 公共接口或 syscall 编号。

find/xargs 四阶段覆盖普通 -exec 的子进程身份、cwd 和参数，带空格路径的
-execdir 批量执行，以及 xargs -0/-P2 的真实 /dev/null、独立 slot 和双向重叠
握手。缺失和非零命令核对上游状态与后续恢复，find 的记录精确对应失败文件。

tar 四阶段覆盖外部过滤助手的普通文件与不可 seek 管道往返、成员字节及
TAR_* 环境、成员助手结束后的 checkpoint 隔离，以及失败助手和缺失命令的
错误传播与后续恢复。管道两端状态分别核对，成功前清理临时目录。

主会话完成差异审查，修正未 finalize 助手的 SDK 选择、find 谓词分组及 tar
checkpoint 顺序。GCC/Clang 严格构建、Clang22 静态分析、双位宽 Wasm 前端和
ShellCheck/shfmt 通过。原生参考为 findutils4.9.0 与 tar1.35，不能替代固定
4.10.0 的目标执行。新增代码采用 MIT，GNU 产品保留 GPL 和运行时通知。
一次聚合检查要求双位宽各四阶段、唯一 pass 和机器关闭，真实结果待日志核实。
[GNU 工具聚合检查](https://github.com/HighCWu/distro/actions/runs/42602956896)。

## 匿名 MREMAP_DONTUNMAP 的直接内存实现

Linux `8856f4a0d`、musl `98017031`、distro `5aa0f7c` / 集成 `ef538b6`
接通普通 mremap 的 MAYMOVE|DONTUNMAP 路径。源区间须完整落在一条登记的匿名
私有映射记录内，页取整后新旧长度相等。返回新地址前复制字节并清零原区间，
原地址仍登记且可独立读写。实现使用实际复制和立即清零，不提供缺页或 COW。

FIXED 组合复用已有原子替换逻辑，目标须在分配器已拥有的预留范围内，且与源
不重叠。同 backing 子区间和跨 backing 替换均保留原映射与邻居，替换后的
目标继承源的 WIPEONFORK 标记。文件初始化副本返回 EOPNOTSUPP。

非固定路径在锁外准备新 backing，再重新查找当前完整覆盖记录后提交。合法的
元数据变更不会仅因旧记录被拆分而误报 EFAULT；源已消失或变成文件副本时
则拒绝并释放准备资源。固定路径同样在修改字节前完成验证和元数据准备。
私有 user_v2 执行入口只调用 __wasm_mremap_dontunmap_v1，缺少该导出时返回
EOPNOTSUPP，旧 allocator 不会收到新请求。公共 musl 函数和头文件 API 未增加。

主会话完成实现与差异审查，修复重验证及二次加锁失败的资源清理。真实 allocator
的 GCC/Clang ASan/UBSan 与 Clang analyzer、531项运行层及两套 TypeScript
检查通过。双位宽前端编译和现有 FREE、fork-advice 回归通过。本机 Linux
消费者四阶段覆盖复制/清零、固定拓扑、拒绝后恢复和清理，目标验收独立记录。

公开预取已核实 Linux 的已知父版本与候选 NAR 哈希，以及 musl 候选哈希。
首次 Linux 预取在实验脚本的变更路径白名单返回64，3879190补入已审查的两个
文件组合后核实成功。目标聚合要求双位宽新四阶段与已有 mremap 六阶段、各自
唯一 pass 和机器关闭，仍待实际执行结果。内核修改沿用 GPL，其余新增适配为 MIT。
[Linux 哈希预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/42606614843)、
[musl 哈希预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/42606762959)、
[DONTUNMAP 双位宽目标](https://github.com/HighCWu/distro/actions/runs/42607124232)。

## fork 内存建议的双位宽目标验收

固定 `2af5ef1` 的42600310846已核实实际日志。wasm32、wasm64各包含新内存建议
完整四阶段和唯一 pass，已有 fork/exec 及 madvise 语料也逐项通过。固定运行器
等待 machine.closed，关闭或迟到错误会使检查非零退出，该任务与 Heavy 均成功。
这接受登记匿名映射的 WIPEONFORK/KEEPONFORK 范围，浏览器仍待独立验收。
[实际目标日志](https://github.com/HighCWu/distro/actions/runs/42600310846)。

## 既有 vfork 的通用回退与原版 Dash 构建

distro `0a36554` / 集成 `cce0ab6` 恢复 tombl/musl 已有 `vfork` 的 Wasm 门控，
仅可选 fork profile 编译通用 C 实现。原函数体保留，通过标准 SIGCHLD clone
进入既有 continuation。父子采用独立内存快照，可独立运行，调用不执行
pthread_atfork hooks。使用既有 libc 接口，没有新增公共 API 或 Linux syscall。

Dash 配方移除 `-Dvfork=fork`，按原函数名链接原始源码。可选 CONFIG_SITE
同时清除 fork/vfork 的默认否定缓存，让正常声明和链接检测运行，不预填成功。
默认 SDK 的缓存策略保留。单线程、静态 C 和完整链接后 finalizer 的前提继续适用。

五个既有默认 Luna 子代理实现门控、配方、配置和消费者，主会话决定契约并
审查全部差异。新消费者检查缺文件 exec 的 ENOENT 与精确退出状态、随后成功
exec 的 PID/PPID/参数环境、继承 fd 和共享文件 offset，以及 atfork 未调用。
helper 使用普通 SDK，父程序使用 fork profile。主会话修正重复 pass、报告管道
自持写端与 child 中 errno 宏引入的额外函数调用。通过标记只在程序正常退出及
临时文件清理后发送。

GCC、Clang22 原生三阶段、双位宽修补头文件的 C 前端和补丁零 fuzz dry-run
通过。主会话直接编译修补后的真实 vfork.c 与 syscall_ret.c，在 Wasm32/64
微型执行中核对 clone 的六机器字参数、父子返回值和 EAGAIN 转换。该微型执行
使用固定返回的 syscall import 和 errno 存储辅助，只验证 ABI。静态分析保留
unix.Vfork 检查，仅排除消费者刻意调用 vfork 所触发的 insecureAPI 名称提示。
原生消费者与微型执行均不替代 Linux/Wasm 验收。

固定代码版本 `0a36554` 的聚合任务要求双位宽新消费者三阶段、既有 Dash 完整
进程语料、fork/exec 回归与机器关闭。后续 `9485b3e` 仅更新 SDK 说明。
实际目标结果待日志核实。[目标 CI](https://github.com/HighCWu/distro/actions/runs/42613237502)。

## 共享目录的非 UTF-8 文件名操作

distro `b8c7e2a` / 集成 `8a9ddb4` 接通 FUSE 与 POSIX NodeFS 的原始路径字节。
普通 openat/readdir/renameat/readlinkat/unlinkat 可区分非 UTF-8 名字与真实
U+FFFD名字，避免错误访问替换字符文件。六个既有Luna子代理实施，主会话
审查并验证真实源代码。内核和 musl 不变，新增消费者使用普通 SDK。
原生三阶段及轻量检查通过。固定版本的 Node/Wasm32 实际目标日志已核实，
新用例和旧回归共15项通过，包含三阶段精确输出、宿主状态及关闭收尾。见
[字节路径实现与边界](host-storage.md#linux-文件名与链接目标的字节保真)。

## GNU 进程工具构建的材料清单修复

固定 `5aabc63` 的42602956896已明确失败。主会话读取完整 Heavy 日志，首个
builder 错误发生于 sdk-build-materials-wasm32，严格校验报 files 集合不一致。
Nix 材料定义已包含 executable-linker.rsp 和 cxx-linker.rsp，Python 白名单
遗漏这两项。find/tar 消费者尚未构建与运行，此次失败不能作为其功能结论。
[失败任务](https://github.com/HighCWu/distro/actions/runs/42602956896)。

distro `82aa6db` / 集成 `7d12763` 补齐这两个既有产物，并保留缺失和额外输入
的严格拒绝。原 fixture 从同一白名单生成，无法发现 Nix/Python 漂移，因此
回归现在直接比较真实 Nix files 键与 Python 集合。子代理执行明确修复，主会话
审查清单、实际 sysroot 来源及打包调用路径，14项本地检查通过。固定82aa6db的
42616826592已一次派发双位宽 GNU 进程工具聚合复验，完整阶段及关闭待核实。
[修复版复验](https://github.com/HighCWu/distro/actions/runs/42616826592)。

## 官方 BusyBox 源码的普通 fork 构建

distro `164df4c` / 集成 `fdc5d21` 新增可选 busybox-fork 及 wasm64 产品。源码
来自固定 nixpkgs 的官方 BusyBox1.37.0 发行包，沿用该包已有的上游安全与集成
补丁。主会话下载发行包并核对 SHA256 与固定定义一致。项目自有配方、配置、
消费者和 helper 为 MIT，BusyBox 与上游补丁保留其 GPL 许可。

配置选择普通 fork 路径和 Ash，启用基础文件工具、find、xargs、awk、tar 等
选定 applet。BusyBox 的 CONFIG_NOMMU 关闭后可使用现有 fork 执行 ABI，Linux
内核的 CONFIG_MMU 仍为 n。Ash 的 SjLj 使用已有 Clang 参数，整个可执行文件
在链接后经过 fork finalizer。helper 由普通 SDK 构建。

真实二进制和所有上游 applet 链接安装到 /opt/busybox-fork，另提供
/bin/busybox-fork 入口。配置与构建前后校验 ash.c 和 vfork_daemon_rexec.c 的
摘要，保留上游补丁、配置、生成头文件及 SDK 来源材料。四个既有 Luna 子代理
分工实现，主会话负责契约与审查，并修正 Kconfig 精确匹配、真实材料文件名、
Nix 中单文件测试路径及 busybox.links 的生成。finalizer 之后直接运行上游
安装脚本，避免 make install 重新复制未经变换的链接产物。

独立运行语料要求四个阶段依次完成。

1. Ash 的管道、命令替换、后台 wait 和精确退出状态，显式调用外部 helper。
2. find -exec 完整文件参数，以及 xargs 的 NUL 输入和2+1参数分组。
3. awk system() 与命令 getline 的输出、退出状态、close 和重新执行。
4. 缺失 exec 的127、helper 的7，以及随后正常外部命令恢复。

主会话使用 GCC/Clang22 编译 helper，在原生 BusyBox1.36.1 上核实四阶段及唯一
pass。原版1.37.0 的 Kconfig 生成和选项保留已核实；Clang22 检查 Ash、进程
辅助和 applet 入口的 Wasm32/64 前端语法。该发行 Clang 的 wasm64 Linux
triple 不可用，64位前端使用 Wasm64 加 Linux 宏，完整定制工具链仍需 CI。
原版安装脚本另用标记文件核对字节保留和 Ash 的隔离链接，此检查仅验证安装
路径。helper 静态分析、位宽前端、ShellCheck、shfmt、Nixfmt 和工作流检查通过。

固定164df4c的聚合任务已一次派发，要求双位宽真实1.37.0产品四阶段、既有
fork/exec语料和机器关闭。目标运行结果待实际日志核实，原生1.36.1参考与
前端检查各自保留证据范围。[目标 CI](https://github.com/HighCWu/distro/actions/runs/42619738115)。

主会话随后核对 Statix0.5.8 的 manual_inherit_from 实现，确认首版对上游
version/src/patches 的选择赋值会被 fix 改写。`f3eb829` / 集成 `b4df2c1`
改用 inherit 并同步配方检查，Nixfmt 与检查通过。本地依据规则源码进行静态
核对，完整格式门禁仍交由 CI 执行。当前固定f3eb829的42620736032负责该候选
双位宽验收。[格式修复版 CI](https://github.com/HighCWu/distro/actions/runs/42620736032)。

## 异步目标检查的三个接线修复

主会话读取了上述候选的实际失败日志，并逐项定位。

- DONTUNMAP 的42607124232停在普通 toolchain-smoke 的旧信号模块夹具。
  新 Clang 自动读取 sysroot 的 executable response file，显式参数中过滤
  `__stack_pointer` 已不足以撤去导出。`c43fd26` 为该夹具复用 link-sysroot
  配方生成专用响应文件，原来要求无栈指针导出的断言保留。
- vfork 的42613237502与 BusyBox 的42620736032停在隔离 fork SDK 检查。
  复制后的 execution-link.test.js 找不到真实 user-functions.ts。
  `e823d2f` 镜像原始 distro/packages 目录关系，复制实际模块及其依赖。
  新临时隔离目录中原有8项检查通过。
- GNU 工具42616826592已在 Wasm32 输出 tar 前三个阶段，第四阶段失败。
  tar 明确报告过滤器退出37，但旧 Hush 的 else 分支读到状态0。该 shell
  源码在跳过 then 分支时会清零状态，原脚本写法本身符合 POSIX。
  `37840b2` 在命令后立即保存状态，再进入条件判断。非零错误和后续普通归档
  恢复断言保留，GCC/Clang 原生消费者四阶段通过。目标复验仍需确认。

三个修复按独立源码提交发布，集成 pin 为 `cd34295`。复验固定 distro
`37840b2`，分别为 DONTUNMAP 42628068112、vfork 42628083775、GNU 工具
42628094264及 BusyBox 42628105424。这些旧失败任务均不算完整目标验收。
[DONTUNMAP](https://github.com/HighCWu/distro/actions/runs/42628068112)、
[vfork](https://github.com/HighCWu/distro/actions/runs/42628083775)、
[GNU 工具](https://github.com/HighCWu/distro/actions/runs/42628094264)、
[BusyBox](https://github.com/HighCWu/distro/actions/runs/42628105424)。

## 默认 Hush 的条件分支退出状态修复

真实 tar 运行已暴露默认 `tombl/busybox@4ad91c87` 的 Hush 语义错误。内核的
子进程退出37能被 tar 正确接收并报告，但 Hush 在跳过 then 分支时为无 else
情况暂置状态0，进入 else 或 elif 时却没有恢复失败条件的状态。

distro `86c613a` / 集成 `87ab23f` 在首次进入替代分支时恢复保存的 cond_code。
同一 else 中后续命令继续使用各自状态，无 else 的失败 if 整体仍返回0，成功
then 分支保持原路径。普通脚本可直接在 else 中读取 `$?`，无需改写错误处理。
这是默认 shell 的生产兼容性修复，Linux syscall、musl 和 fork 范围均未改变。

四个复用 Luna 子代理实施补丁、消费者、配方与材料接线，主会话确定数据流契约，
接管补丁序列化并完成 review。固定源码零 fuzz 应用通过。主会话提取实际条件
控制块进行原生正反控制，旧块丢失状态，修复块保留首次和后续状态、elif 状态
及无 else 返回值。此控制块检查只证明局部数据流，不代表完整 Hush 执行通过。

Dash 与 BusyBox Ash 原生参考通过三阶段，覆盖直接外部失败及 else 后续命令、
elif/成功 then/无 else，以及函数、子 shell、管道错误与后续恢复。目标脚本
明确启动当前默认 Hush，临时文件清理后才发送唯一 pass。Nix/shell 格式、语法、
ShellCheck 和工作流检查通过。

配套材料保留固定原始源码及有校验和的本地补丁，提供构建前的应用命令。未知
补丁仍被 source bundle 拒绝，清空 patches 的覆盖保留旧五参数导出路径。
材料宿主检查验证归档、补丁应用与防篡改，真实材料检查还会核对发布二进制及
双位宽归档里的补丁。上游许可证保留，自有材料和检查代码使用 MIT。

完整 Hush 三阶段、既有进程回归和关闭门禁仍需固定源码的双位宽目标验收。
固定 `86c613a` 的聚合已派发一次，同时包含双位宽 source bundle 检查。
[目标 CI](https://github.com/HighCWu/distro/actions/runs/42632541709)。

该首次派发在 Plan checks 即失败，聚合被定义为软件包而未进入 checks 收集器。
`6dbc8d5` / 集成 `1b33768` 改为普通 BusyBox 的 `checks.shell-status-both`，
沿现有 extraChecks 模式接入，wasm64 覆盖不重复继承聚合。实际重型检查名为
busybox-check-shell-status-both。固定修复版的
[42634218310](https://github.com/HighCWu/distro/actions/runs/42634218310)已派发，
原 Plan 失败不算执行过 Hush 目标语料。

## DONTUNMAP 与 vfork 的固定版本 Node 验收

主会话已读取固定 distro `37840b2` 的完整实际 Heavy 日志，并对照该版本源码
逐项核实。42628068112 中，wasm32/64 的 DONTUNMAP 四阶段及原 mremap 六阶段
均按运行顺序出现，各机器只有一个 pass。42628083775 中，两位宽 vfork 消费者
三阶段、Dash 四阶段及正常 fork 契约的全部13个标记均出现，各机器唯一 pass。
[DONTUNMAP 验收](https://github.com/HighCWu/distro/actions/runs/42628068112)、
[vfork 验收](https://github.com/HighCWu/distro/actions/runs/42628083775)。

同时核对固定 runner 的源码与执行退出结果，成功必须经过 machine.close、
等待 machine.closed 和磁盘收尾，清理错误会令任务失败。该 runner 与当前版本
一致，不能只凭工作流绿色跳过关闭检查。此验收范围为固定37840b2的双位宽
Node组合。vfork沿既定独立快照回退语义，浏览器和后续ELF/Hush组合仍需各自验证。

官方 BusyBox 的42628105424已进一步到最终链接，实际报 Wasm LLD 不识别
--start-group/--end-group。原版 BusyBox 运行语料尚未执行，归档组参数的
工具链兼容实现继续推进，保留原软件构建脚本。
