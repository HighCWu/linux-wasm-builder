<!-- SPDX-License-Identifier: MIT -->

# musl 兼容性变更边界

本项目 musl 的直接上游是 [tombl/musl](https://github.com/tombl/musl)，不是以
musl 官方版本作为项目差异基线。官方实现可用于核对已有接口的来源和语义，不能
因此把直接上游尚未提供的公共函数加入本项目 musl。

开发重点是 Linux on Wasm 的 syscall 和真实程序能力，而不是扩展 libc API。
musl 只加入必要的架构、位宽、执行 ABI、已有接口声明门控和调用路径兼容代码。
允许恢复上游已有但对 Wasm 隐藏的接口；不新增通用 Linux 包装函数、公共头文件
API 或项目专用应用接口。没有 libc 包装时，语料可在测试内部调用标准 syscall，
遵守 Wasm 机器字参数及返回值约定，不安装额外包装库。

## 2026-10-21 审计

通过直接查询远端 HEAD，确认 tombl/musl 的默认分支 master 为
`637b0d25dafa7e4740357f25fb0b5e3949f1ed1f`。本项目保留的 musl 版本是
`e7bde799c1726088d5074ae21d70368ddbfe0f86`，相对该直接上游有 23 个提交。
审计检查了全部净差异、公共 include 声明和新增源文件，不只检查最近一个提交。

| 变更 | 相对 tombl/musl 的结论与处理 |
| --- | --- |
| pidfd_open、pidfd_getfd、pidfd_send_signal 和 sys/pidfd.h | 新增通用公共 API，移除独立实验提交，不集成 |
| memfd_create | 直接上游已有实现与 GNU 声明，只恢复 Wasm 的声明可见性，保留 |
| msync | 直接上游已有实现和声明，只移除 Wasm 禁用门控，保留；不因此声称文件回写完整可用 |
| mmap、munmap | 直接上游已有公共接口，保留 Wasm 的直接内存及 syscall 接入兼容代码 |
| SYS_clone3、time64 与 LP64 syscall 选择 | 标准 syscall 编号或机器字调用适配，不是新增 libc 函数，保留 |
| inttypes/stdint 宏和 stat/statfs 布局 | Wasm 类型与内核线格式兼容修正，保留 |
| 可选 fork 构建补丁 | 恢复上游已有 fork/_Fork 及显式 Wasm import 选择，不新增公共函数，保留 |

清理后，相对直接上游没有新增公共 include 文件，也没有新增通用 src/linux
包装源文件。唯一新增的源文件是 `src/mman/wasm32/mmap_init.c`。

这里不把“没有新增公共 API”误写成“没有新增任何 C 符号”：`__wasm_mmap`、
`__wasm_mmap_v2`、`__wasm_munmap`、`__wasm_mmap_initialized`、
`__wasm_mmap_init_v1` 和静态辅助函数属于 Wasm 执行/分配兼容实现，不是给应用
调用的 libc API。它们未加入公共 include 声明，现有 loader 的 mmap 路径依赖这些
辅助入口。直接上游已有的 SjLj 辅助声明也不属于本项目新增公共函数。

## 历史清理与验证

三个 pidfd 包装原先在单独的分支末端提交中，主仓库 musl gitlink 和 distro 的
固定 rev/hash 均未引用它。经用户授权，使用精确旧 SHA 的 force-with-lease 将
开发分支退回上述 e7bde799；没有添加 revert 提交，也没有重排此前 23 个兼容性
提交或改写直接上游历史。远端分支已重新核对。恢复点仅保存在本地专用 recovery
ref，不发布为开发分支；移除分支引用不等于物理擦除托管服务缓存中的 Git 对象。

主仓库和 distro 固定来源不变，不需要为相同源码更新下载哈希或派发重型构建。
已移除本地未提交的 pidfd 包装测试，保留原 syscall 语料；公共头文件的 wasm32、
wasm64、x86_64 编译检查通过，可选 fork 补丁对保留基线的 dry-run 通过。
这些轻量检查不替代真实 Wasm syscall 或浏览器验收。
