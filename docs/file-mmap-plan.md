<!-- SPDX-License-Identifier: MIT -->

# 受限文件映射实施计划

状态：设计与拒绝回归阶段，尚未开放文件映射。当前主线仅支持已公布的direct anonymous
子集。本计划不修改Linux UAPI，不引入softmmu，也不声称存在页保护或缺页机制。

## 首批范围

优先研究普通、可定位读取、内容和长度不可变的文件，以eager read形成私有direct副本。
只读挂载本身不是不可变证明：还需保证底层镜像在映射生命周期中不能被宿主修改。
可从项目持有的不可变文件系统镜像开始验证；设备、pipe、socket、可变文件及shared
映射均不在首批范围。具体准入检查必须由实现证明，不能只看fd是否以O_RDONLY打开。

先沿用当前read/write的direct权限子集，不把不可强制执行的PROT_READ、PROT_NONE或
执行权限静默报告为严格成功。MAP_FIXED覆盖、alias、透明fork、共享回写和msync
持久化不随这一功能开放。私有写入不回写文件。

必须限制映射不跨越文件最后一个有效页；最后有效页内的文件尾部清零。空文件及
完全位于EOF之外的请求明确拒绝，不能用全零副本伪造应当触发SIGBUS的访问。
不可变准入用于避免映射成功后截断所需的SIGBUS语义；不能把可变文件的snapshot
行为冒充完整Linux文件mmap。文件大小、offset、请求长度及页取整都需要溢出检查。

## Offset契约

libc的off_t在两个profile均为64位，输入单位是字节。raw syscall则不同：

| 路径 | raw参数单位 | 转换要求 |
|---|---|---|
| wasm32 SYS_mmap2（222） | 4096字节 | 先拓宽到u64，再乘4096 |
| wasm64 SYS_mmap（222） | 字节 | 保留64位，不能经JS Number转换 |

4096字节syscall单位不等于当前65536字节映射页。归一化后仍须按映射页校验offset，
并检查offset加length、页取整和内核文件位置类型的可表示范围。
wasm32的最大raw参数可表示2^44-4096字节offset，不应被地址宽度错误压缩到4 GiB。

现有user_v2.mmap的末参数是pointer-width整数，且只验证过0。不改变其含义或宽度；
文件路径需要新的版本化执行接口，文件offset独立采用i64，而非WasmAddress。
JS边界使用BigInt；内核负返回值和用户地址仍按各自profile处理。
缺少新接口时，文件请求明确失败，不退化为anonymous allocation。

本轮mmap-offsets.c只验证当前拒绝行为：真实普通文件fd、libc字节offset、raw单位、
非零anonymous offset、负值、大于4 GiB及raw宽度边界。检查错误码、文件位置和存活
anonymous映射内容。因为所有文件请求仍失败，它不能证明转换正确，也没有测试真实
大文件读取。开放文件路径时必须增加非零offset的成功内容对照，不能只保留拒绝测试。

preflight首次运行在进入mmap校验前发现wasm64对真实文件执行
lseek(fd, 7, SEEK_SET)返回EINVAL。最初归因为变参传递，但源码进一步证明musl内部的
syscall宏已经转换参数类型；改写该调用没有修复问题，现已恢复原generic实现。
根因是共享的Wasm syscall头文件在64位仍定义32位_llseek布局，同时也定义了mmap2。
修正按long宽度选择别名，并让头文件生成保留条件编译指令，而不是丢弃条件后生成
无条件SYS别名。32位保留_llseek/mmap2，64位改用lseek及字节offset的mmap。

回归增加了编译期别名断言和libc/raw交叉检查大于4 GiB的SEEK_SET和SEEK_CUR。
这只验证文件位置传递，不需要创建大文件，也不证明大文件I/O或Memory64容量。
修正与前置测试已通过验证并合入主线；文件请求当前全部失败，不把它当作成功offset转换的证明。

验证记录（以下测试源码已原样合入主线，固定commit不变）：

