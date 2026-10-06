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
日志均为同一源码下载HTTP 429及依赖构建失败，未进入对应运行检查；仅失败job重跑后
完整workflow已成功。原始失败仍保留，未通过跳过检查获得成功。
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
runner检查也因同一源码下载HTTP 429失败；仅失败job重跑后完整workflow已成功。
上述失败均不通过吞掉错误或跳过检查处理。

## 实际allocator的初始化后发布路径

独立分支`codex/mmap-initialized-backing`新增musl内部bring-up函数
`__wasm_mmap_initialized`，不是稳定用户API或Wasm执行export；标准mmap、munmap和
现有v2接口不变，也未增加host import或文件syscall准入。

初始化请求直接分配全新backing，不走已登记页洞的复用路径。先清零请求区间，然后
调用同步initializer；仅返回0才在原有allocator锁内登记mapping。initializer失败或
最终加锁失败都释放临时mapping和backing；合法负errno原样返回，非法回调结果返回EIO。
初始化过程中不持有mapping锁，不把一个已登记anonymous地址暴露给读取任务。
initializer不得启动异步I/O或在失败后使用候选指针；文件读取必须此前已完成。

这条实际分配器路径为后续copy/commit提供发布边界，但尚未连接kernel staging或VFS。
新函数只由专门C测试引用，发行版默认链接flags不把它导出为Wasm执行ABI。
取消、不可变文件准入、文件引用及host传输仍须独立接入，不能因initializer返回0就
宣称Linux文件映射成立。首次路径不提供fixed覆盖或精确hint。

同一C测试源码在两种指针宽度下运行，配置两个Linux/Wasm CPU。测试用原子barrier
暂停initializer，再并发munmap候选范围、尝试fixed-noreplace以及分配邻接映射，验证
候选尚未登记且不被其它分配覆盖；继续初始化后检查内容并部分解除。另循环注入失败、
非法回调返回和后续成功提交。这里的暂停是测试barrier，不代表支持锁内异步文件读取。
测试检查行为和回滚后的可用性，不声称测出了所有资源泄漏或clone竞态。

