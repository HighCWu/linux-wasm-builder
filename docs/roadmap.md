<!-- SPDX-License-Identifier: MIT -->

# Linux/Wasm 平台路线图

路线图以持续完善 Linux 在 WebAssembly 上的可用性为核心。内核、工具链、用户态、
宿主和发行可以并行推进。用户地址保持direct linear-memory模型；各阶段编号用于组织
依赖和验收，除明确依赖外，所有工作流都应持续推进。

## 全程原则

- 浏览器和 Node 同时验证，浏览器是首要产品环境。
- 优先修复平台能力，避免用越来越多的应用补丁长期掩盖内核或 libc 缺口。
- 每项能力都要有最小测试、真实应用测试和失败语义测试。
- 项目自有实现优先 MIT；LLVM遵循 LLVM exception；Linux修改留在GPL边界。
- 发布物必须可从固定源码重建，并附带许可证清单和对应源码。
- 重型构建和跨平台测试优先使用公开仓库的标准 GitHub-hosted Actions runner，减少对
  开发者本地磁盘和算力的要求；本地应能只运行文档、配置和受影响组件的轻量检查。

## 构建资源策略

- Linux、LLVM、完整rootfs、浏览器集成和测试矩阵在CI中构建，不要求开发者在本地
  同时保留全部构建树。
- Actions工作流使用最小权限；来自fork的代码不得在可访问发布凭据的任务中执行。
- 按组件和路径拆分任务，使用精确源码pin作为缓存键，避免无关修改重复构建全套产物。
- 缓存只保存可安全复用且重建成本高的内容，并设置容量和失效策略；缓存不是发布物。
- 临时测试artifact采用较短保留期。需要长期保留的版本化二进制、SBOM和对应源码包
  应发布到GitHub Releases，而不是长期占用Actions artifact空间。
- 日常PR运行必要的构建和测试；耗时较长的完整矩阵可按合并、定时或手动触发分层运行。
- 工作流不得假设免费额度、runner规格或保留政策永久不变；启用付费runner或外部付费
  服务前必须单独评审。

## P0：可复现上游基线

- 添加 `HighCWu/distro`、`linux`、`llvm-project`、`musl` submodule并固定提交。
- 将 distro/Nix中的 Linux、LLVM和musl来源更新到对应 HighCWu fork的精确commit pin。
- 校验主仓库submodule指针与distro pin一致，避免集成仓库展示的版本与实际构建版本
  分离。
- 可选提供显式的 `sources/*` 本地override，用于尚未推送的跨仓库协同开发；正式构建
  和CI不依赖该override。
- 原样构建并启动现有 Linux/Wasm，不混入新功能。
- 固定 browser engine、Node、LLVM、Linux、musl和Nix版本。
- 建立 hello、线程、文件、进程、网络和关机基线。
- 生成 SBOM、NOTICE和 Linux/rootfs对应源码包。
- 建立GitHub Actions基线工作流，并记录每项任务的触发条件、预计时长、缓存和artifact
  保留策略。

退出条件：任意开发者可从干净 checkout 重现已知产物与测试结果。

## P1：内核架构稳定性

- 启动、异常和panic报告。
- SMP、原子、锁、memory ordering和Worker生命周期。
- 调度、clone、exec、退出、wait和进程组。
- signal frame、`rt_sigreturn`、alternate stack和异步投递。
- futex、robust list、TLS和pthread语义。
- 时间、timerfd、signalfd、eventfd和epoll。
- ptrace/procfs/debug接口的可实现子集。
- 扩大 kselftests/LTP覆盖，并保留长时间压力测试。

这是一条持续工作流，不因某个版本“完成”而结束。

## P2：工具链与 libc

- 稳定 `wasm32-unknown-linux-musl` target和sysroot。
- 在已有wasm64宿主、musl、sysroot和最小用户程序闭环的基础上，扩大SDK与真实软件
  覆盖，并继续审计pointer、TLS、atomics和calling convention。
- 补齐 Clang driver、LLD、compiler-rt、libunwind和sanitizer可行路径。
- musl启动、pthread、signal、spawn/fork接口及标准头文件兼容。
- 构建 C/C++、Rust和其他语言的最小程序与真实软件。
- 工具链升级采用可重放补丁和回归矩阵，避免永久停留在一次性fork。

退出条件：发布的 SDK 可脱离仓库内部脚本构建第三方程序。

当前已加入独立的双位宽C++运行检查，覆盖容器、RAII异常清理、std::thread与TLS；
运行结果和复现命令见[SDK运行验证](sdk-runtime.md)。检查已加入不等于发布SDK已完成。
wasm64 的容器、RAII 异常清理、线程及 TLS 已在默认双核 Linux 内核上运行通过
（distro `ba7bf7f`）；跨线程保留异常对象和浏览器 C++ 的后续结果见下文及 SDK 运行记录。
各子系统的CI构建期间继续推进无依赖的工作，避免把单项测试扩展变成整条路线的串行门槛。

