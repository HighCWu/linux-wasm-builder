<!-- SPDX-License-Identifier: MIT -->

# Direct linear-memory 契约

状态：**项目架构约束；direct anonymous映射及安全地址hint复用已通过标准syscall集成验证**。

Linux/Wasm 用户指针始终表示当前进程 `WebAssembly.Memory` 中可直接访问的字节偏移。
内核、loader和默认工具链不提供隐藏的softmmu地址翻译，也不返回只能通过私有翻译器
访问的伪虚拟地址。

## 1. 基本原则

1. Linux保持`CONFIG_MMU=n`；不得仅为开放接口而声称存在硬件MMU语义。
2. stack、globals、TLS、heap和映射统一使用原生Wasm load/store。
3. `mmap()`成功返回的整个区间必须能够由普通Wasm指令直接解引用。
4. 无法直接表示的固定、高位或稀疏映射必须在建立映射时明确失败，不能推迟到访问时
   trap。
5. 用户态JIT、模拟器或应用可以为其所模拟的地址空间实现自己的softmmu/TLB；该实现
   不属于linux-wasm内核ABI。

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

当前anonymous子集允许`munmap()`按页解除完整映射或其前缀、后缀和中间子区间。
中间解除会把存活范围拆成两个登记区间；共同backing只在最后一个存活区间解除后释放。
对未登记范围执行合法、页对齐的`munmap()`按Linux语义视为成功的no-op，但这不意味着
解除后的原生Wasm load/store会产生页错误。

`brk`和匿名映射必须由同一个direct地址分配器协调，禁止两个互不知情的
`memory.grow`路径返回重叠区间。

当前实现保留`CONFIG_MMU=n`并恢复asm-generic编号的raw `SYS_mmap`/`SYS_munmap`。
Linux的arch wrapper负责校验上述子集，再通过同步Wasm执行ABI调用当前进程的用户态
direct allocator；musl的公开`mmap()`/`munmap()`也走同一标准syscall路径。allocator
元数据留在进程linear memory中，因此与现有malloc/brk共享底层分配状态，并随现有
private-memory callback clone的eager-copy快照一起复制。该机制从明确的子函数和新栈
开始执行，不是标准`fork()`；复制linear memory不能复制Wasm引擎内部的调用栈。内核
不会返回伪地址，也不为这一接口建立softmmu、页表或TLB。

映射执行边界使用版本化的`user_v2.mmap(addr, len, prot, flags, fd, pgoff)` import，
宿主把Linux已校验的完整请求原样转发给当前进程模块的`__wasm_mmap_v2`导出。这一版本
仍落到既有direct allocator；非固定hint向下对齐到页边界后，只有完整请求区间位于该
allocator已经保留、但当前没有live mapping的backing页洞中才会采用，否则按Linux语义
回退到普通分配。这一保守子集不会把任意数字变成可访问地址，也不开放覆盖式fixed或
文件映射。
旧内核继续使用`user.mmap(len)`，新宿主在旧用户模块缺少v2导出时可回退到
`__wasm_mmap(len)`；宿主只允许private anonymous read/write、`fd=-1`、offset=0的请求
进入该回退，非固定hint可以忽略。旧callback无法表达精确地址，因此宿主对
`MAP_FIXED`和`MAP_FIXED_NOREPLACE`返回`ENOMEM`，且不调用分配器。这样旧用户模块不会
把fixed请求静默降级为其他地址的普通分配；使用精确页洞映射需要v2用户模块。无可用
callback时返回`ENOSYS`，上述错误均保持wasm32/wasm64各自的返回值类型。

`MAP_FIXED_NOREPLACE`现已在同一安全页洞子集内开放：地址必须页对齐且完整区间已经由
allocator保留；精确空洞映射成功，live mapping冲突返回`EEXIST`，未保留或不可表示区间
返回`ENOMEM`。普通`MAP_FIXED`仍返回`ENOMEM`，因为覆盖并拆分已有映射的生命周期语义
尚未实现。

为扩大安全可用范围，allocator以8个Linux/Wasm页（当前共512 KiB）作为小型direct
backing chunk。普通匿名映射优先从已有chunk的空闲区间做first-fit分配；新chunk预留失败
时退回按请求大小分配，避免仅因预留策略扩大低内存失败面。尚未映射过的chunk空闲页与
partial `munmap()`形成的页洞遵循相同hint和`MAP_FIXED_NOREPLACE`规则。chunk中最后一个
live mapping解除后释放整个malloc backing，不形成永久地址保留。

普通分配的backing查找采用按次去重：同一backing在一次查找中最多执行一次空闲区间
扫描，并保留其在live mapping链表中首次出现的候选顺序。标记在现有allocator锁内
重置与使用，不增加独立分配、free-list或额外回收路径。构建时可关闭优化，使用原始
搜索路径运行同一正确性检查和性能基准；该开关不属于用户程序ABI。

