<!-- SPDX-License-Identifier: MIT -->

# 标准进程控制 syscall 准入

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
只接纳无 flags、默认栈、SIGCHLD、无 tid/pidfd/TLS/cgroup 选项的单线程 fork。
指针/长度先验证，结构字段保持完整 u64；保存区重入和恢复受现有状态机控制。
对未支持的合法组合拒绝，不声称实现完整 clone3。尤其不支持 CLONE_PIDFD 原子
返回 pidfd；第一组测试用的是已有子进程的 pidfd_open。

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

### 同期 CI 检查修复

主仓库 `39541628806` 和 `39543174124` 的实际日志确认：Python workflow 检查
假定 native job 紧邻 jobs 标题，benchmark job 插入后触发 undefined.split；plan
条件也已增加 benchmark 排斥，旧断言未跟进。这不是 Python 或 Wasm 目标执行失败。
distro `84a3675` / 集成 `c4256ac` 改为按顶层 job 名定位，保留原只读权限、无发布
凭据和不派发目标矩阵断言，并用插入前置 job、移除 guard、扩大权限、缺失 job
的控制验证。19 项相关 Node 检查及 10 项源码包检查通过，主仓库 CI 已随 push 复验。

## 本轮静态 review 与异步验收原则

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
