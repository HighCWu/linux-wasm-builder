<!-- SPDX-License-Identifier: MIT -->

# ELF 与 Wasm 动态加载实施边界

最新验收边界：eeebcd0的双位宽Node及四路浏览器七阶段已核实；35ea6c0的
双位宽Node八阶段已核实。1894258进一步修复既有dlinfo的句柄，九阶段组合
已派发Node和浏览器，尚未验收。ELF文件入口仍未实现。

当前构建接线另有变化：591d8bf / 集成9c41615已将通过独立SDK验收的
LLVM9035266接入默认工具链。下文的“默认LLVM不变”属于相应历史版本的边界；
新默认组合的运行库重建、普通SDK及动态/fork回归仍待独立验收。

## 普通 SDK 启用已有符号版本绑定

默认Clang/LLD和compiler-rt/libc++等运行库的源码pin统一为9035266，使用此前
公开预取核实的相同源码哈希。相对137009e，12个变更文件仅涉及Wasm MC符号
版本、对象符号表及间接调用table索引宽度检查；Clang驱动、compiler-rt、
libc++、libc++abi和libunwind源码没有变化。新版运行库仍会用新编译器重新
构建，不能把独立候选复用旧运行库的结果视为此组合已通过。

旧symbol-versions源码覆盖和独立SDK变量已删除；两个消费者直接引用sdk和
sdk-wasm64。普通源码中的.symver现在沿用已验证的@、@@和@@@绑定实现，
不需要用户选用独立编译器或删除版本引用；这不等于ELF动态版本表或跨DSO版本
查找已经实现。共享驱动补丁仍是独立配置，未因此默认启用动态链接。

静态review核对了符号名存储期、不同C名的同版本规范索引、旧/默认签名隔离、
别名可写数据、无.symver时的原路径及table32/64索引选择。固定输入哈希和
compiler/runtime pin一致；Nix格式、仓库pin检查、25项现有SDK参数转发/配置/
许可证检查通过。没有修改musl、Linux源码或应用API，不计为新增syscall。
新的聚合符号版本检查必须包含普通SDK profile、双位宽C++和两个版本阶段，
并另行验收双位宽动态九阶段及既有fork语料和关闭结果；本地检查不替代它们。

同一591d8bf已各派发一次：符号版本聚合41553968132，动态Node32/64
41553975106/41553981876，fork Node32/64为41553988852/41553995835。
当前排队或运行，尚未接受新默认组合通过；1894258原矩阵继续独立跟进，
不取消或重启，也不把不同编译器/运行库组合的结果混用。

上述591d8bf五路后来均失败。已读取fork32/64各23,755/23,770字节Heavy
日志；32位完整格式差异明确显示statix把sdk = self.sdk改成inherit (self) sdk，
treefmt门禁因此退出，尚未进入目标编译/执行。此前只跑nixfmt未覆盖这条规则，
不能把失败归因于LLVM符号版本语义，也不能把旧候选通过算作默认组合通过。
9250e0c / 集成90888ba修正这处写法，保留Landlock接线及默认编译器输入。
同一修复版本各派发一次：符号版本聚合41555454796，动态Node32/64
41555461464/41555468225，fork Node32/64为41555474987/41555481442；
Landlock Node32/64为41555487998/41555494487。结果仍待目标阶段及关闭证据。

## 浏览器动态加载已核实范围

固定 distro `05e9dbb` 的四路真实 Linux 镜像日志已逐项核实：

| 用户位宽 | Chromium 149.0.7827.55 | Firefox 151.0 |
|---|---|---|
| wasm32 | [41537955279][dylink32c] | [41537955806][dylink32f] |
| wasm64 | [41537956051][dylink64c] | [41537955781][dylink64f] |

[dylink32c]: https://github.com/HighCWu/distro/actions/runs/41537955279
[dylink32f]: https://github.com/HighCWu/distro/actions/runs/41537955806
[dylink64c]: https://github.com/HighCWu/distro/actions/runs/41537956051
[dylink64f]: https://github.com/HighCWu/distro/actions/runs/41537955781

每路在同一页面启动两次独立机器，各轮严格完成主程序符号/函数指针/错误、Linux
文件搜索及依赖/GOT/构造、别名及作用域/复用、循环依赖、跨库 SIMD 数值签名、
损坏和缺失输入拒绝及恢复六阶段，各有唯一 pass 和机器关闭，最后浏览器关闭。
这是共享字符串快照修复后对应源码的验收，不以工作流 success 代替阶段证据。
配置为单 CPU、独立动态 SDK；不覆盖 ELF 文件入口、动态 TLS、线程、动态 fork、
跨库异常或安全卸载，也不扩大普通 SDK 的默认能力。

