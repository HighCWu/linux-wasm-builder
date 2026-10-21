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
[wasm32 Node](https://github.com/HighCWu/distro/actions/runs/39530468988)，均待验收。

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
已对最终版本重新派发，须核实
新增 clone3 阶段、完整原有语料和关闭之后，才将该接入记为目标验收通过。

Dash 的 wasm64 Node 结果和浏览器/wasm32 进度独立记录在
[Dash 接入记录](dash-processes.md)，不将其中的 shell 通过泛化到 pidfd。
