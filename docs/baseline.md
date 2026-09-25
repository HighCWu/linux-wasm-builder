<!-- SPDX-License-Identifier: MIT -->

# 当前 Linux/Wasm 基线

本文件记录开始平台改造前已经存在的能力和已知缺口。它用于区分“继承自现有项目的
能力”“本仓库重新验证的能力”和“未来路线”，避免把源码中存在的实现直接写成已经
通过全部环境验证的承诺。

基线日期：2026-09-25。

## 固定源码

| 组件 | 分支 | commit | 构建关系 |
|---|---|---|---|
| `HighCWu/distro` | `main` | `6e278a8c34d26fa6f05b1acb164b7d15d6f73b1e` | 集成构建与测试入口 |
| `HighCWu/linux` | `wasm` | `cb3bfdbb62a0d52961eca64d209df9ef7fb90e2c` | `distro` Nix pin与submodule一致 |
| `HighCWu/llvm-project` | `wasm-linux` | `137009e264eb237b5f5adcbae1b7e209f79291f5` | `distro` Nix pin与submodule一致 |
| `HighCWu/musl` | `master` | `6c8c062c63d21682828a788a011982339a2f82ad` | `distro` Nix pin与submodule一致 |

`scripts/check_repository.py`在CI中检查URL、分支、gitlink以及三个Nix pin，防止主仓库
展示的源码版本与实际构建版本分离。

## 当前源码已经提供的能力

以下内容来自固定版本的 `distro` 源码、架构文档、变更记录和测试定义；它们仍需由本
仓库的完整CI矩阵持续复验。

### 内核和执行环境

- Linux 7.1 Wasm架构，默认用户ABI为`wasm32-unknown-linux-musl`且采用NOMMU路线；
- 内核提供独立的实验性wasm64/Memory64构建profile；Node 24、Chromium和Firefox已经
  实际执行最小musl用户程序，但SDK、软件包和ABI回归覆盖尚未达到默认发布条件；
- browser Worker和Node宿主；
- SMP、独立用户进程memory以及跨Worker的进程和virtio交接；
- `clone()`/`execve()`和`posix_spawn()`工作流；
- futex、信号、时间和其他接口由现有kselftests/LTP子集覆盖。

### 设备、存储和文件系统

- virtio block、console、filesystem、network、vsock和entropy设备接口；
- EROFS只读系统盘、ext4可写盘和可选OverlayFS临时写层；
- Node目录共享、OPFS以及浏览器File System Access API适配；
- guest SDK提供进程执行、流式I/O、文件和挂载操作。

### 网络

- guest间虚拟以太网交换；
- ARP、IPv4、TCP、UDP和DNS宿主实现；
- HTTP/Fetch适配以及通过可配置connector访问宿主TCP服务。

### 用户态和发行

- musl sysroot及C/C++工具链，并包含Rust smoke路径；
- musl已恢复`MAP_PRIVATE | MAP_ANONYMOUS`、读写、非固定地址的direct `mmap()`子集，
  并支持对整段已登记映射执行`munmap()`；分配与现有malloc/brk路径共用底层分配器；
- BusyBox、Bash、coreutils、curl、Dropbear、Git、Lua、Python、QuickJS、SQLite、Vim等
  软件包定义和测试；
- `@lowland/kernel`和`@lowland/guest` npm包；
- Nix负责构建和依赖求解。当前`distro`内部使用Alpine风格的v3 APK格式组装rootfs并
  支持guest内安装；这是当前发行版的可替换实现选择，不是Linux/Wasm平台ABI，也与
  Android APK无关。

## 当前明确缺失或受限的能力

- 当前基线没有`fork()`或`vfork()`；现有程序主要通过`posix_spawn()`启动子进程。
- `mmap()`当前只是musl libc层的direct anonymous子集，尚未恢复raw `SYS_mmap`；
  `MAP_FIXED`、文件映射、共享映射和严格页保护均不支持，`munmap()`只接受完整、精确
  匹配的映射，释放后也不能保证陈旧指针立即fault。
