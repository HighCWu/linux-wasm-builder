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

## 本地快照设备身份与启动设备树

distro commit `b4c0b6b20c04be5aff9f1a9dc3bbef59b11efa47`新增MIT内部工厂
`snapshot_block_device`，用上述私有storage创建实际virtio block设备，并在模块私有
WeakSet中登记原设备对象。没有公开注册函数或可填入的immutable选项；普通blockDevice
即使接收snapshot storage也不自动登记，同配置设备、对象浅拷贝及Worker代理均不继承
身份。不同模块实例或JS realm之间没有隐式传播，不确定时保持未认证。

实际bootMachine在生成对应`virtio,wasm`节点时，仅为已登记对象添加u32属性
`lowland,snapshot-image-v1 = 1`。属性编码不随memory32/64的root cell宽度变化；host-id
仍由最终设备数组生成，不靠文件路径、设备名称或容量猜测身份。关闭回调撤销登记并
释放storage引用，后续生成的属性为空；已经生成的设备树不会因close动态更新，所以
这个标记只描述启动时来源，不能当作实时存活状态或绕过设备清理错误的许可证。

这是可信宿主内的来源关联，不抵御恶意宿主篡改设备树。在这个阶段属性尚不由Linux文件准入读取，
没有新增内核import或UAPI，也没有开放mmap；默认磁盘加载仍不调用实验工厂，函数尚未
从SDK根入口导出。远程ready协议不携带来源声明，不用一个未经验证的消息布尔值把
Worker设备变成认证快照。

