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
修正仍在独立分支验证中；文件请求当前全部失败，不把它当作成功offset转换的证明。

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
