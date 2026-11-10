<!-- SPDX-License-Identifier: MIT -->

# ELF 与 Wasm 动态加载实施边界

最新验收边界：6b1777e 的合并 Node 任务41572697826现已核实双位宽动态加载
十阶段、跨库符号版本三阶段、各唯一pass及发布runner关闭门禁，覆盖新默认
编译器/内核和Linux文件名字节/BOM增量。浏览器仍接受1894258的四路各两轮
九阶段及机器/浏览器关闭，不能沿用来证明新十阶段或新组合。ELF文件入口新增
默认关闭的静态容器候选，完整目标运行待验收，见本文末节。
详见[合并实际结果](process-syscalls.md#启动修复后的合并-syscall-回归结果)。

当前构建接线另有变化：591d8bf / 集成9c41615已将通过独立SDK验收的
LLVM9035266接入默认工具链。下文的“默认LLVM不变”属于相应历史版本的边界；
新默认组合的6b1777e Node合并回归已验收上述指定范围，后继源码及浏览器仍须
独立核实。

## Linux 文件名字节与前导 BOM

distro3dc5c82 / 集成23a091f修复普通dlopen的路径兼容问题：旧代码用严格
UTF-8解码用户C字符串，拒绝合法的非UTF-8文件名；TextDecoder默认还会删除
字符串开头的BOM，使该相对文件名错误地搜索另一个名称。

Linux C字符串现在使用自有MIT的可逆字节转换：有效Unicode保持原样，每个
不可解码字节在宿主内部暂用U+DC80..DCFF表示，调用libc、发布link_map名称
或返回dlerror时还原原字节。有效代理对整体处理，避免把emoji的低半部分误当
文件名字节。解码前复制独立快照，保留浏览器对SharedArrayBuffer输入的限制。
仍按实际编码字节数执行4096字节上限，不增加用户API或修改musl。

Wasm元数据仍严格要求有效UTF-8，但不再删除BOM字符；依赖、符号、模块和
RUNPATH字段均保留该字符，不允许将Linux文件名的字节转义带入模块格式。
本地测试核对所有65,536种两字节输入的精确往返、过长编码、UTF-8代理区、
截断/越界码点、前导BOM和中文/emoji，以及共享缓冲快照。430项内核宿主检查、
两套TypeScript、29项原有I/O/浏览器控制器检查通过。

Clang18/22双位宽的小型实际Wasm产物调用生产ProcessDylink；模型C查找用独立
Buffer原始字节比较，验证新inode加载、原始musl dlinfo和link_map名称，另核对
前导BOM相对搜索及Unicode别名。构造顺序/重入拒绝的反向控制仍通过。原始C
读取桥也在GCC/Clang下真实读取非UTF-8硬链接，并逐字节核对realpath结果。
新增C消费者和独立共享库的双位宽前端/静态分析通过。这些不替代目标Linux。

真实语料在原九阶段中加入第十项：创建三份独立共享库，使用非UTF-8、前导BOM
和中文/emoji文件名；验证构造一次、精确link_map名称、inode别名及文件/fd清理。
每个别名使用独立路径，避免在驻留加载器内用同一缓存路径代指不同inode。
新双位宽Node已各派发一次；需完整十阶段、唯一pass和机器关闭。对应四路浏览器
在Node结果后继续，各需两轮十阶段及机器/浏览器关闭。此前9250e0c及1894258
检查继续独立跟进，不取消或将旧九阶段用于证明此字节路径增量。

固定3dc5c82的Node32/64任务41557112361、41557119503均已失败；实际 Heavy
日志核实为内核 LSM 边界符号缺失，没有进入十阶段语料。后继已修复该链接缺口，
并在6c6ac0a合并检查中到达 Linux 启动，但另遇 FDT/initrd 覆盖导致根目录挂载
失败。6b1777e 已接入相应启动修复，41572697826 的实际双位宽十阶段、跨库
版本三阶段和关闭现已核实，接受该组合的Node范围。原失败任务的状态未改写，
详见[实际合并结果](process-syscalls.md#启动修复后的合并-syscall-回归结果)。

## 已核实的九阶段 Node 与浏览器

1894258的六路实际Heavy日志已读取并按固定源码的九阶段合同核对：

| 检查 | 任务 | 完整构建日志字节 | 已核实轮次 |
|---|---|---:|---:|
| Node wasm32 | 41552635774 | 2,687,594 | 1 |
| Node wasm64 | 41552642934 | 5,191,905 | 1 |
| Chromium wasm32 | 41552657841 | 2,763,038 | 2 |
| Firefox wasm32 | 41552668415 | 2,762,505 | 2 |
| Chromium wasm64 | 41552685894 | 5,266,609 | 2 |
| Firefox wasm64 | 41552694884 | 5,265,974 | 2 |

工作流及Heavy均成功。每轮精确九阶段和唯一pass均已核对；浏览器同一页面两次
独立机器，每轮machine shutdown及最终browser shutdown均匹配，单CPU，
Chromium149.0.7827.55/Firefox151.0。Node固定runner要求await machine.closed
且清理失败使任务失败。接受这些源码的真实对象句柄/依赖范围/元数据错误恢复，
连同此前TLS和构造函数重入的这一组合；不扩大为新的默认LLVM/内核、字节路径、
ELF入口、跨库异常、线程或动态fork的结果。

## 普通 SDK 启用已有符号版本绑定

后续独立跨库实验见[动态绑定实验](#跨共享库的符号版本绑定实验)；静态通过不
代表跨DSO版本绑定已实现或通过，也不代表存在ELF版本表。

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

## 跨共享库的符号版本绑定实验

distroaf63fe8 / 集成5934ac3新增独立dynamic-symbol-versions及wasm64配置。
它使用默认LLVM9035266和已有动态SDK，不覆盖主动态加载语料或添加新的libc
函数。沿用Wasm PIC对象、dylink.0、普通dlopen/dlsym与已有进程加载器，检查
显式版本名在MC、对象链接、GOT和跨模块调用中的完整路径，不伪造ELF版本表。

提供者直接复用已有symbol-versions/provider.c，保留同单元旧/默认版本别名；
新的消费者是普通C，包含旧版i32函数与默认long函数、两个旧名引用、函数指针
及可写数据引用。真实消费者经标准.symver声明选择版本，不要求应用使用某个
新的查询API，主程序只用现有dlsym按普通未限定名字取得默认定义。

三个规定阶段分别检查：

1. 含api@VER_MISSING强引用的独立库必须被拒绝，不能绑定到默认api；dlerror
   单次读取后清空，GLOBAL查询仍无该定义，临时fd全部清理，随后正常加载可用。
2. 加载消费者及其$ORIGIN依赖，真实C调用核对旧/默认不同签名、wasm64高于
   32位的long参数、同单元引用及规范函数/数据指针；修改旧数据后默认值仍23，
   提供者的same_unit从76变124。
3. 通过NOLOAD取得已加载提供者；dlsym默认函数/数据地址与C引用保持一致，
   旧指针及数据仍有效、局部范围没有进入RTLD_DEFAULT，驻留关闭后无fd泄漏。

两个C库原样在宿主GCC的真实ELF共享库下通过正向调用、版本选择与指针检查，
Clang18使用GNU汇编器也通过。宿主Clang18默认集成ELF汇编器则在提供者链接
时因api@VER_1没有符号版本节而失败；记录为该宿主路径的差异，未修改提供者
或把它算成Wasm后端结果。原始C的Clang18/22、wasm32/64前端及静态分析通过，
但这些命令不执行.symver的MC对象生成和链接，不能冒充目标编译器已通过。

Wasm实际共享链接和三阶段、唯一pass、runner等待machine.closed仍待公开CI。
通过后也只能接受这些Wasm版本名的跨库绑定，不能扩大为dlvsym、ELF版本需求
校验、版本脚本、跨库C++异常或普通SDK默认启用动态链接。自有实验/构建采用
MIT，发布物保留musl及compiler-rt许可证，构建材料带原始消费者、提供者、
配方及SDK材料链接，运行包声明保留LLVM例外。

固定af63fe8的Node32/64检查各派发一次：41558262193、41558269642，均仍
运行。其结果独立于字节路径十阶段和9250e0c的默认工具链/Landlock检查，
不取消旧任务或混用这些不同语料的通过状态。

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

## RTLD_NEXT 与真实调用者所属对象

distro `8f1c28f` / 集成 `e709c2e` 为可选动态配置实现 `RTLD_NEXT`。
按已发布对象及全局符号链查找后继定义，使普通拦截函数可以调用下一层实现。
主程序的已有 libc `dlsym` 保留调用者所属对象，其他跨模块入口安装对应对象身份。
原模块先完成准入，再添加仅供运行层使用的函数别名，覆盖未导出的函数指针。
别名不参与公共查找或原始表容量规划。类型化 Wasm 包装保留 SIMD 参数及原规范
函数指针槽，正常返回和可捕获异常恢复外层所属对象，执行陷阱沿用进程终止边界。

实际三层 DSO 消费者检查构造器查询、间接 dlsym、私有函数指针、主程序私有回调、
缺失符号后的恢复及描述符清理。产品配方保留真实 NEEDED 和 RUNPATH，阶段总数
从十增至十一。musl、Linux、默认 SDK 与多线程支持边界均沿用原版本。

主会话已完成代码审查、Clang18/22 双位宽 C 前端与静态分析、两套 TypeScript、
506项运行层检查及浏览器阶段控制器检查。小型真实 Wasm 执行在双位宽通过，
包含原有构造顺序和嵌套装载的反向控制；Clang18 的 memory64 产物仍为 table32。
这些证据尚不能证明 booted Linux/Wasm 十一阶段或浏览器验收。

固定该版本的 [42558908006](https://github.com/HighCWu/distro/actions/runs/42558908006)
异步构建双位宽 SDK、实际驱动和 Linux 动态消费者。结果待核实。
下一增量补齐 imported function 的公共重导出及提供者规范地址，目前仍在实现。

## 函数重导出的工具链与运行时实现

distro `4a12230` / 集成 `469f12b` 补齐可选共享工具链的函数重导出路径。
普通 `-Wl,--export=reexport_target` 请求保留真实函数 import，并以相同函数索引
导出。LLD 使用独立标记区分显式重导出与 export-all、GOT 所需导出和输入标志；
未允许导入、无类型和弱未定义函数保持原有边界。LLVM Object reader 同时为
import-function export 填入签名，使下一层 DSO 可以读取提供者的正确类型。
两个补丁仅进入现有可选 sharedDriverToolchain，默认 LLVM pin 沿用原版本。

运行时在实例化前将函数别名归一到真实提供者，保留提供者导出名称、类型和规范
函数指针。包括多级不同名别名、同名转发和主程序优先绑定；直接调用、GOT.func、
单对象及依赖作用域查找共用该提供者。别名环和缺少提供者在修改 arena/table 前
失败，host-only 命名空间和纯 JS 函数重导出仍不在此配置支持范围。

实际产品新增 provider、forwarder、consumer 三份 C 源和第十二阶段。构建时读取
原始 Wasm，精确验证 forwarder 的 import-function export、签名和两条 NEEDED 边，
并要求普通 provider/consumer 未意外重导出该符号。这避免依赖作用域查找掩盖
LLD 遗漏导出。C 程序另外验证直接/GOT 调用、规范地址及描述符回收。

主会话已审查全部生产差异，并补齐 LLD 手动分配 symbol variant 时的新标记初始化。
两份补丁对固定 LLVM `90352668` 零修改应用检查通过，lit 的三份 MC 输入可编译。
Clang18/22 双位宽 C 前端及静态分析、两套 TypeScript、514项运行层检查和精确
浏览器阶段控制器检查通过。修补后的 LLVM 尚未编译，lit 尚未执行。

根探针新增显式 `--check-reexports`，要求本机链接器原生输出真实重导出。
旧本机 LLD 无此能力时该检查失败；`--test-only-patch-reexport` 仅供本地追加
export-section 别名验证解析与执行语义，输出明确标识。该模式双位宽通过，
不计为修补后工具链或 Linux 目标验收，产品构建不使用该变换。

随后主会话另用 Clang22 完成同一双位宽轻量执行，wasm64 实际使用 table64；
规范地址、函数重导出、主程序回调及原有负向控制均通过。此记录仍属于上述
显式 test-only 语义验证，修补后 LLD 的原生导出须由下述 CI 单独接受。

固定 `4a12230` 的 [42561363780](https://github.com/HighCWu/distro/actions/runs/42561363780)
异步构建双位宽 SDK、驱动及十二阶段消费者。尚待实际阶段、唯一 pass 和关闭
证据。此前 `58cb26b` 与 `8f1c28f` 的两个独立动态任务仍在运行，保留原任务。

## RTLD_LAZY 的直接函数延迟绑定

distro `5202cce` / 集成 `fc6482d` 接通未解析强直接函数导入的延迟绑定。
此前虽然接受 RTLD_LAZY 标志，缺少提供者时仍一律按立即解析失败。现在先建立
保留原类型的 Wasm forwarder，模块的独立函数可运行；后续 GLOBAL 提供者提交
后，运行层将目标更新为真实提供者的规范表槽，随后才执行构造器。

LOCAL 对象不发布延迟目标。GLOBAL 类型不兼容在实例化及 table 扩容前拒绝，
包括已驻留 LOCAL 对象的 NOLOAD|GLOBAL 提升。类型视图与指针分配分离，避免
先分配表槽才发现不兼容；合法 table import minimum 在验证后按已声明上限扩容。
失败回收临时逻辑分配与文件引用，不要求不可缩小的 Wasm memory buffer 回缩。

本增量支持直接函数调用，缺少强 GOT.func/GOT.mem 提供者和函数重导出目标仍
按既有规则拒绝。未解析函数若实际执行，沿用空表槽 trap 的终止边界；弱未定义
绑定规则保持原版本。musl、内核、默认 SDK 和多线程 fork 支持边界均未调整。

四份实际 C DSO 提供 consumer、LOCAL 同名对象、错误类型及正确提供者。第十三
阶段检查 NOW 拒绝与未发布、LAZY 独立函数、LOCAL 隔离、错误提供者不执行构造器，
以及正确提供者在构造器内经 main 回调已绑定 consumer 得到42，规范地址保持稳定。
文件、安装、材料及浏览器精确阶段列表同步接通。

主会话完成生产差异静态审查、Clang18/22 双位宽 C 前端与 analyzer、两套
TypeScript、517项运行层及34项浏览器阶段控制器检查。真实小型 Wasm 执行在
Clang18/22 双位宽通过，Clang22 wasm64 使用 table64。另核实已驻留错误类型对象
提升失败时 table 长度、活跃分配、pin 和构造次数保持不变，再装载正确提供者成功。
与前一增量的显式 test-only 重导出探针组合也通过；LAZY 自身不依赖导出段变换。

固定该源码的 [42564317353](https://github.com/HighCWu/distro/actions/runs/42564317353)
已排队，异步验收双位宽 SDK、驱动和十三阶段 Linux 消费者。尚待真实目标阶段、
唯一 pass 及关闭证据；先前动态任务继续独立跟进。

## 原版 GNU libltdl 与 Autoconf 动态配置

distro `ae75015` / 集成 `9aefc5d` 新增可选 GNU libltdl 2.5.4 静态库、原版头文件
和实际消费者。源码固定为 GNU 发布归档，原始 SHA256 如下。

`f81f5860666b0bc7d84baddefa60d1cb9fa6fceb2398cc3baca6afaa60266675`

标准 configure/make 使用动态 SDK 的同一 CC 及显式 wasm-ld、llvm-ar、llvm-ranlib
和 llvm-nm。配置后核验真实 dlopen 后端及目标搜索路径，构建后核验 archive 的
loader 符号和关键 C 源码哈希。材料保留原始归档、配置、构建参数与 SDK。
GNU 库保留 LGPL-2.0-or-later 及上游通知，自有 recipe 和消费者采用 MIT。

动态 SDK 新增安装的 config.site 及 configSite 属性。它保留 fork/vfork 和完整
固定文件映射探测的负面答案，省略默认 SDK 的三个 dlopen 禁用答案，让实际
compile/link 探测发现已启用接口。两个标准 libtool 搜索路径缓存明确为目标的
`/lib /usr/lib`，避免 GNU 配置读取构建宿主 ld.so.conf 后嵌入错误目录。
dlopen self 的运行探测保留普通 cross unknown，未预填函数探测成功。

普通消费者使用 lt_dlopenext 解析真实 .la 文件，查找插件 LTX 函数及可写数据，
验证重复打开的引用计数，再经 lt_dlopenadvise GLOBAL 装载独立提供者，满足插件
先前未解析的强直接调用。这条成功路径实际依赖前述 RTLD_LAZY 实现。四阶段
还核对单次错误读取、恢复和关闭；脚本清理临时文件后才输出唯一最终 pass。
runtime 包和镜像保留通知文件，插件与提供者分别链接，未设为彼此 NEEDED。

主会话静态审查并修正了 backend archive 路径、checks 聚合位置、安装目录、
未使用参数及验收收尾。GCC/Clang 的宿主参考使用系统 GNU libltdl 2.4.7 和
2.5.4 头文件，四阶段及清理后 pass 通过。Clang18/22 双位宽 C 前端和 analyzer、
ShellCheck/shfmt、Nixfmt 解析、配置文件空环境检查及仓库检查通过。
本地没有执行 Nix 求值、GNU 库完整构建或 Linux/Wasm 目标运行。

SDK 使用文档独立提交于 `01ea741`，主仓库 `150072a` 单独同步 pin。该版本较
ae75015 仅改 SDK.md，重型检查固定最新 `01ea741`。
[42567886543](https://github.com/HighCWu/distro/actions/runs/42567886543) 首轮在
安装 Nix 的 action 中报 zstd unsupported format，未求值项目、Heavy 跳过。
同一任务仅重跑失败部分，第二次 Plan 已成功，Heavy 正在构建双位宽 SDK 驱动
及 GNU 消费者。实际四阶段、唯一 pass 与机器关闭尚待核实。

## 动态 SDK 省略启动文件的复验

固定 `58cb26b` 的 `42554769847` 已明确失败。实际日志定位于 SDK 检查脚本的
`-nostartfiles` 用例，普通 main 和共享库链接在此之前已完成。该用例仍链接静态
libc，却对整个链接添加 import-dynamic，使弱引用的 `_DYNAMIC` 和 init/fini
数组边界变成动态导入，wasm64 绝对地址重定位因此被拒。

`a3a20d9` / 集成 `be3e6de` 将两种省略行为分别验证。`-nostdlib` 使用未解析函数
动态导入，`-nostartfiles` 保留 libc、提供真实定义并使用严格解析。两者继续要求
执行启动适配导出缺席。Clang22 的小型 wasm32/64 对象独立复现了弱绝对地址在
严格链接成功、import-dynamic 下被拒的边界，未为此修改生产 libc 或链接器。

[42569931015](https://github.com/HighCWu/distro/actions/runs/42569931015) 两次尝试
都失败于 Nix 安装归档的 zstd unsupported format，Heavy 未执行。没有继续重复
重跑。此结果无法验收 SDK 修复，后续 SQLite 双位宽检查也依赖修复后的 SDK 检查。

## 原版 SQLite 的标准扩展加载

`cb42db0` / 集成 `c1c55c6` 新增可选 sqlite3-dynamic 和 sqlite3-extension-runtime
双位宽产品。CLI 复用现有固定 SQLite 3.51.0 源码，使用动态 SDK 的普通 CC，
通过上游 configure/make 构建批处理 shell。显式 `--enable-load-extension`
要求真实 dlopen 编译链接探测成功，配置后核对实际生成文件。WAL 和 mmap 的
现有关闭策略保留，未修改 SQLite、musl 或 Linux 源码。

扩展使用标准 sqlite3ext.h、sqlite3_extension_init 和 API 函数指针表。四阶段
核对 `.load` 后 SQL 返回42、反复回调及模块数据、数据库关闭重开后的持久化，
以及同一 CLI 进程加载缺失模块报错后继续加载有效模块。脚本清理临时数据库后
才输出唯一 pass。固定3.51 shell 的错误累积路径要求恢复批处理最终状态1。
宿主参考使用系统3.45.1，其同类批处理可返回0，单独标记为参考模式。

主会话完成静态审查，修正许可证路径、实际生成文件及位宽依赖。固定3.51的
原生 configure 生成结果与 recipe 断言一致。GCC/Clang22 的原生四阶段、
Clang18/22 的双位宽前端和 analyzer、Nixfmt、ShellCheck/shfmt、Ruff 及
工作流语法检查通过。新代码采用 MIT，SQLite 原版 blessing、musl 及 compiler-rt
通知随产品保留。根仓库轻量 CI 使用同一消费者做原生参考。

[42570603052](https://github.com/HighCWu/distro/actions/runs/42570603052) 固定
`cb42db0`，请求 sqlite3-extension-runtime-check-both。Linux/Wasm 的四阶段、
唯一 pass 和机器关闭尚待实际日志验收，原生结果不扩大为目标环境通过。

## CPython 的标准 C 扩展导入

`7ae8bc1` / 集成 `1bc606b` 新增独立 python-dynamic、对应动态 stdenv 和双位宽
扩展消费者。默认 stdenv 的 config.site 仍作为形参默认值，原有 SDK 策略检查
同步适配。动态配置采用现有 SDK 的编译器、启动 sysroot 和 config.site，
由真实 dlopen 探测启用 CPython 原有 dynload_shlib 路径。

CPython 3.13.14 在 Wasm 下仍将标准库模块静态构建，Linux 的普通 C 扩展入口
则由 PyInit_*、dlopen 和 dlsym 提供。该配置保留 --disable-shared，不额外修改
CPython 源码或使用 Emscripten 专用开关。其静态主程序原本直接链接完整对象集，
动态 stdenv 增加 export-all 和 growable-table 以提供 API 与后续函数槽。
上游选择路径见 [CPython 配置](https://raw.githubusercontent.com/python/cpython/v3.13.14/configure.ac)。

新消费者通过 Python.h、PyModuleDef 和模块局部状态实现普通扩展。四阶段核对
指定目录的真实 .so 导入、返回42、Python 回调及异常传播、初始化失败后的新路径
重新加载，以及标准库 JSON 和文件往返。重载使用普通 import、独立文件副本和
新模块状态，随后恢复 sys.path 和 sys.modules；旧模块状态也必须保留。
解释器成功退出并清理临时目录后，由 shell 输出第四阶段与唯一最终 pass。

目标镜像显式提供地址位数，消费者校验实际解释器的指针宽度。产品保留原有
Python 及依赖通知，扩展包的通知放在独立目录，避免 initramfs 路径冲突。
新增 recipe 与消费者采用 MIT，musl 公共接口和 fork 范围不作扩展。

主会话完成静态审查。GCC/Clang22 与本机 CPython 3.11.15 的原生四阶段通过，
Clang22 对两个 C 文件的原生静态分析、Nixfmt、ShellCheck/shfmt、Ruff、
工作流语法及原有 SDK 策略检查通过。本地没有构建 CPython 3.13.14，也没有用
宿主头文件结果代替其实际 Wasm 头文件和 ABI 检查。

[42572763311](https://github.com/HighCWu/distro/actions/runs/42572763311) 固定
`7ae8bc1`，请求 python-extension-runtime-check-both，同时复用双位宽 SDK 驱动
及现有十三阶段动态加载检查。实际 CPython 构建、Linux/Wasm 四阶段与机器关闭
尚待目标日志验收，浏览器扩展消费者尚未验收。

同期已核实旧 `8f1c28f` 的
[42558908006](https://github.com/HighCWu/distro/actions/runs/42558908006) 失败于同一
旧版 SDK 省略启动文件检查，其 wasm64 重定位错误与前述已修用例相同。
该结果不构成 RTLD_NEXT 的目标验收。`c1c55c6` 的根仓库轻量 CI
[42570599904](https://github.com/HighCWu/linux-wasm-builder/actions/runs/42570599904)
已成功，范围包括实际 Clang 小型 Wasm 语料和原生 SQLite 参考，不扩大为上述
完整 Linux/Wasm 产品验收。

## 同名函数导入的逐项类型预检

`e6ed049` / 集成 `a9fdd14` 修复主会话静态审查发现的运行时错误。合法 Wasm
模块可用相同 module/name 导入不同函数类型。原实现只查找该名称的第一个签名，
可能遗漏后续导入的不兼容，直到实例化时才抛错，此时已进入资源初始化阶段。

两处签名查询现在同时匹配 typeIndex。对需要 typed forwarder 的未解析函数，
同一 DSO 内的签名冲突在 table 准备和数据清零前报告；不同 DSO 的独立弱导入
保持可共存。JS host 的 Number/BigInt 适配也保留，不统一禁止同名多类型导入。

主会话复验完整518项运行层检查、两套 TypeScript 项目和固定格式检查通过。
回归直接使用有效 Wasm 模块，核对失败前后内存、table 及函数指针映射，并实际
调用 JS 多类型导入。使用 `7ae8bc1` 旧生产代码执行同一新增回归时，复现不可恢复
的 DylinkInitializationError；修复后在资源修改前报告预期签名错误。

新 pin 的根仓库 CI 将执行该回归。此前 CPython 任务固定 `7ae8bc1`，不含本修复；
其构建与运行结果仍按该固定版本记录。本增量的轻量引擎证据不扩大为全部
Linux/Wasm 或浏览器消费者验收。

## C++ 动态模块的共享异常运行时

`2ed9aae` / 集成 `ecba22e` 增加可选 wasm-linux-dlopen-c++。普通 C++17 主程序
与共享库使用同一套 libc++、libc++abi 和 libunwind。主程序提供规范异常 tag，
加载器按原始模块的 tag 签名绑定同一实例，并在修改资源前检查不兼容导入。
函数与数据的 dlsym 命名空间保持各自规则。

PIC typed catch 通过 libunwind accessor 获取主线程 landing-pad context，避免
共享库引用未定义的外部 TLS。补丁同时应用于可选编译器和运行库，普通非 PIC
路径保留原有 TLS lowering。主程序强制导出 C++ 运行库，共享库导入这些定义；
独立 C++ 配置以 link-only 形式选择 unwinder，编译对象时可使用 -Werror。

消费者源码使用标准 dlopen/dlsym、std::string、typed catch 和 RAII，检查跨库
抛出、回调重抛、两侧析构及异常后的正常调用。四阶段的最后一项只在程序成功
退出后输出。resident dlclose 策略保留，尚未提供通用 imported TLS、跨 Worker
发布或动态 SDK 与 fork 的组合。

主会话复验521项运行层检查、源码与测试 TypeScript 项目、GCC/Clang22 原生
四阶段、静态分析、固定源码补丁 dry-run 及 LLVM IR verifier。未修改 LLVM 的
非 PIC FileCheck 通过；新增 PIC lowering 仍需构建后的目标编译器验收。
自有消费者及新增 IR 用例采用 MIT，修改的 LLVM/libunwind 文件保留原许可证。

## 默认运行库与启动对象的归属修复

固定 `7ae8bc1` 的 CPython 检查实际失败于 SDK 的 -nostartfiles 链接。
__wasm_dynamic_symbol、__wasm_dynamic_invalid 和 __wasm_dynamic_open 缺失，
原因是这些默认运行库适配曾放在 CRT archive 中。此前 `a3a20d9` 只修复检查里
不适用的 import-dynamic 弱重定位，未解决这项生产实现错误。
[实际失败任务](https://github.com/HighCWu/distro/actions/runs/42572763311)。

`6d84e2d` / 集成 `5e7b7c8` 将 execution object 放入默认 libc export archive。
CRT archive 只保留原启动对象，-nostartfiles 现在保留运行库辅助定义并省略
_start，-nostdlib 与 -nodefaultlibs 继续控制默认库。SDK 检查同步要求这一行为。
后续 `0f1daca` 仅调整 SDK 说明与注释。

固定旧 SDK 的 C++ 任务42580397472已请求停止，因为它依赖同一个已确认失败
用例；请求停止时尚无新 C++ 目标验收结果。修复后的聚合检查固定 `0f1daca`，
包含双位宽 SDK 驱动、C++ 四阶段、动态加载十三阶段、GNU libltdl、SQLite 和
CPython 扩展消费者，复用同一次编译器构建。各消费者的实际阶段、唯一 pass 与
关闭仍待日志核实，宿主参考和工作流状态不作为替代。
[修复后聚合检查](https://github.com/HighCWu/distro/actions/runs/42582967182)。

后续读取 SQLite 固定 `cb42db0` 的42570603052实际日志，确认同样失败于 wasm64
SDK -nostartfiles 的上述三个缺失定义，尚未运行 SQLite 消费者。根仓库 `ecba22e`
的42579888864日志则已核实521项运行层检查和原生 Clang18 C++ 四阶段通过，
这些证据限定于相应轻量检查。

## 动态 SDK 的标准部分链接

`ce94a9c` / 集成 `e980281` 为可选动态 SDK 接通普通 -r。Clang 识别部分链接后
省略默认 CRT、libc/C++ 运行库、进程 table base、profile runtime 和 wasm-opt。
动态 sysroot 的共享内存、growable table 与栈指针导出默认值移到最终链接阶段，
用户显式传入的链接参数继续传递。正常共享库仍采用可重定位 table 布局。

SDK 检查覆盖普通和嵌套 response file 的 -r，再从结果构建共享库，核对未定义
主程序函数与 C++ 异常 tag 保留。十三阶段 Linux 加载器消费者的 libplugin-a 也
改为从实际 partial object 构建，原有构造函数、数据与调用断言保留。聚合目标
加入底层 Clang driver 检查，核实同一编译器的真实 PIC 部分链接和引擎调用。

主会话完成代码审查，并独立使用 Clang18/22 验证双位宽的两对象合并、共享链接、
未定义 provider 导入和实际调用返回42。补丁在固定 LLVM90352668上 dry-run
通过，Nixfmt、Ruff、固定 JS 格式、语法与工作流检查通过。本地没有构建后的
定制 SDK，相关两项 Node 检查跳过，未计为通过。纯对象链接仍可能报告已有
-mllvm -wasm-enable-sjlj 的 unused 警告，本增量未全局屏蔽参数诊断。

固定 `ce94a9c` 的双位宽聚合检查包含 C++、加载器及 GNU libltdl、SQLite、
CPython 扩展路径。其真实阶段和关闭仍待验收，普通默认 SDK 的配置本轮未变。
[本增量聚合检查](https://github.com/HighCWu/distro/actions/runs/42584789604)。

## 原版 Lua 的标准 C 模块与跨库 SjLj

`9313076` / 集成 `dc21c12` 新增可选 lua-dynamic 和 lua-extension-runtime
双位宽产品。Lua5.4.8复用现有 lua.src 的固定源码，直接使用上游 make linux
目标，由其选择 LUA_USE_LINUX、POSIX、dlopen 和通常的导出参数。解释器和
luac 使用同一动态 SDK，开发输出包含原版头文件与 liblua.a。

标准模块入口为 luaopen_nativeprobe，通过普通 require 和 package.loadlib
加载。模块使用主解释器导出的 Lua C API。回调错误从主程序的 Lua error 路径
穿过模块调用帧回到 protected frame；另有模块内 setjmp，经共享 libc 的
__wasm_longjmp 返回模块 catchpad，复用已有规范 __c_longjmp tag 接线。
消费者源码使用普通 Lua 和 C 接口。

四阶段核对 require 的表身份与累计状态、模块错误和 Lua 回调错误、标准
longjmp 的7及0转1语义，以及错误后的正常调用。缺失文件加载失败后再加载
有效副本，要求新副本具有独立原生状态、原模块状态保留。解释器成功退出并
清理临时目录后，shell 才输出第四阶段和唯一 pass。按可选动态 SDK 的单线程、
驻留加载范围验收。

主会话复核本地解包目录的 NAR SHA256，精确匹配产品固定输入。原版 make linux
构建的 GCC 与 Clang18 原生四阶段通过。使用当前 musl 生成头文件的 Clang22
双位宽 PIC 前端编译，以及新增 C 模块的静态分析通过；实际对象含预期 SjLj
helper 和 tag 引用。Nixfmt、Ruff、ShellCheck/shfmt、工作流与仓库检查通过。
新增 recipe、模块及运行脚本采用 MIT，产品保留 Lua、musl、SDK 和 compiler-rt
通知。此增量恢复的是普通软件的构建与运行路径，没有新增 libc 公共接口。

固定 `9313076` 的聚合检查请求双位宽 SDK 驱动、既有十三阶段 Linux 加载器和
Lua 四阶段及各自关闭。真实 Linux/Wasm 和浏览器结果仍待验收，原生和前端
结果限定于上述范围。
[Lua 双位宽聚合检查](https://github.com/HighCWu/distro/actions/runs/42587510265)。

## 动态 SDK 材料中的只读配置复制

固定 `0f1daca` 的42582967182实际日志已读取。首个 builder 错误发生在
dynamic-sdk-materials-wasm32，第二次复制 compiler-cxx.cfg 时报告 Permission
denied。Nix 源配置为只读文件，第一次复制保留了其权限。后续 SQLite、Python、
加载器和 C++ 产品显示的是依赖失败，目标消费者的阶段继续等待对应版本验收。
[实际失败任务](https://github.com/HighCWu/distro/actions/runs/42582967182)。

`ce94a9c` 已在部分链接增量中删除这条重复复制。主会话逐项比较 `0f1daca`、
`ce94a9c` 和当前 `1165894`，确认后两者各保留一次复制。现有42584789604与
42587510265均包含该修复，按既有任务继续核实阶段和关闭。

## 普通 SDK 的标准部分链接

LLVM `ea19eeb`、distro `3b8def1` / 集成 `0e01e92` 将 Linux 的普通 `-r` 支持
移入基础驱动。部分链接跳过 CRT、默认运行库、SDK 执行对象、内存与 table
配置和 wasm-opt。普通 C/C++ 构建可先合并目标文件，再用同一 SDK 最终链接。
显式用户输入仍交给 Clang 和 LLD 处理，嵌套 response file 由 Clang 解析。

最终链接按显式 sysroot 下的内部 response file 读取 executable、shared 和
C++ 参数。普通 SDK 提供 executable/C++ 配置，可选动态 SDK 另外提供 shared
配置。省略默认库的最终链接继续使用已有执行环境参数，默认库与 CRT 则按各自
选项控制。fork/poll 配置的执行对象仅用于最终链接，poll 编译插桩保留。
该配置属于 SDK 内部集成，没有新增应用接口或 musl 公共函数。

主会话审查并修正 poll 插桩遗漏、共享补丁条件和验收代码的内存类型读取。
轻量包装、参数解析、材料归档、格式、补丁 dry-run 与工作流检查通过。
公开预取42599762208已核实 LLVM 固定源码哈希；本地没有构建修补后的 LLVM。
聚合目标要求双位宽普通 C/C++ 真实部分链接、消费合并产物的最终链接、动态
Clang PIC 链路，以及已有普通 SDK C++ 运行阶段和机器关闭。真实目标结果待
对应日志验收，本地缺少 built SDK 的检查明确跳过。

## Wasm CRT 的无效通用启动引用

固定 `ce94a9c` 的42584789604已明确失败。首个 builder 错误为 C++ 动态主程序
链接 crt1.o 时找不到 main，尚未执行新消费者。Wasm 的架构 _start 已通过
__main_void 启动，但通用 _start_c 仍编译进同一对象；whole-archive/export-all
保留了该函数对 main 的无效引用。两参 C++ main 实际使用 __main_argc_argv。
[实际失败任务](https://github.com/HighCWu/distro/actions/runs/42584789604)。

distro `caf6762` / 集成 `012dcaf` 仅在 __wasm__ 下排除通用启动体，沿用已有
架构启动链。该补丁接入所有 musl 构建配置，没有添加公共函数或头文件 API。
主会话直接编译固定源码的真实 CRT 与两个已有 main 适配器，原对象在双位宽
均复现相同 undefined main；修补对象通过无参/两参 C、两参 C++ 的链接及 Wasm
启动检查，参数和退出值符合预期。此微型执行使用初始化与 syscall stub，
证据限定于启动 ABI。固定工具链下的真实 C++ 动态程序、既有扩展消费者与机器
关闭仍需新的聚合任务验收。

Lua 的旧版本9313076任务42587510265随后明确失败，首错同为wasm64的crt1.o
引用未定义main，未进入Lua扩展运行阶段。按已包含CRT修复的caf6762一次派发
42606405684复验双位宽SDK、加载器和Lua四阶段及关闭，继续等待实际结果。
[Lua 修复版复验](https://github.com/HighCWu/distro/actions/runs/42606405684)。

## 已有 dladdr 接口的动态模块支持

distro `e36e7d8` / 集成 `bbeed98` 将 tombl/musl 已有的 `dladdr` 从静态桩接入
可选动态 SDK。程序可通过原有接口查询插件文件名、加载基址及精确公开符号，
用于定位插件资源等普通软件路径。六个既有默认 Luna 子代理分工实现，主会话
决定地址契约、审查差异并执行独立验证。musl 仅调整已有函数的 Wasm 调用路径。

函数归属来自实际 table 项和定义对象，独立于 RTLD_NEXT 的调用者作用域。
主程序公开符号只从原模块导出读取，避免把后来 GLOBAL 提升的库符号归入主程序。
DSO 数据按其实际静态分配范围归属，主程序使用 LLD 的 `__global_base` 至
`__data_end` 范围，可选 SDK 为最终可执行文件显式导出这两个内部边界。
`dli_fbase` 对主程序为零，对 DSO 为其 Wasm 线性数据加载基址。

当前 Wasm 元数据没有可用的 C 符号大小。数据内部地址可返回对象，符号名和
符号地址保持空值；精确公开数据地址及可核实的函数 table 地址提供符号信息。
隐藏函数指针可返回定义对象。函数 table 索引与线性地址数值重合且对象冲突时
返回未找到，同对象跨域重合仅返回对象信息。lookup 不创建新函数槽，失败保留
输出结构，成功与失败均不消费原有 dlerror，名字缓存随本进程的常驻模块保留。

主会话执行 GCC、Clang22 原生四阶段消费者、双位宽 C 前端、Clang 静态分析、
两套 TypeScript 检查和完整运行层538项检查。真实 Clang Wasm32/memory64 模块
探针核实函数与数据归属、主程序内部数据地址、内存增长后的输出及失败恢复。
补丁零 fuzz dry-run、格式与工作流检查通过。这些轻量证据不代表 Linux/Wasm
进程验收。[聚合 CI](https://github.com/HighCWu/distro/actions/runs/42611728431)
已一次派发，要求双位宽独立 SDK 驱动、新消费者四阶段、
原有加载器十三阶段及机器关闭，目标结果待实际日志核实。

42611728431现已明确失败。主会话读取实际 Heavy 日志，首错为普通 SDK 材料
导出的 files 白名单不一致，dladdr 程序尚未运行。该问题已由此前 `82aa6db`
修复，现以包含该修复的固定 `ec69ee4` 派发一次聚合复验，阶段及关闭结果待
实际日志核实。[复验 CI](https://github.com/HighCWu/distro/actions/runs/42630896189)。

后续 42682754978 固定 `6ab0360` 已运行到 wasm32 消费者，插件函数返回的对象
归属正确，但符号名为空。distro `ee1684a` / 集成 `07a58f2` 修复这一生产路径。
动态调用包装后的 callable 与原始导出函数可能是不同对象，dlsym 分配的 table
指针登记在已解析符号上，原始导出对象未必有相同的指针登记。现在按链接器提供的
canonical slot 选择名字，仍核对符号 owner 和当前 table 项，不按同一 owner
随意选择其他函数。

主会话独立运行实际 PIC 插件的 ProcessDylink 回归，旧源码稳定返回空名字和
地址，修复后插件函数、同 owner getter、隐藏函数归属、数据及 main 查询通过。
该回归使用 wasm32 模块及执行层 I/O 夹具，551 项运行层检查、两套类型检查通过。
完整双位宽 Linux 文件装载、消费者四阶段、原加载器阶段与机器关闭仍须目标验收。

## 静态 ELF 容器的实验性文件入口

Linux `e34fb21f6` 增加默认关闭的 `CONFIG_WASM_ELF_CONTAINER`，LLD
`b4a039ea` 增加 `--experimental-elf-container`。后续 Clang `722d8bc3`
调整优化器选项的认领顺序，使 Linux 部分链接识别 `--no-wasm-opt` 并跳过后处理。
容器使用 ELF32/64 小端头、`EM_NONE` 和本配置局部使用的 OS 扩展段类型，
由精确魔数与版本识别。这是尚未注册 psABI 的实验格式，完整 ELF 目标文件、
PT_INTERP、动态节及共享 ELF 对象仍需后续实现。字段见
[容器契约](elf-container-abi.md)。

LLD 在外层分配前缀，模块 section offset 和 build-ID 哈希保持相对 Wasm
载荷。Linux 在创建编译流前检查头部、位宽与完整长度，按模块相对偏移送入
原有编译路径，完整引擎准入成功后才提交 exec。原始 Wasm 沿用同一后续路径。
文件字段或模块验证失败时，调用者仍可继续执行原程序。

独立 sdk-elf-container 及 wasm64 配置使用标准编译入口。可执行链接响应文件
选择容器，Clang 配置通过普通配置参数 `--no-wasm-opt` 关闭只接受原始 Wasm 的
链接后优化。配置参数由 Clang 标记为已使用，支持 `-c -Werror` 编译和 `-r`
链接。部分链接产生原始 Wasm 对象。元数据分别记录编译器、
链接器和仅链接驱动参数。默认 SDK 继续输出原始 Wasm。

五个复用的 Luna 子代理实施生产者、内核、消费者、SDK 和格式工具，主会话
确定契约并审查所有差异。主会话修正同名 wrapper 的 PATH 歧义、仅链接选项、
候选 SDK 的执行内核绑定，以及消费者 BSS/TLS 检查的易被优化问题。自有新增
组件采用 MIT，既有内核和 LLVM 文件保留各自许可证，musl 无新增接口。

实际 LLD helper、实际内核 parser 和 inspector 的原生桥接通过双位宽检查。
GCC/Clang22 消费者三阶段、双位宽 Wasm C 前端、Clang 静态分析、既有 exec
提交检查、SDK 配置和材料检查通过。消费者要求 posix_spawn 的参数、环境、
PID/PPID 和继承 fd offset，fexecve 后同 PID、BSS/TLS 重置和 CLOEXEC 关闭，
三种坏镜像 ENOEXEC 后继续 ELF 与原始 Wasm exec、回收全部子进程。
完整候选 SDK 驱动及 Linux/Wasm 三阶段与关闭门禁仍需真实目标 CI 验收。

集成固定 distro `ec69ee4`、主仓库 `506fb93`。Linux 源码哈希由公开任务
42627745467核实，最终 LLVM `722d8bc3` 的哈希由42629726223核实；Nix 源码
输入与主仓库 gitlink 一致。固定版本的聚合任务已派发一次，要求双位宽完整
SDK C/C++ 驱动、三阶段消费者、唯一 pass 及发布 runner 的关闭门禁，实际结果
待日志核实。[目标 CI](https://github.com/HighCWu/distro/actions/runs/42630206187)。

42630206187已明确失败于 treefmt，尚未构建候选。`"$${flag}"` 产生转义文本，
检查器发现 lambda 参数未被使用；`8bb4720` 改为 `"$" + flag` 显式构造仅链接
参数。固定 `6dbc8d5` 包含该修复，已一次派发
[复验 CI](https://github.com/HighCWu/distro/actions/runs/42634205111)。

后续默认工具链更新为 GNU 归档组兼容的 LLVM `dc787527`，固定 distro86bbf93
的候选 SDK 检查同步覆盖 LLVM ar 与带组最终链接。新组合由
[42636418886](https://github.com/HighCWu/distro/actions/runs/42636418886)验收，
不沿用旧编译器组合的结果证明新组合通过。

## GNU Make 的标准 load 插件

仓库原有 GNU Make4.4.1 使用 posix_spawn，已覆盖普通 recipe 和 -j2。本增量
接通其原来在静态 SDK 配置中关闭的 load 指令。新增 make-dynamic 及 wasm64
产品复用原 make 的固定 src/version，使用动态 SDK、--enable-load 和现有
posix_spawn 路径。configure 真实探测 dlopen/dlsym/dlerror，要求对应声明宏、
MAKE_LOAD 与 USE_POSIX_SPAWN，保留原有同步 spawn 的已知实现事实。

GNU Make 的进程、加载与函数注册源码未加应用补丁，配方对 job.c、load.c、
loadapi.c、function.c 直接比较原始输入并记录构建前后校验和。产物以
/bin/make-dynamic 独立入口启动，附 GNU gnumake.h 和标准示例插件。
插件通过 gmk_eval、gmk_add_function、gmk_expand、gmk_alloc/gmk_free 与主程序
交互，沿用 GNU 的参数语法和内存所有权规则。主会话核对上游 load.c 的初始化
签名与重复加载行为，审查跨模块回调、分配边界、配方和双位宽接线。

四个复用 Luna 子代理实施插件、消费脚本、产品配方和集成。主会话核实已有
普通 Make 后撤去未发布的重复 fork 草稿，将实现集中到实际缺失的插件能力。
宿主 GNU Make4.3 配 GCC/Clang 插件的四阶段、静态分析、GNU4.4.1头文件下的
Wasm32/64 插件 C 前端、Nix/shell 格式及工作流检查通过。前端检查使用发布版
Clang 的通用 Wasm target 验证字宽与语法，完整定制 SDK 和 GNU4.4.1 构建由 CI
承担。

运行语料核对初始化和主变量展开、插件到主程序再回到插件的嵌套调用、重复
load 的一次初始化、正常 recipe 与第二次 no-op。坏插件须实际进入 setup 后
返回失败，GNU Make 停止执行 recipe，随后由新的 Make 进程加载正常插件恢复。
临时目录清理后才发送唯一 pass。GNU 源许可证和 SDK 依赖许可证一并保留，
自有配方、插件和消费代码为 MIT。

固定 distro `3404432` / 集成 `59deda3` 已一次派发聚合，要求双位宽动态 SDK
driver、新 Make 消费者四阶段、原动态加载器十三阶段与关闭门禁。实际目标
结果待日志核实。[目标 CI](https://github.com/HighCWu/distro/actions/runs/42645087631)。

## GNU Awk 的标准 C 扩展

distro `90a8697` / 集成 `8fd7de7` 新增可选 gawk-dynamic 与 wasm64 产品，
接通原配方关闭的扩展加载。沿用固定 GNU Awk5.3.1 源码及已有的 posix_spawn、
pty callback-clone 两个进程兼容补丁，动态 SDK 编译主程序与共享扩展。
configure 实际探测 dlfcn/dlopen 并要求 DYNAMIC，持久化地址分配器显式关闭。
ext.c 与 gawkapi.h 对照原始源码，进程源码及构建配置、补丁、依赖源码和许可证
一并留作材料。自有配方、示例扩展和消费者采用 MIT。

标准 dl_load 入口接收 GNU API 表，注册字符串和数组函数，并在初始化时发布
普通 AWK 标量。字符串通过 API 分配器取得所有权，数组更新使用已有 API。
扩展安装于编译进主程序的搜索目录，目标恢复阶段直接使用 -l wasmext。
坏扩展缺少 dl_load，须在 BEGIN 前失败，随后新的 Gawk 进程加载正常扩展恢复。
源码中的初始化返回零仅产生警告，消费者遵循 GNU 的这一行为。

四个复用 Luna 子代理实施扩展、消费者、配方和双位宽集成，主会话完成方案、
源码与差异审查。审查修正材料 Makefile 同名冲突、安装搜索路径和 AWK 换行
语法。宿主 Gawk5.2.1/API3.2 的 GCC、Clang 扩展四阶段通过，GNU5.3.1/API4.0
头文件下的 Wasm32/64 前端与 Clang 静态分析通过。两者的 API 版本分别记录，
完整定制 SDK 和 GNU5.3.1 的目标运行尚待验收。

固定版本的 gawk-dynamic-check-both 已一次派发，要求双位宽四阶段、唯一 pass、
SDK driver、既有动态加载器阶段及关闭门禁。
[目标 CI](https://github.com/HighCWu/distro/actions/runs/42648082562)。

## ELF 候选的 Clang 驱动策略修复

固定86bbf93的42636418886已明确失败于 wasm64 SDK 的 C/C++ 驱动检查。
两个 -### 输出都仍选择了 wasm-opt，ELF 消费者尚未运行。主会话读取固定
Clang Driver.cpp，确认 `$` 配置参数只经链接输入路径处理，驱动策略
`--no-wasm-opt` 因而没有进入工具链参数。普通配置参数由 Clang 标记为已使用，
可以直接用于 compile-only 和最终链接。

两个复用 Luna 子代理实施 SDK 配置与聚焦回归，主会话审查源码并独立验证。
`1c7cd78` / 集成 `0e4b664` 将该策略放入普通配置区，保留已有元数据字段。
真实 Clang22 的负向控制确认旧 `$` 写法会选择探针，普通写法通过 -###、
`-c -Werror` 及实际 Wasm 链接，探针没有执行。C 与 C++ 驱动的完整配置检查、
嵌套响应文件和包装入口检查通过。既有 C 探针显式指定 -x c，使 SDK 的 C++
驱动验证按其原定 C 输入执行。

此修复复用已发布 LLVMfb960167。固定版本的
[42659111460](https://github.com/HighCWu/distro/actions/runs/42659111460)一次派发，
该任务实际停在 wasm64 SDK 检查，普通 C/C++ 样例未使用信号接口，却无条件
要求 `__wasm_signal_handler_v2`。该导出属于 musl 的私有 `__restore`，仅在
相关归档成员被抽取时出现，平台配置没有强制拉入它。ELF 消费者尚未执行。

distro `2e38449` / 集成 `14a081b` 修正此检查。通用 profile 只要求无条件
执行能力，C/C++ 样例实际调用标准 `sigaction` 后分别核验信号恢复导出。
主会话审查调用链与差异，JS 语法、格式及宿主解析检查通过，两个真实 SDK
检查因本地没有候选 SDK 而跳过。
[42681240190](https://github.com/HighCWu/distro/actions/runs/42681240190)
继续异步验收双位宽实际驱动、ELF 三阶段消费者及关闭，尚未取得目标通过证据。

## 动态地址查询的函数类型准入修复

[42638173513](https://github.com/HighCWu/distro/actions/runs/42638173513)
在 wasm64 动态加载回归启动 `/init` 时返回 ENOEXEC，阶段尚未执行。主会话核对
加载链后发现，普通导入白名单已包含 `linux_dlopen_v1.address`，函数类型提供表
却漏了这一项。动态 SDK 的执行对象始终导入此入口，以调用已有 `dladdr`。
双位宽有效 Wasm 模块均可重现类型准入拒绝。

distro `6ab0360` / 集成 `878b4c3` 补齐两机器字参数、i32 返回值的类型契约。
子代理实施，主会话审查并独立完成双位宽实际 Clang22 产物准入、错误类型拒绝、
545 项内核运行库检查及源码/测试 TypeScript 检查。未降低未知导入的准入要求。
[42682754978](https://github.com/HighCWu/distro/actions/runs/42682754978)
异步复验原双位宽动态加载与 dladdr 的实际阶段及关闭，尚待目标结果。

## GNU 软件自带兼容实现的链接修复候选

Make 的 42645087631 与 Gawk 的 42648082562 实际在最终链接失败。两者自带的
getopt、glob、正则等兼容实现与 SDK 强制导出的 libc 强定义冲突，程序尚未运行。
主会话选择只把动态 SDK 的 libc 导出副本作为后备定义，普通应用的强定义优先。

LLVM `e1c44e8f` 实现标准 `llvm-objcopy --weaken` 和按名转换的 Wasm 支持。
转换仅修改 linking 符号表中已定义 global 符号的 binding，保留其他 flags、
undefined/local、符号索引、重定位及 section 顺序。源码改动保留 LLVM 许可证，
独立回归使用 MIT。公开预取
[42684271651](https://github.com/HighCWu/linux-wasm-builder/actions/runs/42684271651)
已核实固定提交及下载哈希。

distro `e4929b4` / 集成 `4504a1a` 使用该工具链弱化 libc 导出副本，再加入强定义
的私有执行适配。原始 libc.a 与 libc++ 归档保持原有处理。新增实际 SDK 链接正控
允许程序自带 getopt/optind，负控要求两份用户强定义仍报 duplicate symbol。

主会话审查并独立执行修改后 ObjCopy 的对象、按名和真实归档处理路径。实际
双位宽 Wasm 小程序验证了应用函数、数据定义优先，以及原强定义冲突继续报错。
四个 ObjCopy 源文件轻量编译通过。本地完整 SDK 链接用例因缺少候选 SDK 跳过，
未运行完整 LLVM 构建或 lit。两项原软件由
[Make 42685098219](https://github.com/HighCWu/distro/actions/runs/42685098219) 和
[Gawk 42685109057](https://github.com/HighCWu/distro/actions/runs/42685109057)
异步验收双位宽实际构建、运行阶段、SDK 及动态加载回归和关闭，结果尚待核实。

Gawk 42685109057 已明确失败。实际 GNU 软件链接完成，基础动态加载器尚未发出
首阶段，就在 closedir → free → __libc_free → get_meta 中 trap。上一批对归档
整体弱化也改掉 mallocng 内部强定义，可能使 lite allocator 分配的指针进入
mallocng 释放。该版本不能据链接成功视为运行可用。

distro `8e755cc` / 集成 `701720e` 改为按公开可见性生成弱化名单。仅动态 musl
配置设置 -fvisibility=default，显式 hidden 声明保留。脚本合并同名 nonlocal
符号的可见性，任何 hidden 定义、弱别名或引用均使该名字留在原有内部绑定关系。
因此一个 TU 未包含内部头文件时，也可由其他成员的 hidden 声明保住其强定义。
局部符号和 section 不参与名单，私有执行对象在转换后以强定义加入。修改后重建
归档索引，构建期检查完整 allocator 与 fallback 的 T/W 关系。

主会话独立以 Clang22 编译精确 musl getopt/malloc 源码的双位宽 IR，核对公开
getopt 可见而 __libc_malloc_impl 保持 hidden。真实成员精简归档的名单保留
getopt/malloc/free，排除内部 allocator 和 __malloc_atfork。实际补丁单对象按名
转换得到 weak getopt。现成本地归档 harness 调用了系统 libLLVM 的内部路径，
没有进入新 WasmObjcopy 实现，不能据此证明按名单转换完整归档；完整候选 SDK
链接和运行由新固定版本 CI 验收。musl 源码 pin、公共函数和头文件均未增加。

固定 `8e755cc` 的
[dladdr 42721961733](https://github.com/HighCWu/distro/actions/runs/42721961733) 和
[Gawk 42721969856](https://github.com/HighCWu/distro/actions/runs/42721969856)
已各派发一次，分别覆盖双位宽消费者、SDK 驱动和原动态加载回归。实际阶段、
唯一 pass 与关闭待核实。旧 Make 42685098219 后续也已失败，实际日志同样在
closedir/free/get_meta 中 trap，属于 `8e755cc` 修复前的版本，不能计为可用。

后续 Gawk 42721969856 已明确失败，实际日志显示 dynamic-libc 构建期的
llvm-objcopy 按名弱化被拒绝，尚未再次执行加载器。主会话核对固定 LLVM 源码，
发现 getWasmConfig 仍拒绝 SymbolsToWeaken，尽管 WasmObjcopy 的实现已支持
它。先前直接调用格式实现的本地 harness 绕过了公共配置入口，不能证明完整
CLI 可用。该失败不能据此认定 allocator 修复后的运行结果，最小入口修复与
实际 CLI 复验继续单独推进。

LLVM `a98781cc` 已推送最小配置入口修复，保留其它格式和未实现选项的拒绝。
现有对象 CLI 测试保留，追加按名处理归档与 localize 拒绝的回归。主会话独立
编译 ConfigManager 源码，以同一 API 正反控制确认旧版拒绝、修后接受，Wasm
localize 与 XCOFF 仍拒绝，源码语法检查通过。这些结果覆盖配置入口，完整
CLI、候选 SDK 与运行尚未验收。公开源码哈希预取已派发，随后再更新构建 pin。

## 静态 ELF 容器的双位宽 Node 验收

固定 distro `7f5db96` 的
[42719246681](https://github.com/HighCWu/distro/actions/runs/42719246681)
实际 Heavy 日志已核实。wasm32 和 wasm64 各依次完成 posix_spawn 的参数、
环境、身份与继承 fd，fexecve 的 PID 保持、BSS/TLS 重置与 CLOEXEC，以及
ENOEXEC 回滚和 raw/ELF exec 恢复三个完整阶段，各有唯一 pass。两套 SDK
链接驱动检查也各三项通过，包括 C++ 异常 tag 在最终模块中的内部解析。

该固定源码的 runner 等待 machine.closed，关闭异常会令构建失败；两次真实
消费者运行后的聚合成功，关闭门禁成立。接受范围为默认关闭的静态 ELF
容器实验，使用 EM_NONE 承载 Wasm 模块。C++ 项只有构建契约证据，尚未因此
验收 C++ fork 运行。该结果也不覆盖浏览器、原生机器码 ELF 或 ELF 共享库。

## 匿名文件描述符的动态加载候选

distro `81d6c8b`，主仓库 pin `f5d5f57`，修复已打开匿名文件通过
`/proc/self/fd/N` 加载时的两个问题。文件已经通过类型、大小和执行权限检查，
但其匿名目标会令 `realpath()` 返回 ENOENT。此时加载器保留合法的描述符路径
作为 origin，继续按打开文件的 device/inode 标识对象。`/dev/fd/N` 使用相同规则。
描述符路径每次都重新打开并核对 inode，避免 close 后复用同一 fd 号时返回旧模块。

主会话分别运行 GCC、Clang 的实际匿名文件 I/O 检查，并在隔离的 HEAD 执行适配
源码加本增量上运行 ProcessDylink 回归，覆盖同 inode 重开及同路径的新 inode。
运行消费者新增两份匿名模块加载、构造器次数、关闭源 fd 后继续调用、fd 号复用
及描述符清理。模块关闭继续遵循现有 musl resident-close 语义。

[42760428290](https://github.com/HighCWu/distro/actions/runs/42760428290) 和
[42760435146](https://github.com/HighCWu/distro/actions/runs/42760435146)
已派发双位宽 Node 验收，实际新增阶段与机器关闭结果待核实。上述本地检查
覆盖 I/O 与加载器逻辑，目标 SDK 构建和 Linux/Wasm 执行仍需独立证据。

## 跨模块尾调用与 Linux64 ABI 候选

distro `753c754` 接通默认关闭的 `linux.dylink.tail.v1` 模块标记。加载器为带标记
的模块维护同索引的尾调用表，保留普通调用表的调用方状态恢复。新增消费者执行
两份共享库间的实际间接尾调用。主会话核对类型检查及针对性回归，双位宽目标任务
[42762420846](https://github.com/HighCWu/distro/actions/runs/42762420846) 和
[42762427610](https://github.com/HighCWu/distro/actions/runs/42762427610)
仍待实际运行阶段及关闭结果验收。

公开 LLVM 候选 `c07823c5` 已通过重建后的默认 ABI、Linux64 ABI 各自普通链接和
LTO 的 memory64 执行检查，以及符号版本和 PIC 表预留检查。distro `b61d734`
将实际编译器 pin 与该候选对齐。其两个 SDK C++ 任务在运行前被导出脚本格式检查
阻挡，`6fca50c` 已按固定 shfmt 格式修复，并重新派发对应检查。

distro `bb2975d` 增加独立的 `linux64-abi-wasm64` scope，使 musl、编译器运行库、
sysroot、zlib、SQLite 及所需库统一使用 `-mabi=linux64`。`df94fe8` 增加匹配的
`linux64-abi-dynamic-wasm64` 配方，覆盖普通变参的 main/DSO/libc 调用及变参回调。
这两个 scope 均已完成完整 derivation 求值。构建材料检查及 GCC、Clang 原生消费者
通过，目标 SDK 的构建、执行与关闭继续异步验收。混用两种 ABI 的对象尚无自动
检测机制，交换变参的调用方及库需要采用相同配置重新构建。

## 可选的公开运行资产导出

distro `6fca50c` 为既有 SDK closure 导出增加默认关闭的 runtime 选项。固定的
`runtime-assets-wasm64` 包含内核 npm 输出、Node runner、Node、cpio 及 Linux
源码和许可证材料。manifest 记录两个输出 root，导出脚本核对它们均进入 closure。
主会话已完成 derivation 求值、脚本及工作流静态检查，实际资产构建和归档待 CI
完成。该输出用于本地复现公开 Linux/Wasm64 执行环境。

## 匿名文件创建与实验 ABI 构建修复

实际日志确认 `81d6c8b` 双位宽动态加载任务及 `753c754` 的 wasm32 任务在
`memfd_create` 返回 ENOSYS 时停止。NOMMU 配置未通过 TMPFS 选中 MEMFD_CREATE。
distro `f6515da` 显式启用官方 memfd 实现，始终执行 olddefconfig，并校验最终
`CONFIG_MEMFD_CREATE=y` 与 MMU 关闭。该增量的内核包求值通过，实际 NOMMU
匿名文件行为及加载阶段等待目标复验，完整 sealing 语义仍需另行验证。

`df94fe8` 的 Linux64 ABI 任务 `42769619602` 则在构建 musl 时停止，错误为
unknown target ABI linux64。实际命令中，架构配方后追加的 `--target=wasm64`
覆盖了所需的 Linux triple。distro `c722239` 仅在实验 ABI 配置中将最终 target
恢复为 `wasm64-unknown-linux-musl`。固定 musl 源码上的 make dry-run 已确认参数
顺序，SDK derivation 求值通过，默认配置参数保持原样。

固定 `c722239` 已派发动态加载双位宽复验、Linux64 ABI 运行复验和包含运行资产的
实验 SDK 导出。实际构建、完整运行阶段和关闭结果仍待核实。

这两项实验 ABI 任务的实际日志随后确认，最终 Linux triple 已生效，构建在
`libc.so` 链接时被 `--table-base may not be used with -shared/-pie` 阻挡。
LLVM `2b52cbc3` 将 Linux 信号值所需的固定 table base 限于非 PIE 可执行文件，
共享库与 PIE 交由加载器分配表项，并增加对应 driver 回归。主仓库的候选检查
另行覆盖 wasm32、wasm64 及 Linux64 ABI 的真实共享库链接和 Node 模块校验。

公开预取任务已核实该源码的 unpacked hash，distro `2189490` 更新实际工具链
来源，实验 SDK derivation 求值通过。候选 LLVM 构建
[42787321396](https://github.com/HighCWu/linux-wasm-builder/actions/runs/42787321396)
以及固定该版本的实验 ABI 运行与 SDK 导出任务
[42788117236](https://github.com/HighCWu/distro/actions/runs/42788117236)、
[42788126903](https://github.com/HighCWu/distro/actions/runs/42788126903)
仍在执行，尚未确认目标运行阶段或关闭结果。

## Linux64 工具链与闭包导出的后续结果

固定 LLVM `2b52cbc3` 的候选 job `129731710274` 已核实实际日志。
三种 Linux driver 配置的共享库链接及 Node 模块校验通过，默认 ABI 与
Linux64 ABI 各自的普通链接、LTO 变参消费者均在 Node memory64 执行通过。
该证据覆盖编译器和链接器检查。它没有覆盖完整 Linux 运行或浏览器。

固定 distro `2189490` 的 SDK 导出任务 `42788126903` 已产出包含匹配运行
资产的闭包归档。独立运行任务 `42788117236` 仍待完整阶段与关闭结果核实。

同一主仓库任务的 metadata job 则在 Clang 18 的 imported mutable global
检查失败。该旧链接器损坏的名称偶尔仍是合法 UTF-8，原跳过条件遗漏了这一
表现。distro `63b23b8` 将已知旧版本的限制显式标为跳过，主仓库 `1db630b`
更新 pin。主会话使用 Clang 22 重跑双位宽检查，四项全部通过且无跳过。
这一修复没有将 Clang 18 的该项检查标记为已验收。

固定 `2189490` 的实验 ABI 运行任务随后失败。实际日志显示普通格式化结果
`17/1234567890123/4.5/<pointer>` 正确，PID 1 以状态 0 退出后触发内核 panic。
该消费者直接作为 init，遗漏了 raw-initramfs runner 要求的结果标记和保持存活。
distro `0e9271f` 保留原有 ABI 检查，在成功后输出阶段摘要和唯一 pass、刷新
输出，并等待机器关闭。失败会报告具体检查及错误码。
主仓库 `7b69b5c` 更新 pin，复验
[42807564440](https://github.com/HighCWu/distro/actions/runs/42807564440)
已通过。实际目标日志包含格式化、变参、syscall、prctl 和 Landlock 阶段摘要及唯一
pass。该固定版本的 runner 在成功退出前等待机器关闭，任务成功结束。

动态变参消费者存在同样的 init 生命周期遗漏。distro `a59b135` 为其增加结果
报告与等待关闭，并保留 DSO 变参、回调、格式化及 dlclose 检查。主会话使用
GCC、Clang 核实原生成功与缺库失败路径，并完成 Clang 静态分析。
主仓库 `db246b3` 更新 pin，首次动态目标验收
[42808913688](https://github.com/HighCWu/distro/actions/runs/42808913688)
在链接阶段失败，缺少 `__wasm_dynamic_open`、`__wasm_dynamic_symbol` 和
`__wasm_dynamic_invalid`，尚未执行动态 ABI 检查。

## Linux64 动态 SDK 的共享工具链接线修复

distro `237aad9` 将独立 Linux64 动态 SDK 接入已有 `sharedDriverToolchain`。
此前该配置传入 `sharedCompiler = null`，因此缺少共享链接、函数重导出及 PIC
异常上下文补丁。Linux64 的 musl、libc++、unwind 及依赖继续使用独立 ABI 配置。
同时刷新 shared-link 补丁的上下文，保留固定可执行文件、PIE 与共享库的函数表
布局规则。主会话核实补丁适用性，并用旧 SDK 的显式归档链接确认缺失符号的来源。
这些诊断链接没有替代新 SDK 的运行验收。

首次派发 `42839146544` 使用了不存在的检查名，在计划阶段停止，未启动重型构建。
已按既有目标名称修正派发。固定 distro `d4e6c58` 的
[42840412553](https://github.com/HighCWu/distro/actions/runs/42840412553)
正在重验动态模块、跨模块变参、回调、格式化、关闭及机器退出门禁。
`d4e6c58` 还修正了宿主 Python 工作流测试的过期断言，使其精确包含 SDK 导出模式
的隔离条件。生产工作流条件保持原配置，十四项轻量检查通过。

## Wasm cache-clear intrinsic 的编译兼容候选

公开 LLVM 候选 `0ca346ed` 修复 `llvm.clear_cache` 在 Wasm 后端触发 fatal error
的问题。Wasm 指令与线性内存分离，由引擎管理模块编译和指令缓存。lowering 保留
输入 chain，不生成目标缓存刷新指令。该行为不赋予线性内存执行能力。

主会话用旧 SDK 的独立 LLVM IR 复现编译失败，并审查候选实现和既有回归测试。
候选 CI 同时构建 llc、FileCheck、Clang 和 lld，检查 wasm32/wasm64 的前后 volatile
写入，并通过普通及 LTO 链接运行已有变参消费者。候选
[42838146097](https://github.com/HighCWu/linux-wasm-builder/actions/runs/42838146097)
仍在运行。普通 SDK 的 LLVM 源码 pin 继续为 `2b52cbc3`，候选尚未成为默认工具链。
