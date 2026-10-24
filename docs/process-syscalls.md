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
- pthread 的实际 open 等待权限答复；非法响应不消耗请求，FAN_DENY 得 EACCES，
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
