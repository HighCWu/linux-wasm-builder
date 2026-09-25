<!-- SPDX-License-Identifier: MIT -->

# Direct linear-memory 契约

状态：**项目架构约束；direct anonymous映射子集已进入实现和验证阶段**。

Linux/Wasm 用户指针始终表示当前进程 `WebAssembly.Memory` 中可直接访问的字节偏移。
内核、loader和默认工具链不提供隐藏的softmmu地址翻译，也不返回只能通过私有翻译器
访问的伪虚拟地址。

## 1. 基本原则

1. Linux保持`CONFIG_MMU=n`；不得仅为开放接口而声称存在硬件MMU语义。
2. stack、globals、TLS、heap和映射统一使用原生Wasm load/store。
3. `mmap()`成功返回的整个区间必须能够由普通Wasm指令直接解引用。
4. 无法直接表示的固定、高位或稀疏映射必须在建立映射时明确失败，不能推迟到访问时
   trap。
5. 用户态JIT、模拟器或应用可以在自身内部实现guest softmmu/TLB；该实现不属于
   linux-wasm内核ABI。

## 2. 地址空间上限

wasm32的理论地址宽度是4 GiB，当前wasm64 profile的链接上限是16 GiB；二者都不是
单次`mmap()`必然可用的容量。实际direct范围还受以下因素共同限制：

- 模块声明的memory maximum；
- exec时由`RLIMIT_AS`截取的进程memory maximum；
- globals、shadow stack、TLS、heap和已有映射；
- 运行时可提交的memory容量及资源限制。

发行说明必须公布各profile的构建上限。程序应通过标准资源限制接口和`mmap()`结果
判断运行时能力，不应硬编码“wasm32必有4 GiB”或“wasm64必有16 GiB”。

## 3. 第一阶段映射语义

优先恢复`MAP_PRIVATE | MAP_ANONYMOUS`：

- `mmap(NULL, length, ...)`从direct地址空间分配；
- 非固定地址hint能满足时可以采用，不能满足时允许选择其他地址；
- `MAP_FIXED`只有在完整请求区间可直接表示、满足对齐和保留区约束时才能成功；
- 超出direct范围的`MAP_FIXED`返回`ENOMEM`，非法对齐或flag组合返回`EINVAL`；
- `MAP_FIXED_NOREPLACE`与已有区域冲突时返回`EEXIST`；
- 不支持的文件映射、alias、权限或共享语义必须返回明确错误。

`brk`和匿名映射必须由同一个direct地址分配器协调，禁止两个互不知情的
`memory.grow`路径返回重叠区间。

## 4. 不能伪造的语义

Wasm linear memory当前不能为单个页提供Linux式fault和访问权限。实现不得把以下操作
静默报告为严格成功：

- `munmap()`后保证所有陈旧指针立即fault；
- 通过`mprotect()`移除读、写或执行权限；
- 同一backing在多个虚拟地址建立alias；
- 稀疏高地址映射到低地址backing；
- 内核透明处理用户load/store page fault。

能安全提供较弱但标准允许的行为时必须配套测试和文档；否则返回标准错误。

## 5. 用户态guest MMU

FEX、Box64及类似JIT控制guest每次访存，可以自行把guest virtual address翻译为direct
Wasm backing。应用也可以选择相同方式。linux-wasm只为这些程序提供普通进程、线程、
文件、信号、futex和direct内存资源，不规定其页表或TLB格式，也不进行第二次翻译。

## 6. 未来Wasm能力

Memory Control、Multiple Memories和Custom Page Sizes都不应被提前等同于完整MMU。
只有标准化并由目标浏览器稳定实现的机制真正提供所需页映射、保护、重映射或fault
能力后，项目才评估新的可选profile。实验性提案不能成为默认ABI前提。