这里的目标是支持重新面向 Linux/Wasm 构建的 ELF 用户程序和共享库，让应用继续
使用通常的编译选项、`execve`、`dlopen`、`dlsym`。本文是实施设计，尚未冻结新的
文件 ABI，也不表示现有 SDK 已能生成或运行这种 ELF。

## 标准共享编译驱动接入真实进程候选

既有独立驱动任务41530620425的实际日志现已核实：两位宽静态/共享分派、真实
PIC链接及引擎内的主程序数据/函数指针调用均通过。它仍不是Linux进程运行验收。
8c2a568的Node任务41535070759/41535070917也已逐项核实六阶段、唯一pass及
已发布runner等待machine.closed的关闭门禁，接受该源码的双位宽Node范围。

distro `13b54fe` / 集成 `08fa383` 复用同一已验证的驱动编译器，增加独立
dynamic-loader-driver及wasm64配置：共享库用普通Clang的-fPIC编译和-shared
链接，SONAME、RUNPATH经-Wl传入；不使用-nostdlib或手工wasm-ld回退。
普通动态镜像保留既有路径，候选主程序继续使用已验收SDK；仅DSO的编译和链接
切换到带Linux共享驱动补丁的固定默认LLVM源码。主程序专用执行对象及强制libc
导出归档不进入DSO，避免重复进程状态。两位宽共用同一编译器构建。

这是编译路径到Linux文件加载、标准dlfcn调用及真实库依赖/循环/SIMD语料的
集成验证，不是新的syscall实现或ELF入口。未切换默认LLVM、musl或动态SDK，
也未宣称一个通用CC包装已经能为任意构建自动区分主程序及共享库配置。
自有集成采用MIT，LLVM补丁保留原许可并随构建材料提供。

Nix语法/格式、差异及仓库元数据检查通过；本机LLVM22的两位宽小型链接确认
SONAME/RUNPATH参数拼写可用。本机LLVM18拒绝RUNPATH，不作为此LLVM22组合
的验证替身。真实进程六阶段及关闭由41542937012、41542944612异步验收，
尚未接受这一候选组合通过，不沿用旧镜像结果。

## 符号版本消费者的独立运行包修复

41529152599已明确失败。读取完整8,731,762字节Heavy构建日志后，首个失败是
apk-symbol-versions-wasm32运行包检查：SDK join中的许可证文件仍是指向构建机
Nix store的符号链接，原cp-r保留这些链接，触发现有包边界检查。该结果尚未进入
符号版本程序执行，不能归为.symver语义或syscall失败，也不能列为SDK验收成功。

distro `446dbef` / 集成 `df469d7` 改用cp-rL复制实际许可证字节，并执行SDK
原始SHA256SUMS核验，保留完整通知且不放宽运行包的store引用拒绝规则。
轻量受控目录验证旧外部链接被拒绝、物化后无符号链接且字节/校验和保持一致；
Nix格式、差异及元数据检查通过，不代替实际SDK打包和双位宽执行。已针对失败的
symbol-versions-check-both重新派发一次：41543946241，待核实原有C++回归、
两个版本阶段及关闭。

### 符号版本候选与标准共享驱动的目标结果

