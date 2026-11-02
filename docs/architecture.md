<!-- SPDX-License-Identifier: MIT -->

# 架构

## 目标与非目标

项目建设一个可持续演进的 Linux/Wasm 平台。核心衡量标准是 Linux 能力在 Wasm 上的
覆盖程度、语义正确性、真实软件兼容性、性能和长期可维护性。Linux 内核、工具链、
libc、发行版和宿主必须以清晰边界协同，使普通 Linux 源码和标准 syscall 在浏览器及
服务器 Wasm runtime 中可用，并让用户像在普通 Linux 用户态一样，依照自身代码和
依赖的许可证选择开源、闭源、非商业或商业发行方式。

核心验收要求之一是程序源码基本不改，通过常规交叉编译即可构建和执行。
兼容工作优先落在标准 syscall、工具链、执行 ABI 和 libc 的必要架构层；不能
把持续增加程序专用补丁、替代函数或要求应用使用项目专有加载 API 当作完成。

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

当前系统已经在NOMMU基础上恢复raw `SYS_mmap`/`SYS_munmap`的direct anonymous子集，
但仍缺少完整`mmap`/`fork`使用面。本项目恢复标准接口时不冒充硬件MMU：成功返回的
用户地址必须直接存在于进程linear memory中；无法满足的固定、高位或稀疏映射明确失败。

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
补齐mmap和进程复制；超出direct范围的高地址、稀疏映射和严格页保护明确报告不支持。

应用使用已实现的标准`mmap`、`munmap`、`clone`和`execve`接口；尚未实现的
`mprotect`和`fork`语义必须通过标准错误、缺失符号或明确能力说明暴露，不能静默假装
成功。当前非`CLONE_VM`的callback clone会eager-copy linear memory，但子进程从明确
提供的函数和新栈开始，不具备`fork()`从调用点继续执行的语义。需要表示被模拟程序
地址空间的JIT或应用在自身内部翻译地址。

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

## ELF 与动态链接：应用兼容优先

用户态 ELF 支持纳入后续实现路线，不包括把现成 x86/ARM ELF 当作 Wasm
直接执行，也不等于支持 ELF 内核模块。ELF 是容器和链接元数据；Wasm 仍是
交给引擎验证、实例化的代码。需要分别实现文件/段校验、符号和版本解析、
重定位、解释器及库搜索，不能只加 ELF magic 或换扩展名就宣布兼容。
ELF/Wasm 的机器标识、代码/数据/函数表索引表达及重定位映射必须先形成
明确的架构契约，不能伪造 x86 machine ID，或把原生 CPU 重定位直接套用。

