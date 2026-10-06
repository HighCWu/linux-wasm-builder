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

## P3：存储、文件系统与设备

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
  callback clone快照已通过，首轮540行配对数据已归档。但目标小规模并发组没有改善，
  wasm64双线程三个pair反而均更慢；第二轮复测中，不提升为默认策略，详见
  [mmap基准](mmap-benchmark.md)。
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

- 扩大可构建、可安装的软件包集合，并维护其构建定义和依赖关系。
- BusyBox、Bash、coreutils、Git、Python、QuickJS等持续回归。
- 区分平台修复、临时port patch和上游软件缺陷。
- 提供可复现rootfs、软件源、安装工具和升级测试；不把某一种包管理器规定为平台ABI。
- 维护最小镜像与开发镜像，避免一个镜像承担所有用途。

## P7：SDK、API与发布

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

## 质量矩阵

每项工作至少在以下维度选择适用组合：

| 维度 | 组合 |
|---|---|
| 宿主 | Chromium、Firefox/WebKit可用路径、Node |
| CPU | 单CPU、SMP |
| 用户ABI | wasm32、后续wasm64 |
| 文件系统 | EROFS、ext4、OverlayFS、OPFS/host share |
| 网络 | 无网络、运行实例私网、宿主代理 |
| 程序 | 微测试、kselftests/LTP、真实应用 |
| 构建 | debug、release、对应源码重建 |

任何单一门矩阵全绿都不能代替跨层真实工作负载验证。
