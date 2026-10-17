<!-- SPDX-License-Identifier: MIT -->

# 标准文件 mmap 候选入口

Linux `8bd657d` 新增默认关闭的 `CONFIG_WASM_FILE_MMAP`。这是待验证的候选配置，
不是默认发行版/SDK 已开放文件映射的声明，不引入 softmmu 或新的应用 syscall。
仍使用 `CONFIG_MMU=n` 和 direct pointer；应用走标准 `mmap/mmap2/munmap`。
固定源码哈希由[公开预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39016327047)
取得，不在本地构建 LLVM、内核或系统镜像。

## 首批范围

- 只接受 `MAP_PRIVATE`，权限为 `PROT_READ` 或 `PROT_READ | PROT_WRITE`。
- 来源须为已认证私有快照上的单设备 EROFS 普通文件，并具有 fd 读权限。只读 fd、
  只读挂载、相同内容的普通宿主磁盘或文件系统名称本身均不构成认证。
- 单请求最多 128 KiB，在途 staging 和候选副本按双份页对齐长度预留，全内核载荷
  额度 512 KiB。容量上限或并发额度不足返回 ENOMEM；不等待额度，不伪造稀疏映射。
- 文件 offset 必须按 64 KiB 页对齐。wasm32 的 mmap2 参数以 **4096 字节**为单位，
  在内核扩为 u64 字节 offset；wasm64 的 mmap 参数本就是字节 offset。超过有符号
  64 位文件位置范围返回 EOVERFLOW，不把 offset 转成宿主 Number。
- 允许包含 EOF 的最后一页，其余尾部由用户分配器清零；空文件、起点位于 EOF、
  或请求包含完整的 EOF 后页面均拒绝。源 fd 的共享文件位置不变。
- 每次产生独立私有副本，关闭 fd 后仍可读取；写入 RW 副本不修改文件或别的副本。
  读取失败、异常短读、分配/复制失败不得发布部分内容，须归还 staging 和预算。

`PROT_READ` 遵循上游 NOMMU 的限制，**不保证违规写入触发 SIGSEGV**，不能用于
隔离不可信代码。不共享所谓只读副本，避免缺少写保护时污染其他映射。继续拒绝
PROT_NONE、PROT_EXEC、MAP_SHARED、MAP_FIXED 和 MAP_FIXED_NOREPLACE；普通非固定
地址 hint 可忽略。没有按需分页、COW、写回、执行文件映射或逐页 mprotect。

该入口 pin 住 `struct file`，检查来源/权限并调用 `security_mmap_file`，随后走 VFS
`kernel_read`，不绕过 Linux 去读取宿主路径。与原私有语料共用 `mmap_file.c` 的读取、
预算和回滚实现；受控测试 inode 只允许通过原测试入口，不能进入标准路径。

## 版本化执行能力

不新增应用私有 UAPI，也不更改现有匿名 mmap v2 参数。候选内核在
`user_mmap_init_v1` 执行 namespace 增加 `capabilities() -> i32`：bit 0 表示当前用户
模块导出了 `__wasm_mmap_init_v1` 私有初始化分配器。查询只检查导出，不调用程序、
不授权文件来源，也不授予复制 lease；每次按当前模块查询，不缓存旧模块的能力。

缺少能力时，在分配 staging、读取 VFS 前返回 EOPNOTSUPP。随后仍使用原有同步
`map(rounded, kernel_source, length)` 和 `linux_mmap_init_v1.copy`：只有有效 lease
才能复制一次，内核 staging 地址、fd 和 offset 不传给应用。初始化和零填充完成后
才发布分配器记录。复制桥本身不判断文件准入，也不承诺内存保护。

候选程序仅在链接时加 `-Wl,--export=__wasm_mmap_init_v1`，无需改应用解引用或
添加私有 syscall。当前 musl 已有该可选对象，本轮不修改 libc/LLVM，不把新 import
强加给普通程序；默认 SDK 也不自动导出它。v1 仍是候选执行协议，尚未承诺稳定发布。
新候选内核须配套支持 capabilities 的宿主，旧宿主不能实例化该候选内核；这不是
通过用户模块能力查询就能兼容旧宿主。默认内核不引用该新增 import。