[41543946241](https://github.com/HighCWu/distro/actions/runs/41543946241)
现已完成，工作流及Heavy均成功。读取完整7,509,705字节构建日志，按固定
446dbef的消费者源码逐项核对：wasm32/64各有六个C++阶段及唯一pass，覆盖
类型异常/RAII、跨线程exception_ptr、继承异常/RTTI、thread_local析构、
条件变量和容器/线程/TLS；各有两个符号版本阶段及唯一pass，覆盖旧/默认版本、
不同函数签名、long宽度、同单元绑定、规范函数/数据指针及可写数据隔离。
固定源码runner要求await machine.closed，清理失败使检查失败；两个位宽均完成
该门禁。SDK profile也是聚合构建的必需依赖，未跳过许可证复制及校验和检查。
接受独立候选SDK在此静态链接Linux进程范围的结果，不等于跨DSO符号版本、
ELF入口或默认LLVM切换已经完成。

[41542944612](https://github.com/HighCWu/distro/actions/runs/41542944612)
也已完成且Heavy成功。读取完整6,019,556字节日志，按13b54fe合同核实wasm64
六阶段及唯一pass，包括Linux文件/RUNPATH、GOT和构造函数、别名/局部全局范围、
循环依赖/规范重定位、SIMD和错误恢复；固定runner的机器关闭门禁通过。
接受该候选普通Clang -fPIC/-shared构建DSO的wasm64进程范围。wasm32任务
41542937012仍运行，不扩大为双位宽通过；也不覆盖1894258的新九阶段组合、
浏览器、共享TLS或跨库C++异常。

## C++ 共享异常的 TLS 前提核查

本机Clang/LLD22的小型freestanding实验发现，仅给动态加载器增加异常tag绑定
仍不足以支持普通try/catch：-fwasm-exceptions、-fc++-abi=webassembly、-fPIC
编译的catch(int)产物，在-shared及import-dynamic链接时就因未定义
__wasm_lpad_context的R_WASM_MEMORY_ADDR_TLS_SLEB重定位失败，wasm64为对应
SLEB64。-ftls-model=local-exec和global-dynamic均复现；未通过关闭异常或复制一份
进程异常状态来绕过。这是本机wasm32/64-unknown-unknown的LLVM22前置实验，
不是固定Linux编译器或运行目标的验收，也未修改应用/libc或为此派发重型任务。

后续跨库C++异常必须先解决编译器/链接器的TLS引用、同一线程的异常运行状态及
共享异常tag，再验证析构、重抛和错误恢复；不得将现有C/SIMD动态链接通过
扩大为C++异常或动态TLS支持。原版上游的
[LLD实现](https://raw.githubusercontent.com/llvm/llvm-project/main/lld/wasm/Writer.cpp)
可用于后续对照，不能用当前main分支行为代替固定源码检查。

## 首个线程的库内 TLS 与指针重定位

distro `eeebcd0` / 集成 `92cff8c` 接通独立动态模式中的库内TLS。真实LLD产物
会将已定义TLS变量标为hidden/local，并把首个线程的初始TLS镜像放入本模块的
dylink数据区域；旧加载器一律拒绝TLS标志，因此普通C共享库也会装载失败。
组件仍默认拒绝TLS，只有禁止创建Worker的进程加载器显式启用该模式。外部TLS
导入、公开TLS数据绑定及未知标志继续拒绝，不把TLS地址按普通全局数据导出。

审查进一步实际复现：仅放行符号后，TLS中指向对端数据的初始化指针仍为零，
而普通数据指针已正确重定位。现在在所有实例和GOT建立后，先核对首线程TLS的
base/size/alignment及符号偏移位于本模块数据内，再执行普通和TLS重定位，最后
运行构造函数。不再次调用__wasm_init_tls，也不重置已驻留库的TLS；初始化后
布局错误属于不可恢复失败，不能伪装成普通dlopen错误继续执行。

真实循环C库验证初始值、零填充、构造函数读取对端TLS、volatile TLS指针的
跨库重定位及其先于构造函数完成、两个库及主程序状态隔离、后续修改和驻留复用。
新增第七阶段；隐藏TLS名称及初始化辅助符号不进入普通符号作用域。
编译配方显式导出内部__tls_base供布局核对，兼容LLD18与22的导出差异；不新增
应用函数、libc接口或syscall。Linux、musl与默认LLVM pin均不变。

本机Clang/LLD18和22的双位宽真实C产物及生产加载器模型通过，LLVM18两位宽
均table32，LLVM22的wasm64为table64。未开启首线程契约的反向控制在写入前
拒绝，原TLS指针遗漏重定位的实现实际得到零指针；布局/可见性/导入拒绝检查、
423项内核侧检查、两套TypeScript、双位宽C前端/静态分析、格式及差异检查通过。
小型通用工具链实验也补齐明确的import-dynamic策略，避免依赖LLVM18的旧默认。
这些不代替固定SDK/Linux目标或浏览器验收。双位宽Node和四路浏览器已各派发
一次，按同一eeebcd0的七阶段、规定轮次及机器/浏览器关闭核实，不沿用旧六阶段。
Node32/64为41546646208/41546653644；浏览器32位Chromium/Firefox为
41546660851/41546668003，64位为41546675381/41546682895。

此增量不提供额外线程、跨模块TLS绑定、TLS扩展/卸载、跨库C++异常、动态fork
或ELF入口。先前C++异常所需的未定义__wasm_lpad_context重定位障碍仍在，
不能用已定义的库内TLS通过来代替该问题的实现。自有加载器和消费者仍采用MIT。

## 构造函数中的标准 dlopen

distro `35ea6c0` / 集成 `b34347f` 接通构造函数里的递归dlopen。旧实现的busy
保护覆盖整个构造过程，因此构造函数无法装载新插件或重新打开正在初始化的父库。
现在全部实例、GOT/TLS重定位及文件引用就绪后，先发布句柄、记录和GLOBAL符号，
再释放构建保护并执行构造函数；文件I/O、分配器回调和Wasm start仍受原保护。

每个模块的pending/running/done/failed状态由所有复用图共享。递归打开会执行
尚未初始化的依赖，跳过正在执行或已完成的构造函数；失败状态保留，不能通过
重新打开另一个图来重试或掩盖失败。start/重定位/构造函数后的异常仍不可恢复，
exit/exec控制转移保留原路径，不声称能撤销用户初始化副作用。

真实C库使用未改动的标准dlfcn声明：根库构造函数先捕获一个缺符号拒绝，再加载
新叶库；叶库绑定已发布的GLOBAL函数/数据，重新打开仍在初始化的父库，并核对
函数指针及数据重定位。随后核对构造函数各一次、值的传递、驻留复用及fd清理。
新增第八阶段。轻量模型使用生产加载器和真实Clang共享库，只有libc转发及文件I/O
使用替身；它不能替代真正的musl、Linux或浏览器结果。

本机Clang/LLD18和22双位宽模型通过，LLVM22的wasm64为table64；保持构造期间
busy的受控旧行为会让同一C观察失败。共享依赖的重入/待初始化状态、构造失败
跨图不可重试、424项运行层检查、两套TypeScript、C前端/静态分析和格式检查
通过。通用实验和候选LLVM工作流初始化精确musl pin，以其真实头文件编译新C库。
双位宽Node八阶段41548686298/41548694359已针对35ea6c0各派发一次；
先核实这批结果，再派发对应
四路浏览器。现有eeebcd0七阶段浏览器继续运行，不取消或用其代替新构造能力。

这改善普通库的标准接口调用路径，不是新增syscall或libc接口；内核、musl、
默认LLVM pin均未变。模块仍驻留，不提供安全卸载、跨库异常、RTLD_NEXT、线程
或动态fork。自有实现、配方与C消费者采用MIT。

## TLS 的双位宽 Node 已核实结果

eeebcd0的41546646208及41546653644均已完成。分别读取2,685,993字节和
5,190,403字节Heavy实际日志，核实两路原七个完整阶段、各唯一pass，以及
该源码发布runner等待machine.closed的关闭门禁。接受该源码在双位宽Node的
首线程库内TLS及指针重定位范围，不扩大为浏览器或35ea6c0构造函数重入；
其它仍运行的任务按各自实际结果核实。

## 原始 musl dlinfo 与实际对象句柄

distro `1894258` / 集成 `59b1ff5` 修复已有dlinfo接口错误：musl原始
src/ldso/dlinfo.c会把已验证的句柄直接作为link_map指针返回，旧加载器却给出
1、2等小整数。程序使用dlinfo成功后得到错误地址；轻量对照用原始函数体复现
了句柄1被原样当作指针返回，没有以直接解引用低地址制造不确定行为。

现在dlopen返回通过既有用户分配器分配的真实struct link_map。主程序和每个
依赖对象各有稳定句柄、名字及双向链表，inode别名和驻留dlclose不重建对象。
l_addr是本模块线性数据基址；原始Wasm文件没有ELF dynamic节，l_ld明确为NULL，
不伪造动态节或PHDR。SDK编译期断言公共结构的五个机器字布局；新私有
linux_dlopen_v1.link_map_abi导入让旧宿主在exec提交前拒绝新SDK。未改变
musl源码、公共函数或头文件，也未改动Linux或默认LLVM pin。

对象句柄覆盖依赖库，因此查找、GLOBAL提升及待执行构造函数也改为以该对象的
依赖子图为范围，不能把依赖的消费者暴露进来。所有提供者的规范函数指针均有
预算，包含同名的不同定义；复用仍共享初始化状态且失败不可重试。

小型实验直接编译固定musl的原始dlinfo.c，仅替换其内部句柄验证/错误通知，
调用生产加载器及真实C共享库；核对链表完整性、依赖范围、别名、错误输出保留。
Clang/LLD18及22双位宽通过，LLVM22的wasm64含table64；C布局及前端/静态分析、
426项运行层检查、两套TypeScript、已有I/O及浏览器控制器检查通过。
这不是Linux进程验收。新九阶段真实组合已各派发一次，按对应源码、Node阶段及
浏览器各两轮、机器/浏览器关闭核实，不沿用原七/八阶段。原定八阶段浏览器验收
合并到此九阶段组合，避免对同一功能连续构建两组浏览器镜像。

待验收任务：Node32/64分别为41552635774、41552642934；浏览器32位
Chromium/Firefox为41552657841、41552668415，64位为41552685894、
41552694884。以上均固定1894258，当前仍运行，尚不作为目标验收证据。

## 已核实的七阶段浏览器与八阶段 Node

eeebcd0四路41546660851/41546668003/41546675381/41546682895的实际日志
现已全部读取并逐项核对。各路七个精确阶段均出现两轮、各轮唯一pass及机器
关闭，最后浏览器关闭；分别为wasm32/64 Chromium149.0.7827.55和Firefox151.0，
单CPU。四个构建日志分别2,761,162、2,760,786、5,264,697、5,264,186字节。
接受该源码首线程库内TLS及指针重定位的这些浏览器范围。

35ea6c0的41548686298/41548694359也已读取各2,687,243和5,191,537字节
Heavy日志，确认双位宽Node八阶段、各唯一pass及发布runner等待machine.closed
的关闭门禁，接受构造函数dlopen的对应Node范围。上述结果不覆盖1894258真实
link_map句柄的新组合，也不扩大为ELF、外部TLS绑定、线程或动态fork。

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
快照仍待实现。该早期组件当时拒绝循环依赖、TLS/absolute/未知符号能力、函数重导出
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

### 搜索优先级与共享链接参数修正

源码`9d15937` / 主仓库`d23e13f`修复读取搜索中的实际语义错误：此前任何
候选错误都会继续尝试后续目录，可能绕过已经打开的损坏同名库。现在只在
open本身返回ENOENT、ENOTDIR、EACCES或ENAMETOOLONG时继续；其它open
错误、打开后的noexec/读取/分配错误及格式错误均停止。已有驻留对象仍按原
身份复用，普通失败释放临时缓冲与fd，后续请求可恢复。没有新增libc函数。
依据是当前tombl/musl基线dynlink.c的path_open及load_library先打开再解析
边界，未复制其实现代码进入MIT运行层。

轻量双位宽真实PIC产物/进程模型验证先损坏后有效的同名搜索、EMFILE、打开
前后EACCES的区别、ENOMEM、清理与恢复；使用修复前源码的反向控制必须在
损坏首候选断言失败。两套TypeScript、417项既有运行层及新C语料双位宽静态
分析通过。Linux语料已加入真实首目录损坏文件、失败无fd泄漏、删除后正常
搜索和依赖装载；仍需booted目标确认。

后续读取a10ec98实际日志：41528174103为wasm64，在直接wasm-ld链接时漏
传-mwasm64；41528174233为wasm32，固定LLD对共享库的main_value未解析
数据引用报错。两项均停于构建，没有进入四阶段；前述启动入口错误已越过。
源码`1ec430b` / 主仓库`1087117`分别增加明确位宽与
`--unresolved-symbols=import-dynamic`，保留真正的动态导入及运行时符号解析，
不使用忽略错误/零地址替代。独立Linux -shared驱动补丁也选择这一默认策略，
位置在用户链接参数之前，用户可再指定更严格策略。默认LLVM pin仍未切换。

本地LLD18双位宽两库PIC链接通过，不据此接受固定LLD的RUNPATH或真实
Linux进程；补丁对精确固定驱动源码以fuzz=0干跑通过。最终1ec430b已针对
Node两位宽和独立驱动构建各派发一次，任务集合为
[41530620340](https://github.com/HighCWu/distro/actions/runs/41530620340)、
[41530620425](https://github.com/HighCWu/distro/actions/runs/41530620425)、
[41530620735](https://github.com/HighCWu/distro/actions/runs/41530620735)。
当前排队，按各任务计划中的检查名识别；尚未接受目标阶段或关闭。9d15937
两项41530248183/41530248231及旧驱动41528943175仍在运行，保留原任务，
其较早源码不含最终链接参数修复，不能代验最终版本。

### 循环共享库依赖接入

源码`3c3246e` / 主仓库pin `65f4a60`接通循环NEEDED图。模块记录在跟随
依赖边之前注册，回边复用同一记录；迭代DFS生成单次初始化序列。所有模块
先实例化并完成GOT/数据重定位，再运行构造函数。前向函数导入仍经过已有
标量签名检查；未实例化的提供者使用既有延迟转发绑定，构造阶段调用时全部
实例已存在。自依赖、互依赖及已有菱形图均保持有限遍历和单一实例。

循环内不存在适用于所有成员的“依赖先构造”顺序。本实现按DFS后序执行，
遇到回边不重复安排；库不得假设循环中每个对等成员的构造函数都已执行。
Wasm start或构造陷阱继续作为不可恢复的初始化失败处理，不伪装为普通
dlerror回滚。TLS、构造中重入dlopen、跨库异常、线程发布、动态fork及ELF
入口仍不因此实现。

两份普通MIT C共享库使用最终basename的临时A、B、最终A三次普通链接，
生成真实A→B→A依赖，仅最终两库进入镜像。轻量Clang18/LLD18双位宽
产物先核对两条NEEDED，再通过ProcessDylink模型验证双向数据与函数指针
重定位、构造函数调用对方函数、有限递归调用、每库构造一次，以及以另一个
成员为root重新打开时复用状态。旧已发布加载器的反向控制在真实循环加载
断言失败。模型桥接仍不作为Linux进程或table64验收。

两套TypeScript、现有运行层、三份C消费者的双位宽静态分析及格式检查通过。
Linux镜像增加独立阶段`cyclic dependencies, peer constructors and canonical
relocations pass`，在此前四阶段之外核对真实文件加载、上述状态、驻留close
和fd清理。新Node双位宽各已派发一次，须完整五阶段、唯一pass、退出及发布
runner关闭结果才可接受；默认SDK和musl/LLVM pin不变，没有新增公共函数。
对应任务为
[41531559713](https://github.com/HighCWu/distro/actions/runs/41531559713)和
[41531559935](https://github.com/HighCWu/distro/actions/runs/41531559935)，
位宽以各任务的实际计划/Heavy检查名为准，当前均在运行。

### 标准dlfcn的双位宽Node已核实结果

固定1ec430b的41530620340实际为Node wasm32，41530620735为Node wasm64，
两项现已读取完整构建步日志并确认四阶段各一次、唯一`::vm-test::pass`且无
失败标记：主程序符号/错误、真实Linux文件及RUNPATH/GOT/构造、别名/作用域/
复用/close、缺失损坏输入及恢复收尾。对应压缩日志/构建步大小分别为
1,089,011/4,969,734和490,134/2,519,336字节。

已核对该源码发布的run-test.js/shutdown.js及Nix runner路径：成功标记后
仍须await machine.closed，关闭异常、启动异常或后续运行错误均令退出码
失败；两项Heavy和工作流均成功，该范围关闭门禁成立。由此接受1ec430b的
真实内核/libc/Worker/独立SDK组合的Node范围，不扩大为后继循环图、start
重入、浏览器、动态fork或ELF能力。

旧9d15937的wasm64任务41530248231也已取实际日志，仍因未传-mwasm64
失败于DSO构建，未进入目标运行；后继1ec430b已修复且通过，无需重派旧版。

### start回调中主程序dlsym的表项隔离

源码`de74734` / 主仓库pin `0164c9d`修复一个具体覆盖缺陷：新模块的活动
element段已在实例化时写入表，但ProcessDylink游标此前仍指向该批次起点。
Wasm start回调主程序并dlsym一个尚未取址的主程序函数时，可能覆盖刚写入的
模块表项。现在在实例化前将临时分配游标放到整个发布区间之后，供重入的
主程序规范函数指针分配；批次仍用独立保存的起点布局。成功保留回调新分配的
指针，未发生重入分配时回收多余预留。实例化前的普通验证错误恢复旧游标；
陷阱和控制转移仍按原不可恢复边界处理。没有禁止main dlsym或新增应用API。

轻量双位宽模型使用真实Wasm start、活动element段和主程序Wasm函数，在
start回调中取得新指针，随后分别执行原模块表项与主程序函数并核对身份；
修复前已发布源码的反向控制实际复现覆盖并失败。两套TypeScript、既有运行
层及格式检查通过。这一分支的I/O/主回调使用模型桥接，不称为booted Linux
或table64验收。新Linux目标继续跑完整五阶段，验收本轮源码的组合回归，
不将其当作这个专门start分支的目标覆盖；默认SDK、内核及musl/LLVM pin不变。
固定de74734的两项新任务为
[41532654095](https://github.com/HighCWu/distro/actions/runs/41532654095)与
[41532654276](https://github.com/HighCWu/distro/actions/runs/41532654276)，
当前均在运行，位宽按各任务Heavy检查名识别。

### 浏览器进程镜像接线

源码`37c5ed4` / 主仓库pin `7c6f72a`增加Chromium/Firefox的wasm32/wasm64
四路执行入口。复用dynamic-loader对应位宽的runtimeAssets.initramfs和发布
kernel包，加载共享库继续走Linux文件syscall；不把库文件改成host fetch，
也不增加浏览器专用应用接口。独立配置固定单CPU、无外部磁盘，Nix和运行器
都检查这一配置，未扩大线程或fork支持。

沿用process-app.js、runRuntimeSmoke和独立Playwright控制器，在同一页面
运行两次完整新机器。每次要求五阶段按顺序各出现一次及唯一pass，包含循环
依赖；缺失/重复/错序、其它语料阶段、失败及RCU stall均拒绝。每轮返回前
须等待machine.closed并排空控制台，浏览器关闭后还检查迟到pageerror/crash。
start中重入dlsym的专门分支仍只有轻量模型证据，不能由这些五阶段代验。

本地只运行已有Node控制器/协议验证及格式检查，真实浏览器和重型构建交给
公开Actions。新corpus也验证两轮、错误CPU和关闭后迟到异常拒绝；这些宿主
替身不是浏览器结果。四项实际计划和Heavy检查名已核对，当前均在运行：

| 目标 | 任务 |
|---|---|
| wasm32 Chromium | [41533159785](https://github.com/HighCWu/distro/actions/runs/41533159785) |
| wasm32 Firefox | [41533159121](https://github.com/HighCWu/distro/actions/runs/41533159121) |
| wasm64 Chromium | [41533158701](https://github.com/HighCWu/distro/actions/runs/41533158701) |
| wasm64 Firefox | [41533159385](https://github.com/HighCWu/distro/actions/runs/41533159385) |

须逐项读取真实五阶段、两轮、机器及浏览器关闭结果后，才接受对应浏览器
范围；旧Node通过不替代。9d15937的旧wasm32任务41530248183现已取实际
日志，确认仍因main_value数据引用未选择动态导入失败于构建；1ec430b已
修复并通过双位宽Node，无需重新派发旧版。

### 数值及SIMD函数的原生前向调用

源码`8c2a568` / 主仓库pin `d08d209`移除共享库函数ABI的一处实际限制：
原签名解析器把v128当成非法类型；循环中的前向调用又经JavaScript包装，
即使放宽解析也无法传递SIMD值。现在解析保留i32/i64/f32/f64/v128精确
签名，前向边使用独立MIT Wasm跳板，参数和结果直接通过共享表的call_indirect
进入提供者，不经过JS数值转换。表索引类型独立采用table32或table64。

每个提供者实例化完成后就发布规范表项并更新跳板目标，保留后续start调用
已就绪函数的行为；全部GOT/数据重定位仍在构造阶段之前完成。未绑定及未
定义的弱目标保留空表项陷阱，签名不匹配继续在初始化前拒绝。规范函数指针
仍指向提供者本身，跳板不成为dlsym或GOT.func的新地址。引用值ABI、函数
重导出、TLS、跨库异常和JS host callback接收SIMD仍不在已实现范围内。

普通C循环库用vector_size(16)和-msimd128构建，在B构造中跨前向边调用A的
向量函数，并在后续标量入口中再次调用，核对结果220。双位宽Clang18/LLD18
产物通过ProcessDylink模型；仅恢复旧JS转发器、保留新签名解析的反向控制
实际在v128构造调用处产生JS/Wasm类型错误。另以真实Wasm标量入口执行
v128跳板，分别验证table32/table64及空目标陷阱；这些是Node引擎fixture，
不是Linux或浏览器验收。回归还核对提供者已就绪而整个图尚未完成时的start
调用、规范指针、弱空指针及此前的start表项隔离。

两套TypeScript、既有运行层、三份C消费者双位宽静态分析、浏览器协议及格式
检查通过。Linux及浏览器语料增加第六阶段`cross-module SIMD signatures
and typed forward calls pass`，并保留此前五阶段；浏览器仍每路两轮及关闭。
默认SDK和内核/musl/LLVM pin均不变，没有新增公共函数或提案阶段的Wasm特性。
以下精确8c2a568任务计划和Heavy检查名已核对，当前均在运行：

| 目标 | 任务 |
|---|---|
| Node wasm32 | [41535070759](https://github.com/HighCWu/distro/actions/runs/41535070759) |
| Node wasm64 | [41535070917](https://github.com/HighCWu/distro/actions/runs/41535070917) |
| wasm32 Chromium | [41535070764](https://github.com/HighCWu/distro/actions/runs/41535070764) |
| wasm32 Firefox | [41535071096](https://github.com/HighCWu/distro/actions/runs/41535071096) |
| wasm64 Chromium | [41535071069](https://github.com/HighCWu/distro/actions/runs/41535071069) |
| wasm64 Firefox | [41535070933](https://github.com/HighCWu/distro/actions/runs/41535070933) |

须实际六阶段、唯一pass、正常收尾和关闭才可接受；较早版本任务不代验新ABI。

此前3c3246e的wasm64任务41531559713现已读取实际完整五阶段及唯一pass，
压缩日志/构建步分别为484,970/2,508,768字节。发布run-test.js/shutdown.js
与已审计门禁无差异，仍须等待machine.closed且关闭异常使任务失败；该任务
成功，接受该源码的wasm64 Node循环装载范围，不扩大为wasm32、后继SIMD、
start专门分支或浏览器结果。

### 浏览器共享字符串解码修复

37c5ed4的四路浏览器任务现均已读取实际失败日志。Chromium149.0.7827.55
和Firefox151.0都在首次main_add符号检查失败，尚未通过第一阶段；原输出为
`main_add errno=0 dlerror=none`。不是五阶段或关闭已通过。语料先消费dlerror
再交require二次读取，掩盖了原始错误；e0ccd29 / 集成5fa0ad0先保留原始
symbol/address/error，单路诊断41536583996已派发，当前仍在运行。

本机已有Chrome153.0.8010.36，在隔离的极小页面中验证：共享视图直接交给
TextDecoder.decode会抛出`The provided ArrayBufferView value must not be shared`，
复制成普通Uint8Array后正确解码。同页函数表身份和grow正常。随后将修复前后
的生产ProcessDylink源码打成小型API fixture，分别提供真实共享Wasm32/64
Memory、table32/64和Wasm函数。旧类的main_add查询返回0并记录同一异常；
修复后均返回规范表项4，函数调用结果42。这个对照验证了生产类的浏览器API
路径，完整内核/libc/镜像组合仍由公开CI验收。

4d13d79 / 集成eac3370将有界C字符串复制为自有字节快照后再严格UTF-8解码，
不放宽UTF-8、NUL或4096字节边界，也不改变地址范围和应用接口。当前源码
05e9dbb / 集成8484b31另外整理SDK说明，执行代码相同。这是宿主实现兼容，
不是声称编码规范要求拒绝shared输入；[Encoding接口定义](https://encoding.spec.whatwg.org/#dom-textdecoder-decode)
本身仍声明AllowSharedBufferSource。

Node进程模型主动启用实测浏览器的解码限制，再检查首次主程序符号、搜索、
循环/SIMD及start重入路径；两位宽通过，修复前实现的反向控制在首次main
dlsym断言失败。两套TypeScript、现有运行层、格式与仓库检查通过。本地只做
小型源码/API验证，所用临时浏览器会话和HTTP服务均已关闭。

新精确05e9dbb四路各派发一次，计划及Heavy检查名已核对，均在运行：

| 目标 | 任务 |
|---|---|
| wasm32 Chromium | [41537955279](https://github.com/HighCWu/distro/actions/runs/41537955279) |
| wasm32 Firefox | [41537955806](https://github.com/HighCWu/distro/actions/runs/41537955806) |
| wasm64 Chromium | [41537956051](https://github.com/HighCWu/distro/actions/runs/41537956051) |
| wasm64 Firefox | [41537955781](https://github.com/HighCWu/distro/actions/runs/41537955781) |

仍须实际六阶段、两轮、唯一pass及机器/浏览器关闭结果，才能接受对应范围。
Chrome API对照不能扩大为Firefox或完整Linux支持，旧8c2a568任务不代验修复。