参考 [Emscripten 动态链接](https://emscripten.org/docs/compiling/Dynamic-Linking.html)
的多模块加载思路和 [Wasm 动态链接约定](https://github.com/WebAssembly/tool-conventions/blob/main/DynamicLinking.md)
中的 dylink.0、GOT、memory/table 分配与初始化机制，但不直接采用其系统库和
JavaScript 环境作为本平台 Linux ABI。该工具约定仍声明 ABI 未稳定，试验须
固定版本、独立启用；自定义段不是新的引擎指令，不以未落地引擎提案作前提。

优先顺序：

1. 通用工具链兼容 ELF 风格的符号/版本语义，先核查 .symver、默认/指定版本、
   weak/visibility 和版本脚本；不能把所有历史版本悄悄合并到最新实现。
   libkcapi 尚未集成的专用符号补丁保留为调研草案，不作为正式交付路线。
2. 实现进程内的 Wasm 动态加载基础：依赖图、共享地址空间、GOT/函数表、
   重定位、构造顺序、失败回滚，再以不修改源码的真实共享库验证。
3. 接入用户态 ELF 加载及 PT_INTERP/依赖搜索；应用使用通常的编译选项和
   已有 dlopen/dlsym 等接口，不要求应用调用宿主 JavaScript 加载函数。
   若 ELF 与 Wasm 同时携带元数据，必须明确权威来源并拒绝冲突，而非猜测。
4. 补齐 TLS、跨库异常/SjLj、符号抢占/循环依赖、多线程装载与卸载安全。
   Worker 之间不能假定一个 JS Table 对象可直接共享，需一致的模块世代与
   函数表槽位协议；初期单 Worker 实验不得扩展为线程或 fork 已受支持。

所有数据地址仍须存在于有界 linear memory，装载分配必须与现有 allocator
协同，不能自行侵占 brk/mmap 区域或以 softmmu 模拟高地址。现有静态 SDK、
线程和实验性静态 fork 的支持范围保持不变；动态模块的 fork/exec 恢复需要
另行验证，不因新增加载器而解除原能力门禁。自有加载器与独立 ABI 支撑代码
采用 MIT，LLVM/musl/Linux 的必要改动保留各自许可证。

`scripts/probe_wasm_dynamic_linking.py` 是有界前期实验，不是生产加载器：
本地 Clang/LLD 18.1.3 与 Node 25.9.0 下，两个 C 共享模块在 wasm32/64
共享 memory 与 table32、数据/函数 GOT、构造函数、间接/跨模块调用和
memory.grow 后访问通过，并检查缺少数据符号必须装载失败。wasm64 首轮因
实验装载器漏设 __table_base32 而失败，补齐它与 __table_base 的一致基址后
通过，未归咎于编译器。实验没有 libc、Linux syscall、文件系统依赖装载、
ELF、TLS、浏览器、多 Worker 或卸载，不代表这些能力已实现，也不能代替
配套 LLVM 22 SDK 的目标检查。

通用 `.symver` 候选已发布到独立 LLVM 分支 `codex/wasm-symbol-versions`，
固定源码为 `b42af703f40a934728dc3ced88418dd1f46f6b2f`。Wasm 汇编器接受
显式旧版本和默认版本，并把版本绑定保留为不同的链接器名字；不把旧版本
引用退回到默认实现。独立的版本解析实现及新增测试采用 MIT，原有 LLVM
文件保留上游许可证。默认 SDK 和主仓库 LLVM pin 尚未切换。

[候选编译器验证](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41390102227)
通过已有 CI 的 `llvm-symbol-revision` 输入调用独立构建配置，固定使用上述
完整源码 SHA。它会构建候选 Clang、llvm-mc 和 lld，在 wasm32/64 下分别验证
C 源码到汇编再到对象、集成汇编器直接生成对象两条路径，再以 Node 执行
实际链接产物。测试包含不同签名的旧/默认函数、数据版本、同一编译单元中
旧版本引用与默认定义共存，以及缺少版本必须链接失败。Python 静态检查和
工作流 YAML 解析已通过；目标构建/运行待 CI，不能据此宣布兼容已完成。

这个候选仅验证 Wasm 对象中的静态显式版本绑定，不包含 ELF 动态版本表、
版本继承图、版本脚本、ELF 文件加载或 Linux 进程内 dlopen。后续需分别验证
这些语义，不能把名称兼容当作完整 ELF 二进制兼容。

该候选首次 CI 已完成编译，但在实际链接 definitions32.o 时被 wasm-ld 以
`duplicate symbol name api@VER_1` 拒绝。失败出现在同一编译单元的显式旧版本
引用与旧版本定义共存用例；尚不能视为符号版本兼容通过。需要修复重复链接符号
的归一化，并保留旧版本与默认版本的隔离，再重新验证双位宽两条对象生成路径。
默认 LLVM pin 保持不变。

修复候选 `533cc7e5de5d813266ebc31f4f03b0eee0159e2d` 保留各 MC 符号的汇编身份，
在对象 linking section 中将同名版本引用统一到定义优先的符号索引，重定位也
使用这个索引；同一版本的类型、函数签名或 TLS 属性不符时拒绝。未使用版本指令的
模块不执行这项归一化。实现继续位于独立 MIT 文件，既有 MC 头与 writer 仅作必要
连接并保留原许可证，默认 LLVM pin 仍为 `137009e`。

主仓库 `f421de9` 扩充真实编译语料：多个外部名称绑定同一旧版本、同对象旧版本
数据引用及经 volatile 函数指针的调用，并增加冲突签名拒绝检查。GCC 与 Clang
前端配 GNU 汇编器/链接器的原生 ELF 对照均通过；本机 Clang18 集成 ELF 汇编器
对该共存语料未能链接，而其原始 Wasm 汇编器会拒绝 .symver，均不作为候选通过证据。
双位宽前端/代码生成仅在禁用本机旧汇编器验证的轻量检查中通过，Python/JS 语法、
格式与静态 review 通过；
[41403636442](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41403636442)
实际完成了候选构建，但独立 llvm-mc 在函数指针的 call_indirect 显式表操作数处
报错，尚未完成对象链接/执行。实际日志 job125140679858 为432,616字节，失败
发生在 definitions32.s 的汇编，不是已通过版本隔离后才出现的运行错误。

Clang 默认输出该表操作数，而 llvm-mc 的默认特性不解析它；候选的实际 parser
按 reference-types/call-indirect-overlong 选择语法。主仓库 `8a2c7ca` 将两条 C
路径都明确设为 -mreference-types，所有 MC 路径对应 -mattr=+reference-types，
没有删减函数指针或版本检查。本机 Clang18/MC18 的双位宽普通函数指针语料已
复现默认 MC 失败、对齐特性后成功，但它不包含符号版本候选的验收。
同一固定候选 533cc7e 的新版完整检查已各配置一次于
[41410371324](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41410371324)，
仍待目标结果，默认 SDK/compiler pin 未切换。
本轮没有新增 libc API，也没有实现 ELF 文件加载或动态版本解析。

该次41410371324现已完成候选编译，完整压缩 run 日志为188,978字节。
wasm32 实际完成旧/默认函数及数据版本、同一编译单元引用、函数指针重定位、
Clang直接对象路径和缺失/冲突版本拒绝。wasm64 随后在独立 MC 汇编
definitions64.s:105 的 call_indirect 报 expected i32 / got i64，未完成该
位宽链接/运行，不能把 wasm32 的通过泛化为双位宽或 Linux/ELF 加载验收。

源码审查发现这是另一个真实 MC 问题：WebAssemblyAsmTypeCheck 的间接调用
无条件 pop i32，尽管本 fork 的 wasm64 函数表符号已标记64位索引，Clang
也生成 i64 函数指针。实验分支候选
`90352668f9244889a82254abf71ca9c46a2e8996` 修改 call_indirect 和
return_call_indirect 的类型检查：显式表根据实际 table limits 的 IS_64
选择索引类型；MVP 隐式默认表按目标默认宽度。没有把用户代码改为 table32
截断，也没有关闭类型检查。其它 table 指令的全部 memory64 组合未因此验收。
既有 LLVM 文件保留原许可证，新独立汇编回归语料为 MIT。

主仓库 `f3b0200` 在版本语料之前加入不含 .symver 的普通 volatile 函数指针
C 对照，沿真实 Clang汇编→MC对象→LLD→Node 路径执行，并要求相反索引宽度
的汇编被明确拒绝。原版本绑定、签名、数据与缺失/冲突检查保留；不能只通过
改名或跳过函数指针消除错误。Python语法/ruff、格式与静态数据流 review
通过，本机旧 MC18 也复现 i64 索引被按 i32 拒绝，但不作为已修候选的运行
证据。本地未进行重型 LLVM 构建。

固定新候选的完整云端检查已派发一次：
[41426210857](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41426210857)。
两位宽普通函数指针、原符号版本两条对象路径与错误拒绝均待该任务的实际日志。
默认 LLVM gitlink/SDK pin 继续保持137009e，Linux/musl 不变；这仍是工具链
兼容基础，不是 ELF 容器、动态 loader、版本表、TLS 或浏览器验收。