- musl：`e4c2cca8d0327da47c3ff50b3164fd37c2fcdf1b`
- distro：`e56f8a125cb9294b1d86ed2f6f4f6f4d45bb2a9c`
- [wasm32初始化检查](https://github.com/HighCWu/distro/actions/runs/37447772557)和
  [wasm64初始化检查](https://github.com/HighCWu/distro/actions/runs/37447779526)均已成功。
- 同版本的[wasm32既有mmap回归](https://github.com/HighCWu/distro/actions/runs/37447988161)和
  [wasm64既有mmap回归](https://github.com/HighCWu/distro/actions/runs/37447994400)均已成功。
- 本地C语法、TypeScript和仓库元数据检查通过；没有本地构建LLVM或Linux。

## 宿主侧同步staging复制桥接

distro独立分支commit `87dbcea33ebc1c9fa3493a73ba37ac71a0b39b25`新增MIT实现
`FileMmapCopy`，已接入实际worker的实例化和kernel import对象，但Linux尚未声明或调用
该接口，该版本的musl尚未提供对应export。不是已接通的VFS路径，也没有开放文件mmap。

实验执行契约使用独立版本名，不改变legacy或v2 mmap：

- 内核侧`user_mmap_init_v1.map(rounded, source, length)`提供内核staging地址和已读字节数。
  内核调用者须独占持有staging，确保生产者已停止写入，且在同步调用返回前不释放它。
- 宿主调用用户模块`__wasm_mmap_init_v1(rounded, length)`；缺少export返回ENOSYS。
  用户模块只接收长度，不接收内核地址；未来musl wrapper负责清零、分配和失败回滚。
- 用户侧`linux_mmap_init_v1.copy(destination, length)`仅在这次同步调用中有效，且只能
  调用一次、复制全部已读字节。越界、长度不匹配或重复调用明确失败，不允许换目标重试。
  实例化allowlist只允许此copy，不允许用户模块导入内核侧map接口。
- 源范围在分配器进入前检查，复制时重新刷新两块memory并重新取视图。嵌套map返回EBUSY，
  正常返回或trap都在finally中撤销授权。桥接不负责allocator发布或trap后的C资源回收。

这些参数均为当前平台的指针/长度宽度，不是文件offset；后续文件offset仍采用独立i64
契约，不能因该复制接口以指针宽度传长度而缩窄文件位置。这里没有异步等待、跨Worker
租约移交或文件不可变性检查。未来initializer必须同步完成copy并检查返回值，不得重入
syscall、切换用户实例或忽略复制失败后发布候选映射；staging取消与最终发布仍须接入。

新增13组检查覆盖真实Wasm export/import的i32/i64传参、两种memory宽度、memory.grow后
的复制、越界和错误类型、零长度、旧export缺失、重复/嵌套调用及trap后授权撤销。
真实Wasm小模块只验证传输ABI；其它检查使用可控回调，不证明musl初始化/发布已接通。
已有零尾检查只证明复制没有改写尾部，实际清零仍由先前allocator路径负责。

本地TypeScript及61组相关Node检查通过（包含现有memory/worker检查）。
[轻量公开CI](https://github.com/HighCWu/distro/actions/runs/37450194272)已通过37组契约检查。
新增宿主接口后的[wasm32既有mmap复验](https://github.com/HighCWu/distro/actions/runs/37450293296)
及[wasm64既有mmap复验](https://github.com/HighCWu/distro/actions/runs/37450299409)均已成功。

## 可选musl复制wrapper与拒绝路径实测

musl commit `7c45461e5f34ad629a3bed0314b66d6a42c19d86`新增独立MIT对象
`src/mman/wasm32/mmap_init.c`，实现实验函数`__wasm_mmap_init_v1(rounded, length)`。
它先验证正的整页长度及`length <= rounded`，再使用已有初始化分配器分配新backing、
清零并同步调用`linux_mmap_init_v1.copy`；只有copy返回0才允许分配器登记mapping。
正常负errno触发已有回滚路径；宿主trap不等同于普通errno，仍不保证C层资源已回收。

独立对象避免普通mmap链接时强制引入新copy import。发行版默认linker flags没有加入
该export，只有新`mmap-copy.c`检查显式链接导出它；因此目前不是默认SDK能力，也不改变
旧程序执行契约。Linux仍未调用新桥接，没有staging来源或成功VFS文件映射。

distro commit `f5cb317217c6a6d4e923245a7b4eafdbbad62de6`更新musl pin/hash并添加
两个位宽共用的真实启动检查：验证非法长度拒绝、直接用户调用没有内核授权时返回EPERM、
零长度copy也不能绕过授权；循环失败后再做普通anonymous分配，检查新区域清零、已有
映射内容不变及munmap可用。该检查经过实际musl wrapper和宿主copy import，不是模拟
回调，但只覆盖拒绝/回滚路径，不证明所有泄漏已排除或成功复制发布已接通。

本地C语法检查通过，源码hash由[公开prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/37451427689)
计算成功，没有本地构建LLVM或Linux。
[wasm32复制拒绝/回滚检查](https://github.com/HighCWu/distro/actions/runs/37451615569)和
[wasm64复制拒绝/回滚检查](https://github.com/HighCWu/distro/actions/runs/37451620863)均已成功。
后续需要内核拥有的受控staging检查，覆盖实际成功复制、尾部清零、copy失败及发布边界，
再加入文件不可变性准入、VFS读取与文件引用生命周期，不能跳过这些条件开放文件映射。

## 默认关闭的内核staging集成检查

Linux commit `c8d1ed15ffa5067217f95cbaf1612a070ade6bb7`声明新复制import并新增
`CONFIG_WASM_MMAP_COPY_TEST`，默认n，只在专门测试内核启用。该fixture使用架构私有
syscall槽253，没有写入UAPI头，不承诺编号稳定，也不得供应用使用；默认内核仍返回
ENOSYS。Linux内修改遵循Linux许可证，独立C测试和Nix集成保持MIT。

fixture最多分配两个64KiB页的内核staging，对调用者指定的有效长度写入确定性模式，
然后同步调用新复制桥接；无异步生产者、无用户提供的源地址、无VFS读取。只有同步调用
返回后才释放staging，成功返回的用户backing由musl继续持有；长度超过上限先返回EINVAL。
这是集成测试入口，不是新的文件映射实现。宿主trap仍可能阻止C清理，不把它归类为已
验证的普通errno回滚，也没有加入异步取消或跨Worker资源移交。

distro commit `0e09defc2bfa09ff8965694c6ba7b9d2f06be66d`新增两个位宽共用的检查：

- `mmap-staging.c`经过真实syscall、内核缓冲、宿主桥接、musl初始化和映射登记，测试
  零字节、单字节、跨页及整区间长度；逐字节检查内容与清零尾部，内核释放源后修改用户
  backing并部分munmap，返回用户态后再确认copy授权已撤销。
- `mmap-staging-legacy.c`故意不链接新export，确认内核正常持有/释放staging时宿主返回
  ENOSYS，而不是偷偷回退anonymous分配。它和成功路径合为一个heavy check，复用同一个
  专用测试内核，避免在不同公开job重复构建。
- 既有`mmap-copy.c`另加入默认内核不得启用测试槽的检查；新版该检查尚待独立复验。

专用内核通过Nix局部override启用测试选项，默认linux/kernel包与默认defconfig不启用；
默认SDK链接flags仍不导出新wrapper。模型和上述测试不能代替不可变文件准入、EOF边界、
实际读取失败及短读处理、信号与clone并发检查。文件mmap继续明确拒绝。

本地C语法、TypeScript及13组复制桥接检查通过；Linux源码hash由
[公开prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/37455898107)计算成功。
[wasm32内核staging集成](https://github.com/HighCWu/distro/actions/runs/37456155367)及
[wasm64内核staging集成](https://github.com/HighCWu/distro/actions/runs/37456161792)均已成功。
没有本地构建LLVM或Linux，尚未合入主线。下一步先确认这条实际复制/发布链路，再处理
可证明不可变的文件子集与有界VFS读取，保持现有文件mmap拒绝契约直到准入条件满足。

## NOMMU约束下的受控VFS读取检查

核对当前Linux上游实现后，不能直接把sealed memfd当作首批准入方案：
`init/Kconfig`中的完整`SHMEM`依赖`MMU`，`fs/Kconfig`中的`TMPFS`依赖`SHMEM`；
`include/linux/shmem_fs.h`在`CONFIG_SHMEM=n`时使`shmem_file()`返回false，
`mm/memfd.c`的seal查询仅支持shmem或hugetlb文件。现有NOMMU配置不能靠打开
`MEMFD_CREATE`获得完整shmem sealing，也不为此改成MMU=y或绕过Kconfig依赖。
hugetlb不是当前可用后备方案。这排除的是当前配置下的直接复用，不是断言NOMMU平台
永远无法另行实现文件不可变性。普通O_RDONLY、只读挂载和initramfs仍不自动满足准入。

Linux commit `b809e0cc542b4365b5e49fbdca3c8a71d8cb2bff`在默认关闭的测试配置内
新增VFS fixture，不接入标准mmap：

- 私有槽254创建匿名只读file，内容由内核生成并独占持有，没有写入或mmap操作；禁止
  重新open其inode，避免新file没有初始化private_data。私有槽255只接受这个fixture的
  file_operations，不根据O_RDONLY接纳普通文件。release释放文件数据。
- 读取请求限制为最多两个64KiB页；持有fget引用，使用局部loff_t位置循环kernel_read，
  不修改file->f_pos。只把已完成读取的staging交给同步复制桥接，返回后释放staging和
  file引用。尚不包括跨异步I/O取消或并发fd关闭barrier。
- 不允许映射完全超出EOF的页，最后有效页的尾部由musl清零。仅允许已知EOF导致的尾部
  清零，预期区间内的提前EOF返回EIO；负读取错误原样返回，不发布候选映射。
- 私有测试offset用两个u32表达64位字节位置，保持wasm32检查不截断；它不是稳定执行
  ABI，也不是mmap2单位。后续正式文件接口仍须采用既定独立i64契约。

新MIT C检查`mmap-vfs.c`覆盖普通只读文件拒绝、非法fd/长度/对齐、4GiB及高位offset
拒绝、非零offset读取、末页清零、文件位置不变、映射后的close/fd复用及独立用户backing。
fixture还可注入提前EOF、部分读取后EIO和EINTR，检查反复失败后仍能成功读取/分配。
这里的EINTR是读取函数的错误注入，不证明真实信号中断/重启已实现；close/fd复用发生
在读取结束后，不证明读取中的关闭竞态。没有测量全部资源泄漏或真实磁盘性能。

本地C语法、TypeScript及37项契约测试通过，Linux编译与实际VFS启动检查待公开CI确认。
源码hash由[公开prefetch](https://github.com/HighCWu/linux-wasm-builder/actions/runs/37464191408)
计算成功；distro集成commit为`9f18475a5e8d167d215fed3e6517c8b1ff782220`。
[wasm32受控VFS检查](https://github.com/HighCWu/distro/actions/runs/37464566888)和
[wasm64受控VFS检查](https://github.com/HighCWu/distro/actions/runs/37464575133)均已成功。
这条路径验证真实kernel_read、staging和分配器的组合，但文件内容来自测试专属file，
不能声称普通文件mmap已实现。下一步仍须选择并证明默认NOMMU内核可用的不可变文件
来源，并覆盖实际文件生命周期和并发错误，标准文件mmap在此之前继续拒绝。

## 有界私有镜像backing

distro commit `0870b716553bbfe2ce08894c5ed6e99e55bb4926`新增MIT内部函数
`snapshot_block_storage`，可作为现有`blockDevice`的storage。尚未从SDK根入口导出，
没有更改默认磁盘加载方式、Linux import或mmap准入，也没有给通用storage增加可随意
声明的immutable布尔值。

函数同步复制输入Uint8Array到私有缓冲，不保留输入view；Node Buffer也复制而不是
使用会共享底层数据的Buffer.slice。默认最多64MiB，可显式提供有限的安全整数上限，
镜像长度须按512字节sector对齐。拒绝SharedArrayBuffer源，不把并发修改期间得到的
混合镜像当作一致快照；源获取过程、内容完整性和文件系统格式仍由调用者负责。

返回对象冻结，容量固定，不提供write/flush，不暴露私有字节或view。read只复制到
调用者提供的目标，使用内建set避免把私有view交给可重写的target.set；修改目标不
影响后续读取。非法offset失败，越过capacity返回短读，close撤销读取并丢弃私有引用，
重复close无副作用。GC何时归还内存不做承诺，分配异常明确抛出，不回退到可变源。

这提供可信宿主内的backing不变性，不是防恶意JavaScript宿主的安全边界，也不等于
已验证文件内容真实性。会额外复制并持有整个镜像，峰值至少包括源与副本，不替换
大磁盘的现有按需读取路径，不声称所有镜像都适合整份复制。

新增7项测试包括输入subarray/Buffer修改、目标修改与set覆盖、容量/offset/共享源
拒绝、短读及close，并经过实际virtio packed队列检查读取、OUT拒绝及拒绝写后重读。
本地TypeScript及68项相关Node检查通过。
[轻量公开CI](https://github.com/HighCWu/distro/actions/runs/37473996168)已通过68项检查；
仅安装kernel所需npm依赖并构建bytes辅助包，不下载或构建Linux、LLVM或Nix大源码。

后续候选组合是“项目持有的私有镜像backing + EROFS只读文件系统”，但仍需建立可靠的
设备身份与内核文件来源关联，覆盖跨Worker路由、设备生命周期、默认加载路径和真实
文件读取。virtio RO位只表示不提供写操作，不能证明读取源不可变；EROFS类型或只读
mount也不能单独代替backing证明。在这条链路接通前，不接纳任何普通文件mmap。

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