- `futex_waitv`对有效的栈上参数仍返回`EFAULT`。
- 宿主网络尚无任意目标的出站UDP代理，TCP桥接尚无重传，并存在队列丢包风险。
- System V IPC当前配置或执行路径不完整，`shmget`会在已知实验配置中trap。
- 重复创建guest进程会使宿主emulator内存持续增长，进程销毁后的资源回收尚未稳定。
- 浏览器CPU交接与并发memory growth之间存在已知stale typed-array view竞态。
- 若干LTP测试仍失败、跳过或hang；测试框架本身也还有可能掩盖部分晚到错误。

这些条目是基线缺口，不等同于最终设计限制。修复时应优先恢复标准Linux可观察语义，
并为无法实现的语义提供明确错误。

## 验证层级

1. `CI`检查文档格式、submodule元数据和Nix pin一致性，不构建大型源码树。
2. `Build baseline`在GitHub-hosted runner上构建kernel和guest包。
3. 标准distro checks在单独任务中运行。
4. scheduler敏感或耗时较长的heavy checks按测试项拆分运行。

工作流不上传大型临时构建树。本地默认只初始化较小的`distro` submodule；Linux、LLVM
和musl工作树可在确有源码修改需要时再按需初始化。

## 首次验证结果

2026-09-24的首次公开CI结果：

- 主仓库元数据检查通过；
- 主仓库在`distro` commit `90d4ed4`上完成kernel和guest packages构建，用时42秒；
- `HighCWu/distro`完成标准构建、npm packages和完整heavy-check矩阵；
- 第一次矩阵中`util-linux-check-programs`的`uuidd`前台`SIGALRM`退出测试等待5秒后
  超时；仅重跑失败任务后通过，workflow attempt 2最终成功。

对应运行记录：

- [主仓库元数据检查](https://github.com/HighCWu/linux-wasm-builder/actions/runs/35989981737)
- [主仓库基线构建](https://github.com/HighCWu/linux-wasm-builder/actions/runs/35989981757)
- [distro既有wasm32完整矩阵](https://github.com/HighCWu/distro/actions/runs/35989601707)
- [Linux wasm32/wasm64内核矩阵](https://github.com/HighCWu/linux/actions/runs/36089002814)

更新Linux pin后的[distro验证作业](https://github.com/HighCWu/distro/actions/runs/36089806803)
确认新内核可以完成编译；作业随后因Nixpkgs引用的`util-linux-2.42.2.tar.xz`和
`git-2.55.0.tar.xz`上游镜像返回404而失败。主仓库的
[固定基线构建](https://github.com/HighCWu/linux-wasm-builder/actions/runs/36091182303)也复现了前者。
这些失败不在内核构建栈中，外部源码可用性问题需与Memory64集成分开跟踪。
`distro` commit `6e278a8`随后修正了`mirror://kernel`路径中重复的`pub/`前缀；修正后的
util-linux和Git地址均返回HTTP 200。

独立的[wasm64启动验证](https://github.com/HighCWu/distro/actions/runs/36095361227)在Node 24
中创建shared Memory64，实例化64位内核、启动首个kernel Worker，并读到`Linux version`
banner。Node 22不能验证该产物中的64位table limits，因此当前实验profile的Node测试
基线为Node 24。

独立的[wasm64浏览器验证](https://github.com/HighCWu/distro/actions/runs/36095849736)还在
Playwright固定的Chromium和Firefox稳定浏览器中，以COOP/COEP隔离页面和Web Worker启动
同一内核并读到banner。该测试只证明内核与宿主启动边界，不代表wasm64 libc或用户态
已经完成。

随后完成的[wasm64用户态执行验证](https://github.com/HighCWu/distro/actions/runs/36116763735)
将由本项目工具链构建的最小musl程序直接作为`/init`，在Node 24、Chromium和Firefox
stable中经过`execve`、`binfmt_wasm`和Memory64用户模块loader运行，并通过Linux
`write` syscall返回成功标记。这确认了最小用户态闭环；尚未覆盖的线程、TLS、信号、
映射和更大软件包不能由该结果推定为已经完成。

`uuidd`结果应继续作为flaky候选跟踪。后续若再次失败，应保留guest日志并诊断signal投递、
进程状态转换和测试等待上限，不能用无界重试掩盖。
