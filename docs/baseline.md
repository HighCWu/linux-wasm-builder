<!-- SPDX-License-Identifier: MIT -->

# 当前 Linux/Wasm 基线

本文件记录开始平台改造前已经存在的能力和已知缺口。它用于区分“继承自现有项目的
能力”“本仓库重新验证的能力”和“未来路线”，避免把源码中存在的实现直接写成已经
通过全部环境验证的承诺。

基线日期：2026-10-04。

## 固定源码

| 组件 | 分支 | commit | 构建关系 |
|---|---|---|---|
| `HighCWu/distro` | `main` | `080f9bc72134ff173965659d7a274cc2475989ba` | 集成构建与测试入口 |
| `HighCWu/linux` | `wasm` | `fa8637a3088f6eb3fa79436ecc74c743d3a068c6` | `distro` Nix pin与submodule一致 |
| `HighCWu/llvm-project` | `wasm-linux` | `137009e264eb237b5f5adcbae1b7e209f79291f5` | `distro` Nix pin与submodule一致 |
| `HighCWu/musl` | `master` | `03594de9a5b30b541b6c94f0379c300624526133` | `distro` Nix pin与submodule一致 |

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
- futex、信号、时间和其他接口由现有kselftests/LTP子集覆盖；`futex_waitv`已验证
  private/shared waiter在值不匹配时返回`EAGAIN`，并在绝对超时到期时返回`ETIMEDOUT`。

### 设备、存储和文件系统

- virtio block、console、filesystem、network、vsock和entropy设备接口；
- EROFS只读系统盘、ext4可写盘和可选OverlayFS临时写层；
- Node目录共享、OPFS以及浏览器File System Access API适配；
- `@lowland/guest` SDK提供进程执行、流式I/O、文件和挂载操作。

### 网络

- Linux/Wasm运行实例间虚拟以太网交换；
- ARP、IPv4、TCP、UDP和DNS宿主实现；
- HTTP/Fetch适配以及通过可配置connector访问宿主TCP服务。

### 用户态和发行

- musl sysroot及C/C++工具链，并包含Rust smoke路径；
- Linux已恢复asm-generic编号的raw `SYS_mmap`/`SYS_munmap` direct anonymous子集，
  musl公开接口通过标准syscall进入同一路径；支持读写、非固定的
  `MAP_PRIVATE | MAP_ANONYMOUS`，以及按页解除完整映射或其前缀、后缀和中间子区间；
  分配与现有malloc/brk路径共用底层分配器，拆分映射的最后一个存活区间解除后才释放
  共同backing；
- BusyBox、Bash、coreutils、curl、Dropbear、Git、Lua、Python、QuickJS、SQLite、Vim等
  软件包定义和测试；
- `@lowland/kernel`和`@lowland/guest` npm包；
- Nix负责构建和依赖求解。当前`distro`内部使用Alpine风格的v3 APK格式组装rootfs并
  支持在运行中的Linux/Wasm系统内安装；这是当前发行版的可替换实现选择，不是
  Linux/Wasm平台ABI，也与Android APK无关。

## 当前明确缺失或受限的能力

- 当前基线没有`fork()`或`vfork()`；现有程序主要通过`posix_spawn()`启动子进程。
  callback形式的非`CLONE_VM` clone已经能eager-copy进程linear memory，但子进程从
  明确提供的函数和新栈开始，不能从`fork()`调用点继续执行。
- `mmap()`当前只恢复了direct anonymous子集；`MAP_FIXED`/`MAP_FIXED_NOREPLACE`、文件
  映射、共享映射和严格页保护均不支持。`munmap()`会更新进程内的区间登记并回收完整
  解除的backing，但不能保证陈旧指针立即fault或让linear memory物理缩小。
- 宿主网络尚无任意目标的出站UDP代理，TCP桥接尚无重传，并存在队列丢包风险。
- System V IPC当前配置或执行路径不完整，`shmget`会在已知实验配置中trap。
- 重复创建Linux/Wasm运行实例会使宿主runtime内存持续增长，实例销毁后的资源回收
  尚未稳定。
- 浏览器CPU交接与并发memory growth之间存在已知stale typed-array view竞态。
- 若干LTP测试仍失败、跳过或hang；测试框架本身也还有可能掩盖部分晚到错误。

这些条目是基线缺口，不等同于最终设计限制。修复时应优先恢复标准Linux可观察语义，
并为无法实现的语义提供明确错误。

## 验证层级

1. `CI`检查文档格式、submodule元数据和Nix pin一致性，不构建大型源码树。
2. `Build baseline`在GitHub-hosted runner上构建`@lowland/kernel`和`@lowland/guest`包。
3. 标准distro checks在单独任务中运行。
4. scheduler敏感或耗时较长的heavy checks按测试项拆分运行。

工作流不上传大型临时构建树。本地默认只初始化较小的`distro` submodule；Linux、LLVM
和musl工作树可在确有源码修改需要时再按需初始化。

## 首次验证结果

2026-09-24的首次公开CI结果：

- 主仓库元数据检查通过；
- 主仓库在`distro` commit `90d4ed4`上完成`@lowland/kernel`和`@lowland/guest`包构建，
  用时42秒；
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

