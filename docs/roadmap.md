<!-- SPDX-License-Identifier: MIT -->

# Linux/Wasm 平台路线图

路线图以持续完善 Linux 在 WebAssembly 上的可用性为核心。内核、工具链、用户态、
宿主和发行可以并行推进；softmmu2 是内存兼容工作流中的一个里程碑，不是总路线。
各阶段编号用于组织依赖和验收，不表示整个项目在等待 softmmu2；除明确依赖外，所有
工作流都应持续推进。

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
- 建立 wasm64/memory64 target，审计pointer、TLS、atomics和calling convention。
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
- 多guest私网、端口转发和连接生命周期。
- socket、poll/epoll、超时、半关闭和错误码一致性。
- TLS、curl、SSH、包管理器和语言runtime的真实网络测试。
- 明确浏览器安全模型，不伪装浏览器无法提供的原始网络能力。

## P5：进程和内存兼容

这一工作流在 `CONFIG_MMU=n` 基础上逐步恢复应用所需接口。

### P5.1 direct 基线

- stack/global/TLS/heap继续原生linear-memory访问。
- direct memory grow、brk、匿名分配和边界错误。
- fork第一版允许eager copy，先保证可观察语义。

### P5.2 softmmu2+TLB里程碑

本阶段交付一种地址兼容机制，而不是新的应用编程模型，也不是平台完成的标志。若验证
表明其他实现更合适，可以在保持 Linux UAPI 和已发布 psABI 兼容性的前提下替换内部
机制。

- 定义版本化 `linux.softmmu` psABI和loader协商。
- wasm32固定高地址与稀疏managed mapping。
- LLVM对stable-direct访问消除翻译，unknown pointer动态分流。
- TLB fast path、跨页/权限slow path和hybrid uaccess。
- `munmap`后失效、managed `mprotect`和多线程invalidation。
- direct-only对照构建仅用于调试和性能比较，正式工具链默认支持softmmu。

专项设计见 [softmmu-abi.md](softmmu-abi.md)。

### P5.3 标准映射与fork完善

- `mmap`自动选择direct或managed实现。
- `MAP_FIXED`、文件映射、dirty tracking和`msync`。
- managed私有映射复制或COW优化。
- `MAP_SHARED`共享backing。
- `/proc/<pid>/maps`与guest-visible地址一致。
- 不支持的direct页保护返回明确错误，不能静默成功。

### P5.4 wasm64

- 64位pointer ABI和softmmu2两级稀疏chunk。
- 高GVA映射到低backing。
- pointer/int往返、syscall结构和原子宽度审计。

## P6：用户态发行版

- 扩大可构建、可安装的软件包集合，并维护其构建定义和依赖关系。
- BusyBox、Bash、coreutils、Git、Python、QuickJS等持续回归。
- 区分平台修复、临时port patch和上游软件缺陷。
- 提供可复现rootfs、软件源、安装工具和升级测试；不把某一种包管理器规定为平台ABI。
- 维护最小镜像与开发镜像，避免一个镜像承担所有用途。

## P7：SDK、API与发布

- 稳定 `@lowland/kernel`、guest和高层facade边界。
- npm包的Node/browser条件导出和package-relative assets。
- 源码联合构建与预编译runtime使用相同版本协议。
- 错误、日志、性能计数和调试接口。
- 示例应用、迁移指南、版本策略和兼容性表。
- 每次发布自动生成二进制、rootfs、source bundle、SBOM和NOTICE。

## P8：动态链接与高级能力

- 在静态程序和进程内存语义稳定后，单独设计Linux/Wasm动态loader ABI。
- 共享memory/table、TLS、relocation、constructors和`dlopen/dlsym`。
- 动态库映射可使用managed内存能力，但不得反向绑死softmmu内部布局。
- 评估调试器、性能分析、checkpoint、容器式隔离和不可信模块验证。

## 质量矩阵

每项工作至少在以下维度选择适用组合：

| 维度 | 组合 |
|---|---|
| 宿主 | Chromium、Firefox/WebKit可用路径、Node |
| CPU | 单CPU、SMP |
| 用户ABI | wasm32、后续wasm64 |
| 文件系统 | EROFS、ext4、OverlayFS、OPFS/host share |
| 网络 | 无网络、guest私网、host代理 |
| 程序 | 微测试、kselftests/LTP、真实应用 |
| 构建 | debug、release、对应源码重建 |

任何单一门矩阵全绿都不能代替跨层真实工作负载验证。
