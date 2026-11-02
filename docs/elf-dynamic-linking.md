<!-- SPDX-License-Identifier: MIT -->

# ELF 与 Wasm 动态加载实施边界

这里的目标是支持重新面向 Linux/Wasm 构建的 ELF 用户程序和共享库，让应用继续
使用通常的编译选项、`execve`、`dlopen`、`dlsym`。本文是实施设计，尚未冻结新的
文件 ABI，也不表示现有 SDK 已能生成或运行这种 ELF。

## 源码核查结果

当前可用路径仍是 Wasm 文件：

- Linux 的 `arch/wasm/kernel/binfmt_wasm.c` 负责装载程序、参数及辅助向量，
  并通过现有执行契约交给宿主编译和实例化。
- distro 的 `packages/kernel/src/worker.ts` 在 `compile_end` 中校验导入内存，
  然后直接构造 `WebAssembly.Module`；这里不能直接接收 ELF 字节。
- musl 的 `ldso/dynlink.c` 主体被 `#ifndef __wasm__` 排除；
  `ldso/dlstart.c` 的下一阶段调用也被排除。
  `arch/wasm32/reloc.h` 中的 `CRTJMP` 目前是 trap，没有可用的 Wasm 重定位及
  动态入口实现。不能只解除条件编译就视为完成移植。
- `src/ldso/dlopen.c` 的弱失败实现仍然存在，动态链接实现才能覆盖它。
  这份文件本身是静态链接的通用后备路径，不能据此推断上游删除了其它平台的
  动态加载实现。我们的工作是接通 Wasm 的已有接口，不新增 musl 公共函数。

独立 LLVM 符号版本候选已经验证的能力、默认 pin 和前期 PIC 实验见
[架构记录](architecture.md#elf-与动态链接应用兼容优先)。这些结果尚不覆盖
ELF 动态版本表或 Linux 进程内加载。

## 两层格式，分别解决问题

建议先保留 LLVM 的 Wasm 对象及链接流程，建立进程内多模块装载，再增加 ELF
输出和入口。暂不要求第一步就为 Clang 重写完整 ELF 目标文件后端。

| 层次 | 负责的内容 | 实现约束 |
|---|---|---|
| ELF 文件与进程入口 | 文件身份、解释器、依赖、符号版本及装载元数据 | 需要明确 Wasm 架构契约，不能假冒 x86/ARM |
| Wasm 模块 | 经引擎验证的代码、导入导出、线性内存及函数表引用 | ELF 中的代码仍须提取为合法 Wasm 模块再实例化 |
| 进程内动态加载器 | 地址分配、符号解析、GOT、模块依赖与初始化 | 与进程 allocator 和现有 syscall/信号路径协作 |

ELF 的 `PT_LOAD` 地址不能直接解释为 JavaScript 可调用的函数地址，`e_entry`
也不能当作 linear memory 中可跳转的 CPU 指令地址。数据地址、函数表索引、
模块内函数索引和文件偏移是不同的量，必须分别校验。这个差别同样存在于
wasm32，不由 memory64 自动解决。

正式定义文件格式前，要通过实际链接产物确定以下内容：

1. ELF machine/ABI 标识、32/64 位选择、字节序及兼容版本；不在实现前随意占用
   一个数值并声称它是标准 Wasm ELF ABI。
2. Wasm 代码载荷的定位方式、入口表达、段/节的用途，以及去掉节头后的可装载性。
3. 数据符号与函数符号的值如何表达，ELF 重定位与 Wasm 重定位分别由谁执行。
   不把本机 ELF relocation 编号套用到 Wasm。
4. `PT_INTERP`、`DT_NEEDED`、库搜索、辅助向量和权限检查如何进入现有 Linux
   exec 路径；失败必须符合 exec 的提交边界，不能破坏原进程后再返回普通错误。
5. 若 ELF 和 `dylink.0` 都携带依赖或布局信息，只允许一个权威来源，另一个必须
   一致；拒绝冲突，避免两个 loader 各自分配一次同一份数据。

## 从 Emscripten 借鉴的机制

[Emscripten 动态链接文档](https://emscripten.org/docs/compiling/Dynamic-Linking.html)
说明了多模块装载和既有 `dlopen`/`dlsym` 的接入；其 side module 产物本身仍是
Wasm，并不是 ELF loader。参考它不等于改用 Emscripten 的 libc 或 JavaScript
系统调用环境。

按照 [Wasm 动态链接约定](https://github.com/WebAssembly/tool-conventions/blob/main/DynamicLinking.md)，
下一项有界实现应从 `dylink.0` 的真实布局和依赖读取开始，替换前期实验中手工
指定的模块地址和函数表位置，再实现符号解析、数据重定位及构造顺序。
约定仍声明 ABI 未稳定，实验需固定所依据的版本，不引入未实现的引擎提案。

加载顺序必须是：校验全部依赖和能力 → 预留互不重叠的 memory/table 区间 →
建立符号和 GOT → 实例化并完成重定位 → 按依赖顺序运行构造函数 → 发布可用句柄。
实例化的 start 段可能执行代码，不能默认所有构造行为都发生在最后一步；初期
配置应拒绝无法纳入初始化协议的 start 段。

预留失败、缺符号和签名冲突应在执行用户初始化代码之前发现并回收本次预留。
构造函数已经执行后的 trap 不具备通用事务回滚能力，必须单独定义失败处理，
不能声称撤销几个地址就撤销了文件写入或其它 syscall 副作用。

## 首批验收与后续能力

首批进程内实验使用未修改源码的 C 库，验证普通 `-fPIC -shared` 产物中的依赖、
数据与函数 GOT、函数指针、重定位、构造顺序和缺依赖拒绝。真实 Linux/Wasm
程序随后通过已有 libc 接口装载它，验收文件查找、错误报告、重复装载与关闭；
宿主 Node 单独实例化成功不能代替这一步。

ELF 入口再分别验证普通 exec、解释器启动、错误 ELF/位宽/依赖拒绝及失败后原
进程恢复；先做完整静态程序的载荷提取可用于验证文件入口，但不得称为动态链接
已完成。正式 SDK 输出只在对应工具链、内核、libc 和宿主组合通过后启用。

TLS、符号抢占、版本继承、循环依赖、跨库异常、多 Worker 模块同步、安全卸载
及 fork 恢复需要各自验收。初期动态配置不得沿用静态 fork 已通过的结论。
所有数据仍在有界直接线性内存内，不为 ELF 或动态链接加入内核 softmmu。

自有独立加载器采用 MIT；Linux、LLVM、musl 文件中的必要修改保留对应许可证。
应用无需调用项目专有加载函数，也无需为了这个实验改用另一套 libc 公共 API。