- 最初的[wasm64失败](https://github.com/HighCWu/distro/actions/runs/37419656809)
  在小offset seek返回EINVAL；仅改写调用后的
  [wasm64失败](https://github.com/HighCWu/distro/actions/runs/37420047994)
  仍无法通过libc/raw大offset位置对照，故不接受最初的变参归因。
- 修正源码：musl `cc93a0d6e41e75d7d058eea8466c1a4f0ce3e6e9`、
  distro `9865c5e82a497ce67ee9ab601b2b8f2e5d469bcd`。
- 当前[wasm32定向检查](https://github.com/HighCWu/distro/actions/runs/37422145740)、
  [wasm64定向检查](https://github.com/HighCWu/distro/actions/runs/37422149817)、
  [完整CI](https://github.com/HighCWu/distro/actions/runs/37422258526)及
  [Memory64回归](https://github.com/HighCWu/distro/actions/runs/37422265224)均成功。
- 本地仅生成syscall头文件并按long为4/8预处理检查，不构建内核或LLVM。
  生成后的NR与SYS别名均按宽度选择；generic lseek实现与原主线一致。

## Offset契约模型的当前进度

独立分支`codex/mmap-file-offset-contract`新增了MIT的内部契约模型
`packages/kernel/src/file-mmap-offset.ts`和八组单元测试，源码commit为distro
`48e3bc6a549d9288bc40a656afc4d6f2d0abcd10`。

- raw mmap2先按unsigned i32解释传输位，再拓宽并乘4096；同时接受Wasm signed i32
  和显式unsigned表示，拒绝越宽、非整数及错误JS类型，不静默截断输入。
- raw mmap输入必须是BigInt，采用字节单位；负offset返回EINVAL，超出signed 64位
  文件位置范围返回EOVERFLOW。大于2^53的值不能借道Number。
- canonical extent校验页对齐、正length、页取整与exclusive end；保守要求取整后的
  整个extent都能由signed 64位文件位置表示。失败结果不包含有效extent。
- 4096字节syscall单位不替代65536字节页对齐；同一非零offset在32/64位得到相同
  byte_offset，最大raw mmap2值仍须独立通过页对齐检查。

模型不读取文件、不分配backing、不发布映射，不接入现有syscall，不新增Wasm import，
也不通过包主入口发布稳定SDK。现有v2/legacy兼容测试原样保留。它是未来实现的对照
契约，而不是“已经完成内核offset转换”的证据；实际VFS路径还需用成功内容测试与该
契约交叉验证。正式新执行接口只传canonical i64字节offset，不能在宿主再次乘4096。

本地TypeScript检查与八组新测试、八组既有mmap桥接测试均通过；
[独立分支CI](https://github.com/HighCWu/distro/actions/runs/37436143890)首轮有四个job失败，
日志均为同一源码下载HTTP 429及依赖构建失败，未进入对应运行检查；仅失败job已重跑。
内核staging及新的执行接口仍未实现，不把契约校验成功当作文件准入成功。

## Staging所有权原型

独立分支`codex/mmap-file-staging`增加MIT的`FileMmapStaging<T>`内部原型和八组测试。
它持有调用者提供的缓冲及回收函数；不实现内核缓冲分配、VFS读取、线程唤醒或跨Worker锁。
每个请求有自己的记录，不能靠可能复用的tid找到旧请求。尚未接入任何文件mmap路径。

- reading不能取得提交租约。complete_read表示生产者已经停止写入，不能仅因调用者
  不再等待就调用它。读取成功进入ready，读取失败进入aborted并保留错误。
- 取消reading立即关闭提交资格，但保留缓冲，直到生产者确认停止写入才回收。
  生产者若无法终止或确认，必须由集成层提供有界取消、隔离及资源预算；原型不伪造确认。
- ready只能取得一次拷贝租约。拷贝的目标必须是未发布candidate；拷贝中取消不会
  提前回收源缓冲。租约结束后才回收，且此时finish(true)仍返回false，candidate必须丢弃。
- finish只接受一次终态。成功授权所有权移交，失败不可重试成成功；重复完成、取消和
  回收通知不能重复释放缓冲。回收回调要求同步且不抛异常。
- finish成功不等于已发布映射。集成层仍必须在同一同步allocator临界区内完成最终
  校验、finish和发布，不能在成功授权与发布之间加入异步等待。租约必须在finally中结束。

本地TypeScript检查及24组相关测试通过（offset 8、staging 8、既有mmap桥接8）。
[轻量公开CI](https://github.com/HighCWu/distro/actions/runs/37446439154)在Node 24同样通过
全部24组，不下载Linux/LLVM源码；该工作流不替代完整构建、TypeScript或浏览器回归。
distro原型commit为`263500e8e15383671dd328ceb9af6a919b44168a`，尚未合入主线。

主线的[Memory64合入后复验](https://github.com/HighCWu/distro/actions/runs/37435459409)
已成功；[主线完整CI](https://github.com/HighCWu/distro/actions/runs/37435459432)的kcmp和
runner检查也因同一源码下载HTTP 429失败，失败job已重跑，不能记录为完整矩阵已通过。
上述失败均不通过吞掉错误或跳过检查处理。

## 读取与发布的生命周期

首选“任务独占staging，读取完成后选址并同步提交”，而不是把已经登记的anonymous
区间直接交给异步I/O。优先评估内核拥有的staging缓冲及标准文件引用，让文件访问
继续走Linux VFS；内核实现按Linux许可证，独立宿主桥接和测试保持MIT。

1. 请求验证后获取稳定file引用；以后用该引用读取，不能每次重新查fd数字。
2. 请求记录独占staging及完成状态。I/O期间staging不属于用户映射列表，munmap不能
   释放它；不跨I/O持有全进程syscall锁或allocator mutex。
3. 读取完成后验证存活请求、不可变文件条件和长度。短读不能一律当成功补零：只有
   已确认的末页尾部可以清零，其它异常短读和读取失败必须返回错误。
4. 通过新执行接口同步进入allocator，重新选择或校验direct区间，复制完成后一次性
   发布。普通hint允许换址；精确地址要求不得偷偷降级。提交不得覆盖已有live mapping。
5. 成功时移交最终backing所有权，再释放staging和file引用；失败时回滚所有临时状态。

这种方案无需在I/O期间为最终用户地址占坑，但仍需要对staging的独占持有和释放证明。
同步提交内部若存在重入、阻塞或跨Worker访问，必须重新审查原子发布假设。eager read
会增加临时内存峰值；首次实现要有有界请求大小和明确ENOMEM路径，不做性能承诺。

close(fd)不取消已经持有file引用的读取，fd复用不改变请求目标。不能依赖关闭广播代替
持有引用。信号是否中断读取由实际Linux读取路径决定，不从其它系统推断mmap永不EINTR；
若返回中断错误，取消和清理必须完整，不遗留永久等待。

退出或取消后，丢弃晚到完成通知不足以证明安全：生产者可能仍向staging写入。
需要确认生产者终止，或把staging保留到生产者完成后回收。完成与取消只有一个终态，
重复完成不得重复发布或重复释放；若跨宿主任务路由，要验证请求和进程实例身份，
不能只依赖可能复用的tid。失败必须唤醒发起线程或完成其退出清理。

private-memory callback clone也须纳入设计：读取中没有已发布用户映射；子进程不得
继承父请求的宿主资源所有权、在途写目标或悬挂完成记录。内核staging可降低复制用户
allocator临时状态的风险，但不能替代父子并发测试。完成后的映射沿用已有eager-copy
快照，不引入COW。

## 实施与验证顺序

1. 当前拒绝preflight：32/64位使用同一C源码，通过独立raw initramfs检查。
2. 新offset执行契约及单位/溢出测试，不改变v2兼容路径。
3. staging持有、单终态、回滚及可控延迟/错误注入；先独立测试再接入VFS读取。
4. 不可变文件子集：非零offset内容、末页清零、private不回写、fd关闭/复用、clone隔离。
5. 并发hint占用、munmap、信号、进程退出、晚到/重复完成、分配失败、异常短读。

所有竞态测试使用可控barrier，不靠大文件“读得够慢”制造窗口；每条失败路径有watchdog
和资源回收断言。先跑Node wasm32/64定向CI，再运行稳定浏览器及主线回归矩阵。
未完成上述准入前，能力文档继续标明文件映射不支持。
