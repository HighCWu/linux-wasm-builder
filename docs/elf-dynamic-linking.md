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

## 已推进的元数据实验

主仓库 `eedaa34` 改进既有 `scripts/probe_wasm_dynamic_linking.py`：通过普通
`-fPIC -shared` 与 SONAME/共享库输入，让 LLD 真正生成依赖；解析 `dylink.0`
的布局、对齐及 NEEDED 信息后，再计算不重叠的 memory/table 预留和依赖顺序。
缺依赖与容量不足在实例化前拒绝。构造函数按解析结果排序，外部数据指针通过
真实数据重定位初始化；函数 GOT 使用生产者的原始表索引，核对跨库函数指针
身份，不再另外分配同一函数的重复槽位。

新增反向控制发现旧语料的简单构造操作可被 Clang 折叠进初始数据，因此旧结果
不能证明运行时构造顺序。现在用 volatile 输入保留实际构造操作，初始化前核对
原值，消费者构造函数观察依赖的结果；颠倒顺序必须使真实 C 观察断言失败。

本地 Clang/LLD18 与 Node25 的 wasm32/64 正向、颠倒顺序拒绝、函数指针身份、
数据重定位及增长后访问均通过；这两种产物使用 table32。实际源码编译量很小，
没有进行本地 LLVM 构建。Ruff、工作流 YAML 和差异检查通过。
既有独立 LLVM 云端工作流增加同一实验，使用固定9035266候选的实际编译器；
它与默认 SDK/LLVM pin 分开。固定eedaa34的
[41474068045](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41474068045)
已通过既有CI入口派发一次，先保留完整符号版本检查，再执行新的PIC检查；
候选结果已核实，见下文。直接按独立工作流文件名派发返回404且未创建任务，因此
改用已注册的CI入口调用该分支的复用工作流，没有重复目标构建。

这仍是有界工具链/引擎实验：仅两个已知模块、无环依赖，未解析所有符号属性，
没有接通 Linux 文件系统查找、libc 动态入口、ELF、TLS 或多 Worker。
实例化可执行链接器生成的内存初始化 start 段；尚未建立任意模块 start 代码的
信任或回滚协议，不能把当前预留计划当作生产加载事务。

固定eedaa34的41474068045中，candidate作业125374896700现已成功，实际日志
确认完整符号版本检查及两位宽PIC阶段，包括反向构造顺序必须拒绝。候选9035266
生成的wasm32使用table32，wasm64使用table64；本机Clang18的table32结果不能
替代这一差异。整体工作流因独立metadata作业的文档行宽检查失败而失败，该问题
已由763a939修复并经41476117126验收；没有重启已成功的重型candidate作业。
上述证据仍不覆盖Linux进程加载、ELF入口或libc动态链接，默认LLVM pin不变。

## 独立 SDK 与 Linux 进程验收接线

distro677cf9e / 集成363f770把候选9035266接入独立symbol-versions配置。
它通过现有SDK配方覆盖编译器输入，保留已验收的musl、compiler-rt、libc++、
Linux与执行层；默认LLVM gitlink及普通SDK源码pin继续使用137009e。
这一步把原先不带libc的引擎实验推进到正常SDK的链接、安装和进程执行入口，
不是增加ELF文件格式或动态加载支持。

候选源码的
[公开预取41487600049](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41487600049)
实际日志确认90352668f9244889a82254abf71ca9c46a2e8996及
`sha256-/l/16+htX8HXUrQS6ehSCpWr1Hc8Szl7awt5bpeqFNw=`。
独立编译器只生成WebAssembly，省去此配置无需使用的本机代码后端；普通配方
仍默认构建本机与Wasm后端，SDK工具和标准C/C++入口保留。