[direct anonymous mmap验证](https://github.com/HighCWu/distro/actions/runs/36144523610)
随后构建并运行了包含匿名`mmap()`/`munmap()`、线程、TLS、table64回调和信号处理的
wasm64工具链smoke，同时确认超范围`MAP_FIXED`返回`ENOMEM`；该工作流也通过Node 24、
Chromium和Firefox stable的Memory64启动检查。此结果只覆盖当前明确列出的direct子集，
当时尚不代表raw mmap syscall、固定映射、文件映射或严格页保护已经实现；raw syscall
在后续direct-memory增量中恢复。

后续的partial `munmap()`验证在[wasm32常规CI](https://github.com/HighCWu/distro/actions/runs/36205546683)
中真实启动工具链smoke，并在[wasm64工作流](https://github.com/HighCWu/distro/actions/runs/36205546695)
中完成Memory64用户程序执行及Node 24、Chromium和Firefox stable启动验证。测试覆盖
中间拆分、前缀和后缀裁剪、共同backing的最后释放、未登记范围no-op，以及非对齐
`munmap()`的`EINVAL`语义。

[标准mmap syscall集成CI](https://github.com/HighCWu/distro/actions/runs/36280351560)进一步从
Linux、musl和宿主runtime的固定GitHub pins重建发行栈；其中`basic-init-check-mmap`真实
启动Linux/Wasm用户态程序并验证libc和raw `SYS_mmap`/`SYS_munmap`路径、页对齐、
zero-fill、普通load/store、前缀/后缀/中间partial unmap，以及fixed、非法protection和
zero-length请求的错误语义。

[direct mmap并发与边界检查](https://github.com/HighCWu/distro/actions/runs/37199096884)
随后在`distro` commit `e177452`上扩展同一用户态测试，覆盖四线程重复分配、映射内容
隔离、并发partial unmap、碎片解除后的重新分配与zero-fill，并确认长度溢出、未对齐
`munmap()`及尚未支持的`MAP_FIXED_NOREPLACE`返回明确错误。

[direct mmap地址hint检查](https://github.com/HighCWu/distro/actions/runs/37207472475)在
`distro` commit `87fc6bd`上从固定musl pin重建并启动用户态测试，验证未对齐hint的
页对齐、已保留backing空洞的精确复用与zero-fill，以及hint与live mapping冲突时回退
到普通分配而不覆盖原映射。

[futex_waitv完整验证](https://github.com/HighCWu/distro/actions/runs/36289066632)在同一
`distro` commit上通过全部116个job。`basic-init-check-futex`覆盖private/shared waiter的
值不匹配和绝对超时语义；恢复的`kselftests-check-futex`通过
`KSELFTEST_HARNESS_NO_FORK`适配NOMMU用户态，并重新运行upstream
`futex_wait_wouldblock`和`futex_wait_timeout`。因此此前对合法参数返回`EFAULT`的记录已
判定为过期，不需要Linux架构特判或softmmu。

[合入main后的复验](https://github.com/HighCWu/distro/actions/runs/36290446402)再次通过上述
futex检查，但`util-linux-check-programs`先后暴露`uuidd`的SIGINT清理和前台`SIGALRM`
退出超时。后续压力测试确认Linux/Wasm可以稳定完成跨进程signal路由、signalfd唤醒、
双fd poll、进程回收和Unix socket清理；故障样本中的SIGALRM已经从pending队列移除，
而服务仍能响应新的UUID请求。

最终确认这是测试readiness竞态：uuidd会先创建socket并写pidfile，随后才阻塞受管信号、
创建signalfd并进入服务循环。测试若在文件刚出现时发送外部SIGALRM，可能命中仍在生效
的启动超时handler；该handler只处理`SI_TIMER`，因此会消费并忽略来自`kill()`的信号。
测试现在以一次成功的UUID协议请求作为服务循环ready barrier，再分别对24个全新进程
发送SIGALRM和SIGINT，并要求正常退出、回收及删除socket/pidfile。修正后的两轮定向压力
检查（[第一轮](https://github.com/HighCWu/distro/actions/runs/36313842026)、
[第二轮](https://github.com/HighCWu/distro/actions/runs/36314247672)）和
[117-job完整矩阵](https://github.com/HighCWu/distro/actions/runs/36314691212)均通过。因此该
现象不再作为内核signal投递缺陷或独立flaky项跟踪；失败时的pending mask、fd和服务探测
诊断仍予以保留。

private-memory callback clone随后增加了有界的Worker启动握手：父Worker最多等待30秒，
子Worker只有在内核与用户实例准备完成后才能发布成功，创建、反序列化、实例化或memory
复制失败会发布负errno；超时后晚到的子Worker不能执行子进程用户代码。Linux端同时补齐了
`kernel_clone()`失败时callback参数的释放。定向检查
[basic-init-check-clone-no-vm](https://github.com/HighCWu/distro/actions/runs/37195556538)
从新的Linux固定pin重建并验证了全局区、堆、栈和direct mmap allocator的父子快照与
后续隔离。该结果验证的是从明确函数和新栈开始的callback clone，不代表标准`fork()`。