新增检查验证原对象与同配置设备区分、属性返回对象修改不影响登记、关闭撤销、真实
MessagePort代理不继承身份，以及两种root cell宽度下的实际FDT编码。实际virtio队列
测试改用新设备工厂，继续检查源修改、读取、OUT拒绝和关闭后的登记撤销。
本地TypeScript及71项相关Node检查通过；
[公开轻量CI](https://github.com/HighCWu/distro/actions/runs/37475990604)同样通过71项检查，
没有重建Linux或LLVM。

后续内核关联已有代码证据可复用：virtio_blk通过device_add_disk把disk的parent设为
对应virtio_device，virtio_wasm再关联其platform设备及OF节点；但必须验证transport身份，
不能把其它virtio transport的parent强行转换为wasm设备。文件侧还要验证其文件系统及
所有实际backing来源。EROFS的dev_context支持extra_devices，主superblock设备带标记
不代表额外数据设备也不可变；首批应拒绝多设备、file-backed及无法证明来源的组合。
overlay等间接来源也不自动继承标记。完成内核检查、真实单设备EROFS读取、设备生命周期
及32/64位启动验证之前，不能宣称已建立完整“普通文件到不可变backing”的准入链路。

## 单设备EROFS的内核来源查询（实验）

Linux commit `95426f820b1db264b4c1821f385e0342630b031a`接入两项独立检查：

- `erofs_is_single_bdev`确认superblock确实属于EROFS、有主块设备，并拒绝额外设备、
  file-backed、fscache及非零backing偏移。不能仅凭文件系统名称或只读mount认证来源。
- `wasm_bdev_has_snapshot_source`拒绝分区，沿disk parent找到实际virtio设备；确认
  transport config ops确实属于virtio_wasm、设备类型为block、已协商RO特征，并要求
  对应OF节点的`lowland,snapshot-image-v1`为u32版本1。其它transport不作强制类型转换。

必要内核实现及helper按Linux许可证；独立宿主实现、用户测试及文档保持MIT。
两项检查只能证明受信任宿主建立的启动来源关联，不证明设备当前健康或抵御恶意宿主。
调用者仍须持有文件及挂载backing引用，读取错误不得转为成功；这不是sealed memfd，
也没有开启CONFIG_MMU或把普通Wasm指针变为Linux页表管理的虚拟地址。

测试开关`CONFIG_WASM_MMAP_COPY_TEST`下新增私有syscall 256，仅查询fd来源，持有
fget引用后组合上述检查并fput。返回1/0或EBADF，不进行mmap，不发布到UAPI头文件，
默认生产内核关闭此测试开关。普通文件mmap准入及既有v2执行ABI均未改变。

distro commit `f970d81f0208c471724377bab64788793af1d890`加入实际启动检查：构建
一个小型EROFS镜像，以相同内容挂载两个只读virtio块设备；一个使用内部快照工厂，
另一个使用普通只读宿主文件。前者查询应为1，后者及initramfs文件为0；同时验证
两份真实文件读取内容、EBADF、close和卸载。测试runner显式选择实验工厂，默认
加载路径不变，不把普通只读磁盘自动认证为快照。

distro commit `503f1d3ab3a17eaaf6cebe90743bd411ae3b36b7`补上配置合并边界：插件
设备树的任何层级不得提供保留来源属性；已登记快照节点不得被替换，或覆盖compatible、
host-id、virtio-device-id、features、config。先验证完整fragment再合并，最后才从
私有登记生成标记；拒绝时不部分应用配置。普通自定义节点和非身份属性仍可合并。
这避免普通配置伪造来源或把认证节点重定向至另一宿主设备，不作为恶意JavaScript隔离。
新增测试覆盖伪造属性、嵌套节点、身份覆盖、节点替换及关闭撤销；本地TypeScript和
72项相关Node检查通过。

Linux源码pin的解包hash为`sha256-AcBT3gCq7OPH/LeR5RsvYzGVHiEIiWHR3oSv5k+pgyw=`，
[公开预取检查](https://github.com/HighCWu/distro/actions/runs/37478312511)通过。
本轮实际启动检查
[wasm32](https://github.com/HighCWu/distro/actions/runs/37478732014)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37478742787)均已通过，基于f970d81；
配置合并加固的
[轻量CI](https://github.com/HighCWu/distro/actions/runs/37479331449)已通过72项检查。
它们验证了两种位宽下的实际挂载、来源查询、文件内容读取、关闭和卸载；配置合并
加固由后续轻量CI验证。来源查询通过仍不等于普通文件mmap已经实现。

随后是在这条已验证的来源链上，把真实EROFS文件的有界kernel_read接入既有staging
和初始化allocator测试桥，检查非零offset、末页清零、拒绝未认证文件及失败回滚。
仍先走测试开关，不直接开放标准文件mmap；文件类型、访问权限、范围、生命周期与
并发行为必须分别验证，来源查询成功本身不是映射许可证。

## 真实EROFS文件的有界初始化副本（实验）

Linux commit `2ee52fc40fe2f99d33f3cf1b4ff1b5601fe75f8b`扩展测试开关下的私有
syscall 255：除原有受控anon-inode fixture外，接受上述来源校验通过的EROFS普通
文件。查询来源的syscall 256不变，默认生产内核仍关闭测试接口；标准mmap仍拒绝
所有文件请求。本轮没有新增公开UAPI、内核softmmu或执行ABI版本。

持有fget引用后验证文件类型、来源和FMODE_READ，用i_size_read确定不可变长度。
请求上限仍为两个64KiB页，offset必须页对齐且落在有符号64位范围。通过比较最后
请求页的起点与剩余文件长度，拒绝任何整页超出EOF，并避免向上取整大文件长度时
溢出；仅EOF末页缺失部分允许补零。不支持空文件、目录、O_PATH描述符或普通只读
磁盘上的文件。使用独立loff_t循环kernel_read，不改变file->f_pos；异常短读及负
错误保持原有失败清理路径。全部读取完成后才调用同步初始化桥，发布副本后释放
staging和文件引用。

MIT测试`mmap-erofs.c`使用同内容的认证快照设备和普通只读设备，检查来源拒绝、
目录/O_PATH/空文件、无效fd、长度及32/64位offset边界，且确认标准文件mmap仍
返回EINVAL。真实pattern文件长两个64KiB页加7字节，验证从非零offset读取、所有
数据字节及末页零尾。修改一个副本后重新映射和pread均应读到原数据；关闭及复用fd、
关闭所有源文件并卸载文件系统后，已发布副本仍须完整可读，最后正常munmap。

本轮测试证明目标是同步读取后的副本独立性，不声称验证了读取途中close、信号、
退出、设备故障或clone竞态。既有受控VFS fixture的短读、EIO、注入EINTR与恢复
检查继续保留；真实EROFS异步故障与生命周期验证仍是后续工作。私有fixture的
split-u32 offset传参不是正式文件映射ABI；完整准入之前不能把这一入口作为SDK能力。

distro测试commit为`86dd83e`，Linux pin更新为`337f46d`；源码hash是
`sha256-UgQIyrPVX5I8M5wybxXud/nZ5yaBH6sgQYQWETkqB0w=`，
[公开预取CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/37556045905)通过。
本地C语法（Wall/Wextra/Werror）、Nix格式、TypeScript、72项相关Node检查和4项
runner协议检查通过，仓库元数据检查通过；没有在本地构建Linux或LLVM。
基于337f46d的实际初始化副本检查
[wasm32](https://github.com/HighCWu/distro/actions/runs/37556226657)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37556232380)均已通过。
这证明上述有界、已认证的真实EROFS文件经过完整初始化副本链路；仍是测试接口，
不代表标准文件mmap或尚未验证的并发、信号和进程退出行为已受支持。

## 读取途中fd复用与失败恢复（受控fixture）

Linux commit `83df39cb39375ac0e017a804c20cbfc3ef7e5e20`只扩展测试内核的
anon-inode fixture：mode 4在首次读取前，mode 5在复制7字节后的下一次读取处，
通过completion通知进入barrier，再等待显式放行。mode 4随后成功，mode 5返回
EIO。控制ioctl只存在于这个私有测试inode，命令`0x5770/0x5771`无指针参数，
没有公开UAPI头文件、正式SDK协议或生产配置改动。等待采用可中断completion，
但本轮不发送信号，不把它描述为已验证的真实EINTR行为。

MIT用户测试`mmap-vfs-lifetime.c`使用pthread及dup保留控制fd。工作线程进入
kernel_read barrier后，主线程进行anonymous mmap/munmap，关闭原读取fd，再
创建另一fixture要求复用该fd数字。替代文件故意选择与原请求相反的读取结果，
便于检测错误地重新查找fd数字。最后通过原文件的控制fd放行，并join检查结果：
成功请求只能返回原文件完整内容；已复制7字节的失败请求只能返回EIO，不能发布
半成品映射。共享file position及替代文件position均不改变，已有anonymous
sentinel逐字节保持完整；关闭文件后成功副本仍可正常读取和munmap。

两种结果各重复8轮，并检查随后的健康请求可正常映射及清理。barrier固定竞争窗口，
不靠sleep或大文件读取速度；既有runner超时负责阻止永久等待。匿名分配和释放在
读取暂停期间进行，用于验证这条等待路径不妨碍其它线程使用allocator及系统调用。
定向CI同时依赖原有VFS回归检查，继续覆盖mode 0–3的正常读取、异常短读、EIO、
注入EINTR及失败后的恢复，不因引入barrier漏测旧分支。

这里控制fd仍保持原文件引用，验证的是在途请求的fd身份稳定性和失败恢复，不是
“读取期间所有文件引用均已释放”的实验；也没有直接计数内核分配或证明零资源泄漏。
真实EROFS设备故障、最后一个外部fd关闭、信号中断、退出及clone仍待分别验证。
本轮没有改变普通文件mmap准入、staging到allocator同步提交方式或CONFIG_MMU=n。

distro测试commits为`c31b007`和`f1f30c7`，Linux pin更新为`1f4eac3`；hash为
`sha256-z8LRscnYmaMIOXp02N+Rnpmq1/+algI0et59+H5IV+A=`，
[公开预取CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/37557610011)通过。
本地C语法（Wall/Wextra/Werror）、Nix格式、TypeScript、72项相关Node检查、
4项runner协议检查及仓库元数据检查通过。新的并发与原有VFS回归组合检查
[wasm32](https://github.com/HighCWu/distro/actions/runs/37557810523)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37557814338)均已通过，覆盖实际
Wasm pthread、内核completion、fd关闭/复用、allocator进展及mode 0–3回归。

## 真实信号打断读取等待（受控fixture）

distro commit `2acc58697b497066f50cde4b8eb4f7e1bdd4f108`加入MIT测试
`mmap-vfs-signal.c`，复用已有mode 4/5的completion，不改Linux pin或增加内核
接口。主程序安装不带SA_RESTART的处理器，工作线程显式解除SIGUSR1屏蔽；主线程等到
kernel_read进入barrier后用pthread_kill向该读取线程发送SIGUSR1，并在不放行
barrier的情况下join。请求必须返回-1/EINTR，处理器须在读取线程恰好执行一次，
控制线程不能收到该信号。这与mode 3直接返回EINTR的错误注入是不同检查。

两个位置各重复8轮：首次复制前，以及已复制7字节后等待下一次读取。检查独立
file position不变、中断后初始化copy授权为EPERM、已有anonymous sentinel
逐字节保持完整。join确认读取已结束后，晚到及重复的PROCEED只改变fixture的
completion，不得复活旧请求；mode 4可对原文件重新映射，所有轮次还要用新健康
文件验证后续映射和munmap。handler只修改线程本地volatile sig_atomic_t，不做
分配或映射。这里没有外部异步I/O生产者，不能把控制completion等同于任意宿主
晚到完成消息的安全性证明。

组合检查依赖信号、原有fd复用并发及mode 0–3 VFS回归三个独立启动结果，继续
使用两种位宽和300秒runner watchdog。该测试只约束无SA_RESTART的受控等待；
真实EROFS块I/O可否中断、SA_RESTART重试、进程退出和clone仍须各自验证。
普通文件mmap准入、生产配置和执行ABI均未改变。

本地C语法（Wall/Wextra/Werror）、Nix格式、TypeScript、4项runner协议检查和
benchmark解析测试通过，仓库元数据检查通过。基于2acc586的组合启动检查
[wasm32](https://github.com/HighCWu/distro/actions/runs/37558507392)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37558510807)均已通过。
这验证了两个读取位置的真实SIGUSR1、无SA_RESTART的EINTR及后续恢复，不能外推
到任意真实EROFS块I/O中断、进程退出或所有资源泄漏行为。

## SA_RESTART后的重新读取（受控fixture）

distro commit `4fb874a08a190e436916f5118f7c45d02b04c388`新增MIT测试
`mmap-vfs-restart.c`，继续复用同一Linux pin及mode 4/5 completion。安装带
SA_RESTART的SIGUSR1处理器，向已进入读取barrier的工作线程发送信号。handler
修改线程本地计数、保存/恢复errno，并通过async-signal-safe的write向空pipe写入
一个字节；fd在pthread_create前设置，join结束前不变且不关闭。主线程必须收到
确认后才放行completion，无sleep、busy-wait或handler内分配/映射。

mode 4必须重试后返回完整副本，mode 5在重试的部分读取后仍返回EIO，不能把旧
staging当作完成数据或把重启错误变成EINTR。两个位置各重复8轮，并要求handler
恰好在读取线程执行一次、file position不变、同步copy授权在返回后为EPERM，
anonymous sentinel保持完整且健康后续请求能够正常读取及munmap。

fd在重启期间保持打开且不复用；这不是重启过程中close/复用fd语义的检查。
也不直接计数重试次数或分配释放，不能据此声称零泄漏。SA_RESTART是测试私有
可中断等待的行为，不是正式文件mmap的通用信号保证。Linux实现、生产配置、
UAPI及原有执行ABI均未改变；退出、clone及真实设备故障仍是后续验证范围。

本地C语法（Wall/Wextra/Werror）、Nix格式、TypeScript、4项runner协议及
benchmark解析测试通过，仓库元数据检查通过。基于4fb874a的定向启动检查
[wasm32](https://github.com/HighCWu/distro/actions/runs/37559599981)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37559605418)均已通过，覆盖实际
handler确认、SA_RESTART后完整副本、重试后EIO及后续健康请求恢复。

## 初始化副本的callback clone隔离（受控fixture）

distro commit `3ad8450c81bdae7405530ee48e1ad4c8d87c6299`加入MIT测试
`mmap-vfs-clone.c`，只使用已有私有VFS测试入口和callback clone，不实现
普通fork，也不改变Linux pin、生产配置或文件mmap准入。先在单线程阶段完成
副本初始化并关闭源fd，再进行不带CLONE_VM的callback clone：子进程须读到原
完整副本，直接调用初始化copy接口仍为EPERM；修改和munmap继承副本后，在子
进程内创建新的受控文件、初始化新的副本并清理。父进程waitpid后须保持原数据
和映射有效，仍可修改及munmap。共重复8轮，用于检查已发布backing和allocator
状态的eager-copy隔离，不引入COW。

随后另起8轮pthread读取，在mode 4的明确barrier处尝试私有callback clone。
由于另有任务共享mm，现有实现必须返回EOPNOTSUPP；拒绝后放行读取，原请求仍
须返回完整副本并正常清理。这里不尝试绕过多线程快照限制，也不让子进程继承
在途staging或宿主copy授权。两阶段分开排列，不假设pthread_join返回的瞬间
所有内核mm teardown均已完成。

该用例针对受控anon-inode初始化副本，而非真实EROFS读取期间clone、普通fork
或退出中断。copy授权检查发生在无活跃lease时，不构成复制活跃lease的实验。
子进程正常结束不等于验证fatal exit、最后一个外部fd关闭或零资源泄漏；这些
仍需独立barrier和生命周期检查。

本地C语法（Wall/Wextra/Werror）、Nix格式、TypeScript、4项runner协议及
benchmark解析测试通过。基于3ad8450的定向启动检查
[wasm32](https://github.com/HighCWu/distro/actions/runs/37560674146)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37560678430)均已通过。
此前SA_RESTART定向检查已在两种位宽通过。本轮clone结果只覆盖上述受控副本和
多线程拒绝，不扩展为普通fork或fatal exit安全保证。

## fatal exit打断读取等待（受控fixture）

distro commit `78f50daa53c8a2b74447a09c4fcf43ae4270cead`加入MIT测试
`mmap-vfs-exit.c`，复用mode 4/5 completion
和已有callback clone，用
CLONE_VM | SIGCHLD创建共享Wasm内存、独立线程组及fd table的子进程。父进程
等到子进程的kernel_read进入barrier后发送SIGKILL；不先放行completion，必须
waitpid观察到SIGKILL终止，而不是用户回调获得部分映射、错误或普通返回值。
每个请求有独立的共享atomic返回标记，在waitpid后及全部轮次结束时检查，便于
发现旧请求错误地继续执行用户代码。子进程不与控制进程共享线程组，避免SIGKILL
连带终止测试控制者；这里也不是私有地址空间快照或普通fork。

首次复制前及复制7字节后的两个位置各运行8轮。reap后检查共同file position
不变、晚到及重复PROCEED不会损坏父进程的anonymous sentinel；父进程可对
mode 4原文件重新初始化副本，mode 5原文件仍保持EIO，健康新文件则正常完成
读取和munmap。随后关闭控制fd并释放测试资源，继续保留300秒runner watchdog。

父进程保留原文件引用用于控制和复验，所以不把该测试描述为最后一个外部fd关闭
或直接验证file release次数。没有内核staging分配计数，也不声称零资源泄漏。
这是同步VFS等待被fatal signal打断的实验，不能外推为真实EROFS异步生产者退出
后立即可释放staging的保证。生产配置、Linux pin、正式UAPI及mmap准入没有变化；
新增独立测试按MIT发布。

本地C语法（Wall/Wextra/Werror）、Nix格式、TypeScript、4项runner协议及
benchmark解析测试通过。基于78f50da的定向启动检查
[wasm32](https://github.com/HighCWu/distro/actions/runs/37562047822)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37562052198)已触发，尚待结果。
clone用例的双位宽通过结果不能代替这项fatal exit验证。

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