两个标准C单元分别编译、链接成普通Linux/Wasm可执行程序，通过BusyBox启动并
正常退出。消费者验证旧版和默认版函数的不同签名、long宽度、同一编译单元内
版本引用、真实间接调用、跨单元函数/数据指针身份与可写数据的版本隔离。
指针从volatile槽位读回，避免编译器按不同C名称提前折叠比较，使断言真正
观察链接后的重定位。没有给musl增加函数或修改应用调用接口。

GCC及Clang18配GNU外部汇编器的宿主参考通过；Clang18本机集成汇编路径在
同单元版本引用处链接失败，未算通过。原版Clang18的Wasm后端也明确拒绝
.symver；这与候选SDK待验证的能力缺口一致。musl双位宽前端、静态分析、
Nix/shell格式及差异检查通过，不代替目标运行。

单项symbol-versions-check-both聚合双位宽SDK配置校验、既有C++运行语料和
新C消费者，共享一次候选LLVM构建。目标两阶段、唯一pass、正常退出及发布
runner的机器关闭仍待核实；旧引擎实验成功不自动接受这一新SDK组合。
固定677cf9e的
[41488752556](https://github.com/HighCWu/distro/actions/runs/41488752556)
已派发一次，后续按其实际目标阶段验收，不重复构建。
可从legacyPackages的symbol-versions.sdk及symbol-versions-wasm64.sdk访问
独立SDK，暂不切换默认工具链。自有配方和语料采用MIT，LLVM及依赖保留原许可。

## 可复用元数据解析与无副作用布局规划

distro `3a00905` / 集成 `822d420` 将临时 PIC 实验中的关键步骤移入运行时代码：
`wasm_binary.ts` 读取实际模块的 `dylink.0`，`dylink.ts` 计算整批模块的布局。
实验脚本现在直接调用这两份实现，不再维护另一套布局与元数据解析逻辑。
独立候选工作流在 PIC 阶段初始化精确 distro pin；普通 CI 运行解析与布局检查。

解析器逐个限制 subsection、向量及字符串的边界，校验 UTF-8、u32 LEB128、
重复布局和目标架构。它保留 NEEDED、RUNPATH、导入/导出符号属性及未知扩展编号；
重复符号组按出现顺序保存，不把 weak/TLS 标记或未知扩展悄悄删除。后续加载器
必须在执行初始化前完成能力检查；读到元数据不意味着接受对应能力。

布局全程使用 BigInt，内存与函数表分别指定 i32/i64；支持表达 memory64/table32
及 memory64/table64，避免高于 JavaScript 精确整数范围的地址被舍入。对齐、
末端溢出及整批后段失败均在修改实际资源前发现。调用者仍须从进程 allocator
取得独占区域，并在锁内提交；计算结果不是内存预留，不包含依赖解析、符号解析、
start 安全性或初始化回滚。

409项运行层检查、两套 TypeScript、Ruff、格式及差异检查通过。本机小型 Clang18
真实 wasm32/64 产物使用新实现通过原有 PIC 阶段和反向构造顺序控制，两者均为
table32；高位 BigInt/table64 布局只有模型验证，不冒充 table64 引擎验收。
候选9035266的旧 table64 实验也不自动接受这一新实现。未新增或修改 musl 公共
接口，Linux 文件装载、标准 dlopen/dlsym 及 ELF 入口仍待接通。

## 实际模块绑定组件

distro `e456e76` / 集成 `5a175b8` 增加 `dylink_linker.ts`，让真实共享库的装载
不再依赖实验脚本手工填写 GOT。组件读取已取得文件的依赖图，去重并计算依赖
初始化顺序；符号查找另用 root/NEEDED 广度顺序，保留首个可见定义，不把构造
顺序误当查找顺序。局部和隐藏定义不进入该批次的全局作用域。

内存、函数表、全局及函数导入类型从实际二进制读取。内存和表分别验证位宽、
minimum 及调用方保存的实际 maximum；函数签名不匹配在数据初始化前拒绝，
不通过 JS 转发掩盖 ABI 错误。可直接绑定的依赖函数使用原 Wasm 函数。
LLD 可把弱导入属性记录在 env 下，即使实际只有 GOT 导入；组件兼容该表达，
未定义弱符号的地址保持零。函数指针优先复用生产者表槽；确实没有槽的导出
函数从事先计入容量的区域分配规范槽位。

调用者必须先取得并锁定独占 allocator 区域和函数表区域，组件只在这些已提交
资源内初始化，不直接 grow 或另建用户地址空间。先绑定整批 GOT，再运行数据
重定位，最后按依赖顺序执行一次构造函数。缺依赖、缺符号、能力和容量错误
发生在初始化前；start、重定位或构造函数执行后的异常返回专门的不可恢复错误，
后续进程接线必须终止该进程，不能伪装成普通 dlopen 失败或重试构造函数。

实际 Clang18 wasm32/64 产物通过直接/间接跨库调用、外部数据重定位、规范函数
指针、新槽调用、弱空指针、增长后访问和构造顺序反向控制，两者均为 table32。
415项运行层及两套 TypeScript 检查通过。普通公开 CI 新增小型已发布编译器语料，
无需为绑定代码变更重复构建候选 LLVM；云端结果另行核实。旧候选 SDK 联合构建
仍运行，未取消或重复派发。

本组件尚未接入进程执行路径。Linux 文件查找和权限、主程序及已装载库的全局
符号作用域、allocator 锁、句柄生命周期、dlerror/dlclose、Worker 同步及 fork
快照仍待实现。当前明确拒绝循环依赖、TLS/absolute/未知符号能力、函数重导出
及非标量函数参数/返回值；普通 SIMD 指令并不因此被禁用。未知扩展和不兼容
资源也拒绝。它没有实现 ELF、动态符号版本或安全卸载，不新增 musl 公共接口，
默认程序执行路径不启用这份组件。

固定5a175b8的
[41506673065](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41506673065)
现已完成。已读取实际Clang产物作业125488507426的日志：wasm32/64分别确认绑定、
重定位、GOT、弱空指针、规范槽位、构造、直接/间接调用、增长，以及反向构造
顺序拒绝。日志包226,287字节，对应运行步骤1,476字节。它接受e456e76组件在
Clang18/table32范围的引擎实验，不覆盖后续主程序作用域、读取桥接或Linux进程。

## 主程序符号与 Linux 文件读取桥接

distro `f47bc91` / 集成 `0177c50` 为组件增加独立的主程序/全局符号输入。
数据符号使用主程序的绝对地址，不再叠加DSO偏移；函数保留实际签名和已有
规范函数指针。显式库句柄的lookup只搜索自己的对象组，链接时仍允许主程序
优先解析。额外表容量包含可被句柄查找的导出函数，而不只统计已有GOT引用。
构造期间的exit/exec执行控制信号须原样逃出，不能被包装成普通初始化trap。

实际PIC语料加入普通静态Wasm主模块，与库共享memory、table及主模块stack。
主模块函数、数据和规范指针均由真实C代码生成。wasm32/64本地实验确认库能
直接调用主程序、共享其数据，函数和数据指针一致，句柄不查到仅属于主模块的
定义。原重定位、增长、弱符号和反向控制保留。两者仍是table32及引擎实验。

独立MIT执行支持对象位于 `distro/dynamic-loader/execution.c`：通过普通Linux
open/fstat/fstatvfs/read/close取得文件、以dev/ino表达身份，并以固定五个u64
槽传递数据、长度和正errno。使用O_CLOEXEC，校验普通文件和noexec，重试read
的EINTR而不重试close；错误释放缓冲区并关闭fd。单次文件上限64MiB是此加载
配置的容量策略，不是Linux文件或mmap能力限制。还有配对aligned分配/释放、
受AT_SECURE及身份检查限制的LD_LIBRARY_PATH读取；现有binfmt_wasm已提供
AT_SECURE，没有为此改变Linux权限策略或绕过VFS通过宿主fetch读取。

417项运行层及两套TypeScript检查通过，读取桥接在GCC/Clang分别通过真实临时
文件和硬链接身份、read EINTR/EOF、noexec、ENOMEM、重复读取/释放、fd数恢复、
后续成功及安全环境控制。双位宽musl头文件前端和Clang静态分析、GCC分析也
通过。宿主注入不代替Wasm内核运行，读取对象尚未随SDK链接或被Worker调用。
默认SDK、musl gitlink及公共函数声明均不改变。

下一步须连接Worker、文件搜索及进程allocator锁、对象复用/句柄生命周期，
再将musl已有dlopen/dlsym调用路径接到独立配置，进行真实Linux进程和关闭
验收。这里尚未完成这个接线，也不接受多线程动态加载、fork动态快照、ELF
入口或动态符号版本。候选SDK联合构建41488752556后续已失败，原因和针对性
修复见下文；此处保留读取桥接阶段的实现范围。

## 标准 dlfcn 调用路径与独立 SDK 接线

distro `9cbe7d0` / 集成 `69d8401` 接通Worker中的每进程加载状态和已有musl
dlopen/dlsym/dlerror/dlclose路径，增加独立 `sdk-dynamic-loader` 及wasm64配置。
应用使用原有dlfcn接口，文件读取走正常Linux syscall；SDK只是隔离交付这组
架构兼容代码。默认SDK、musl gitlink及其公共头文件/函数集合不变。

musl补丁只在Wasm且显式WASM_DYNAMIC_LOADER配置下替换三个已有失败后备的
调用路径，转入独立MIT执行支持对象；普通构建保持原后备。Worker在exec提交前
读取主程序表类型和标量函数签名，检查输入内存、私有导出及内核能力。缺少能力
或混用fork-continuation时返回ENOEXEC，避免运行一半后才发现组合不兼容。
该配置拒绝clone/clone3，不声称已经解决跨Worker模块发布或动态fork快照。

ProcessDylink通过受控C回调取得文件快照、规范路径和allocator区域。支持直接
路径、LD_LIBRARY_PATH、直接依赖的RUNPATH/$ORIGIN及系统目录查找；文件身份、
别名、句柄、LOCAL/GLOBAL/NOLOAD和已有依赖实例在进程内复用。构造函数不因
重复打开或单独打开已有依赖而重跑，句柄关闭采用musl的对象驻留策略。普通失败
撤销临时引用/缓冲区；C回调或初始化trap终止进程，exit/exec控制转移原样传递，
不在旧执行上下文继续调用libc清理。内核私有函数异常则按内核故障终止机器。

源码复核确认，当前Wasm专用文件mmap在完成复制后释放文件引用，不能用它固定
已加载库的inode。Linux `1be96089c` 增加mm所有的fget引用、单调私有ID和清理，
`356fb863f` 使用VFS getattr校验与用户fstat相同的dev/ino，兼容文件系统身份
转换。输入fd只在读取和引用交接期间保留，之后关闭；close_range不能释放这些
mm引用，mm关闭时统一fput。初始化新mm时不继承宿主加载状态。没有新增应用
syscall、软件MMU或地址翻译，Linux文件内的必要修改保留GPL。

内核源树的
[41516892547](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41516892547)
先验证59937da的既有hash并取得1be96089c；后续
[41519085644](https://github.com/HighCWu/linux-wasm-builder/actions/runs/41519085644)
以该结果验证父树，再取得356fb863fc217b662d8da08bfa4e289ff969b159，hash为
`sha256-aNrKArZmnXmPgI73OShgnUTLjWlRK22LLL2Pz+8Xkrw=`。
构建继续用固定内容hash的Git获取，未绕过校验。

本地417项运行层、两编译器读取测试、两套TypeScript、双位宽前端/静态分析及
格式检查通过；实际内核引用函数的宿主模型验证fd复用、VFS身份转换、错误无
泄漏、ID边界和mm清理。真实小型Clang18产物在两位宽通过ProcessDylink模型，
覆盖作用域、依赖复用、读取收尾、重入拒绝和控制转移；其中I/O/内核引用使用
模型桥接，仍不作为Linux目标运行或table64验收。

独立目标用普通C主程序和两个普通C共享库，要求四阶段、唯一pass及发布runner
的machine.closed门禁：主程序符号/错误报告；Linux文件、RUNPATH、GOT和构造；
别名/作用域/复用/close；缺失/损坏输入及恢复收尾。Linux Clang当前仍向-shared
注入静态table base，所以共享对象由同一Linux ABI编译成PIC对象，再交普通
wasm-ld链接；通用cc -shared驱动还需独立修复，不能称为已完成。

固定9cbe7d0的新目标已分别派发一次，计划阶段通过且Heavy已开始：

| 目标 | 任务 |
|---|---|
| Node wasm32 | [41523965930](https://github.com/HighCWu/distro/actions/runs/41523965930) |
| Node wasm64 | [41523974771](https://github.com/HighCWu/distro/actions/runs/41523974771) |

实际四阶段、关闭和内核无异常结果尚待日志核实。前一代引擎模型/工作流成功
不替代这一新内核、libc、SDK及Worker组合。ELF入口、TLS、循环依赖、非局部
跳转、C++、线程及动态fork仍需继续实现，完整目标不因此缩小或完成。

后续两项9cbe7d0目标均已结束且工作流失败；wasm64实际构建日志确认，整库
引入libc使弱启动适配对象`__main_argc_argv.o`引用了当前主程序不需要的
`__main_argc_argv_envp`，在链接时失败，尚未执行上述四阶段。
源码`a10ec98`、主仓库pin `8198aa5`将两个弱启动适配对象排除在强制导出
归档之外，保留原始libc供链接器按main签名选择；没有修改musl源码或应用
入口。轻量Clang18/Wasm测试确认void、argc/argv及显式envp启动ABI均能
链接执行，其他库函数仍导出；这不是完整SDK验收。两位宽已针对修复各重新
派发一次，实际Linux目标结果仍待核实。

### 独立的Linux共享链接驱动候选

源码`ce11b6a`、主仓库pin `390ad02`新增`dynamic-driver-check-build`，在
既有LLVM源码pin上应用独立的Apache-2.0 WITH LLVM-exception补丁。只对
Linux/Wasm `-shared`省略可执行文件的crt1、固定table base和隐式静态系统
归档；显式库参数照常传给链接器，libc/runtime符号由主模块提供。普通可执行
链接和非Linux目标保持既有分支。默认LLVM、musl及动态SDK配置没有切换到
候选编译器；当前SDK的通用cc -shared接线仍待后续完成。

公开任务[41528943175](https://github.com/HighCWu/distro/actions/runs/41528943175)
将构建候选Clang，检查两位宽的实际驱动命令，并用普通-fPIC -shared生成
DSO、与主模块在引擎内实例化，验证直接调用、主模块数据和函数指针。该任务
尚在运行。本地Clang18/LLD18小产物已验证同一引擎检查路径，但不证明候选
Clang已构建成功，也不替代Linux进程或ELF入口验收。

### 符号版本SDK候选的宿主后端修复

41488752556实际日志确认`SDK consumer wasm64`在配置驱动检查时失败：
候选禁用宿主后端后，默认目标被识别为unknown，显式宿主三元组也没有可用
后端。该项尚未进入目标运行语料，不能据此接受SDK或符号版本的进程能力。
源码`3762d29`、主仓库pin `3f2f209`恢复候选的默认宿主后端构建，保留原来
完整SDK的环境隔离、响应文件和C++检查。候选LLVM源码及普通SDK pin均未
改变，没有删除检查或把宿主失败视为Wasm通过。

同一联合目标已针对修复派发
[41529152599](https://github.com/HighCWu/distro/actions/runs/41529152599)，
当前运行中；双位宽目标阶段、退出和关闭结果仍待实际日志核实。
