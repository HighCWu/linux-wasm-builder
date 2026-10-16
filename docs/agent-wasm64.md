<!-- SPDX-License-Identifier: MIT -->

# 高层 agent 的 wasm64 接入

目标是在已有 wasm64 内核、SDK 和浏览器用户程序路径上，继续提供匹配位宽的
进程、文件、挂载及网络 API。当前 `@lowland/guest` 默认打包镜像仍使用 wasm32，
新增显式自定义 ABI/镜像的公开入口，其 Node 实际启动检查已通过；
内部原生 wasm64 会话、文件与进程请求链已在 Node 最小启动检查和 Chromium 的
生产入口/根切换检查中运行通过；GPT 磁盘启动也已在 Node 通过。
Firefox、公开镜像选择的浏览器端到端路径和完整发行版仍需分别验证。
保持 `CONFIG_MMU=n` 和真实线性内存指针，不引入内核 softmmu。

## ABI 前置工作

distro `7e8eeb7` 新增内部 `abi-wasm64.ts`，不切换现有会话，不增加公开包导出。
原有 `abi.ts` 保留 wasm32 默认行为。两者复用结构描述器和已检查的公共 flags、
errno、signals、目录记录及 wait 宏，避免复制另一套独立常量。

wasm64 使用原生 `lseek/newfstatat/fstat/ftruncate`，不暴露 ILP32 的
`llseek/fstatat64/fstat64/ftruncate64` 名称。相同 syscall 数字不意味着相同参数
约定：原生 lseek 接收一个有符号 64 位 offset 并直接返回结果，而不是拆分高低位
及输出指针。原生内核 `struct stat` 为 128 字节，时间秒和纳秒字段为 64 位，
以 bigint 保存；它不是 wasm32 的 104 字节 `struct stat64`，也不是 musl 的公开结构。

新增 `guest-agent-check-abi-wasm64` 用 wasm64 SDK 编译由描述器生成的 C 静态断言，
核对 syscall、字段 offset/size、结构大小及 pointer/long 位宽，同时将 agent C
源码编译为目标对象。它不启动 agent、不提供可用的 wasm64 系统镜像，也不能代替
端到端行为检查。重型编译由公开 CI 承担：

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref YOUR_PUSHED_BRANCH \
  -f heavy-check=guest-agent-check-abi-wasm64
```

4 项宿主回归及同套独立打包检查通过，覆盖原生别名、128 字节布局、大于 2^53 的
字段、负秒、带偏移视图、wasm32 描述不受影响及 C 断言生成。类型检查通过。
[目标编译检查](https://github.com/HighCWu/distro/actions/runs/38945796060)
已通过，固定 distro `7e8eeb7`：日志确认构建 `linux-agent-abi-wasm64`，生成的
原生 ABI 静态断言和当时的 agent C 源码均成功编译，目标检查和整个工作流成功。
这仍不是 agent 启动、镜像或完整发行版的运行证明。

## 显式会话身份

distro `943aae8` 保持默认 v3/wasm32 会话，新增内部显式 ABI 的 v4 握手。
8 字节头的末尾 u16 在 v3 必须为 0，在 v4 为 32 或 64；agent 按实际 pointer/long
位宽校验，不把请求中的任意值盲目回显。原生 LP64 executor 拒绝 v3，避免继续接受
没有目标身份的 ILP32 请求。session 确定版本后，agent 对每条 lane 要求相同版本；
宿主也要求相同版本及 ABI 回显，lane 不一致会使会话失败并关闭连接，不自动降级。

内部 `GuestSession.connect(device, { abi })` 使用 v4；不指定 abi 时保留 v3，
因此现有合规 wasm32 镜像保持原握手。高层公开 API 尚未选择 wasm64 镜像。
该提交曾在原生 syscall adapter 接入前禁止 wasm64 请求；下节的后续提交已移除
这项临时保护，改为按已协商的会话 ABI 编码。

11 项宿主回归及同套独立打包检查、类型检查通过，覆盖两种 ABI 的 v4、默认 v3、
短回复、错误身份、lane 不一致、关闭及当时的 syscall 保护。GCC/Clang 通过本地
socket pair 执行真实 C 握手，包括拒绝 native LP64 的 v3、错误 ABI 和错误 lane
版本；没有启动 PID 1，也不计作 Wasm 执行证明。更新后的
[目标编译](https://github.com/HighCWu/distro/actions/runs/38947236148) 已通过，
日志确认构建 `linux-agent-abi-wasm64`，包括 v4 agent C 与 ABI 静态断言。
[默认 wasm32 完整 agent 集成检查](https://github.com/HighCWu/distro/actions/runs/38947242982)
已通过，日志确认默认混合套件（宿主回归与启动 Linux 的集成用例）共 210 项，
零失败、零跳过。两项均固定 distro `943aae8`，不包含下述后续 syscall 改动，
不能用这次成功证明后续提交已回归通过。

## 按会话选择 syscall 布局

distro `70ad41c` 将 seek、truncate、路径与描述符 stat 接入已协商的会话 ABI。
wasm32 保留拆分参数与 104 字节结构；wasm64 使用原生参数与 128 字节结构。
原始 seek 结果保持 bigint，超出有符号 64 位的 offset/length 在发送前拒绝。
公开 number 字段不可精确表示时抛出 RangeError，不静默舍入；公开 seek 若收到
不可表示的结果，会在内核已改变文件位置后拒绝。调用者应留意这一副作用。
时间先以 bigint 合并秒与纳秒，再转换为毫秒；超过 JS Date 范围返回 null。

13 项新增 syscall/精度回归与更新后的 11 项会话回归均通过，独立打包执行也通过。
加上已有 stat 与 ABI 描述检查，共 30 项宿主测试及类型检查通过。覆盖负 offset、
两种参数布局、带偏移视图、errno、整数精度与 Date 正负边界。它们验证的是宿主
编码和解码，不能代替真实 wasm64 Linux 上的 agent syscall 运行。

## 最小原生运行检查

distro `165bdfd` 新增 `guest-agent-check-runtime-wasm64` 重型检查：用 wasm64 SDK
编译 `runtime-init.c`，以最小 initramfs 在 wasm64 内核中启动。测试外壳包含并调用
现有 agent 的 session worker；v4 校验、clone 后启动线程、vsock lane 与 syscall
执行器均为真实实现，没有复制另一套协议或在宿主模拟 syscall。

测试要求原生 executor 拒绝 v3 和显式 wasm32 身份，然后用 v4/wasm64 建立会话。
文件回归包含超过 4 GiB 的 seek、负相对 offset、非法负绝对 offset 的 EINVAL、
小文件 truncate/read/stat，以及 unlink/recreate 后原描述符的内容与 inode 分离。
两个并发 stat 请求也经过独立 lane。大 offset 检查只移动文件位置，不分配大文件，
不能作为大文件容量、内存分配或超过 4 GiB truncate 支持的证明。

GCC/Clang 的本地语法检查、TypeScript 检查和 Nix 格式检查通过；目标编译及实际
运行交给[公开 CI](https://github.com/HighCWu/distro/actions/runs/38949325409)，
固定上述提交。首次运行失败：目标程序已成功编译，日志确认 wasm64 内核启动并执行
`/init`，且输出 `agent-wasm64-runtime: ready`，但宿主仍在就绪等待阶段超时，尚未
进入握手或文件断言。不能把它记为 agent 请求链通过。检查不属于默认 wasm32
测试自动发现范围，必须显式运行：

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref YOUR_PUSHED_BRANCH \
  -f heavy-check=guest-agent-check-runtime-wasm64
```

