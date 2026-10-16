<!-- SPDX-License-Identifier: MIT -->

# 高层 agent 的 wasm64 接入

目标是在已有 wasm64 内核、SDK 和浏览器用户程序路径上，继续提供匹配位宽的
进程、文件、挂载及网络 API。当前 `@lowland/guest` 公开启动路径仍使用 wasm32；
内部原生 wasm64 会话、文件与进程请求链已在 Node 最小启动检查和 Chromium 的
生产入口/根切换检查中运行通过；Firefox、GPT 磁盘启动和完整发行版仍需分别验证。
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
已启动、结果待确认。编译、实际磁盘构建及启动在公开 CI 执行，不以本地类型或
格式检查替代启动证据；旧版浏览器任务保留，不因运行较久而重启或取消。

### 下一步

1. 保持目标 ABI 编译检查，并验证新增 v4 代码的目标编译及现有 wasm32 会话回归；
   头文件与描述不一致时，以真实目标 ABI 为准修正。
2. 定位 Firefox 就绪后的等待问题，验证生产入口的根切换；已通过的 Chromium
   生产入口和 Node 最小外壳不代替 Firefox、GPT 磁盘启动或后续改动的验证。
3. 验证原生 GPT 磁盘启动，再接入高层镜像选择，保持现有 wasm32 会话兼容性。
4. 构建匹配位宽的完整启动镜像和用户态，不混用 wasm32 BusyBox/rootfs。
   wasm64 SDK 不等于整个发行版 scope 已转换为 wasm64。
5. 在 Node 和真实 Chromium/Firefox 验证启动、进程/标准流、metadata、大 offset、
   删除后打开描述符、挂载、网络及关闭，同时保留 wasm32 回归。

这些增量不改变 Linux UAPI 或组件许可证。新增自有描述器、测试和构建检查采用 MIT；
内核、libc 和工具链仍遵循各自上游许可证。