## 4. 文件映射准入条件

当前实现不接受文件映射。后续实现必须从可验证的`MAP_PRIVATE`子集开始，并满足以下
约束：

- 异步读取完成且目标direct区间重新校验成功后，才能一次性发布映射；读取、分配或
  校验失败必须向发起线程返回标准错误，不能留下半完成区间或无限等待；
- 初始内容来自请求的文件offset，文件末页未覆盖的尾部按Linux规则清零；无法提供
  截断后访问、文件末尾外访问等必要错误语义时，应限制可接受的映射范围；
- `MAP_PRIVATE`写入不得回写文件；进程复制时是否复制或共享内部backing不能改变这一
  可观察语义；
- 在无关进程间可见的共享backing、写入传播和持久化路径全部存在以前，不开放
  `MAP_SHARED`；
- `msync()`只有在请求范围的同步及异步持久化语义真实实现后才能成功。未实现时必须
  返回明确错误，不能以no-op报告成功；
- `munmap()`、进程退出、文件截断和I/O失败的引用释放与回滚必须有独立测试。释放映射
  不得被错误表述为已经完成文件持久化。

首个文件映射子集可以使用eager read形成direct私有backing；按需缺页、页缓存alias或
透明dirty tracking不是开放`MAP_PRIVATE`的前提，但这些较弱实现边界必须进入能力文档
和回归测试。

接入前需单独验证两项当前anonymous测试无法证明的边界：

- offset单位：wasm32 musl通过`SYS_mmap2`传入以4096字节为单位的offset，wasm64
  `SYS_mmap`传入字节offset。当前arch wrapper直接拒绝非零末参数，v2只验证过offset=0；
  参数名`pgoff`不能作为已完成单位转换的证据。文件路径必须明确归一化的位置、文件
  offset的宽度和溢出处理，区分4096字节syscall单位与当前64 KiB映射页。测试应包含
  同一非零文件offset的libc/raw路径、非页对齐拒绝与可表示范围边界。
- 读取中backing保活：不能直接把已登记的anonymous地址交给异步读取，再假定其它
  线程不会解除该区间。需要可测试的reserve/pin、commit/abort生命周期，读取期间
  不得释放或复用backing；完成时重新校验预留状态，失败时释放预留与文件引用。
  并发解除、进程退出、信号中断和I/O失败均须有有界终止检查，不能仅以“尚未向
  mmap调用者返回地址”代替内存保活证明。

以上是未来文件映射的准入要求，不是已经实现的新能力；不改变当前v2 anonymous
ABI或开放文件请求。实际实现仍需按标准Linux UAPI和版本化执行ABI独立审阅。
分阶段实现、64位文件offset及staging持有方案见[文件映射实施计划](file-mmap-plan.md)。

## 5. 不能伪造的语义

Wasm linear memory当前不能为单个页提供Linux式fault和访问权限。实现不得把以下操作
静默报告为严格成功：

- `munmap()`后保证所有陈旧指针立即fault；
- 通过`mprotect()`移除读、写或执行权限；
- 同一backing在多个虚拟地址建立alias；
- 稀疏高地址映射到低地址backing；
- 内核透明处理用户load/store page fault。

能安全提供较弱但标准允许的行为时必须配套测试和文档；否则返回标准错误。

## 6. 用户态自有地址翻译

FEX、Box64及类似JIT控制被模拟程序的每次访存，可以自行把被模拟程序的virtual
address翻译为direct Wasm backing。应用也可以选择相同方式。linux-wasm只为这些程序
提供普通进程、线程、文件、信号、futex和direct内存资源，不规定其页表或TLB格式，也
不进行第二次翻译。

## 7. 未来Wasm能力

Memory Control、Multiple Memories和Custom Page Sizes都不应被提前等同于完整MMU。
只有标准化并由目标浏览器稳定实现的机制真正提供所需页映射、保护、重映射或fault
能力后，项目才评估新的可选profile。实验性提案不能成为默认ABI前提。

## 8. Raw syscall测试的参数类型

当前musl公开的变参`syscall()`实现按六个`long`读取参数。raw mmap测试必须把地址、
长度、protection、flags、fd和offset显式转换为机器字；raw munmap测试也补齐六个
`long`参数，未使用项为`0L`。这些辅助函数仍调用标准`SYS_mmap`/`SYS_munmap`，不是
改走libc映射封装或宿主allocator捷径。

wasm64中`int`为32位、`long`为64位，Wasm变参不使用某些本机架构的寄存器槽布局。
混用类型会使被调用者读到错误参数；不能把这种测试调用错误记作内核mmap拒绝合法
请求，或通过忽略flags/fd校验使测试通过。这也不意味着所有用户软件的raw syscall
调用已经完成wasm64审计；其余调用与更易用的类型安全封装应另行评估。