该提交的外壳不执行生产环境的 root discovery/pivot，不启动用户子程序，不安装 wasm32
BusyBox，也不依赖完整 wasm64 rootfs。即使本项通过，也只证明 Node 上的最小
agent 请求链；生产镜像、进程/标准流、浏览器及高层公开镜像选择仍需分别验证。

## 进程与标准流增量

distro `c6d1980` 在同一最小检查中加入由 wasm64 SDK 编译的用户程序，不依赖 shell。
新增用例经现有 spawn/reap 与 `ChildProcess` 路径检查 PATH、argv、cwd、环境变量、
含 NUL 的 128 KiB + 17 字节标准流往返、独立 stderr、EOF、退出码 23 及 SIGTERM。
最后断开仍有运行程序的会话，重新连接后要求原 PID 的信号探测返回 ESRCH。
该提交发布时这些断言仍待运行验证；后续 `243a96d` 已取得下述 Node 运行证据。

生产 agent 原有 kill/reap 逻辑提取为共享 `cleanup_session_descendants`，生产入口与
最小测试外壳均调用它，行为保持按原 session 进程组清理。新增宿主 Linux 进程回归
在 GCC/Clang 下均通过：收养的同组后代被杀死并回收，无关进程保留，重复清理空组
成功。真实 C 握手回归、用户程序的宿主二进制流冒烟及 TypeScript 检查也通过；
这些宿主证据不能替代 Wasm 执行。已结束的 wasm32 基线之后，另行对该提交启动
[默认集成回归](https://github.com/HighCWu/distro/actions/runs/38950090520)，已通过。
该结果固定 `c6d1980`，不覆盖后续共享套件重构或生产根切换改动。
原有 wasm64 文件检查已经失败结束，不冒称包含本增量。

共享清理函数不新增跨 session、主动脱离原进程组的程序或浏览器崩溃后的清理保证。
生产 root pivot、完整 wasm64 用户态及真实浏览器执行仍不在这项最小检查范围内。

### 控制台就绪识别修正

distro `243a96d` 移除严格查找 `ready` 后紧跟 LF 的方式，改为复用已有 boot harness
的 `LineDecoder` 和 `writeConsoleLines`：接受 LF/CRLF，支持 UTF-8 与行的任意分块，
每个控制台流独立解码；只有完整、精确的 ready 行触发就绪，不将 EOF 残片视为成功。
就绪后的 syscall/进程断言没有删除或降级。新增 3 项回归与原有 helpers/protocol
测试合计 16 项通过，TypeScript 检查通过。

[wasm64 定向重跑](https://github.com/HighCWu/distro/actions/runs/38950484007) 固定该提交，
已通过。日志确认原生身份拒绝、文件 seek/truncate/stat、unlink/recreate、用户程序
参数/环境/标准流、退出码/SIGTERM，以及会话关闭后的进程清理和重连全部执行成功。
六组用例加外层测试共 7 项，零失败、零跳过。这次是实际 wasm64 Linux/用户程序
运行证据，不再仅是描述器、编译或宿主 mock 测试；范围仍限于 Node 最小启动外壳。

## 共享语料与浏览器矩阵

distro `7108d56` 将六组断言抽入 `agent-wasm64-suite.ts`，Node 入口继续使用原生
assert 和 test；浏览器使用经宿主回归检查的轻量断言适配器。参数、syscall、
数据与资源关闭检查共用，不另写浏览器专用的降级用例。资源以显式 finally 关闭，
不要求浏览器支持 `await using`。只有用户控制台的完整 ready 行可以建立就绪证据。

新增 `browser-tests-check-agent-wasm64-chromium/firefox`，复用完全相同的 initramfs，
要求精确的六组完成名称以及 machine.closed；报告门禁要求一个成功的浏览器测试，
零跳过、零重试。不启用实验性引擎参数，不跳过不支持 memory64 的引擎。
本地 19 项适配器、控制台及协议回归、类型检查、浏览器隔离打包和语法检查通过。
这些打包/宿主检查不构成真实浏览器运行证明。

固定该提交的 [Chromium](https://github.com/HighCWu/distro/actions/runs/38951454269)、
[Firefox](https://github.com/HighCWu/distro/actions/runs/38951462378) 和
[共享套件 Node 重跑](https://github.com/HighCWu/distro/actions/runs/38951533223)
中，Chromium 与 Node 已通过：Chromium 日志确认六组断言完成，Node 共 7 项通过、
零失败、零跳过。Firefox 已启动内核并输出就绪行，但随后等待 180 秒超时，
没有任何一组断言完成的日志，不能宣称双浏览器通过，也尚未确定卡住的具体阶段。
仍不包含生产 root discovery/pivot、完整软件包系统、挂载或网络矩阵。

## 原生生产入口与根文件系统

distro `dd5051b` 新增内部 `guest-agent.nativeWasm64`，以 wasm64 SDK 编译真实
`agent.c` 入口，强制检查 pointer/long 均为 64 位，而不是以测试 PID 1 代替。
产物随附 agent 的 MIT、musl 及 compiler-rt 许可声明；不改变依赖组件许可证。

`guest-agent-check-production-wasm64` 将该入口放入 initramfs，并构建显式 wasm64
软件包组成的只读 EROFS 根盘（标签 `LOWLAND_ROOT`）。它沿用内核已有的 rootfs
分层和 pivot_root 支持，无需修改 Linux。共享测试新增根标记、根挂载、proc/sys/devpts
及旧 initramfs 脱离检查，再运行原有六组文件和进程断言。根盘只包含测试程序及
必要目录，不是完整发行版，也未切换公开启动镜像。

软件包系统默认仍为 wasm32，新增显式架构参数并拒绝直接混入另一位宽的软件包
（允许 noarch）。[首次生产检查](https://github.com/HighCWu/distro/actions/runs/38952973425)
在格式门禁失败，未取得根切换运行证据，不能记为该功能通过。构建和运行继续由
公开 CI 承担：

```sh
nix build .#legacyPackages.x86_64-linux.guest-agent.nativeWasm64 -L
gh workflow run ci.yml --repo HighCWu/distro --ref YOUR_PUSHED_BRANCH \
  -f heavy-check=guest-agent-check-production-wasm64
```

## 握手等待边界

distro `5cea709` 修正传输连接成功后握手读写仍可能无限等待的问题。会话的
`timeoutMs` 分别限制连接和握手两个阶段，默认各 5 秒；lane 握手也有默认 5 秒
边界。超时关闭连接并抛出普通 Error，不冒充身份不匹配的 ProtocolError，因而
不会让负向身份断言误通过。新增挂起写入和挂起读取两项回归，与原有测试合计
13 项通过，类型检查通过。共享运行套件增加用例开始、各身份握手和机器清理日志。
这为 Firefox 故障定位提供边界和证据，不等于已经查明或修复其根因。
会话与 syscall 宿主测试合计 26 项通过，零失败、零跳过。

后续 `85fcbb9` 简化架构检查的求值表达式以避免冗余括号参与格式修正，
没有禁用格式门禁或更改架构断言。固定该提交的
[Firefox 重跑](https://github.com/HighCWu/distro/actions/runs/38953856289) 和
[生产入口重跑](https://github.com/HighCWu/distro/actions/runs/38953864071) 已分别结束，
两项均包含握手超时和新增阶段日志。Firefox 在首个旧版 v3 拒绝检查中约 3 秒后
收到不符合 ProtocolError 的错误，随后 machine.closed 正常完成；不是机器关闭卡住。
当前日志只显示断言外层错误，尚不能区分连接与握手超时，不据此归因浏览器引擎。
生产入口重跑已通过：日志确认真实入口输出就绪行、根标记与 EROFS 根挂载、
proc/sys/devpts、旧 initramfs 脱离，以及原有六组文件/进程/会话清理断言全部完成。
七组用例加外层共 8 项通过，零失败、零跳过。这固定 `85fcbb9`，不包含下述
后续高层客户端断言，不代表完整发行版或生产浏览器矩阵通过。

### 生产入口的浏览器矩阵

distro `6b59bdc` 新增 `browser-tests-check-agent-production-wasm64-chromium/firefox`。
两项直接使用生产 Node 检查暴露的 initramfs 和带标签 EROFS 根盘，而不依赖
Node 检查成功作为浏览器证据。浏览器挂载只读块设备，并在同一共享语料中要求
根切换检查和全部七组文件/进程用例（含高层客户端）。基线浏览器检查仍使用
最小外壳，不混用入口或资产。下载失败直接报错，不退回外壳或另一位宽。

两种模式复用浏览器断言外壳，但分别要求精确的七组或八组完成名称和 machine.closed；
报告门禁仍要求一个通过的测试、零跳过、零重试。新增 JS 的语法、共享套件类型、
浏览器打包、3 项断言适配器回归与 Nix 格式检查通过；这些不是浏览器运行证明。

[生产 Firefox](https://github.com/HighCWu/distro/actions/runs/38954969112) 固定
`6b59bdc`；[生产 Chromium](https://github.com/HighCWu/distro/actions/runs/38955273955)
和[基线 Firefox](https://github.com/HighCWu/distro/actions/runs/38955281226) 固定
`498dbce`。生产 Firefox 已失败，基线 Firefox 仍待确认。生产 Chromium 已通过：
日志确认全部八组断言完成（含真实根切换、高层文件与进程 API），机器正常关闭，
浏览器测试共 1 项通过，报告门禁明确确认零跳过、零重试。这是真实浏览器的生产
入口证据，但仍使用 initramfs 启动 agent，不证明下节 GPT 磁盘启动或完整发行版通过。
后两项因触发时的远端版本，不包含 `14755d0`
的诊断改进；不取消已有运行，也不将它们当作新诊断已经验证。

distro `14755d0` 将拒绝断言的原始错误名称和消息写入外层错误，同时保留 cause，
避免浏览器测试序列化时丢失内层错误。新增回归区分连接与握手超时，两者都必须
导致身份断言失败；4 项断言适配器回归通过。该变更只补诊断，不宣称修复 Firefox。

## 后续接入顺序

### 高层客户端的原生 ABI 接入

distro `5965a37` 让内部 `create_guest_client(vsock, { abi: "wasm64" })` 将 ABI
身份固定到会话及其所有 lane。省略选项仍是原有 v3/wasm32；显式 wasm32 使用 v4。
身份在创建时复制，后续修改调用方选项不影响它；拒绝后的重试仍用相同 ABI，
不自动退回 wasm32。此入口尚未从公开包导出，也不改变 `guestAgent()` 的默认镜像。

新增 5 项宿主回归覆盖三种选择、会话复用、选项快照、拒绝重试与非法 ABI；
连同会话和 syscall 回归共 31 项通过。类型检查、浏览器隔离打包和语法检查通过，
但它们不是目标运行证据。

共享 Node/浏览器语料新增第七组检查：通过高层文件 API 写入、读取、stat、
truncate、删除、超过 4 GiB 的 seek，以及通过 exec 启动原生用户程序并核对退出码。
原有六组未删减，浏览器要求精确的七组完成名称；生产模式另含根切换检查。
[新增 Node 运行检查](https://github.com/HighCWu/distro/actions/runs/38954442131)
固定 `268c761`（实现与文档），已通过。日志确认新增高层文件/进程用例实际完成，
七组加外层共 8 项通过，零失败、零跳过。`85fcbb9` 的 Firefox/生产检查不包含
这组新增断言；本次成功仍限于 Node 最小外壳，不能证明生产或浏览器高层 API 已通过。

### 原生引导磁盘

distro `e97db21` 抽出 `image.mkGptDisk`，保留原 wasm32 agent 的分区起点、尺寸
计算、固定 GUID 和 `sgdisk --verify`，新增分区标签检查。原 wasm32 镜像改为调用
该共享构造器，格式和标签不变；其实际行为仍需下述集成回归确认。

distro `c6ff369` 在 `guest-agent.nativeWasm64.bootDisk` 打包 GPT 包裹的 EROFS
引导文件系统，分区和文件系统标签均为 `LOWLAND_AGENT`。其中 `/init` 是真实
LP64 agent 二进制，不经 wasm32 shell/BusyBox。文件系统使用显式 wasm64 软件包
元数据，保留 musl、compiler-rt 与 agent 的许可声明，并准备只读引导阶段的挂载点。
这不是完整系统根盘，也未切换公开 `guestAgent()` 的 wasm32 默认镜像。

新增 `guest-agent-check-boot-disk-wasm64` 不传入外部 initramfs，而以
`root=PARTLABEL=LOWLAND_AGENT rootfstype=erofs ro rootwait init=/init` 启动。
系统根盘故意排在 agent 磁盘前面，要求 Linux 按 GPT 标签寻找引导根，然后由
真实 agent 切换到 `LOWLAND_ROOT`；继续执行根切换和全部七组文件/进程断言。
测试外壳禁止同时传入 initramfs 和引导磁盘，避免绕过被测启动路径。

```sh
nix build .#legacyPackages.x86_64-linux.guest-agent.nativeWasm64.bootDisk -L
gh workflow run ci.yml --repo HighCWu/distro --ref YOUR_PUSHED_BRANCH \
  -f heavy-check=guest-agent-check-boot-disk-wasm64
```

类型检查、浏览器共享语料打包/语法检查、4 项浏览器断言适配器回归及 Nix 格式
检查通过。固定 `c6ff369` 的[磁盘启动检查](https://github.com/HighCWu/distro/actions/runs/38955898504)、
[wasm32 完整集成回归](https://github.com/HighCWu/distro/actions/runs/38955905288) 和
[带完整错误诊断的生产 Firefox](https://github.com/HighCWu/distro/actions/runs/38955911495)
中，磁盘启动已通过：日志确认根切换及全部七组文件/进程断言完成，八组加外层共
9 项通过，零失败、零跳过。wasm32 回归仍待确认。Firefox 已失败，完整错误确定
为 `agent v3/wasm32 handshake timed out`：传输连接已建立，首次 v3 握手超时，
机器随后正常关闭；尚不能确定是数据投递、会话初始化还是拒绝后的关闭通知问题。
本次磁盘成功固定 `c6ff369`，不包含下一节新增的公开镜像选择接口。

### 显式公开镜像选择

distro `8fb34f7` 新增 `guestAgent({ abi: "wasm64", image })`，调用方提供匹配的
GPT agent 磁盘，仍由插件负责启动参数、vsock、就绪等待和高层能力，不必自行创建
内部会话。默认 `guestAgent()` 保持打包 wasm32 镜像和 v3；显式 ABI 使用 v4，
无自动降级。公开 `GuestAgentOptions` 为判别联合，并导出 `AgentAbi` 类型。

运行时也检查 JavaScript 调用：自定义镜像必须显式指定 ABI，wasm64 不得误用默认
wasm32 镜像，镜像必须是非空且整扇区的 Uint8Array。创建时复制输入视图，避免
调用方之后修改字节或选项改变已选镜像。形状检查不等于解析或验证镜像内程序位宽，
真正的内核加载与握手验证仍不可省略。必须使用匹配的 wasm64 内核和独立系统根盘；
这不是将默认发布的内核/根盘包全体切换到 wasm64。

4 项镜像选择回归连同会话、syscall 和客户端回归共 35 项宿主测试通过；类型检查及
公开入口的浏览器打包/语法检查通过。新增 `guest-agent-check-public-wasm64` 通过
公开导出创建 agent，不传 initcpio 或手写启动参数；检查根切换、只读根、文件 seek/
metadata/truncate、`run()` 的退出码及 argv/env/cwd。它复用磁盘启动检查的资产，
不以那项检查的成功代替自己的运行结果。
[公开启动检查](https://github.com/HighCWu/distro/actions/runs/38956757415) 固定
`a0498bc`（实现及说明），已通过：日志确认三个子用例实际完成，加外层共 4 项，
零失败、零跳过，并正常等待机器关闭。这证明 Node 上的公开插件路径，不是浏览器
公开插件、完整发行版或默认 npm 发布包已切换到 wasm64 的证明。

### 会话阶段诊断

distro `af5a160` 新增默认关闭的 `lowland.agent.trace=1`，记录接受连接、clone、
会话 worker、lane listener、reaper 创建、握手读取和接受/拒绝退出阶段及 PID，
不输出请求载荷或程序数据。共享运行检查显式启用，便于定位 Firefox 超时在哪一层，
不增加实验性引擎参数，不延长原握手期限或放宽断言。

GCC/Clang 的真实握手回归与新增日志回归通过，检查默认静默、启用输出及 errno
保留；生产 agent 和测试入口的严格语法检查、TypeScript 检查通过。该增量只补
诊断，尚未证明 Firefox 根因已修复。构建和运行继续交由公开 CI，旧版任务不因
运行较久而重启或取消。
[带阶段日志的生产 Firefox](https://github.com/HighCWu/distro/actions/runs/38957371982)
固定 `af5a160`，已通过：日志确认 v3 和显式 wasm32 握手被拒绝，wasm64 握手
被接受，根切换及全部七组文件/进程断言完成，机器正常关闭。外层 1 项浏览器
测试通过，报告门禁确认零跳过、零重试。这是启用阶段日志后的成功结果；日志可能
影响时序，不能据此确定此前超时的根因或宣称默认关闭日志时的问题已经修复。

### 公开插件浏览器检查

distro `688fdba` 将已通过 Node 的三组公开 API 断言抽成浏览器可复用语料，新增
`browser-tests-check-agent-public-wasm64-chromium/firefox`。使用公开镜像/ABI
选择、独立系统根盘和 GPT agent 磁盘，不传外部 initramfs 或手写启动参数，也不
启用会话阶段日志。根切换与只读根、文件 seek/metadata/truncate、进程退出码及
argv/env/cwd 均为必须完成的断言；另要求机器关闭和精确报告门禁，不允许跳过、
重试或退回内部客户端。浏览器 import map 将 kernel 及其 plugin 入口指向同一
安装包，保留插件身份符号，避免打包另一份符号后无法识别公开插件。

类型检查、共享语料浏览器打包、JavaScript 语法和 4 项断言适配器测试通过。
以下公开 CI 均固定 `688fdba`，已通过检查发现与 derivation 求值阶段，运行结果
现已全部通过；此前 Node 成功没有替代此次共享语料重构后的复验：

- [公开 Chromium](https://github.com/HighCWu/distro/actions/runs/38958330336)
- [公开 Firefox](https://github.com/HighCWu/distro/actions/runs/38958337096)
- [公开 Node 复验](https://github.com/HighCWu/distro/actions/runs/38958343918)

两项浏览器日志均确认三组断言完成，外层 1 项测试通过，精确报告门禁确认零跳过、
零重试；返回结果同时要求机器关闭。Node 日志确认三组加外层共 4 项通过，零失败、
零跳过。它们未启用会话阶段日志，但没有覆盖故意错误 ABI 的拒绝/重连序列。
固定 `c6ff369` 的既有 wasm32 完整集成回归也已通过：日志为 233 项通过，
零失败、零跳过；这不是下文新 musl pin 的回归结果。

### 下一步

已新增两项并行推进的增量：

- distro `9aa970e` 恢复共享运行语料默认不启用会话阶段日志；诊断仍可显式开启。
  [无日志生产 Firefox 复验](https://github.com/HighCWu/distro/actions/runs/38958737342)
  固定该提交，已失败：v3 拒绝完成后，显式 wasm32 的 v4 握手超时。与此前
  首次 v3 超时不同，再次说明问题有时序敏感性；公开插件的正确 wasm64 握手
  成功不能替代错误 ABI 拒绝序列的验证，尚未确定根因。
- distro `787177d` 新增 `stdenv-wasm64`、`apk-wasm64`、`image-wasm64` 和
  `busybox-wasm64`：显式选择匹配的工具链、sysroot、Linux 头文件、包架构和
  BusyBox 引导镜像。复用既有安装系统检查，不混入 wasm32 loader。
  [安装后的 BusyBox smoke](https://github.com/HighCWu/distro/actions/runs/38958962664)
  已完成编译并成功挂载 ext4 根盘，但 `switch_root` 报旧根不是 ramfs/tmpfs 后
  PID 1 退出，smoke 未通过。其目标为真实
  shell、文件操作、管道、命令替换、time/ts；不是另一个单文件 C 启动测试。
  进程与 loopback 网络仍是独立检查，尚不宣称通过；浏览器和完整发行版也未覆盖。
  默认包 scope、发行仓库和 npm 镜像保持 wasm32。BusyBox 保持 GPL-2.0-only，
  构建基础设施的 MIT 不改变它的许可或对应源码交付义务。

### 原生文件系统统计 ABI 修正

上述 BusyBox 失败对应一处实际的 musl ABI 错配：Linux asm-generic 在 LP64
为 43/44 号选择双参数 `statfs/fstatfs`，而旧 wasm 头文件无条件声明
`statfs64/fstatfs64`，使 musl 通用实现按三参数 ABI 传入额外的结构体大小。此时大小值会
占据内核期望的输出指针位置，能够产生 EFAULT；调用方得到的零值结构体会导致
文件系统类型检查失败。不能把这个现象当作 nullfs 或 ext4 挂载失败，更不能绕过
BusyBox 的根类型保护。

musl `5baebf92200899c02ea4f36f9b16d66dea79297e` 按 long 位宽选择名称，保留
wasm32 的三参数接口。双位宽轻量编译检查通过；distro `a3e7fad` 新增真实根目录
的 statfs/fstatfs/statvfs/fstatvfs 返回值、根类型和元数据断言，`5cfce7b` 更新
musl pin。hash 由[公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/38960110635)
确认；`fc6e24a` 将 C 运行检查接入独立重型检查，保留原运行产物入口的别名。

另有 distro `5f592b0` 的 BusyBox 链接产物检查，要求位宽匹配的单个共享
env.memory、无自定义 memory，且声明上限与平台一致；3 项宿主回归通过，包括
双位宽接受和非法输入拒绝。这项结构检查不等于运行成功，也不保证宿主能分配上限。

以下四项均固定 `fc6e24a`，现已全部通过，日志均确认实际 `::vm-test::pass`。
BusyBox 构建日志分别确认共享 wasm32/wasm64 env.memory，声明上限为 4/16 GiB；
声明上限不代表宿主实际能分配该容量。wasm64 安装系统已完成原先失败的根切换和
完整 smoke，新增文件系统统计断言也在两个位宽实际完成：

- [wasm64 BusyBox smoke](https://github.com/HighCWu/distro/actions/runs/38960354491)
- [wasm32 BusyBox smoke](https://github.com/HighCWu/distro/actions/runs/38960361134)
- [wasm64 C 运行回归](https://github.com/HighCWu/distro/actions/runs/38960367458)
- [wasm32 C 运行回归](https://github.com/HighCWu/distro/actions/runs/38960373351)

### 后续验证

#### 公开插件接入原生 shell

distro `50e37e4` 增加 `guest-agent-check-public-userland-wasm64` 和对应的
Chromium/Firefox 检查。通过 wasm64 包构造器把 BusyBox 安装到独立系统根盘，
与原有原生测试程序共同组成版本匹配的用户态；不改变默认 wasm32 scope 或镜像。
三宿主共享语料和真实根盘/引导盘资产，不依赖其它检查成功的结果。

新增第四组断言从公开 `run()` 启动 `/bin/sh`，检查 cwd、带空格 argv/env、
管道、命令替换、文件复制/读取/删除、非零子进程退出和后台子进程 wait。要求精确
stdout、空 stderr、成功状态、四组断言完成和机器关闭；不存在 shell 时直接失败，
不退回单个 C 程序，也不传外部 initramfs、手工启动参数或会话 trace 标志。

TypeScript、浏览器共享语料打包、JS 与 shell 语法检查通过，7 项相关宿主断言及
二进制契约测试通过。以下三项均固定 `50e37e4`，现已失败：前三组完成，但
shell 在 `set -eu` 处退出，三宿主日志均报 `sh: set: -eu: invalid option`。

- [公开原生 shell Node](https://github.com/HighCWu/distro/actions/runs/38961589917)
- [公开原生 shell Chromium](https://github.com/HighCWu/distro/actions/runs/38961598074)
- [公开原生 shell Firefox](https://github.com/HighCWu/distro/actions/runs/38961604793)

BusyBox 保持 GPL-2.0-only，自有构建/测试代码采用 MIT。这里的测试根盘不等于
完整发行版或正式发布，分发时仍需履行组件各自的许可与对应源码义务。

#### 公开 exec 的二进制管道与背压

distro `515dc27` 将 userland 语料扩为五组，新增公开 `exec()` 调用原生 shell 的
`tee | cat` 管道。输入为 256 KiB + 17 字节的确定性数据，包含 NUL，跨越注入 I/O
块和 Linux pipe 容量；以 8191 字节分块写入，同时读取 stdout、stderr 并等待退出。
要求两路输出逐字节等于输入、退出成功且临时文件已删除。子进程在 finally 关闭，
最外层仍要求机器关闭，浏览器门禁精确要求五组用例，不能跳过新用例获得成功。

TypeScript、浏览器打包、JS 语法和 7 项相关宿主断言/二进制契约回归通过。这些
轻量检查不证明实际 Wasm 程序通过。以下三项固定含文档的 `316d7b0`，已提交
公开 CI，现均已失败。它们仍包含同一条不受支持的 `set -eu`，需要下述修正，
不能把编译通过视为运行验证通过；原任务未取消或重启：

- [二进制管道 Node](https://github.com/HighCWu/distro/actions/runs/38963030942)
- [二进制管道 Chromium](https://github.com/HighCWu/distro/actions/runs/38963038435)
- [二进制管道 Firefox](https://github.com/HighCWu/distro/actions/runs/38963045467)

#### 固定 hush 的能力边界与命令语料修正

固定 BusyBox `4ad91c87` 的 `shell/hush.c` 仅实现 pipefail、noexec、errexit
及可选 xtrace，没有 nounset；这不是配置开关或 wasm64 argv 传递错误。
distro `8122442` 将共享命令提取到独立文件，使用受支持的 `set -e`，保留 cwd、
参数、环境、数据和退出断言，未新增 shell、未声称补齐 POSIX shell。更完整的
shell 支持仍属于用户态软件工作，不能以本次测试修正代替。

两项新增宿主回归检查脚本语法、fail-fast 首语句和明确的输入值断言，并实际在
隔离临时目录运行同一二进制管道命令，核对双路输出、文件清理及空 TMPDIR 的失败。
TypeScript、浏览器打包、相关宿主检查通过；它们不替代真实 Linux/Wasm 执行。
主仓库轻量 CI 已接入该回归。以下三项固定 `189a7a7`，现均已失败；Node 和
Firefox 日志确认前三组通过，shell 仍以状态 1 退出且无具体 stderr，下一处失败
尚未唯一定位，不能把去掉 nounset 误写成整个 shell 场景已经修复：

- [修正后 Node](https://github.com/HighCWu/distro/actions/runs/38963628226)
- [修正后 Chromium](https://github.com/HighCWu/distro/actions/runs/38963636320)
- [修正后 Firefox](https://github.com/HighCWu/distro/actions/runs/38963643976)

#### 公开网络插件与原生 HTTP 服务

distro `36578fd` 增加独立的 `public-network-wasm64` 检查和对应浏览器入口，
复用原生 BusyBox 用户态资产，不依赖 userland 检查的成功产物。先前的三组最小
公开 API 和五组 userland 检查保持独立，新网络配置共要求六组完成。

网络 attachment 插件刻意放在 agent 之前，验证启动依赖排序和真实 eth0 配置。
通过公开 `exec()` 启动 BusyBox httpd；读取 `/proc/net/tcp` 确认精确端口处于
LISTEN 后，从公开 `attachment.connect()` 发起 HTTP 请求，要求 200 与精确正文。
随后 SIGTERM 终止并回收服务、要求空 stdout/stderr，关闭连接、网络及机器。
启动失败也关闭网络；错误和超时不改为跳过。

本项不启用 DNS 或外连适配器，禁止意外外连。它验证浏览器/Node 到运行实例的
私网 Ethernet/TCP，不代表浏览器原始 socket、外网、代理、TLS、DNS 或 UDP 已验证，
也不替代安装系统的独立回环网络检查。

TypeScript、JS 语法、浏览器打包和 10 项相关宿主回归通过。其中新增 socket
就绪解析回归拒绝错误端口、已建立连接及仅远端端口匹配。以下三项均固定含文档的
`1e99e15`，已提交公开 CI，实际执行结果待确认；shell 复验仍独立运行：

- [公开网络 Node](https://github.com/HighCWu/distro/actions/runs/38964197663)
- [公开网络 Chromium](https://github.com/HighCWu/distro/actions/runs/38964203587)
- [公开网络 Firefox](https://github.com/HighCWu/distro/actions/runs/38964210907)

其中 Firefox 已失败在前置 shell 场景，HTTP 用例尚未执行；不能记作 HTTP 本身
失败或通过。Node、Chromium 尚待结果。

#### run() 的异常清理和定向 shell 诊断

distro `8045aad` 修正公开 `run()`：原实现直接收集 status、双路输出和 stdin EOF，
没有 dispose 路径。现在将原收集逻辑提取为内部模块，成功和异常都等待 child.close，
非零退出仍返回 RunResult；仅清理失败则报告该错误，主错误与清理错误同时出现则
用标准 AggregateError 保留两者并设置 cause。没有依赖仍在提案阶段的运行时特性。

六项新增宿主回归在原收集逻辑均失败，修正后通过，涵盖二进制输出、EOF、非零
退出、输出失败后先清理、status/输入失败，以及双重错误。与双位宽关闭回归共
14 项通过，再加共享命令回归共 16 项通过；TypeScript 和浏览器打包通过。
真实公开 shell 语料增加运行中命令取消：先以 rename 原子发布就绪标记，再取消，
要求原取消原因并成功执行下一条命令；不是 spawn 前直接拒绝的假覆盖。

由于 shell 修正批次仍在无标签断言处失败，`ad0186a` 为每条既有检查增加精确失败
标签和值，不删除断言、不启用全局会话 trace。宿主验证错误 cwd 会以指定标签
失败。当前优先启动定向 Node 和 wasm32 集成，待定位后再铺开新的浏览器复验，
避免在同一未定位失败上重复扩展矩阵；已有任务没有取消。

- [带标签的公开 Node / run 清理](https://github.com/HighCWu/distro/actions/runs/38965682439)
- [run 清理后的 wasm32 集成](https://github.com/HighCWu/distro/actions/runs/38965689912)

两项均固定 `ad0186a`。Node 已失败，实际日志定位到 `child-status [0]`：前三组公开
API 用例通过，shell 在保存子进程退出状态处失败，第五组 256 KiB + 17 字节的
二进制管道也已通过。wasm32 结果仍待确认。

固定 BusyBox hush 源码 `shell/hush.c` 的 `run_list()` 在跳过失败条件的 THEN 分支
时执行 `G.last_exitcode = rcode = EXIT_SUCCESS`，因此进入 ELSE 才保存 `$?` 会得到 0。
distro `f62f9d1` 改为 `command || status=$?` 立即保存，仍严格要求退出状态为 7，
没有修改内核、libc 或 BusyBox 源码。新增宿主测试也要求退出 0 或 23 时该断言失败；
共 18 项相关宿主回归、TypeScript 和浏览器打包通过。这是兼容已固定的 hush 行为，
不宣称完整 POSIX shell 语义，也尚未证明取消检查及整个 shell 场景实际通过。

[定向 Node shell/管道/HTTP 复验](https://github.com/HighCWu/distro/actions/runs/38967861065)
固定 `82bd0d4`，先验证包含 shell 前置检查的六组完整语料，再决定浏览器网络复验。

#### 不含测试程序的最小系统根盘

distro `380d21d` 暴露 `guest-agent.nativeWasm64.rootfs`，仅安装匹配的 wasm64
BusyBox 和最小文件系统配置，使用独立的 wasm64 仓库，不包含 runtime-child 或
测试标记。它与 `nativeWasm64.bootDisk`、`kernel-wasm64` 配套，不切换默认 wasm32
npm 资产。构建命令及挂载方式见源码 `packages/linux-guest/README.md`。

独立 `guest-agent-check-minimal-root-wasm64` 通过公开 API 启动该实际根盘，检查
DNS 配置、测试程序缺席、随包许可证、文件写入/原生 BusyBox cat 的二进制往返、
基本 shell pwd 和机器关闭。TypeScript 与 17 项相关宿主回归通过；
[实际启动检查](https://github.com/HighCWu/distro/actions/runs/38966392888)固定 `1f6f85a`，
现已成功；实际日志确认最小系统完成标记、1 项通过、零失败、零跳过。
它不替代复杂 shell、浏览器、网络或后续根盘版本的验证，
也不是配套源码与发布清单已经齐全的正式发行。

后续 distro `0bb77e7` 为该独立 wasm64 根盘增加 `/etc/passwd`、`/etc/group` 的
UID/GID 0 名称记录，以及 `/etc/mtab → /proc/mounts`。通用根盘模板的新增配置参数
默认留空，不改变默认 wasm32 根盘内容。检查扩展为验证配置内容、原生 `id -un`
输出 `root`、挂载表非空且能通过链接读取；不代表提供登录认证或多用户隔离。
TypeScript 检查和 17 项相关宿主回归通过，新增目标断言仍待公开 CI 验证。
[扩展后的实际根盘检查](https://github.com/HighCWu/distro/actions/runs/38967110788)
固定 `55ead4c`，现已成功；实际日志确认最小系统完成标记、1 项通过、零失败、零跳过。
该次检查包含身份文件内容、原生 `id -un` 和挂载表链接读取，不覆盖后续共享语料版本。

distro `65310ff` 将实际最小根盘的四组语料提取为 Node/浏览器共享实现，新增
Chromium 和 Firefox 定向检查：身份及挂载表、许可证及无测试程序、BusyBox 二进制
往返、基本 shell cwd。浏览器要求完整四组名称、机器关闭、精确外层用例及零跳过、
零重试；不以 Node 成功替代浏览器结果。TypeScript、浏览器打包及 4 项浏览器断言
适配器宿主测试通过，以下三项均固定 `78ce491`，实际结果仍待确认：

- [最小根盘 Node](https://github.com/HighCWu/distro/actions/runs/38967783538)
- [最小根盘 Chromium](https://github.com/HighCWu/distro/actions/runs/38967769877)
- [最小根盘 Firefox](https://github.com/HighCWu/distro/actions/runs/38967777005)

#### SDK 子进程关闭与回收顺序

distro `6e6047c` 修正实际 SDK 的 `ChildProcess.close()`：原实现仅等待缓冲输入和
描述符关闭，未等待 status/reap，因此可能在进程槽释放前返回；正常回收完成后的
dispose 还会再次对原数字 PID 发 SIGKILL。新增的三项可控宿主回归在旧实现均失败。

修正后，成功 reap 会记录状态；已确认回收的进程关闭时不再发送信号。关闭仍先
终止运行进程、等待缓冲输入和关闭描述符，之后等待 status 完成与槽释放，即使
描述符关闭失败也不跳过等待。取消原因继续由 status 返回，不被 dispose 覆盖。
这不是 pidfd 或完整进程组管理，不宣称消除所有 signal/reap 并发竞态。

双位宽共八项可控协议回归通过，覆盖延迟回收、幂等关闭、回收后不发送信号、取消
原因及描述符关闭错误；独立打包后也通过，主仓库轻量 CI 无需安装整个 workspace
即可执行。TypeScript、浏览器语料打包和相关三项命令/就绪回归通过。真实 wasm64
语料补充 SIGKILL disposal 返回前必须释放槽的断言，wasm32 语料也检查关闭返回时
status 已完成。

以下四项固定含文档的 `5c4d1bb`。Node、Chromium、Firefox 均已通过；实际日志确认
Node 为 9 项通过、零失败、零跳过，两个浏览器均完成 8 个内部场景、外层 1 个用例
通过，严格门禁确认零跳过、零重试。wasm32 集成仍待确认。先前 shell 和网络任务
保持独立，没有因等待而被重启或取消；此结果不代表公开 BusyBox shell 场景通过：

- [进程关闭 Node](https://github.com/HighCWu/distro/actions/runs/38964964797)
- [进程关闭 Chromium](https://github.com/HighCWu/distro/actions/runs/38964971985)
- [进程关闭 Firefox](https://github.com/HighCWu/distro/actions/runs/38964979535)
- [wasm32 完整集成](https://github.com/HighCWu/distro/actions/runs/38964986294)

#### 错误身份的会话资源顺序

distro `f0ef828` 收紧会话资源创建顺序：先验证握手身份，再创建子进程回收线程和
lane worker 属性。不匹配 ABI 的拒绝路径保持单线程退出，不再为无请求可执行的
会话创建回收线程。lane listener 仍在握手 echo 前绑定，不改协议布局、超时时间
或错误断言；身份接受后资源创建失败则终止会话，不在缺少回收线程时服务请求。

GCC/Clang 的真实 socketpair 握手及资源顺序测试通过，覆盖错误 ABI/版本不创建
线程、正确身份创建一次回收线程、线程创建失败返回错误，并保持 detached lane
属性。该宿主测试拦截了 pthread_create，不是 Wasm 调度器的复现。已有真实进程
清理回归及生产入口严格语法检查也通过；不能据此声称 Firefox 已修复。

以下三项固定 `f0ef828`，均默认不启用阶段日志，现已全部通过；前一批 libc/BusyBox
任务保持独立运行并已全部通过，没有被重启或取消：

- [生产 Firefox](https://github.com/HighCWu/distro/actions/runs/38960838496)
- [生产 Chromium](https://github.com/HighCWu/distro/actions/runs/38960845879)
- [生产 Node](https://github.com/HighCWu/distro/actions/runs/38960853049)

实际日志确认 Chromium 和 Firefox 都依次完成拒绝旧 v3、拒绝显式 wasm32、接受
显式 wasm64，且各有 1 个浏览器用例通过，严格门禁确认零跳过、零重试。Node 为
9 项通过、零失败、零跳过。本次默认关闭 trace 的 Firefox 回归已通过，但尚不能
仅凭单次成功证明历史超时的唯一根因，仍需保留后续重复回归。

#### 安装系统的独立进程、网络与许可检查

以下两项固定 `3d47240`，均已通过，实际日志确认 `::vm-test::pass`；不依赖公开 shell 场景
通过，也不能被 shell smoke 的成功代替：

- [wasm64 BusyBox 进程](https://github.com/HighCWu/distro/actions/runs/38962167511)：
  继承描述符、定时终止、PTY/script、后台守护进程、ifup/down hook 和 crond。
- [wasm64 BusyBox 回环网络](https://github.com/HighCWu/distro/actions/runs/38962173958)：
  HTTP、FTP 目录列表、TCP/UDP 服务；不是浏览器外网连通性验证。

distro `684f996` / `a798519` 为双位宽 BusyBox 安装上游 LICENSE、对应 musl
COPYRIGHT、实际选用 compiler-rt 源码的 LICENSE.TXT 和说明文件到
`/share/licenses/busybox/`。安装后的 smoke 要求四个文件均非空。

以下两项固定包含该变更的 `2b34bfb`，均已通过，实际日志确认 `::vm-test::pass`：

- [wasm64 安装 smoke 与许可文件](https://github.com/HighCWu/distro/actions/runs/38962531852)
- [wasm32 安装 smoke 与许可文件](https://github.com/HighCWu/distro/actions/runs/38962537913)

这些文件不包含对应源码包或书面源码提供承诺，不构成完整发布合规证明。
BusyBox 保持 GPL-2.0-only，不将本项目的 MIT 声明用于重新许可第三方软件。

1. 保持目标 ABI 编译检查，并验证新增 v4 代码的目标编译及现有 wasm32 会话回归；
   头文件与描述不一致时，以真实目标 ABI 为准修正。
2. 保留默认关闭日志的 Firefox 生产入口复验并观察后续稳定性；
   单次成功不作为历史时序敏感问题根因已唯一确定的证明。
3. 检查新接入的公开镜像选择链路在浏览器和 Node 的结果，并保留 wasm32 回归。
4. 验证新接入的原生 BusyBox 构建与安装系统，再扩展匹配位宽的启动镜像和用户态；
   不混用 wasm32 BusyBox/rootfs，wasm64 SDK 不等于整个发行版 scope 已转换。
5. 在 Node 和真实 Chromium/Firefox 验证启动、进程/标准流、metadata、大 offset、
   删除后打开描述符、挂载、网络及关闭，同时保留 wasm32 回归。

这些增量不改变 Linux UAPI 或组件许可证。新增自有描述器、测试和构建检查采用 MIT；
内核、libc 和工具链仍遵循各自上游许可证。