当前 Chromium wasm64 运行套件已实际通过全部 8 项，包括 C/C++、SDK SQLite、
socket、time64 定时器和 pthread 等待/取消/广播，以及加载失败后的恢复；
[定向记录](https://github.com/HighCWu/distro/actions/runs/38943658455)固定 distro
`0316709`，报告门禁确认零跳过、零重试。该结果不等于 wasm64 高层 agent 或
完整发行版矩阵通过。公开 agent 镜像路径仍为 wasm32，但内部 v4/wasm64 会话的
真实最小 Node 请求链已通过：包括文件操作、原生用户程序与标准流、信号及会话清理。
[运行记录](https://github.com/HighCWu/distro/actions/runs/38950484007)固定 distro
`243a96d`，六组用例加外层共 7 项，零失败、零跳过。共用语料的浏览器检查已接入，
固定 `7108d56` 的共享 Node 重跑及 Chromium 已通过，Firefox 则在就绪后超时，
仍待定位。真实生产入口与根切换已在 Node 验证通过（固定 `85fcbb9`，共 8 项，
零失败、零跳过），不覆盖后续高层客户端断言。生产 Chromium 已在 `498dbce`
通过真实根切换及高层文件/进程用例：八组断言完成，1 项浏览器测试通过，报告门禁
确认零跳过、零重试。带会话阶段日志的生产 Firefox 也在 `af5a160` 通过全部八组
断言和相同报告门禁；该结果不证明默认关闭日志时的既有超时已修复。
新增高层客户端文件/进程用例已在 Node 最小外壳通过（固定 `268c761`，共 8 项，
零失败、零跳过）。原生 GPT/EROFS agent 引导磁盘已在无外部 initramfs 的 Node
启动路径通过（固定 `c6ff369`，共 9 项，零失败、零跳过）。公开 API 的显式镜像/ABI
路径也已在 Node 通过（固定 `a0498bc`，共 4 项，零失败、零跳过），公开插件的浏览器
路径已在 `688fdba` 接入独立 Chromium/Firefox 检查，并同时复验重构后的 Node
语料，三项现已全部通过：两项浏览器均完成三组断言及精确报告门禁，Node 共 4 项
通过，零失败、零跳过；不替换默认 wasm32 镜像。既有 wasm32 完整集成回归也已
通过 233 项。此前无日志的生产 Firefox 错误 ABI 序列失败，在 v3 拒绝后发生
v4/wasm32 握手超时；正确 wasm64 公开插件的成功不证明该拒绝序列已修复。
后续 `f0ef828` 将回收线程创建移至身份接受之后，宿主资源顺序回归通过；无日志
的 Node 与两种浏览器生产检查现已全部通过：Node 9 项、两浏览器各 1 项及精确
报告门禁，均完成错误版本/位宽拒绝后接受 wasm64。保留重复回归，不能以单次成功
断言历史超时的唯一根因或长期稳定性。
范围及后续依赖见[agent wasm64 接入](agent-wasm64.md)；
不把 Node 最小外壳通过当作生产镜像或浏览器矩阵已经完成。

原生用户态开始从单文件程序向安装系统推进：distro `787177d` 新增显式
`stdenv-wasm64`、64 位包/镜像构造器及 `busybox-wasm64`，重用原有 shell、
进程与 loopback 网络检查，而不是复用 wasm32 loader。首项安装系统 smoke
完成编译和 ext4 根盘挂载，但在 switch_root 的文件系统类型检查处失败。
已发现 musl 将 LP64 的双参数 statfs 声明成三参数 statfs64；按位宽修正后更新
pin，并补双位宽文件系统统计运行断言。修正后的 wasm32/wasm64 BusyBox smoke
和独立 C 运行检查共四项均已通过，日志确认实际完成标记；链接产物位宽、共享
memory 和上限检查另有 3 项轻量回归通过。`50e37e4` 进一步将原生 BusyBox
安装进公开插件的测试根盘，在 Node 和两个浏览器检查 shell、管道、命令替换与
子进程生命周期。三宿主现均在固定 hush 不支持 `set -u` 处失败，并非完成验证。
`8122442` 改用支持的 errexit，保留所有结果断言并补共享命令的宿主回归；三宿主
复验已启动。固定 hush 仍不支持 nounset，不宣称补齐 POSIX shell。
默认 scope 仍为 wasm32，不宣称完整发行版已迁移。
`515dc27` 再增公开 `exec()` 的原生 shell 二进制管道：超过 pipe 容量的输入，
同时收集 stdout/stderr，逐字节核对且要求成功退出与文件清理。Node 和两个浏览器
的五组语料已提交独立 CI，轻量检查通过，实际执行结果待确认。
wasm64 安装系统的独立进程、回环网络检查均已通过（固定 `3d47240`）。双位宽
BusyBox 还新增随包许可证文本与静态链接运行库声明，以及安装后的非空检查，
双位宽均已通过（固定 `2b34bfb`），四项日志均确认实际完成标记。
这些声明不替代 GPL 对应源码交付，也不表示完整发布材料已就绪。
`36578fd` 新增公开网络插件的独立六组语料，Node 和两浏览器均已提交 CI：从
宿主连接原生 BusyBox HTTP 服务，检查 NIC 配置、TCP LISTEN、HTTP 正文和服务
退出/资源关闭。轻量检查通过，实际结果待确认；不依赖外网，也不宣称外网已可用。
`6e6047c` 修正 SDK 子进程 disposal：等待回收及槽释放，已确认回收后不再对原
数字 PID 发送 SIGKILL。八项双位宽协议回归通过；真实 wasm64 Node/两浏览器与
wasm32 完整集成已提交 CI。Node 和两个浏览器的实际日志现已确认通过；wasm32
结果待确认。该修正不等于 pidfd 或完整进程组生命周期支持。
`8045aad` 接着修正公开 run() 的成功/异常清理，六项新增宿主回归通过。shell
修正批次仍失败，网络 Firefox 也尚未进入 HTTP；`ad0186a` 的定向 Node 日志已定位
`child-status [0]`，同时确认二进制管道通过。固定 hush 跳过 THEN 时会重设 `$?`，
`f62f9d1` 改为 OR 列表内立即保存状态，仍要求 7；18 项相关宿主回归通过，先做
Node shell/管道/HTTP 全链复验，再补浏览器网络复验，不宣称第三方 shell 语义已修复。
该 Node 全链在 `82bd0d4` 实际通过六组加外层共 7 项、零失败/跳过，包括运行中
取消及恢复、二进制管道和附加网卡的原生 HTTP；已提交两浏览器复验，不宣称外网可用。
`380d21d` 暴露独立、无测试程序的 wasm64 最小根盘，配套原生 agent 引导盘和
内核包。最初版本 `1f6f85a` 的真实根盘公开 API 启动检查现已通过，日志确认实际
完成标记、1 项通过及零失败/跳过；不代表后续配置版本或浏览器已经通过。
`0bb77e7` 再为该独立根盘补入 root 身份名称记录及 `/etc/mtab` 链接，扩展启动
检查以验证 `id -un` 和挂载表读取；固定 `55ead4c` 的实际 Node 启动检查已通过，
日志确认 1 项通过及零失败/跳过，不代表登录认证或后续浏览器版本通过。
`65310ff` 为真实最小根盘接入共享的 Node/Chromium/Firefox 四组检查，要求无测试
程序、系统配置、实际用户态运行和机器关闭。固定 `78ce491` 的三项现已全部通过：
Node 为 5 项、两浏览器各完成四组及 1 项外层测试，严格门禁确认零跳过/重试。
`9e042d7` 修正 SDK 排队进程取消及 grant 后取消，六项双位宽宿主回归通过；新增
真实满槽取消断言已接入 wasm64 公开链路及 wasm32 集成。固定 `e630196` 的 wasm64
Node 全链现已成功，日志确认六组加外层共 7 项通过、零失败/跳过；wasm32 仍待确认。
`aa33c39` 同时补入双位宽 BusyBox 的独立构建材料及选定源码归档，宿主故障注入、
重现性和链接保留测试通过；固定 `0314774` 的双位宽源码归档与 wasm64 安装 smoke
现均通过，实际日志和临时 artifact 已核对，详见许可文档。
此归档不含完整运行库/工具链源码或离线重建环境，不代表发行合规已完成。

`accdea0` 再提供显式可写 wasm64 ext4 根盘，默认 EROFS 和 wasm32 不变。共享
Node/Chromium/Firefox 检查覆盖第一实例写入、同步、rename/chmod 与块 flush，关闭后
第二实例只复用块字节并核对数据和元信息。固定 `a5886c1` 的两浏览器检查已成功，
日志各确认两组完成及外层 1 项通过、零跳过/重试；同版本 Node 也已成功，实际
两组加外层共 3 项通过、零失败/跳过。
不将内存块保留等同于 OPFS、页面重启存储或物理耐久性。

`d72b88d` 在上述浏览器 profile 增加实际 OPFS 页面刷新检查，复用站点的同步访问
worker，但与 wasm64 内核包独立打包。写入并同步后关闭机器和设备，刷新页面后仅
凭 OPFS 文件名重新打开已有磁盘；禁止重新获取根盘模板，并复用同一数据/权限断言。
新增六项宿主编排回归、相关共 34 项宿主回归、类型检查和浏览器打包通过；实际双
浏览器检查已失败在远程 worker 的 memory64 `grow(0)` 绑定，未完成 OPFS 用例。
`329b5ab` 显式传播内存位宽并调用位宽感知刷新方法，新增回归先复现再通过；全部
130 项内核宿主测试、同套隔离运行及类型检查通过，真实双浏览器复验已启动。
固定 `329b5ab` 的 Chromium/Firefox 复验现均通过，日志各确认 2 项及严格门禁
零跳过/重试，包含实际 OPFS 正常同步后页面刷新并重开读回。
它不承诺浏览器进程重启、存储不被回收、崩溃恢复或断电耐久性。

Memory64浏览器检查已从“看到Linux启动横幅”升级为双核启动musl用户程序，复用
toolchain-smoke的参数/环境、malloc、匿名mmap与partial munmap、越界MAP_FIXED、
pthread/TLS及信号检查，只有完整用户程序通过标记才算成功。宿主控制流回归已覆盖
失败、panic、提前关闭和启动超时后的迟到实例清理；它们不等于浏览器运行通过。
首次[Chromium定向验证](https://github.com/HighCWu/distro/actions/runs/38883890314)
使用distro提交`e200a282e51b9b357826a135036045ae5ae17812`，已于2026-10-16通过：
日志确认实际执行1项Memory64 musl用户程序测试，并要求完整`::vm-test::pass`标记。
它不包含后续加载器和宿主修复，不代表当前提交完整浏览器矩阵已通过。
Firefox针对`680ccfd94a1223c33f13ee6fd1f9dcb6cb83ef1c`的
[定向验证](https://github.com/HighCWu/distro/actions/runs/38893749018)已完成：
Build isolated check 成功，日志确认三项测试全部通过，包括无效 CPU 数量提前拒绝、
Memory64 musl 用户程序运行，以及下述加载器恢复场景。整个工作流失败是后续缓存
保存步骤缺少 `primary-key`，不是浏览器运行失败；后续提交已修复缓存键传递，但本次
不能证明缓存保存成功，也不覆盖后续 C++、RTTI 或 TLS 析构扩展。

浏览器宿主加载器已支持失败后再次启动，以及非标准Wasm MIME的字节编译回退。
新增浏览器场景在同一页面先注入HTTP 503，再用application/octet-stream返回内核，
要求第二次请求完成上述用户态测试。相关14项宿主回归已通过，该新场景也已在上述
Firefox 检查中通过；首次 Chromium 任务固定在更早提交，不包含这两项修复及场景。

同一用户态与恢复场景现也接入wasm32，使用匹配位宽的内核、工具链程序及initramfs。
新增定向检查名为`browser-tests-check-runtime-wasm32-chromium`和
`browser-tests-check-runtime-wasm32-firefox`；wasm64保留原有
`browser-tests-check-memory64-chromium`/`browser-tests-check-memory64-firefox`名称。
wasm32 Firefox 已针对 distro `c9f7083aae0c8ddf5b622a8b883418f57988a42f` 启动
[定向检查](https://github.com/HighCWu/distro/actions/runs/38908463360)，包含当前 C/C++
运行用例、RTTI 和工作线程 TLS 析构扩展，结果待确认；不替代已有发行版启动及 uname 回归。

上述双位宽套件现还包括 C++ 容器、RAII、类型化异常、跨线程 exception_ptr 生命周期
与线程/TLS 检查。distro `80528ae` 的
[Chromium wasm64 检查](https://github.com/HighCWu/distro/actions/runs/38896599293)
实际构建与浏览器测试步骤已成功，四项测试全部通过，包含 C 用户程序、C++ 容器、
RAII、跨线程保留异常清理与线程/TLS，以及加载器恢复场景。整个工作流失败是后续
旧缓存保存缺少 `primary-key`。此提交尚不包含 RTTI、TLS 析构或条件变量扩展。
后续 `49ae22a` 将结果协议限定到用户控制台，
启动控制台仍检测 panic，但不再接受其通过标记；此后续修复不在该运行内。

站点现会在缺少跨源隔离时显示 COOP/COEP 配置提示并停止，且检查早于 Service Worker
注册/注销及 OPFS 访问。实际页面启动代码已在本地模拟 Chromium/Firefox 分支验证，
并加入 `site-live` 浏览器回归。
[定向检查](https://github.com/HighCWu/distro/actions/runs/38898909579)的实际构建与
浏览器测试步骤已成功：Chromium 三项测试全部通过，分别覆盖缺少跨源隔离时提前
停止、空白持久磁盘初始化启动，以及存储不可用时回退 live-only。整个工作流失败
是后续旧版缓存保存缺少 `primary-key`，不是站点测试失败；不据此宣称崩溃恢复、
长期持久化可靠性或整个浏览器矩阵已获验证。

后续站点用例增加已安装根文件系统中的普通文件写入、`sync`、页面重载及内容核对。
[定向验证](https://github.com/HighCWu/distro/actions/runs/38908758379)对应 distro
`f722b87a9533746f28e8b5dd900b5e0027d91474`，结果待确认；这检查正常同步后的持久化，
不模拟断电、未同步写入丢失或 OPFS 崩溃恢复。

后续 distro `f0c053e` 把 SQLite 安装、事务提交/回滚以及重载后的只读完整性、
64 位整数和 BLOB 核对加入同一场景。
[38923175031](https://github.com/HighCWu/distro/actions/runs/38923175031)
实际执行三项站点测试，两项通过，安装持久化场景失败：精简 rootfs 没有 `/root`，
普通文件写入报目录不存在，尚未进入 SQLite 安装及事务阶段。因此本次既不证明
SQLite 持久化通过，也不是 SQLite 或存储同步故障的证据。distro `fffb035` 已让
测试显式创建目录，再执行原有写入与同步检查。

[38928608737](https://github.com/HighCWu/distro/actions/runs/38928608737)
在 distro `fffb035` 上已执行到页面重载后的 `persistence-restored` 和
`sqlite-persistence-restored`：Chromium 中普通文件与 SQLite 的同步持久化、只读
完整性检查、精确 64 位整数和 BLOB 核对均通过。但整个站点工作流仍失败：最后的
`lowland-boot` 重装停在 97%，60 秒内未出现 `protected-boot-ok`。这不是 SQLite
检查失败；也尚不能据此判定是 OPFS 死锁或单纯耗时较长。

distro `6f28004` 为该场景增加测试专用文件操作追踪，失败时输出最多 64 项近期完成
操作与 64 项待完成操作及耗时，不记录文件内容，不改生产文件系统行为，不放宽
原有超时。追踪的 5 项宿主契约测试通过；后续
[站点 CI](https://github.com/HighCWu/distro/actions/runs/38933955211)
现已成功：Chromium 三项站点用例及整个工作流通过，包含文件/SQLite 同步重载和
最终 `/boot` 重装保护检查。此轮没有修改生产存储行为，一次成功重跑不解释此前
停顿的根因，也不应称为已修复该停顿。
上述证据仍不覆盖断电、未同步写入、WAL 或 wasm64 站点持久化。

## P3：存储、文件系统与设备

当前块设备接入契约、错误边界及 OPFS 持久性限制见[宿主块存储说明](host-storage.md)。

- 稳定 virtio block、console、entropy、fs、net和vsock。
- EROFS只读系统、ext4持久安装和OverlayFS临时可写层。
- OPFS块设备和目录共享，覆盖崩溃恢复、flush和并发。
- Node宿主文件系统的路径隔离与竞态限制文档化。
- tty/pty、ioctl、设备发现和热关闭语义。
- 大文件、压力、断电模拟和跨版本镜像测试。

## P4：网络

- virtio-net与虚拟交换机稳定性。
- 浏览器可用的TCP、UDP、DNS宿主适配。
- 多运行实例私网、端口转发和连接生命周期。
- socket、poll/epoll、超时、半关闭和错误码一致性。
- TLS、curl、SSH、包管理器和语言runtime的真实网络测试。
- 明确浏览器安全模型，不伪装浏览器无法提供的原始网络能力。
  当前 Fetch 转换、取消所有权和验证边界见[宿主 HTTP 说明](host-http.md)。
  私网 UDP 的正文边界和写入失败清理见[宿主私网说明](host-network.md)。
  SDK 双位宽的 Unix/TCP/UDP 回环、非阻塞就绪、消息 ABI 和半关闭验证见
  [SDK socket 说明](sdk-sockets.md)；wasm64 新增 epoll 场景已通过 Node、Chromium
  和 Firefox 定向验证，不据此宣称外部网络支持。TCP 关闭清理及 FIN 半关闭的
  宿主网卡回归见[宿主私网说明](host-network.md)。

## P5：进程和内存兼容

这一工作流在 `CONFIG_MMU=n` 基础上逐步恢复应用所需接口。

### P5.1 direct 基线

- stack/global/TLS/heap继续原生linear-memory访问。
- direct memory grow、brk、匿名分配和边界错误。
- private-memory callback clone使用eager copy：子进程得到独立linear memory，并从调用者
  明确提供的函数和新栈开始执行。
- 标准`fork()`还需要让子进程从调用点以返回值0继续执行。原生Wasm调用栈不在linear
  memory中，不能仅靠复制memory实现；在具备可移植的执行continuation方案前不得把
  callback clone表述为`fork()`。

### P5.2 direct匿名映射

- 已让brk和匿名映射共享同一个direct地址分配器，禁止重叠。
- 已通过标准raw `SYS_mmap`/`SYS_munmap`恢复
  `MAP_PRIVATE | MAP_ANONYMOUS`和partial `munmap`的可验证子集。
- 已记录wasm32/wasm64 profile上限，并以`RLIMIT_AS`约束进程maximum。
- 已覆盖长度溢出、多线程并发分配、并发partial unmap、碎片解除后的重新分配及zero-fill。
- 已把完整映射请求放入版本化`user_v2`执行ABI，同时保留旧内核和旧用户模块兼容路径；
  当前allocator仍只实现已验证的direct anonymous子集。
- 已限制旧用户模块的length-only回退：固定请求在调用allocator前返回`ENOMEM`，普通
  anonymous请求及非固定hint继续兼容；wasm32/wasm64转发和错误类型有宿主回归测试。
- 已支持在allocator既有backing的空闲页洞内采用非固定地址hint；冲突或未保留的hint
  回退到普通分配，不会覆盖live mapping或凭空声明任意地址可用。
- 已在同一安全页洞子集内支持`MAP_FIXED_NOREPLACE`的精确映射、`EEXIST`冲突检测、
  未对齐`EINVAL`和未保留区间`ENOMEM`；普通`MAP_FIXED`仍明确失败。
- 已让普通匿名映射优先复用512 KiB direct backing chunk中的空闲区间，并允许hint和
  `MAP_FIXED_NOREPLACE`采用尚未映射过的保留页；预留失败退回请求大小，最后一个live
  mapping解除后释放整个chunk。
- 已覆盖16轮交错页拆分与精确回填，以及8线程争抢同一`MAP_FIXED_NOREPLACE`空洞时
  恰好一个成功、其余返回`EEXIST`的并发生命周期。
- 继续补齐地址空间耗尽和exec后的allocator状态压力测试；callback clone后的快照与隔离、
  非法flag、zero-length和普通load/store已有集成检查。

专项约束见[direct-memory.md](direct-memory.md)。

### P5.3 标准映射与fork完善

- 已建立16/64/256映射、0/25/50%空洞和1/2/4线程的wasm32采样基准，保留原始样本与
  汇总脚本；数据见[mmap-benchmark.md](mmap-benchmark.md)。已实现重复backing扫描去重，
  并通过可关闭基线的正确性检查和首轮性能对照。下一步重复独立run、检查小规模开销，
  再根据多轮对比决定chunk尺寸、空闲区间索引或区间树，并扩展wasm64采样。
- 已建立wasm32/wasm64共用正确性源码和基准源码的raw initramfs入口，以及同runner
  交替开关、每次重新启动的三轮配对工作流。采样按需手动运行；只有完整校验通过的
  CSV进入比较，不把一次启动回归或缓存测试输出当作性能复测。
- 已完成两个独立run的wasm32/wasm64配对复测并归档1080条记录。较多映射的收益可复现，
  但wasm64小规模双线程组存在退化；下一项性能实验保留当前重置式去重和关闭优化两条
  基线，先定位开销，再评估generation tag等方案及其计数器回绕正确性。
- generation tags已作为独立分支的opt-in实验接入，默认不变；32/64位正确性、强制回绕和
  callback clone快照已通过，两轮1080行配对数据已归档。目标小规模并发组未改善，
  大规模并发收益方向也未稳定复现；实验已结束，实现和pins不合入主线，仅保留分支与
  证据。后续性能诊断需区分查找、锁内清零和调度成本，详见[mmap基准](mmap-benchmark.md)。
- `MAP_FIXED`仍须单独证明冲突替换、拆分和生命周期语义，超范围请求返回明确错误。
- 文件映射从读取完成后原子发布的`MAP_PRIVATE`子集开始；异步失败必须返回错误，不能
  留下半完成映射或永久等待。
- `MAP_SHARED`只在跨进程可见的共享backing、写入传播与持久化路径完整后开放；在真实
  回写存在以前，`msync`不得以no-op报告成功。
- 维持callback clone的eager-copy快照并完善失败回滚、超时和Worker/Memory回收；不承诺
  透明COW。
- 单独研究标准`fork()`的执行continuation。若需要工具链变换，必须形成公开、版本化并
  可测试的ABI；不能仅增加syscall号或libc符号来假装支持。
- `/proc/<pid>/maps`与用户态可见地址一致。
- 不支持的direct页保护返回明确错误，不能静默成功。

### P5.4 wasm64

- 维持已跑通的Memory64内核、匹配宽度用户模块loader和最小musl程序执行闭环。
- 64位pointer ABI、direct allocator和边界溢出审计。
- 公布16 GiB构建上限与实际运行时可用范围的区别。
- pointer/int往返、syscall结构和原子宽度审计。

## P6：用户态发行版

`8af0f0d` 为独立 `sqlite3-wasm64` 和 SQLite ext4 应用根盘接入共享的 Node/浏览器
事务、回滚及新实例数据库读回检查，保持最小根盘不变。六项宿主命令回归、类型
和打包检查通过；实际目标编译/运行先由 Node CI 验证，不把现有 SDK SQLite 或
wasm32 站点证据当作新原生 CLI、wasm64 应用根盘已通过。

`aab1a2b` 进一步提供独立静态开发输出及相对前缀 pkg-config 元数据，CLI 使用同一
归档；开发者无需从源码重建 SQLite 即可链接自己的程序，运行根盘仍只装 CLI。
已接入复制安装产物后通过 SDK 构建、启动 SQLite 消费者的检查；宿主元数据重定位
及禁止系统包回退的回归通过，目标多输出及消费者运行仍需公开 CI 结果。
首项应用根盘检查的 CLI 编译及 ABI 检查通过，但 Nix 因源码路径引用拒绝打包，
未进入 Linux 事务运行；`d9d2d68` 使用相对源文件路径修正，保留引用门禁，待复验。
固定 `ffbdfb6` 的修正后 Node 复验现已成功，实际两组及外层共 3 项、零失败/跳过，
包含原生 CLI 事务/回滚及新 Linux 实例的数据库完整性与字段读回。双浏览器随后
启动复验，不把 Node 结果扩大为 OPFS、崩溃恢复或开发消费者均已通过。

`1ba866e` 再加入原生 SQLite 的 OPFS 页面重载检查：唯一磁盘文件初始化后，通过
安装的 CLI 提交/回滚并同步，关闭机器与设备、刷新页面，再重开同一文件只读验证
完整性及精确字段。读回阶段禁止根盘模板下载，复用生产磁盘启动 helper，不传容量
以免重置已有盘。四项宿主编排回归通过，新增真实 OPFS 用例仍待公开浏览器 CI，
不承诺浏览器进程重启、WAL、崩溃恢复或物理持久性。

固定 `963a86c` 的安装后开发消费者及原内存根盘 Firefox 检查现已成功：前者实际
验证安装库链接的消费者 ABI 并在 Linux 输出运行完成标记；后者两个 SQL 阶段通过，
外层一项、零跳过/重试。两者不包含新增 OPFS 页面重载用例，不能作为其验收证据。
同批 Chromium 也已实际完成两个 SQL 阶段并通过严格报告；原内存块路径的双浏览器
验收均已通过。后续新增 OPFS 检查也已成功：Chromium 固定 `041b82c`、Firefox
固定 `02ce485`，实际日志确认各两项通过，包括原生 SQLite 页面重载读回，均零
跳过/重试。这不是浏览器进程重启、崩溃恢复、WAL 或物理持久性证明。

- 扩大可构建、可安装的软件包集合，并维护其构建定义和依赖关系。
- BusyBox、Bash、coreutils、Git、Python、QuickJS等持续回归。
- 区分平台修复、临时port patch和上游软件缺陷。
- 提供可复现rootfs、软件源、安装工具和升级测试；不把某一种包管理器规定为平台ABI。
- 维护最小镜像与开发镜像，避免一个镜像承担所有用途。

## P7：SDK、API与发布

`68862b7` 为公开远程设备 API 增加启动阶段 AbortSignal，防止调用方只能无限等待
未就绪 Worker。取消清理握手监听，但不转移端点所有权或关闭已就绪设备。六项新增
回归及全部 136 项内核宿主测试通过，站点接入与真实浏览器故障场景仍需分别验收。
`b51d9c2` 已为站点磁盘握手接入默认 30 秒超时、外部取消及失败 Worker 释放，
新增五项 helper 宿主回归通过。双浏览器轻量套件新增真实故障/取消/关闭检查，
严格要求 21 项执行；固定主仓库 `3aceed1`、distro `ad839be` 的
[双浏览器任务](https://github.com/HighCWu/linux-wasm-builder/actions/runs/38976752959)
已成功，实际日志确认 Chromium/Firefox 各 21 项通过、零跳过/重试。
这不替代完整站点或 Linux 文件系统恢复验证。

`a0ba6b4` 提供独立 `wasm64-example`：公开 API 启停、原生命令及 UTF-8 文件往返，
不依赖整个站点或测试程序。服务器宿主检查、脚本语法及打包通过，真实页面运行
已提交首项 Chromium CI，结果待确认。此示例每次启动使用新内存根盘，不是 OPFS
或发布完成的持久化发行版；仍需浏览器验收、版本兼容及发布材料。
`6d9fdb0` 补齐镜像下载前的真实共享 memory64 能力诊断，五项宿主探测回归通过；
不将单页内存分配成功等同于整台 Linux 可用。新增缺少 COEP 的页面回归待浏览器验收。
`aa363a4` 再将说明和完整静态目录校验器随包安装，支持复制后离线核对内核、镜像、
脚本与文本，搬移/损坏检测及 Nix result 链接入口回归通过。真实新版本打包待 CI，
不把校验和当成来源签名、完整许可清单或 SDK 可重定位证明。
首项 Chromium 示例 CI 失败于 Nix 输入只包含单独入口文件而缺少相邻 SDK 模块，
尚未启动浏览器。`fdbc82c` 改为传入完整源码目录；复验确认静态包构建及 111 文件
完整性校验成功，随后测试包因复制的只读 `node_modules` 无法加入 Playwright 链接
失败，仍未启动浏览器。后续仅为测试副本的该目录增加属主写权限；宿主回归复现旧
失败并验证修正不改变应用 payload 权限，真实浏览器复验仍需 CI。
固定 `bfcc295` 的 Chromium 复验现已成功：111 文件包校验及真实控件用例通过，
严格报告零跳过/重试；只证明当时的基础示例，不包括后加的程序导入与整机停止扩展。

`c1dbd0f` 为独立示例补上开发者程序导入：匹配 SDK 的静态 wasm64 文件、字面
JSON 参数、临时根盘、双输出流及用户取消；不再仅能运行预设命令。输出显示有界，
取消后等待进程/管道清理，明确仅运行可信程序且不持久保存。九项新增宿主回归及
全部相关 18 项通过，页面语料加入独立 SDK 编译程序的真实文件选择、退出和取消
验证；实际浏览器结果仍待定向 CI，不把文件头检查当 ABI 或安全验证。

`e7d8418` 进一步保持整机 Stop 在应用运行期间可用，不再排队等待命令结束；
停止等待机器和 console 关闭，并隔离旧操作的输出/错误及文件操作后续命令，避免
污染重启实例。新增五项 UI 竞态/关闭宿主回归，连同相关检查共 23 项通过，浏览器
打包通过；实际停止等待程序、重启及文件清空的扩展仍需浏览器 CI 验证。

`e7408f2` 为开发者程序增加有界 UTF-8 文本 stdin，空输入保持 EOF，并发读写
防止过滤器管道互相等待。保留单进程取消与独立整机停止，生产者 EPIPE 不遮盖
真实退出状态；不宣称 TTY、二进制文件流或资源配额。五项新增宿主回归及相关共
28 项通过，页面打包和 C 语料宿主检查通过；实际 Unicode 往返、前缀消费与后续
控制恢复已在固定 `c58929a` 的 Chromium 页面用例通过，实际日志确认 111 文件
包校验及严格门禁零跳过/重试；不由旧版入口通过或宿主流模拟代替。

固定 `7a639df` 的程序导入 Chromium 验收现已成功，实际日志确认扩展页面用例及
111 文件包校验、零跳过/重试。独立整机停止也已在固定 `103fca4` 的 Chromium
验收通过，实际日志确认扩展用例与相同包校验/严格门禁；文本 stdin 也已取得上述
独立 Chromium 结果，但不包含后续 SDK 生命周期修订。

`7fa1fdf` 修正公开进程句柄在确认回收后仍能向数字 PID 发信号的问题：本地返回
ESRCH、不发送 syscall，并覆盖已取消但确认回收的句柄。六项新增双位宽协议回归
和原生命周期测试共 14 项通过，相关共 26 项通过，类型和打包检查通过；真实
wasm32/wasm64 语料加入对应断言；固定 `50c3439` 的 wasm64 Node 用户态已实际
通过 6 项，零失败/取消/跳过，wasm32 仍待确认。此保护不是 pidfd 或所有并发
PID 竞态的解决方案，不改变内核 UAPI。

`142e9d1` 修正关闭后底层 fd 包装仍能发送请求的问题：关闭开始即失效，等待通道
期间再检查，返回 EBADF 而不破坏会话；旧进程输出只可交付已有缓冲，后续不再
读取关闭的编号。新增八项双位宽宿主回归，相关共 62 项及类型检查通过，已纳入
现有轻量 CI；不是原生 fd 复用压力测试，也不取消已发送请求或改变内核/UAPI。

`fdde5c7` 进一步明确关闭/取消进程时的 stdin 失败语义：未结束的输入流立即报
EPIPE，保留已有输入泵错误和已成功 EOF，不再默默接受随后被丢弃的数据。宿主
新增十项双位宽回归、相关共 72 项和类型/语料打包通过；真实 wasm32 集成及
wasm64 公开用户态已接入对应断言，执行结果待 CI。宿主缓冲成功并不保证送达。

`df2c4cc` 将 SDK 文件复制的身份判断改为已打开描述符的完整 dev/ino，先检查再
截断，避免路径替换为源文件别名后误清空源数据。新增八项双位宽宿主语料，相关
共 85 项及类型/浏览器语料打包通过，真实 wasm32/wasm64 用例已接入；不宣称
原子复制、不可变快照、失败回滚或真实 rename 压力验证，不改变内核/UAPI。

- 稳定 `@lowland/kernel`、`@lowland/guest`和高层facade边界。
- npm包的Node/browser条件导出和package-relative assets。
- 源码联合构建与预编译runtime使用相同版本协议。
- 错误、日志、性能计数和调试接口。
- 示例应用、迁移指南、版本策略和兼容性表。
- 每次发布自动生成二进制、rootfs、source bundle、SBOM和NOTICE。

## P8：动态链接与高级能力

- 在静态程序和进程内存语义稳定后，单独设计Linux/Wasm动态loader ABI。
- 共享memory/table、TLS、relocation、constructors和`dlopen/dlsym`。
- 动态库只能使用可直接访问的linear-memory区间；无法满足的布局明确失败。
- 评估调试器、性能分析、checkpoint、容器式隔离和不可信模块验证。

`cc72990` 为 SDK 增加标准 `try_table` 异常指令的独立 C++ 消费者检查，针对
Firefox 实际日志中的旧式 EH 弃用警告。它保持默认编译配置、内核和运行库不变，
先验证新应用生成方式能否与已安装运行库互操作；检查完整 C++ 语料的汇编门禁、
双位宽共享内存 ABI 及 Linux 运行完成标记。三项宿主门禁回归通过，目标生成与
运行待公开 CI，不据此宣称全系统已去除旧式指令；细节见 SDK 运行文档。
固定 `cc72990` 的 wasm64 检查现已成功，实际日志确认标准处理器门禁、共享内存
ABI 及完整 C++ 运行标记。固定 `ad839be` 的
[wasm32 补验](https://github.com/HighCWu/distro/actions/runs/38976857074) 也已成功，
日志确认标准处理器门禁、共享 memory32 ABI/4 GiB 声明上限及同一完整 C++ 语料。
这仍不是浏览器或整体运行库/内核迁移的完成证明。

## 质量矩阵

每项工作至少在以下维度选择适用组合：

| 维度 | 组合 |
|---|---|
| 宿主 | Chromium、Firefox/WebKit可用路径、Node |
| CPU | 单CPU、SMP |
| 用户ABI | wasm64为主、wasm32兼容 |
| 文件系统 | EROFS、ext4、OverlayFS、OPFS/host share |
| 网络 | 无网络、运行实例私网、宿主代理 |
| 程序 | 微测试、kselftests/LTP、真实应用 |
| 构建 | debug、release、对应源码重建 |

任何单一门矩阵全绿都不能代替跨层真实工作负载验证。
