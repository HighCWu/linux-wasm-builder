<!-- SPDX-License-Identifier: MIT -->

# 有界文件私有复制性能对照

distro `2706fb9` 增加标准文件候选的首轮测量，不改变默认内核、SDK 或任何容量上限。
检查名为 `mmap-benchmark-check-file-benchmark` 与
`mmap-benchmark-wasm64-check-file-benchmark`。所有目标构建/执行在公开 Actions 完成。
双位宽目标已通过，并核对完整数据、完成与 pass 标记。
首轮[原始记录与溯源](benchmarks/file-copy-node-20261018/README.md)可独立重新解析。
这轮 mmap/pread 配对耗时比约为 4.3–9.4，不能声称 mmap 比 pread 更快；仍须分解开销和重复测量。

## 测量范围

使用候选内核、一个 Linux CPU、已认证 EROFS 上固定 pattern 文件和单线程程序。
两种方式对同一来源的 offset 0 读取相同长度：

- `mmap(NULL, length, PROT_READ, MAP_PRIVATE, fd, 0)`，当前实现主动读取并复制到独立用户 backing。
- `malloc(length)` 后循环 `pread` 直到填满，消费后 `free`。

64 KiB 和 128 KiB 各测五对批次，每批 64 次；奇数对先 mmap，偶数对先 pread。
计时前分别实际运行两种方式并逐字节验证 pattern，使文件读取路径和分配路径预热。
计时包含分配、读取/复制、每 4096 字节及末字节的稀疏消费、解除映射/释放。
每批消费校验和须与已验证内容一致；请求不得改变 fd 共享文件位置。
使用 CLOCK_MONOTONIC 纳秒时间，任何失败或零耗时均拒绝完成。

这是原应用可能使用的两种加载方式对照，而不是只测 syscall 入口。两者分配方式、
内部 backing 粒度和复制次数不同；不能从耗时反推内核独占成本。
这里的“单 CPU”指 Linux 实例配置，不表示 GitHub 宿主已做物理 CPU 独占或频率固定。

不测冷缓存、浏览器、压缩比、完整应用、并发背压、RSS、memory.grow 峰值、尾页或
不同 offset 的性能。正确性和来源/权限拒绝继续由独立检查负责。
五对短批次只是初始诊断，不足以宣布普遍性能优势或默认开放候选。

## 数据与解析

每次真实执行输出 20 条 `file-copy-bench` 记录：位宽、backend、长度、trial、
迭代数、整批纳秒耗时和校验和。随后须出现完成标记与最终 pass。
只从一次新执行的完整日志生成表格：

```sh
python3 -B scripts/summarize_file_copy_benchmark.py --bits 64 < target-run.log
```

解析器核对两种长度、五对完整批次、固定迭代数、交替顺序、位宽、校验和及正耗时，
拒绝重复/缺失/未知记录、错误标记、完成后的数据，以及没有完成/pass 的日志。
报告包含各 backend 的 µs/op 中位数和五个**配对比值的中位数**，不是两个中位数相除。
比值大于 1 表示在该次条件下 mmap 批次更慢；不设置速度通过阈值。

原生 GCC/Clang 工作负载也运行共享测量函数，但使用本机真正文件映射，不能代表
Wasm 的主动复制。其输出带 `host-workload-only`，目标解析器必须明确拒绝。
宿主测试还覆盖两种位宽的合成记录、坏数据/标记及配对统计，不能把合成数据当成测量。

首次结果须关联具体源码提交、公开 run/job 和原始日志；后续正式性能记录还需补充
实际 Node/V8、runner 硬件及重复新启动信息。Nix 缓存命中只证明已有检查可复用，
不产生一次新的测量，不能用空日志或缓存成功填写新数据。

## 独立启动复测

distro `8408c6d` 和 builder `7363cd5` 增加复测入口。此轮未改动 allocator、
复制桥、内核映射语义或默认开关；此前已验证的结果仍只对应原始提交。

在 builder 的 GitHub Actions 中手动运行 **CI**，选择工作分支并启用
`file-copy-benchmark` 输入。该入口调用 `Fresh file copy benchmark` 工作流，
先 wasm64 后 wasm32、两种位宽不并行；日常 push 不触发这项重构建。
尚未把新工作流合入默认分支时，也可通过已有 CI 入口调度。

工作流读取 builder 的准确 distro gitlink，而不是跟随 distro 分支的最新 HEAD。
`.fileBenchmarkAssets` 仅构建相匹配的候选内核、程序 initramfs、认证测试磁盘与启动器，
不会执行或复用 `.checks.file-benchmark` 的计时结果。随后对同一组产物执行三个独立
Node 进程，每次重新启动单 CPU Linux，并启用只读磁盘和首盘 snapshot 认证。
每个新实例内仍使用上述预热和五对交替批次，所以这仍不是冷缓存测量。

`scripts/run_file_copy_benchmarks.sh` 拒绝已存在的输出目录；每次启动都有五分钟
watchdog，非零退出或任一次解析失败立即停止，不补齐、不重试、不忽略缺失结果。
每次分别保留原始日志和统计，不把跨启动数据合并成一个新的独立样本。
宿主替代测试覆盖三次调用、两种位宽、失败停止和旧输出拒绝；它们不是目标执行证据。

产物 `file-copy-fresh-wasm{32,64}` 保留七天，包含 Node/V8 等实际运行时版本、
runner 的 uname/lscpu、builder/distro 提交、run/attempt、Nix store 路径、关键产物
SHA-256、Linux/musl/LLVM 构建来源及三次日志。硬件记录不意味着 CPU 独占或无噪声。
只有检查真实日志与这些来源信息后，才能登记新性能结果；失败时保留的部分产物不算通过。
需要长期使用的记录应在到期前核验并另行归档。

复测是下一轮开销分解的基线，不是性能优化本身。候选路径的 backing 粒度、清零、
内核读取和跨 memory 复制均可能贡献开销；目前不能给任何一项归因，也不能宣布默认开放。

独立程序、集成、解析器和文档采用 MIT；所用组件保持各自原许可证。
