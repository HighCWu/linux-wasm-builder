<!-- SPDX-License-Identifier: MIT -->

# 架构

## 目标与非目标

项目建设一个可持续演进的 Linux/Wasm 平台。核心衡量标准是 Linux 能力在 Wasm 上的
覆盖程度、语义正确性、真实软件兼容性、性能和长期可维护性。Linux 内核、工具链、
libc、发行版和宿主必须以清晰边界协同，使普通 Linux 源码和标准 syscall 在浏览器及
服务器 Wasm runtime 中可用，并让用户像在普通 Linux 用户态一样，依照自身代码和
依赖的许可证选择开源、闭源、非商业或商业发行方式。

动态链接、某一种文件系统或某一个应用的成功运行，都只能证明相应能力达到
了一个阶段，不能替代全平台目标。专项实现可以随实验结果演进或被替换，应用可见的
Linux 接口和跨组件 ABI 则必须受到兼容性治理。

近期非目标：

- 不以某一种地址翻译、动态链接或任何单一兼容功能定义整个项目。
- 不承诺安全运行任意未经验证的第三方 Wasm 模块。
- 不在第一阶段实现 swap、完整 page reclaim 或 ELF 内核模块 ABI。
- 不把 Emscripten side-module ABI 直接当作 Linux 进程 ABI。

当前内存路线保持`CONFIG_MMU=n`和direct linear-memory指针；若未来稳定Wasm能力允许
其他内存模型，必须作为独立profile评审，不能隐式改变全平台ABI。

## 当前上游基础

`tombl/linux` 的 Wasm 架构为每个用户进程维护独立的用户
`WebAssembly.Memory`，Linux 内核使用另一块共享 memory。用户模块通过
`linux.syscall` 等少量 imports 进入内核。该模型提供清晰的 syscall 和许可证边界，
本项目保留这一性质。

当前系统缺少完整 `mmap`/`fork` 使用面。本项目在 NOMMU 基础上恢复可用的标准
接口，但不冒充硬件MMU：成功返回的用户地址必须直接存在于进程linear memory中；
无法满足的固定、高位或稀疏映射明确失败。

## 平台工作面

### 内核架构

持续完善启动、SMP、调度、clone/exec、信号、futex、时间、uaccess、ptrace、异常、
virtio 和架构自测。改动应优先落在 `arch/wasm`，避免无必要修改 Linux 通用代码。

### 工具链与 libc

维护 `wasm32/wasm64-unknown-linux-musl` target、调用约定、TLS、原子、链接、启动、
signal trampoline 和 libc syscall 面。工具链必须能独立构建普通应用，而不是只服务
内核测试。

### 用户态和发行版

扩大可构建软件集合，维护构建定义、软件包集合、rootfs、init、shell、语言 runtime
和集成测试。具体构建及包管理工具属于发行实现选择，不构成平台 ABI。端口补丁必须
区分真正的平台限制与暂时缺失的内核能力。

### 宿主与设备

浏览器/Node 宿主管理 Worker、共享 memory、生命周期和 virtio；存储覆盖 EROFS、
ext4、OPFS及宿主目录，网络覆盖虚拟交换、TCP/UDP/DNS与可替换的宿主适配器。

### 兼容性与发行

维护 Linux selftests/LTP子集、浏览器真实运行、性能基准、可复现产物、npm/镜像发布、
SBOM和对应源码包。

## 架构优先级

发生设计冲突时，按以下顺序判断：

1. 标准 Linux 用户态行为和可观察语义是否正确；
2. 是否能在浏览器和 Node 的 Wasm 约束下可靠实现；
3. 跨内核、工具链、libc、宿主的边界是否稳定且可测试；
4. 是否保持与普通 Linux 用户态一致的许可证选择边界；
5. 最后才选择具体的direct分配和优化机制。

因此不能为扩大表面兼容性而返回无法直接解引用的地址，也不能因某项映射语义无法实现
而暂停存储、网络、进程、工具链或发行版工作。

## 内存兼容工作流：Direct pointer

当前`CONFIG_MMU=n`路径只使用原生linear-memory指针。内存工作流在这一约束下逐步
补齐mmap和fork；超出direct范围的高地址、稀疏映射和严格页保护明确报告不支持。

应用继续使用标准 `mmap`、`munmap`、`mprotect`、`fork`、`clone` 和 `execve`，不
改写为私有编程模型。不支持的语义必须通过标准错误或明确能力说明暴露，不能静默
假装成功。需要guest MMU的JIT或应用在自身内部翻译地址。

专项约束见[direct-memory.md](direct-memory.md)。

## 组件边界

### Linux（GPL）

- 全平台的标准 syscall、进程、文件、网络和设备语义；
- `arch/wasm` 启动、SMP、调度、uaccess、signal和设备支持；
- 必要时维护每进程direct mapping元数据和uaccess；
- 通过窄 ABI 驱动 runtime/host，不向用户程序暴露内核内部结构。

### LLVM（Apache-2.0 WITH LLVM-exception）

- Linux/Wasm target、ABI、链接和常规代码生成；
- driver、LLD、compiler-rt和工具链发布；
- 不为默认ABI插入隐藏的用户指针翻译。

### musl（MIT）

- Linux/Wasm 启动、线程、TLS、signal和完整 libc 接口；
- 标准 mmap/fork包装和工具链sysroot；
- 在需要时读取扩展psABI capability；
- 不把 GPL 内核实现链接进用户程序。

### 独立 runtime/host（MIT）

- Linux machine启动、Worker和生命周期；
- virtio设备、存储和网络宿主适配；
- browser Worker、SharedArrayBuffer和平台资源适配；
- loader与各扩展ABI的版本校验；
- 管理每进程direct `WebAssembly.Memory`及其声明上限。

## 安全模型

平台第一阶段信任由配套工具链生成的用户模块。用户代码最终执行raw Wasm memory
access；后续若要运行不可信模块，需要签名、验证/重写或更强的multi-memory
capability边界。