| 内核 | 用户模块 | 认证文件的标准 mmap |
|---|---|---|
| 默认发布配置 | 有或无初始化导出 | 保持 EINVAL |
| 候选配置 | 无初始化导出 | EOPNOTSUPP，无 staging/读取 |
| 候选配置 | 有初始化导出 | 在严格范围和预算内尝试私有复制 |

原 `CONFIG_WASM_MMAP_COPY_TEST` 仍默认关闭，与候选配置分开构建；它的私有 syscall
不是应用 API。候选不启用受控测试 inode、不恢复完整通用 NOMMU VMA 管理，不声称
新增完整 fork、进程隔离、exec 竞态处理或崩溃恢复支持。

## 验收

本地已通过 138 项内核宿主检查、项目 TypeScript 7 检查及 C 语法检查。Linux 自带
MIT 测试 `arch/wasm/tests/run-mmap-file-host.py` 使用 GCC/Clang 编译真实候选 C，
替换 VFS/LSM/原子/分配器为宿主 shim，检查两种 offset 单位、来源/权限、旧模块、
LSM 拒绝、EOF、容量、短读/错误、分配/复制回滚和预算拒绝。它不证明真实 Linux
VFS/LSM、32 位机器 ABI、Wasm 原子或内核执行；候选内核公开构建也会运行此检查。

新增双位宽 `mmap-benchmark[-wasm64]-check-file` 聚合入口，分别启动：

1. 候选配置加初始化导出：标准只读/RW 映射、非零 libc/raw offset、EOF 补零、
   来源/flags/权限拒绝、独立副本、fd 位置及匿名 sentinel。
2. 候选配置加旧模块：保留匿名分配，认证文件请求明确拒绝。
3. 默认内核加初始化导出：不能仅因模块有导出就放行文件映射。
4. 原私有测试内核的预算/生命周期回归：共用读取实现不得破坏已有拒绝/回滚路径。

实际 Wasm 目标结果待公开 CI，不将宿主 shim 或旧版回归记为候选成功。原 EROFS
压力语料改为两个并发最大请求，以匹配八页在途预算；预算耗尽仍由独立屏障语料检查，
不是允许四个最大请求超配。真实设备高并发背压、浏览器、性能及原 Zstd 的强制字典
映射仍须后续单独验收，默认发行配置不会因本轮候选自动开放。

distro `4b06c21` 固定该内核及上述集成。首轮
[wasm32 检查](https://github.com/HighCWu/distro/actions/runs/39016551516) 和
[wasm64 检查](https://github.com/HighCWu/distro/actions/runs/39016555063) 均已失败，
实际日志确认已进入候选程序，在标准文件 mmap 拒绝断言失败，不能记为通过。
检查源码发现 `O_PATH` 预期错误：上游 `fget()` 排除此类 fd，返回 EBADF，而不是
后续 FMODE_READ 检查的 EACCES。distro `cbd0d89` 修正此断言并增加失败参数、
返回指针和实际/预期 errno 诊断；本机 Linux 也验证 O_PATH mmap 返回 EBADF，
但这不能替代候选内核的重跑结果。
[wasm32 重跑](https://github.com/HighCWu/distro/actions/runs/39024983496) 和
[wasm64 重跑](https://github.com/HighCWu/distro/actions/runs/39024986125) 已通过计划检查，
实际构建/运行结果待确认。只有整个聚合及真实日志通过后，才能确认拒绝和正向入口。

下一步已增加[Zstandard 强制字典映射验收](zstd-runtime.md)：只在测试变体导出初始化能力，
默认发行包和内核准入保持不变。该验收与标准入口重跑独立进行，尚不构成候选可用证明。

Linux 实现改动遵循 GPL-2.0；独立测试、宿主和集成修改、文档采用 MIT，其他组件
保持原协议。不把内核实现代码链接进用户程序。
