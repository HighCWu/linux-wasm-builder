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
